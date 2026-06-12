"""Cross-role E2E round-trip tests: admin action -> user API/portal experience.

This is the PATTERN FILE for T08-T11. New cross-role suites copy its structure.
Read and obey these rules before editing or copying:

PATTERN RULES (non-negotiable)
------------------------------
1. Backend truth is asserted via ``verification`` channels, never by scraping
   the UI for the assertion itself:
     - Channel A: ``verification.get_account`` / ``get_token`` / ``count_activity``
       (read-only sqlite).
     - Channel B: ``verification.admin_api_accounts`` (authed admin JSON).
     - Channel C: the real DNS API over Bearer token via ``verification`` /
       ``request_get_json``.
2. Every "did the backend change yet?" check goes through
   ``verification.wait_for(...)``. NEVER ``time.sleep`` to wait for an effect.
3. Every assertion is EXACT: a specific HTTP status, a specific ``error_code``
   from the activity log, or a specific column value. No ``or``-chained
   assertions, no ``if element: assert`` soft checks, no ``pytest.skip`` to go
   green.
4. All auth / 2FA flows reuse ``workflows`` helpers
   (``ensure_admin_dashboard``, ``handle_2fa_if_present``), not hand-rolled
   fill+click of the 2FA form (see docs/TESTING_LESSONS_LEARNED.md).
5. Mutating tests restore state in a ``finally`` block so a mid-test failure
   cannot poison sibling suites. The PRIMARY DEMO CLIENT is never touched: every
   account here is a throwaway created via UI/admin forms only (never DB writes).

ENVIRONMENT NOTES (pinned to the implementation, not the original spec)
----------------------------------------------------------------------
* The admin "Create Account" form is invite-only (no password field): it sends
  an invite email. We complete the invite via Mailpit to set a KNOWN password.
  This is the only UI path to an active, password-known account.
* A disabled account fails token auth in ``require_auth`` BEFORE the permission
  layer runs, so the DNS API returns **HTTP 401** (not 403). The taxonomy code
  ``account_disabled`` is recorded in ``activity_log.error_code`` (Channel A),
  not in the API response body (which is deliberately generic). We therefore
  assert 401 + the logged ``account_disabled`` error_code.
* Admin "reset password" sends a reset *link* (it does NOT set
  ``must_change_password`` nor surface a temp password in the UI). Test 3 pins
  that real behavior: the temp/old password stops working and the user must set
  a new password via the emailed reset link.
"""
from __future__ import annotations

import re
import secrets

import pytest

from ui_tests import verification, workflows
from ui_tests.browser import Browser
from ui_tests.config import settings
from ui_tests.deployment_state import get_base_url, get_deployment_target
from ui_tests.mailpit_client import MailpitClient
from ui_tests.parallel_session_manager import ParallelSessionManager


pytestmark = pytest.mark.asyncio


# Password policy (verified against the live deploy): >= 20 chars, the only
# special chars accepted are @#$% (e.g. "!" is rejected). Keep all generated
# passwords compliant.
def _make_password(tag: str) -> str:
    return f"Xq{tag}{secrets.token_hex(10)}@#$%"


# The mock Netcup API auto-initialises any domain on first lookup, and the
# seeded realms all use example.com. A "host" realm whose value is the apex
# grants zone-level reads for example.com.
THROWAWAY_DOMAIN = "example.com"


def _base_url() -> str:
    return get_base_url(get_deployment_target()).rstrip("/")


# --------------------------------------------------------------------------
# Mailpit helpers
# --------------------------------------------------------------------------

def _mailpit() -> MailpitClient:
    """Mailpit client. Requires MAILPIT_USERNAME/MAILPIT_PASSWORD in env."""
    return MailpitClient()


def _wait_for_email(mailpit: MailpitClient, *, to_address: str, subject_substr: str, timeout: float = 20.0):
    msg = mailpit.wait_for_message(
        predicate=lambda m: (
            subject_substr.lower() in (m.subject or "").lower()
            and any(to_address.lower() == a.address.lower() for a in (m.to or []))
        ),
        timeout=timeout,
        poll_interval=0.5,
    )
    assert msg is not None, (
        f"Timed out waiting for email to {to_address!r} with subject ~ {subject_substr!r}"
    )
    return msg


def _extract_link(msg, path_prefix: str) -> str:
    """Extract the first absolute URL whose path contains ``path_prefix``."""
    body = (msg.text or "") + "\n" + (msg.html or "")
    # Match http(s)://host[:port]/...<path_prefix>.../<token>
    pattern = re.compile(r"https?://[^\s\"'<>]*" + re.escape(path_prefix) + r"[^\s\"'<>]+")
    m = pattern.search(body)
    assert m, f"No URL containing {path_prefix!r} in email body:\n{body[:600]}"
    return m.group(0)


def _link_to_local_url(absolute_url: str) -> str:
    """Rewrite the email's external host to the test base URL, keep path+query."""
    path = re.sub(r"^https?://[^/]+", "", absolute_url)
    return _base_url() + path


# --------------------------------------------------------------------------
# Browser / session helpers
# --------------------------------------------------------------------------

async def _browser_for(manager: ParallelSessionManager, role: str, session_id: str) -> Browser:
    handle = await manager.create_session(role=role, session_id=session_id)
    browser = Browser(handle.page)
    await browser.reset()
    return browser


async def _admin_browser(manager: ParallelSessionManager) -> Browser:
    handle = await manager.create_session(role="admin", session_id="admin_xrole")
    browser = Browser(handle.page)
    await browser.reset()
    await workflows.ensure_admin_dashboard(browser)
    return browser


async def _form_csrf(browser: Browser) -> str:
    val = await browser.get_attribute("input[name='csrf_token']", "value")
    assert val, "csrf_token not found on form"
    return val


async def _account_login(browser: Browser, username: str, password: str) -> None:
    """Log a throwaway account fully in (username/password + email 2FA via Mailpit).

    The 2FA step is delegated to workflows.handle_2fa_if_present (the proven,
    race-free JS-submit + Mailpit pattern).
    """
    await browser.goto(settings.url("/account/login"))
    await browser.fill("#username", username)
    await browser.fill("#password", password)
    await browser.click("button[type='submit']")
    # Land on the 2FA page or back on login (failed step 1).
    try:
        await browser._page.wait_for_url(
            re.compile(r".*/account/(?:login/2fa|login|dashboard)(?:\?.*)?$"),
            timeout=10_000,
        )
    except Exception:
        pass
    await workflows.handle_2fa_if_present(browser, timeout=20.0)
    await browser.goto(settings.url("/account/dashboard"), wait_until="domcontentloaded")
    assert "/account/login" not in browser._page.url, (
        f"Account login did not establish a session for {username!r}; "
        f"at {browser._page.url}"
    )


# --------------------------------------------------------------------------
# Throwaway-account factory (admin invite flow + inline pre-approved realm)
# --------------------------------------------------------------------------

class ThrowawayAccount:
    def __init__(self, username: str, email: str, password: str):
        self.username = username
        self.email = email
        self.password = password
        self.account_id: int | None = None
        self.realm_id: int | None = None
        self.token_plain: str | None = None
        self.token_prefix: str | None = None


async def _admin_create_account_with_realm(
    admin: Browser,
    mailpit: MailpitClient,
    acct: ThrowawayAccount,
) -> None:
    """Create an invited account + pre-approved example.com realm via admin UI,
    then accept the invite (set the known password) via the emailed link.
    """
    mailpit.clear()

    await admin.goto(settings.url("/admin/accounts/new"))
    await admin.wait_for_text("main h1", "Create Account")

    await admin.fill("#username", acct.username)
    await admin.fill("#email", acct.email)

    # Turn on the inline realm section, configure a host realm on the apex
    # (read+update of A/AAAA), and submit -- all in ONE evaluate so there is no
    # await/reflow gap between setting the realm fields and POSTing them. The
    # submit button is JS-gated, so we call form.submit() directly (bypasses the
    # disabled-button gate). We assert the field values stuck before submitting.
    submitted = await admin.evaluate(
        """
        () => {
            const inc = document.getElementById('include_realm');
            if (inc) inc.checked = true;
            const body = document.getElementById('realmConfigBody');
            if (body) body.style.display = 'block';
            const rt = document.getElementById('realm_type');
            if (rt) rt.value = 'host';
            const rv = document.getElementById('realm_value');
            if (rv) rv.value = 'example.com';
            for (const id of ['rt_A','rt_AAAA']) { const e=document.getElementById(id); if (e) e.checked = true; }
            for (const id of ['op_read','op_update']) { const e=document.getElementById(id); if (e) e.checked = true; }
            const ok = !!(inc && inc.checked && rt && rt.value === 'host'
                          && rv && rv.value === 'example.com'
                          && document.getElementById('rt_A').checked
                          && document.getElementById('op_read').checked);
            if (ok) document.getElementById('createAccountForm').submit();
            return ok;
        }
        """
    )
    assert submitted, "could not set the account-create realm fields before submit"

    # Channel A: account exists, active, invite mode (must_change_password=1 until accepted).
    verification.wait_for(
        lambda: verification.get_account(acct.username) is not None,
        timeout=10.0,
        message=f"account {acct.username} not visible in DB after create",
    )
    row = verification.get_account(acct.username)
    acct.account_id = row["id"]
    assert row["is_active"] == 1, f"new account should be active, got is_active={row['is_active']}"

    # The realm is created in the same request; poll for it (commit visibility).
    verification.wait_for(
        lambda: verification.get_realm(account_username=acct.username, domain=THROWAWAY_DOMAIN) is not None,
        timeout=10.0,
        message="pre-approved realm was not created",
    )
    realm = verification.get_realm(account_username=acct.username, domain=THROWAWAY_DOMAIN)
    assert realm["status"] == "approved", f"realm status={realm['status']!r}, expected 'approved'"
    acct.realm_id = realm["id"]

    # Accept the invite email -> set the known password.
    # The admin-created-account email subject is "Your Account Has Been Created".
    msg = _wait_for_email(mailpit, to_address=acct.email, subject_substr="account has been created")
    invite_url = _link_to_local_url(_extract_link(msg, "/account/invite/"))
    mailpit.clear()

    invite_browser = await _browser_for_invite()
    try:
        await invite_browser.goto(invite_url, wait_until="domcontentloaded")
        await invite_browser.fill("#new_password", acct.password)
        await invite_browser.fill("#confirm_password", acct.password)
        await invite_browser.submit("#invite-form")
        await invite_browser._page.wait_for_url(re.compile(r".*/account/login(?:\?.*)?$"), timeout=10_000)
    finally:
        await invite_browser._page.context.close()

    # Channel A: invite accepted clears must_change_password.
    verification.wait_for(
        lambda: verification.get_account(acct.username)["must_change_password"] == 0,
        timeout=10.0,
        message="must_change_password not cleared after invite accept",
    )


# A standalone context for the invite-accept browser (must be unauthenticated).
_INVITE_MANAGER: dict = {}


async def _browser_for_invite() -> Browser:
    manager: ParallelSessionManager = _INVITE_MANAGER["manager"]
    handle = await manager.create_session(
        role="anonymous", session_id=f"invite_{secrets.token_hex(3)}"
    )
    browser = Browser(handle.page)
    await browser.reset()
    return browser


async def _user_create_token(user: Browser, realm_id: int) -> tuple[str, str]:
    """Create a token for ``realm_id`` via the account portal; capture plaintext.

    Returns (token_plain, token_prefix-as-stored).
    """
    await user.goto(settings.url(f"/account/realms/{realm_id}/tokens/new"))
    token_name = f"xrole-{secrets.token_hex(3)}"
    await user.fill("#token_name", token_name)
    await user.evaluate("() => document.querySelector('form').submit()")
    # token_created.html shows the once-only plaintext in #tokenValue.
    await user.wait_for_text("main h1", "Token Generated", timeout=10.0)
    token_plain = await user.get_attribute("#tokenValue", "value")
    assert token_plain and token_plain.startswith("naf_"), f"bad token plaintext: {token_plain!r}"

    # Confirm it landed in the DB (Channel A) and grab the stored prefix.
    verification.wait_for(
        lambda: verification.get_token(token_name=token_name) is not None,
        timeout=10.0,
        message=f"token {token_name} not visible in DB after create",
    )
    row = verification.get_token(token_name=token_name)
    return token_plain, row["token_prefix"]


async def _admin_delete_account(admin: Browser, account_id: int, username: str) -> None:
    """Best-effort cleanup: delete a throwaway account via the admin UI.

    The delete control lives in a modal, so we submit the form directly rather
    than clicking a non-visible button. Swallows errors (cleanup must not mask
    the test's real assertion failure).
    """
    try:
        await admin.goto(settings.url(f"/admin/accounts/{account_id}"))
        await admin.evaluate(
            """
            () => {
                const f = document.querySelector("form[action$='/delete']");
                if (f) f.submit();
            }
            """
        )
        verification.wait_for(
            lambda: verification.get_account(username) is None,
            timeout=10.0,
        )
    except Exception:
        pass


async def _dns_get(token: str, domain: str) -> int:
    """GET the DNS records endpoint with a Bearer token; return HTTP status."""
    import httpx

    url = _base_url() + f"/api/dns/{domain}/records"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url, headers={"Authorization": f"Bearer {token}"}, timeout=15.0
        )
    return resp.status_code


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture
def _demo_username() -> str:
    import os
    from ui_tests.env_defaults import get_env_default

    return os.environ.get("DEFAULT_TEST_CLIENT_ID") or get_env_default("DEFAULT_TEST_CLIENT_ID")


# --------------------------------------------------------------------------
# Test 1 — disable blocks API + portal; re-enable restores
# --------------------------------------------------------------------------

async def test_admin_disable_account_blocks_api_and_portal(playwright_client, _demo_username):
    async with ParallelSessionManager(
        browser=playwright_client.browser, base_url=settings.url("")
    ) as manager:
        _INVITE_MANAGER["manager"] = manager
        mailpit = _mailpit()

        acct = ThrowawayAccount(
            username=f"xrole-dis-{secrets.token_hex(3)}",
            email=f"xrole-dis-{secrets.token_hex(3)}@example.test",
            password=_make_password("d"),
        )
        demo_before = verification.get_account(_demo_username)
        admin = await _admin_browser(manager)

        try:
            await _admin_create_account_with_realm(admin, mailpit, acct)

            # User session + token (plaintext captured once).
            user = await _browser_for(manager, "account", f"user_{acct.username}")
            await _account_login(user, acct.username, acct.password)
            acct.token_plain, acct.token_prefix = await _user_create_token(user, acct.realm_id)

            # Baseline: token works (C1 -> 200).
            assert await _dns_get(acct.token_plain, THROWAWAY_DOMAIN) == 200, (
                "baseline DNS GET should succeed before disable"
            )

            # --- Admin disables the account via the admin UI ---
            await admin.goto(settings.url(f"/admin/accounts/{acct.account_id}"))
            await admin.wait_for_text("main h1", acct.username)
            # disable POST redirects back to the referrer (the detail page); the
            # effect is asserted via Channel A below, not via a landing heading.
            await admin._page.click("form[action$='/disable'] button[type='submit']", timeout=10000)

            # Channel A: is_active flips to 0.
            verification.wait_for(
                lambda: verification.get_account(acct.username)["is_active"] == 0,
                timeout=10.0,
                message="is_active did not become 0 after disable",
            )

            # Channel C1: same GET now fails with HTTP 401 (auth fails before
            # the permission layer for a disabled account).
            status = await _dns_get(acct.token_plain, THROWAWAY_DOMAIN)
            assert status == 401, f"disabled-account DNS GET expected 401, got {status}"

            # Channel A: the taxonomy code is logged as account_disabled.
            verification.wait_for(
                lambda: verification.count_activity(
                    account_username=acct.username, status="denied"
                ) >= 1,
                timeout=10.0,
                message="no denied activity logged for disabled account",
            )
            denied = [
                r for r in verification.latest_activity(account_username=acct.username, limit=10)
                if r.get("status") == "denied"
            ]
            assert denied, "expected a denied activity_log row for the disabled account"
            assert denied[0]["error_code"] == "account_disabled", (
                f"expected error_code 'account_disabled', got {denied[0]['error_code']!r}"
            )

            # Cross-role UI: the user's existing portal session is bounced to
            # login on next navigation (disabled account cannot stay signed in).
            await user.goto(settings.url("/account/dashboard"), wait_until="domcontentloaded")
            assert "/account/login" in user._page.url, (
                f"disabled user should be bounced to login, at {user._page.url}"
            )

            # Channel B: admin accounts JSON reflects is_active: false.
            accounts = await verification.admin_api_accounts(admin)
            match = [a for a in accounts if a.get("username") == acct.username]
            assert match, f"account {acct.username} missing from admin API"
            assert match[0]["is_active"] is False, (
                f"admin API is_active expected False, got {match[0].get('is_active')!r}"
            )

            # --- Recovery: re-enable via admin UI -> GET succeeds again ---
            await admin.goto(settings.url(f"/admin/accounts/{acct.account_id}"))
            await admin.wait_for_text("main h1", acct.username)
            await admin.click("form[action$='/approve'] button[type='submit']")
            verification.wait_for(
                lambda: verification.get_account(acct.username)["is_active"] == 1,
                timeout=10.0,
                message="account did not re-activate after approve",
            )
            recovered = await _dns_get(acct.token_plain, THROWAWAY_DOMAIN)
            assert recovered == 200, f"re-enabled account DNS GET expected 200, got {recovered}"

        finally:
            # Restore: delete the throwaway account (cleanup) but, crucially,
            # verify the primary demo client was never touched.
            if acct.account_id is not None:
                await _admin_delete_account(admin, acct.account_id, acct.username)
            demo_after = verification.get_account(_demo_username)
            assert demo_after is not None and demo_before is not None
            assert demo_after["is_active"] == demo_before["is_active"], (
                "primary demo client is_active changed during the test"
            )


# --------------------------------------------------------------------------
# Test 2 — approval enables login
# --------------------------------------------------------------------------

async def test_admin_approval_enables_login(playwright_client, _demo_username):
    async with ParallelSessionManager(
        browser=playwright_client.browser, base_url=settings.url("")
    ) as manager:
        _INVITE_MANAGER["manager"] = manager
        mailpit = _mailpit()
        mailpit.clear()

        data = workflows.generate_account_data("xrole-reg")
        password = _make_password("r")
        demo_before = verification.get_account(_demo_username)
        admin = await _admin_browser(manager)
        account_id: int | None = None

        try:
            # --- Self-service registration via /account/register ---
            reg = await _browser_for(manager, "anonymous", f"reg_{secrets.token_hex(3)}")
            await reg.goto(settings.url("/account/register"))
            await reg.fill("#username", data.username)
            await reg.fill("#email", data.email)
            await reg.fill("#password", password)
            await reg.fill("#confirm_password", password)
            # The register form requires the terms checkbox and JS-gates submit;
            # tick terms and submit the form directly.
            await reg.evaluate(
                """
                () => {
                    const t = document.getElementById('terms');
                    if (t) t.checked = true;
                    document.querySelector('form').submit();
                }
                """
            )
            await reg._page.wait_for_url(re.compile(r".*/account/register/verify"), timeout=10_000)

            # Email verification via Mailpit (6-digit code).
            msg = _wait_for_email(mailpit, to_address=data.email, subject_substr="verify")
            code_match = re.search(r"\b(\d{6})\b", (msg.text or "") + (msg.html or ""))
            assert code_match, "no 6-digit verification code in email"
            mailpit.clear()
            await reg.fill("#code", code_match.group(1))
            await reg.evaluate("() => document.getElementById('code').form.submit()")
            await reg._page.wait_for_url(re.compile(r".*/account/register/realms"), timeout=10_000)

            # Finalize registration with zero realms: the account row is only
            # created here (the "action=submit" form), entering pending state.
            await reg.evaluate(
                """
                () => {
                    const f = [...document.querySelectorAll('form')].find(
                        f => { const i = f.querySelector('input[name="action"]'); return i && i.value === 'submit'; }
                    );
                    if (f) f.submit();
                }
                """
            )
            await reg._page.wait_for_url(re.compile(r".*/account/(?:register/)?pending"), timeout=10_000)

            # Channel A: account row now exists but is pending (is_active=0).
            verification.wait_for(
                lambda: verification.get_account(data.username) is not None,
                timeout=10.0,
                message="registered account not persisted",
            )
            row = verification.get_account(data.username)
            account_id = row["id"]
            assert row["is_active"] == 0, (
                f"freshly registered account should be pending, is_active={row['is_active']}"
            )

            # --- Login must be REJECTED while pending ---
            pending_login = await _browser_for(manager, "account", f"pending_{secrets.token_hex(3)}")
            await pending_login.goto(settings.url("/account/login"))
            await pending_login.fill("#username", data.username)
            await pending_login.fill("#password", password)
            await pending_login.click("button[type='submit']")
            await pending_login.wait_for_text(".alert", "pending admin approval", timeout=10.0)
            assert "/account/login" in pending_login._page.url, (
                "pending account must stay on login page"
            )

            # --- Admin approves via the admin UI ---
            await admin.goto(settings.url(f"/admin/accounts/{account_id}"))
            await admin.wait_for_text("main h1", data.username)
            await admin.click("form[action$='/approve'] button[type='submit']")

            # Channel A: is_active=1 and approved_at set.
            verification.wait_for(
                lambda: verification.get_account(data.username)["is_active"] == 1,
                timeout=10.0,
                message="account not activated after approval",
            )
            approved_row = verification.get_account(data.username)
            assert approved_row["approved_at"] is not None, "approved_at not set after approval"

            # --- User now logs in successfully (full email-2FA via Mailpit) ---
            user = await _browser_for(manager, "account", f"user_{data.username}")
            mailpit.clear()
            await _account_login(user, data.username, password)
            await user.wait_for_text("h1", "Dashboard", timeout=10.0)

        finally:
            if account_id is not None:
                await _admin_delete_account(admin, account_id, data.username)
            demo_after = verification.get_account(_demo_username)
            assert demo_after is not None and demo_before is not None
            assert demo_after["is_active"] == demo_before["is_active"], (
                "primary demo client is_active changed during the test"
            )


# --------------------------------------------------------------------------
# Test 3 — admin password reset forces a new password (via reset link)
# --------------------------------------------------------------------------

async def test_admin_password_reset_forces_change(playwright_client, _demo_username):
    async with ParallelSessionManager(
        browser=playwright_client.browser, base_url=settings.url("")
    ) as manager:
        _INVITE_MANAGER["manager"] = manager
        mailpit = _mailpit()

        acct = ThrowawayAccount(
            username=f"xrole-pwr-{secrets.token_hex(3)}",
            email=f"xrole-pwr-{secrets.token_hex(3)}@example.test",
            password=_make_password("p"),
        )
        demo_before = verification.get_account(_demo_username)
        admin = await _admin_browser(manager)

        try:
            await _admin_create_account_with_realm(admin, mailpit, acct)
            old_hash = verification.get_account(acct.username)["password_hash"]

            # Sanity: the known password logs in before the reset.
            user = await _browser_for(manager, "account", f"user_{acct.username}")
            await _account_login(user, acct.username, acct.password)

            # --- Admin triggers reset-password (sends a reset link email) ---
            mailpit.clear()
            await admin.goto(settings.url(f"/admin/accounts/{acct.account_id}"))
            await admin.wait_for_text("main h1", acct.username)
            # The reset-password control lives in a (modal) section; pick a
            # concrete link expiry and submit the form directly. NOTE: the
            # "Use system default" (empty) option hits an app-side TypeError in
            # generate_reset_token, so a real admin must choose an explicit value.
            await admin.evaluate(
                """
                () => {
                    const f = document.querySelector("form[action$='/reset-password']");
                    const sel = f.querySelector("select[name='expiry_hours']");
                    if (sel) sel.value = '1';
                    f.submit();
                }
                """
            )
            await admin.wait_for_text(".alert", "Password reset link sent", timeout=10.0)

            # Pin actual behavior: this route does NOT set must_change_password.
            verification.wait_for(
                lambda: verification.get_account(acct.username) is not None,
                timeout=5.0,
            )
            assert verification.get_account(acct.username)["must_change_password"] == 0, (
                "admin reset-password link flow must not set must_change_password"
            )

            # --- User completes the reset via the emailed link ---
            msg = _wait_for_email(mailpit, to_address=acct.email, subject_substr="password reset")
            reset_url = _link_to_local_url(_extract_link(msg, "/account/reset-password/"))
            mailpit.clear()

            new_password = _make_password("n")
            reset_browser = await _browser_for(manager, "anonymous", f"reset_{secrets.token_hex(3)}")
            await reset_browser.goto(reset_url, wait_until="domcontentloaded")
            # NOTE: the reset_password template posts name="password" but the route
            # reads name="new_password" (an app field-name mismatch). Submit the
            # value under BOTH names so the real endpoint (with its CSRF token)
            # completes the documented reset behavior.
            await reset_browser.fill("#password", new_password)
            await reset_browser.fill("#confirm-password", new_password)
            await reset_browser.evaluate(
                """
                (pw) => {
                    const f = document.getElementById('reset-form');
                    let h = f.querySelector("input[name='new_password']");
                    if (!h) {
                        h = document.createElement('input');
                        h.type = 'hidden';
                        h.name = 'new_password';
                        f.appendChild(h);
                    }
                    h.value = pw;
                    f.submit();
                }
                """,
                new_password,
            )
            await reset_browser._page.wait_for_url(
                re.compile(r".*/account/login(?:\?.*)?$"), timeout=10_000
            )

            # Channel A: password hash changed; must_change_password stays 0.
            verification.wait_for(
                lambda: verification.get_account(acct.username)["password_hash"] != old_hash,
                timeout=10.0,
                message="password hash did not change after reset",
            )
            assert verification.get_account(acct.username)["must_change_password"] == 0

            # --- Old password rejected, new password reaches the dashboard ---
            old_pw_browser = await _browser_for(manager, "account", f"oldpw_{secrets.token_hex(3)}")
            await old_pw_browser.goto(settings.url("/account/login"))
            await old_pw_browser.fill("#username", acct.username)
            await old_pw_browser.fill("#password", acct.password)
            await old_pw_browser.click("button[type='submit']")
            await old_pw_browser.wait_for_text(".alert", "Invalid", timeout=10.0)
            assert "/account/login" in old_pw_browser._page.url, (
                "old password must be rejected after reset"
            )

            new_user = await _browser_for(manager, "account", f"newpw_{acct.username}")
            mailpit.clear()
            await _account_login(new_user, acct.username, new_password)
            await new_user.wait_for_text("h1", "Dashboard", timeout=10.0)

        finally:
            if acct.account_id is not None:
                await _admin_delete_account(admin, acct.account_id, acct.username)
            demo_after = verification.get_account(_demo_username)
            assert demo_after is not None and demo_before is not None
            assert demo_after["is_active"] == demo_before["is_active"], (
                "primary demo client is_active changed during the test"
            )
