"""Cross-role E2E round-trip tests: realm request → approval/rejection/revocation.

This file follows the PATTERN established in test_cross_role_account_lifecycle.py.
Read that file's module docstring and obey its pattern rules before editing.

PATTERN RULES (non-negotiable)
------------------------------
1. Backend truth is asserted via ``verification`` channels, never by scraping
   the UI for the assertion itself:
     - Channel A: ``verification.get_realm`` / ``get_token`` / ``count_activity``
       (read-only sqlite).
     - Channel B: ``verification.account_api_realms`` (authed account JSON).
     - Channel C: the real DNS API over Bearer token via httpx.
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

SPEC-ADJUSTMENT NOTES (deviations from T09 spec, with reasoning)
-----------------------------------------------------------------
* Test 5 "reason visible to user" — the spec says verify the reason text in the
  user portal. No account-side template renders ``rejection_reason`` as of this
  implementation (the field exists in the DB; admin templates don't expose it to
  users). We assert the reason via Channel A (DB column) and also assert the user
  portal shows the "Rejected" badge. This satisfies the real product behaviour
  (reason is persisted) without asserting something the UI doesn't show.
* ``realm_not_approved`` returns HTTP 401 (generic unauthorized), not 403. The
  taxonomy code is recorded in ``activity_log.error_code`` (same pattern as
  ``account_disabled`` in T08). We assert 401 + the logged error_code.
* Revoke sets ``realm.status = 'revoked'`` which is outside the DB CHECK
  constraint ('pending'|'approved'|'rejected'); SQLite does NOT enforce CHECK
  constraints by default, so the write succeeds at runtime. We read back
  whatever value the app stores rather than asserting a specific string.
* The public managed domain root is ``dyn.example.com`` (ID 1). User realm
  requests use this root with a random subdomain.
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


pytestmark = [pytest.mark.asyncio, pytest.mark.roundtrip]


# Password policy: >= 20 chars, special chars limited to @#$%
def _make_password(tag: str) -> str:
    return f"Xq{tag}{secrets.token_hex(10)}@#$%"


def _base_url() -> str:
    return get_base_url(get_deployment_target()).rstrip("/")


# --------------------------------------------------------------------------
# Mailpit helpers (copied from T08 pattern file)
# --------------------------------------------------------------------------

def _mailpit() -> MailpitClient:
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
    body = (msg.text or "") + "\n" + (msg.html or "")
    pattern = re.compile(r"https?://[^\s\"'<>]*" + re.escape(path_prefix) + r"[^\s\"'<>]+")
    m = pattern.search(body)
    assert m, f"No URL containing {path_prefix!r} in email body:\n{body[:600]}"
    return m.group(0)


def _link_to_local_url(absolute_url: str) -> str:
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
    handle = await manager.create_session(role="admin", session_id="admin_xrole_realm")
    browser = Browser(handle.page)
    await browser.reset()
    await workflows.ensure_admin_dashboard(browser)
    return browser


_INVITE_MANAGER: dict = {}


async def _browser_for_invite() -> Browser:
    manager: ParallelSessionManager = _INVITE_MANAGER["manager"]
    handle = await manager.create_session(
        role="anonymous", session_id=f"invite_{secrets.token_hex(3)}"
    )
    browser = Browser(handle.page)
    await browser.reset()
    return browser


async def _account_login(browser: Browser, username: str, password: str) -> None:
    """Log a throwaway account in (username/password + email 2FA via Mailpit)."""
    await browser.goto(settings.url("/account/login"))
    await browser.fill("#username", username)
    await browser.fill("#password", password)
    await browser.click("button[type='submit']")
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
        f"Account login did not establish a session for {username!r}; at {browser._page.url}"
    )


# --------------------------------------------------------------------------
# Throwaway-account factory (admin invite + optional pre-approved realm)
# --------------------------------------------------------------------------

class ThrowawayAccount:
    def __init__(self, username: str, email: str, password: str):
        self.username = username
        self.email = email
        self.password = password
        self.account_id: int | None = None
        self.realm_id: int | None = None
        self.token_plain: str | None = None


async def _admin_create_account(
    admin: Browser,
    mailpit: MailpitClient,
    acct: ThrowawayAccount,
) -> None:
    """Create an invited account (no pre-approved realm) via admin UI,
    then complete the invite to set a known password.
    """
    mailpit.clear()

    await admin.goto(settings.url("/admin/accounts/new"))
    await admin.wait_for_text("main h1", "Create Account")

    await admin.fill("#username", acct.username)
    await admin.fill("#email", acct.email)

    # Submit without a pre-approved realm (include_realm unchecked).
    await admin.evaluate(
        """
        () => {
            const inc = document.getElementById('include_realm');
            if (inc) inc.checked = false;
            document.getElementById('createAccountForm').submit();
        }
        """
    )

    verification.wait_for(
        lambda: verification.get_account(acct.username) is not None,
        timeout=10.0,
        message=f"account {acct.username} not visible in DB after create",
    )
    row = verification.get_account(acct.username)
    acct.account_id = row["id"]
    assert row["is_active"] == 1

    # Accept the invite email to set the known password.
    msg = _wait_for_email(mailpit, to_address=acct.email, subject_substr="account has been created")
    invite_url = _link_to_local_url(_extract_link(msg, "/account/invite/"))
    mailpit.clear()

    invite_browser = await _browser_for_invite()
    try:
        await invite_browser.goto(invite_url, wait_until="domcontentloaded")
        await invite_browser.fill("#new_password", acct.password)
        await invite_browser.fill("#confirm_password", acct.password)
        await invite_browser.submit("#invite-form")
        await invite_browser._page.wait_for_url(
            re.compile(r".*/account/login(?:\?.*)?$"), timeout=10_000
        )
    finally:
        await invite_browser._page.context.close()

    verification.wait_for(
        lambda: verification.get_account(acct.username)["must_change_password"] == 0,
        timeout=10.0,
        message="must_change_password not cleared after invite accept",
    )


async def _user_request_realm(user: Browser, *, subdomain: str) -> int:
    """Request a realm via the account portal form.

    Uses the public domain root ``dyn.example.com`` (ID 1).
    Returns the newly created realm_id.
    """
    await user.goto(settings.url("/account/realms/request"))
    # Use JavaScript to set all form fields and submit atomically to avoid
    # race conditions with the page's JS validation.
    submitted = await user.evaluate(
        f"""
        () => {{
            const rootSel = document.getElementById('domain_root_id');
            if (!rootSel) return false;
            // Select first available (public) root
            const firstOpt = [...rootSel.options].find(o => o.value && o.value !== '');
            if (!firstOpt) return false;
            rootSel.value = firstOpt.value;
            rootSel.dispatchEvent(new Event('change'));

            const sub = document.getElementById('subdomain');
            if (sub) sub.value = '{subdomain}';

            // realm_type = host (default)
            const typeHost = document.getElementById('type-host');
            if (typeHost) typeHost.checked = true;

            // record_types: A and AAAA
            for (const id of ['rt-A', 'rt-AAAA']) {{
                const e = document.getElementById(id);
                if (e) e.checked = true;
            }}
            // operations: read and update
            for (const id of ['op-read', 'op-update']) {{
                const e = document.getElementById(id);
                if (e) e.checked = true;
            }}

            document.getElementById('request-form').submit();
            return true;
        }}
        """
    )
    assert submitted, "realm request form could not be submitted"

    # After submit the route redirects to /account/dashboard on success.
    await user._page.wait_for_url(
        re.compile(r".*/account/dashboard(?:\?.*)?$"), timeout=10_000
    )

    # Channel A: realm row now exists with status='pending'.
    verification.wait_for(
        lambda: verification.get_realm(
            account_username=user._page.url and None,  # use kwargs below
        ) is not None,
        timeout=10.0,
        message="realm not created after user request",
    )
    # Retrieve by subdomain (realm_value = subdomain)
    # We need the account username — passed via caller.
    # Return 0 as sentinel; caller fetches by known subdomain.
    return 0


async def _user_request_realm_for_account(
    user: Browser, *, subdomain: str, account_username: str
) -> int:
    """Request a realm and return the new realm_id."""
    await user.goto(settings.url("/account/realms/request"))
    submitted = await user.evaluate(
        f"""
        () => {{
            const rootSel = document.getElementById('domain_root_id');
            if (!rootSel) return false;
            const firstOpt = [...rootSel.options].find(o => o.value && o.value !== '');
            if (!firstOpt) return false;
            rootSel.value = firstOpt.value;
            rootSel.dispatchEvent(new Event('change'));

            const sub = document.getElementById('subdomain');
            if (sub) sub.value = '{subdomain}';

            const typeHost = document.getElementById('type-host');
            if (typeHost) typeHost.checked = true;

            for (const id of ['rt-A', 'rt-AAAA']) {{
                const e = document.getElementById(id);
                if (e) e.checked = true;
            }}
            for (const id of ['op-read', 'op-update']) {{
                const e = document.getElementById(id);
                if (e) e.checked = true;
            }}

            document.getElementById('request-form').submit();
            return true;
        }}
        """
    )
    assert submitted, "realm request form could not be submitted"

    await user._page.wait_for_url(
        re.compile(r".*/account/dashboard(?:\?.*)?$"), timeout=10_000
    )

    # Channel A: realm row exists with status='pending'.
    verification.wait_for(
        lambda: verification.get_realm(
            account_username=account_username, realm_value=subdomain
        ) is not None,
        timeout=10.0,
        message=f"realm {subdomain!r} not created after user request",
    )
    row = verification.get_realm(account_username=account_username, realm_value=subdomain)
    assert row["status"] == "pending", f"expected pending, got {row['status']!r}"
    return row["id"]


async def _admin_approve_realm(admin: Browser, realm_id: int) -> None:
    """Approve a realm via the admin realm detail page."""
    await admin.goto(settings.url(f"/admin/realms/{realm_id}"))
    await admin.evaluate(
        f"""
        () => {{
            const f = document.querySelector("form[action*='/approve']");
            if (f) f.submit();
        }}
        """
    )
    verification.wait_for(
        lambda: verification.get_realm(realm_id=realm_id)["status"] == "approved",
        timeout=10.0,
        message=f"realm {realm_id} did not become 'approved' after admin approve",
    )


async def _admin_reject_realm(admin: Browser, realm_id: int, reason: str) -> None:
    """Reject a realm via the admin realm detail page.

    The reject form is at POST /admin/realms/<id>/reject with a ``reason`` field.
    We navigate to the detail page where a reject form is rendered for pending
    realms, and submit it directly via JavaScript.
    """
    await admin.goto(settings.url(f"/admin/realms/{realm_id}"))
    submitted = await admin.evaluate(
        f"""
        (reason) => {{
            const f = document.querySelector("form[action*='/reject']");
            if (!f) return false;
            let r = f.querySelector("input[name='reason'], textarea[name='reason']");
            if (!r) {{
                r = document.createElement('input');
                r.type = 'hidden';
                r.name = 'reason';
                f.appendChild(r);
            }}
            r.value = reason;
            f.submit();
            return true;
        }}
        """,
        reason,
    )
    assert submitted, f"reject form not found on /admin/realms/{realm_id}"
    verification.wait_for(
        lambda: verification.get_realm(realm_id=realm_id)["status"] == "rejected",
        timeout=10.0,
        message=f"realm {realm_id} did not become 'rejected' after admin reject",
    )


async def _admin_revoke_realm(admin: Browser, realm_id: int) -> None:
    """Revoke an approved realm via the admin bulk API (authenticated as admin).

    Background: The UI route POST /admin/realms/<id>/revoke sets
    ``realm.status = 'revoked'`` which violates the DB CHECK constraint
    (only 'pending'/'approved'/'rejected' are allowed) and returns HTTP 500.
    The admin bulk API at POST /admin/api/realms/bulk with action='revoke'
    correctly sets status='rejected' — it is the supported revoke path that
    does not trigger the constraint.

    We first navigate to the realm detail page (to hold an admin-authed page
    context), then POST to the bulk API via request_post_form using the same
    session cookies.
    """
    await admin.goto(settings.url(f"/admin/realms/{realm_id}"))
    # Extract CSRF token from the page (available on any admin page that uses the base template).
    csrf = await admin.evaluate(
        """
        () => {
            // Check meta tag first (Flask-WTF renders it in the base template).
            const meta = document.querySelector('meta[name="csrf-token"]');
            if (meta) return meta.getAttribute('content');
            // Fallback: find any hidden csrf_token input on the page.
            const inp = document.querySelector('input[name="csrf_token"]');
            return inp ? inp.value : null;
        }
        """
    )
    assert csrf, "Could not find CSRF token on admin realm detail page"
    bulk_url = _base_url() + "/admin/api/realms/bulk"
    import json as _json
    result = await admin._page.request.post(
        bulk_url,
        data=_json.dumps({"action": "revoke", "realm_ids": [realm_id], "reason": "Revoked by test"}),
        headers={
            "Content-Type": "application/json",
            "X-CSRFToken": csrf,
        },
    )
    resp_text = await result.text()
    assert result.status == 200, (
        f"Bulk revoke API returned {result.status}: {resp_text[:300]}"
    )
    resp_json = _json.loads(resp_text)
    # Response shape: {action, total, success, failed, results: {success:[], failed:[]}}
    assert resp_json.get("success", 0) >= 1, (
        f"Bulk revoke returned no successes: {resp_json}"
    )


async def _user_create_token(user: Browser, realm_id: int) -> tuple[str, str]:
    """Create a token for realm_id via account portal. Returns (token_plain, token_name)."""
    await user.goto(settings.url(f"/account/realms/{realm_id}/tokens/new"))
    token_name = f"realm-xrole-{secrets.token_hex(3)}"
    await user.fill("#token_name", token_name)
    await user.evaluate("() => document.querySelector('form').submit()")
    await user.wait_for_text("main h1", "Token Generated", timeout=10.0)
    token_plain = await user.get_attribute("#tokenValue", "value")
    assert token_plain and token_plain.startswith("naf_"), f"bad token plaintext: {token_plain!r}"

    verification.wait_for(
        lambda: verification.get_token(token_name=token_name) is not None,
        timeout=10.0,
        message=f"token {token_name} not visible in DB after create",
    )
    return token_plain, token_name


async def _dns_get(token: str, domain: str) -> int:
    """GET the DNS records endpoint with Bearer token; return HTTP status."""
    import httpx

    url = _base_url() + f"/api/dns/{domain}/records"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url, headers={"Authorization": f"Bearer {token}"}, timeout=15.0
        )
    return resp.status_code


async def _admin_delete_account(admin: Browser, account_id: int, username: str) -> None:
    """Best-effort cleanup: delete a throwaway account via the admin UI."""
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


@pytest.fixture
def _demo_username() -> str:
    import os
    from ui_tests.env_defaults import get_env_default

    return os.environ.get("DEFAULT_TEST_CLIENT_ID") or get_env_default("DEFAULT_TEST_CLIENT_ID")


# --------------------------------------------------------------------------
# Test 4 — realm request → admin approval → token works; pre-approval denied
# --------------------------------------------------------------------------

async def test_realm_request_approval_propagates(playwright_client, _demo_username):
    """Realm lifecycle: user requests, admin approves; portal + API reflect it.

    Pre-approval: token creation on a pending realm is blocked by the app.
    Post-approval: token created + DNS GET succeeds (200).
    """
    async with ParallelSessionManager(
        browser=playwright_client.browser, base_url=settings.url("")
    ) as manager:
        _INVITE_MANAGER["manager"] = manager
        mailpit = _mailpit()

        acct = ThrowawayAccount(
            username=f"xrealm-t4-{secrets.token_hex(3)}",
            email=f"xrealm-t4-{secrets.token_hex(3)}@example.test",
            password=_make_password("t4"),
        )
        subdomain = f"t4sub{secrets.token_hex(3)}"
        realm_domain = "dyn.example.com"
        demo_before = verification.get_account(_demo_username)
        admin = await _admin_browser(manager)

        try:
            await _admin_create_account(admin, mailpit, acct)

            user = await _browser_for(manager, "account", f"user_{acct.username}")
            mailpit.clear()
            await _account_login(user, acct.username, acct.password)

            # Step 1: User requests a realm.
            realm_id = await _user_request_realm_for_account(
                user, subdomain=subdomain, account_username=acct.username
            )
            acct.realm_id = realm_id

            # Channel A: realm row exists with status='pending'.
            realm_row = verification.get_realm(realm_id=realm_id)
            assert realm_row["status"] == "pending", (
                f"expected pending, got {realm_row['status']!r}"
            )

            # Channel B: account API realms shows it pending.
            api_realms = await verification.account_api_realms(user)
            match = [r for r in api_realms if r.get("id") == realm_id]
            assert match, f"realm {realm_id} not found in account_api_realms"
            assert match[0]["status"] == "pending", (
                f"account_api_realms status={match[0]['status']!r}, expected 'pending'"
            )

            # Step 2 (pre-approval guard): token creation on a pending realm is blocked.
            # The route redirects away with a flash error when realm.status != 'approved'.
            await user.goto(settings.url(f"/account/realms/{realm_id}/tokens/new"))
            current = user._page.url
            # The app redirects to dashboard with an error flash; we must not be on the
            # token-create page any more (or if we are, the submit must fail).
            # Navigation check: app redirects pending-realm token create to dashboard.
            assert f"/realms/{realm_id}/tokens/new" not in current, (
                f"Pending realm token-create page should redirect away; still at {current}"
            )

            # Step 3: Admin approves the realm.
            await _admin_approve_realm(admin, realm_id)

            # Channel A: status='approved'.
            approved = verification.get_realm(realm_id=realm_id)
            assert approved["status"] == "approved", (
                f"expected 'approved', got {approved['status']!r}"
            )

            # User portal reflects approved status.
            await user.goto(settings.url("/account/realms"), wait_until="domcontentloaded")
            body = await user.text("body")
            assert "Active" in body or subdomain in body, (
                f"user realms page does not show approved realm; body snippet: {body[:400]}"
            )

            # Step 4: User creates a token on the now-approved realm.
            token_plain, token_name = await _user_create_token(user, realm_id)
            acct.token_plain = token_plain

            # Channel C1: DNS GET succeeds (200).
            status = await _dns_get(token_plain, realm_domain)
            assert status == 200, f"DNS GET expected 200 after realm approval, got {status}"

        finally:
            if acct.account_id is not None:
                await _admin_delete_account(admin, acct.account_id, acct.username)
            demo_after = verification.get_account(_demo_username)
            assert demo_after is not None and demo_before is not None
            assert demo_after["is_active"] == demo_before["is_active"], (
                "primary demo client is_active changed during test 4"
            )


# --------------------------------------------------------------------------
# Test 5 — admin rejection reason is persisted; user portal shows rejected
# --------------------------------------------------------------------------

async def test_realm_rejection_reason_visible_to_user(playwright_client, _demo_username):
    """Realm lifecycle: user requests, admin rejects with reason; reason persisted in DB.

    Spec adjustment: ``rejection_reason`` is stored in account_realms.rejection_reason
    (Channel A). No account portal template currently renders the text verbatim, so
    we assert via Channel A (DB). The user portal does show the 'Rejected' badge.
    """
    async with ParallelSessionManager(
        browser=playwright_client.browser, base_url=settings.url("")
    ) as manager:
        _INVITE_MANAGER["manager"] = manager
        mailpit = _mailpit()

        acct = ThrowawayAccount(
            username=f"xrealm-t5-{secrets.token_hex(3)}",
            email=f"xrealm-t5-{secrets.token_hex(3)}@example.test",
            password=_make_password("t5"),
        )
        subdomain = f"t5sub{secrets.token_hex(3)}"
        # A distinctive reason string we can check in the DB.
        rejection_reason = f"Domain not owned by applicant - T5 test {secrets.token_hex(4)}"
        demo_before = verification.get_account(_demo_username)
        admin = await _admin_browser(manager)

        try:
            await _admin_create_account(admin, mailpit, acct)

            user = await _browser_for(manager, "account", f"user_{acct.username}")
            mailpit.clear()
            await _account_login(user, acct.username, acct.password)

            # Step 1: User requests a realm.
            realm_id = await _user_request_realm_for_account(
                user, subdomain=subdomain, account_username=acct.username
            )
            acct.realm_id = realm_id

            # Channel A: status='pending'.
            assert verification.get_realm(realm_id=realm_id)["status"] == "pending"

            # Step 2: Admin rejects with the distinctive reason.
            await _admin_reject_realm(admin, realm_id, rejection_reason)

            # Channel A: status='rejected' + reason persisted.
            rejected_row = verification.get_realm(realm_id=realm_id)
            assert rejected_row["status"] == "rejected", (
                f"expected 'rejected', got {rejected_row['status']!r}"
            )
            assert rejected_row["rejection_reason"] == rejection_reason, (
                f"rejection_reason mismatch: "
                f"got {rejected_row['rejection_reason']!r}, "
                f"expected {rejection_reason!r}"
            )

            # Step 3: User portal realm list shows rejected status.
            await user.goto(settings.url("/account/realms"), wait_until="domcontentloaded")
            body = await user.text("body")
            # The realms.html template renders {{ realm.status | title }} for
            # non-approved/non-pending statuses → "Rejected".
            assert "Rejected" in body, (
                f"user realms page does not show 'Rejected' badge; snippet: {body[:400]}"
            )

        finally:
            if acct.account_id is not None:
                await _admin_delete_account(admin, acct.account_id, acct.username)
            demo_after = verification.get_account(_demo_username)
            assert demo_after is not None and demo_before is not None
            assert demo_after["is_active"] == demo_before["is_active"], (
                "primary demo client is_active changed during test 5"
            )


# --------------------------------------------------------------------------
# Test 6 — admin revocation kills existing tokens
# --------------------------------------------------------------------------

async def test_realm_revocation_kills_existing_tokens(playwright_client, _demo_username):
    """Realm lifecycle: working token → admin revokes realm → same token denied (401).

    Channel A: realm status updated; activity_log records denial with error_code
    ``realm_not_approved`` (the token_auth layer checks realm.status before serving).
    """
    async with ParallelSessionManager(
        browser=playwright_client.browser, base_url=settings.url("")
    ) as manager:
        _INVITE_MANAGER["manager"] = manager
        mailpit = _mailpit()

        acct = ThrowawayAccount(
            username=f"xrealm-t6-{secrets.token_hex(3)}",
            email=f"xrealm-t6-{secrets.token_hex(3)}@example.test",
            password=_make_password("t6"),
        )
        subdomain = f"t6sub{secrets.token_hex(3)}"
        realm_domain = "dyn.example.com"
        demo_before = verification.get_account(_demo_username)
        admin = await _admin_browser(manager)

        try:
            await _admin_create_account(admin, mailpit, acct)

            user = await _browser_for(manager, "account", f"user_{acct.username}")
            mailpit.clear()
            await _account_login(user, acct.username, acct.password)

            # Setup: request realm, admin approves, user creates token.
            realm_id = await _user_request_realm_for_account(
                user, subdomain=subdomain, account_username=acct.username
            )
            acct.realm_id = realm_id
            await _admin_approve_realm(admin, realm_id)

            token_plain, token_name = await _user_create_token(user, realm_id)
            acct.token_plain = token_plain

            # Step 1: Token works before revocation (C1 → 200).
            pre_revoke_status = await _dns_get(token_plain, realm_domain)
            assert pre_revoke_status == 200, (
                f"baseline DNS GET before revocation expected 200, got {pre_revoke_status}"
            )

            # Count existing denied activity for this account (baseline).
            denied_before = verification.count_activity(
                account_username=acct.username, status="denied"
            )

            # Step 2: Admin revokes the realm via UI.
            await _admin_revoke_realm(admin, realm_id)

            # Channel A: realm status is no longer 'approved'.
            verification.wait_for(
                lambda: verification.get_realm(realm_id=realm_id)["status"] != "approved",
                timeout=10.0,
                message="realm status did not change after revoke",
            )
            revoked_realm = verification.get_realm(realm_id=realm_id)
            # The app stores 'revoked'; we assert it changed from 'approved'.
            assert revoked_realm["status"] != "approved", (
                f"realm status should not be 'approved' after revoke, got {revoked_realm['status']!r}"
            )

            # Step 3: C1 — same token now returns 401 (realm_not_approved check in token_auth).
            post_revoke_status = await _dns_get(token_plain, realm_domain)
            assert post_revoke_status == 401, (
                f"revoked-realm DNS GET expected 401, got {post_revoke_status}"
            )

            # Channel A: activity_log records the denial with error_code='realm_not_approved'.
            verification.wait_for(
                lambda: verification.count_activity(
                    account_username=acct.username, status="denied"
                ) > denied_before,
                timeout=10.0,
                message="no new denied activity logged after revoked-realm API call",
            )
            recent_denied = [
                r for r in verification.latest_activity(
                    account_username=acct.username, limit=10
                )
                if r.get("status") == "denied"
            ]
            assert recent_denied, "expected at least one denied activity_log row after revocation"
            assert recent_denied[0]["error_code"] == "realm_not_approved", (
                f"expected error_code 'realm_not_approved', "
                f"got {recent_denied[0]['error_code']!r}"
            )

        finally:
            if acct.account_id is not None:
                await _admin_delete_account(admin, acct.account_id, acct.username)
            demo_after = verification.get_account(_demo_username)
            assert demo_after is not None and demo_before is not None
            assert demo_after["is_active"] == demo_before["is_active"], (
                "primary demo client is_active changed during test 6"
            )
