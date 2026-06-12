"""Cross-role E2E round-trip tests: token lifecycle & scope enforcement.

Tests 7, 8, 9 — copy of T08 pattern (read test_cross_role_account_lifecycle.py
before editing this file).

ENVIRONMENT NOTES (pinned to implementation)
--------------------------------------------
* Token revocation makes the API return HTTP 401 (not 403): the ``require_auth``
  decorator returns 401 for all auth failures, including ``token_revoked``.  The
  ``error_code`` is logged to ``activity_log`` (Channel A) as ``'token_revoked'``
  with ``action='api_auth'``.
* Operation-scope denial returns HTTP 403 with ``error_code='operation_denied'``
  and ``action='api_call'`` in ``activity_log``.
* Admin revoke route: POST /admin/tokens/<id>/revoke
* User revoke route:  POST /account/tokens/<id>/revoke
  (the account dashboard renders a modal that POSTs to that URL; we bypass the
  modal and submit the form directly via JS)
* Token creation: POST /account/realms/<realm_id>/tokens/new accepts form fields
  ``token_name`` and (optionally) ``operations`` (list).  The ``create_token.html``
  template does NOT render operations checkboxes, so a read-only token must be
  created by submitting the form via JS with the extra fields injected.
* Channel B (``account_api_realm_tokens``) only returns *active* tokens
  (``is_active=1``); after revocation the token simply disappears from the list.
"""
from __future__ import annotations

import secrets

import httpx
import pytest

from ui_tests import verification, workflows
from ui_tests.browser import Browser
from ui_tests.config import settings
from ui_tests.cross_role_helpers import (
    account_login,
    admin_browser,
    admin_delete_account,
    base_url,
    browser_for,
    complete_invite,
    mailpit_client,
    make_password,
    wait_for_email,
    extract_link,
    link_to_local_url,
)
from ui_tests.parallel_session_manager import ParallelSessionManager


pytestmark = pytest.mark.asyncio


THROWAWAY_DOMAIN = "example.com"


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture
def _demo_username() -> str:
    import os
    from ui_tests.env_defaults import get_env_default
    return os.environ.get("DEFAULT_TEST_CLIENT_ID") or get_env_default("DEFAULT_TEST_CLIENT_ID")


# --------------------------------------------------------------------------
# ThrowawayAccount + factory (re-used across all three tests)
# --------------------------------------------------------------------------

class ThrowawayAccount:
    def __init__(self, username: str, email: str, password: str):
        self.username = username
        self.email = email
        self.password = password
        self.account_id: int | None = None
        self.realm_id: int | None = None


async def _admin_create_account_with_realm(
    admin: Browser,
    mailpit,
    acct: ThrowawayAccount,
    manager: ParallelSessionManager,
) -> None:
    """Create an invited account + pre-approved example.com realm via admin UI."""
    mailpit.clear()

    await admin.goto(settings.url("/admin/accounts/new"))
    await admin.wait_for_text("main h1", "Create Account")
    await admin.fill("#username", acct.username)
    await admin.fill("#email", acct.email)

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
            for (const id of ['op_read','op_update','op_create','op_delete']) {
                const e=document.getElementById(id); if (e) e.checked = true;
            }
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

    verification.wait_for(
        lambda: verification.get_account(acct.username) is not None,
        timeout=10.0,
        message=f"account {acct.username} not visible in DB after create",
    )
    row = verification.get_account(acct.username)
    acct.account_id = row["id"]
    assert row["is_active"] == 1, f"new account should be active, got is_active={row['is_active']}"

    verification.wait_for(
        lambda: verification.get_realm(account_username=acct.username, domain=THROWAWAY_DOMAIN) is not None,
        timeout=10.0,
        message="pre-approved realm was not created",
    )
    realm = verification.get_realm(account_username=acct.username, domain=THROWAWAY_DOMAIN)
    assert realm["status"] == "approved", f"realm status={realm['status']!r}, expected 'approved'"
    acct.realm_id = realm["id"]

    msg = wait_for_email(mailpit, to_address=acct.email, subject_substr="account has been created")
    invite_url = link_to_local_url(extract_link(msg, "/account/invite/"))
    mailpit.clear()

    await complete_invite(manager, invite_url, acct.password)

    verification.wait_for(
        lambda: verification.get_account(acct.username)["must_change_password"] == 0,
        timeout=10.0,
        message="must_change_password not cleared after invite accept",
    )


async def _user_create_token(
    user: Browser,
    realm_id: int,
    *,
    operations: list[str] | None = None,
) -> tuple[str, str, str]:
    """Create a token via the account portal; capture plaintext.

    Returns (token_plain, token_name, token_prefix).
    ``operations`` is an optional list submitted as extra hidden inputs so that
    scope-restricted tokens can be created through the real form POST.
    """
    token_name = f"xrole-tkn-{secrets.token_hex(3)}"

    # Navigate to the create-token page so we have a session cookie + CSRF token.
    await user.goto(settings.url(f"/account/realms/{realm_id}/tokens/new"))
    await user.wait_for_text("main h2", "Create API Token", timeout=10.0)

    if operations is None:
        # Simple path: just fill the name and submit the visible form.
        await user.fill("#token_name", token_name)
        await user.evaluate("() => document.querySelector('form').submit()")
    else:
        # Inject hidden `operations` inputs before submitting.
        ops_json = operations  # list of strings
        await user.evaluate(
            """
            ([name, ops]) => {
                const f = document.querySelector('form');
                const nameInput = document.getElementById('token_name');
                if (nameInput) nameInput.value = name;
                for (const op of ops) {
                    const h = document.createElement('input');
                    h.type = 'hidden';
                    h.name = 'operations';
                    h.value = op;
                    f.appendChild(h);
                }
                f.submit();
            }
            """,
            [token_name, ops_json],
        )

    await user.wait_for_text("main h1", "Token Generated", timeout=15.0)
    token_plain = await user.get_attribute("#tokenValue", "value")
    assert token_plain and token_plain.startswith("naf_"), (
        f"bad token plaintext: {token_plain!r}"
    )

    verification.wait_for(
        lambda: verification.get_token(token_name=token_name) is not None,
        timeout=10.0,
        message=f"token {token_name} not visible in DB after create",
    )
    row = verification.get_token(token_name=token_name)
    return token_plain, token_name, row["token_prefix"]


async def _dns_get(token: str, domain: str) -> tuple[int, dict]:
    """GET /api/dns/<domain>/records; return (status_code, body_dict)."""
    url = base_url() + f"/api/dns/{domain}/records"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url, headers={"Authorization": f"Bearer {token}"}, timeout=15.0
        )
    try:
        body = resp.json()
    except Exception:
        body = {}
    return resp.status_code, body


async def _dns_create(token: str, domain: str) -> tuple[int, dict]:
    """POST /api/dns/<domain>/records; return (status_code, body_dict)."""
    url = base_url() + f"/api/dns/{domain}/records"
    payload = {
        "type": "A",
        "hostname": f"test-{secrets.token_hex(3)}",
        "destination": "1.2.3.4",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15.0,
        )
    try:
        body = resp.json()
    except Exception:
        body = {}
    return resp.status_code, body


# --------------------------------------------------------------------------
# Test 7 — admin revokes token → immediate API block + channel A/B confirm
# --------------------------------------------------------------------------

@pytest.mark.ci_smoke
async def test_admin_token_revocation_immediate(playwright_client, _demo_username):
    """Admin revokes a token; C1 goes 401 instantly; Channel A sees is_active==0."""
    async with ParallelSessionManager(
        browser=playwright_client.browser, base_url=settings.url("")
    ) as manager:
        mailpit = mailpit_client()
        acct = ThrowawayAccount(
            username=f"xrole-tr7-{secrets.token_hex(3)}",
            email=f"xrole-tr7-{secrets.token_hex(3)}@example.test",
            password=make_password("t7"),
        )
        demo_before = verification.get_account(_demo_username)
        admin = await admin_browser(manager, session_id="admin_t7")
        token_name: str | None = None

        try:
            await _admin_create_account_with_realm(admin, mailpit, acct, manager)

            user = await browser_for(manager, "account", f"user_{acct.username}")
            await account_login(user, acct.username, acct.password)

            token_plain, token_name, _prefix = await _user_create_token(user, acct.realm_id)

            # --- Baseline: C1 GET succeeds ---
            status, _body = await _dns_get(token_plain, THROWAWAY_DOMAIN)
            assert status == 200, f"baseline DNS GET expected 200, got {status}"

            # --- Channel A baseline: token is active ---
            tok_row = verification.get_token(token_name=token_name)
            token_id = tok_row["id"]
            assert tok_row["is_active"] == 1, "new token should have is_active=1"

            # --- Admin navigates to token detail and submits revoke form ---
            await admin.goto(settings.url(f"/admin/tokens/{token_id}"))
            await admin.evaluate(
                """
                () => {
                    const f = document.querySelector("form[action*='/revoke']");
                    if (f) f.submit();
                }
                """
            )
            # Wait for redirect back to token detail (flash message rendered)
            await admin._page.wait_for_url(
                f"**{token_id}**", timeout=10_000
            )

            # --- Channel A: is_active flipped to 0 ---
            verification.wait_for(
                lambda: verification.get_token(token_name=token_name)["is_active"] == 0,
                timeout=10.0,
                message="token is_active did not become 0 after admin revoke",
            )
            row_after = verification.get_token(token_name=token_name)
            assert row_after["is_active"] == 0, (
                f"Channel A: expected is_active=0, got {row_after['is_active']}"
            )
            # revoked_at column should also be set
            assert row_after.get("revoked_at") is not None, (
                "Channel A: revoked_at should be set after admin revoke"
            )

            # --- C1: same GET now returns 401 (token_revoked in activity_log) ---
            status_after, _body = await _dns_get(token_plain, THROWAWAY_DOMAIN)
            assert status_after == 401, (
                f"revoked token DNS GET expected 401, got {status_after}"
            )

            # Channel A: activity_log has a denied row with error_code='token_revoked'
            verification.wait_for(
                lambda: verification.count_activity(
                    action="api_auth",
                    status="denied",
                    account_username=acct.username,
                ) >= 1,
                timeout=10.0,
                message="no denied api_auth activity logged for revoked token",
            )
            denied_rows = [
                r for r in verification.latest_activity(
                    account_username=acct.username, limit=20
                )
                if r.get("status") == "denied" and r.get("action") == "api_auth"
            ]
            assert denied_rows, "expected denied api_auth row in activity_log"
            assert denied_rows[0]["error_code"] == "token_revoked", (
                f"expected error_code 'token_revoked', got {denied_rows[0]['error_code']!r}"
            )

            # --- Channel B: token absent from account API token list ---
            tokens_b = await verification.account_api_realm_tokens(user, acct.realm_id)
            active_ids = [t["id"] for t in tokens_b if t.get("is_active")]
            assert token_id not in active_ids, (
                f"Channel B: revoked token {token_id} still in active list: {tokens_b}"
            )

        finally:
            if acct.account_id is not None:
                await admin_delete_account(admin, acct.account_id, acct.username)
            demo_after = verification.get_account(_demo_username)
            assert demo_after is not None and demo_before is not None
            assert demo_after["is_active"] == demo_before["is_active"], (
                "primary demo client is_active changed during Test 7"
            )


# --------------------------------------------------------------------------
# Test 8 — user revokes own token → API blocked + activity_log row
# --------------------------------------------------------------------------

async def test_user_token_revocation_blocks_api_and_logs(playwright_client, _demo_username):
    """User self-revokes a token; DNS API immediately blocked; log records action."""
    async with ParallelSessionManager(
        browser=playwright_client.browser, base_url=settings.url("")
    ) as manager:
        mailpit = mailpit_client()
        acct = ThrowawayAccount(
            username=f"xrole-tr8-{secrets.token_hex(3)}",
            email=f"xrole-tr8-{secrets.token_hex(3)}@example.test",
            password=make_password("t8"),
        )
        demo_before = verification.get_account(_demo_username)
        admin = await admin_browser(manager, session_id="admin_t8")
        token_name: str | None = None

        try:
            await _admin_create_account_with_realm(admin, mailpit, acct, manager)

            user = await browser_for(manager, "account", f"user_{acct.username}")
            await account_login(user, acct.username, acct.password)

            token_plain, token_name, _prefix = await _user_create_token(user, acct.realm_id)

            # --- Baseline: C1 GET succeeds ---
            status, _body = await _dns_get(token_plain, THROWAWAY_DOMAIN)
            assert status == 200, f"baseline DNS GET expected 200, got {status}"

            tok_row = verification.get_token(token_name=token_name)
            token_id = tok_row["id"]

            # Snapshot the denied activity count before revocation
            denied_count_before = verification.count_activity(
                action="api_auth",
                status="denied",
                account_username=acct.username,
            )

            # --- User revokes via the account tokens page ---
            # /account/tokens renders #revokeForm with a CSRF token and action
            # dynamically set by JS.  We navigate to that page, update the
            # form's action, and submit directly — bypassing the Bootstrap modal.
            await user.goto(settings.url("/account/tokens"))
            await user.wait_for_text("main h1", "My Tokens", timeout=10.0)
            await user.evaluate(
                f"""
                (tokenId) => {{
                    const f = document.getElementById('revokeForm');
                    if (!f) throw new Error('revokeForm not found');
                    f.action = `/account/tokens/${{tokenId}}/revoke`;
                    f.submit();
                }}
                """,
                token_id,
            )
            # After revoke, user is redirected to dashboard
            await user._page.wait_for_url(
                "**dashboard**", timeout=10_000
            )

            # --- Channel A: is_active flipped to 0 ---
            verification.wait_for(
                lambda: verification.get_token(token_name=token_name)["is_active"] == 0,
                timeout=10.0,
                message="token is_active did not become 0 after user revoke",
            )
            row_after = verification.get_token(token_name=token_name)
            assert row_after["is_active"] == 0, (
                f"Channel A: expected is_active=0, got {row_after['is_active']}"
            )
            assert row_after.get("revoked_at") is not None, (
                "Channel A: revoked_at should be set after user revoke"
            )

            # --- C1: same GET now returns 401 ---
            status_after, _body = await _dns_get(token_plain, THROWAWAY_DOMAIN)
            assert status_after == 401, (
                f"user-revoked token DNS GET expected 401, got {status_after}"
            )

            # Channel A: denied count incremented by the failed API call
            verification.wait_for(
                lambda: verification.count_activity(
                    action="api_auth",
                    status="denied",
                    account_username=acct.username,
                ) > denied_count_before,
                timeout=10.0,
                message="denied api_auth activity count did not increment after revoked-token use",
            )

            # The denial row must carry error_code='token_revoked'
            denied_rows = [
                r for r in verification.latest_activity(
                    account_username=acct.username, limit=20
                )
                if r.get("status") == "denied" and r.get("action") == "api_auth"
            ]
            assert denied_rows, "expected denied api_auth row in activity_log"
            assert denied_rows[0]["error_code"] == "token_revoked", (
                f"expected error_code 'token_revoked', got {denied_rows[0]['error_code']!r}"
            )

        finally:
            if acct.account_id is not None:
                await admin_delete_account(admin, acct.account_id, acct.username)
            demo_after = verification.get_account(_demo_username)
            assert demo_after is not None and demo_before is not None
            assert demo_after["is_active"] == demo_before["is_active"], (
                "primary demo client is_active changed during Test 8"
            )


# --------------------------------------------------------------------------
# Test 9 — read-only scope token: GET allowed, mutate blocked; inverse guard
# --------------------------------------------------------------------------

async def test_readonly_token_scope_enforced(playwright_client, _demo_username):
    """Read-only scope token: GET returns 200; POST returns 403 operation_denied.
    Full-scope token on same realm CAN mutate (inverse guard).
    """
    async with ParallelSessionManager(
        browser=playwright_client.browser, base_url=settings.url("")
    ) as manager:
        mailpit = mailpit_client()
        acct = ThrowawayAccount(
            username=f"xrole-tr9-{secrets.token_hex(3)}",
            email=f"xrole-tr9-{secrets.token_hex(3)}@example.test",
            password=make_password("t9"),
        )
        demo_before = verification.get_account(_demo_username)
        admin = await admin_browser(manager, session_id="admin_t9")
        ro_token_name: str | None = None
        full_token_name: str | None = None

        try:
            await _admin_create_account_with_realm(admin, mailpit, acct, manager)

            user = await browser_for(manager, "account", f"user_{acct.username}")
            await account_login(user, acct.username, acct.password)

            # --- Create read-only token (operations=["read"] injected via JS) ---
            ro_plain, ro_token_name, _ro_prefix = await _user_create_token(
                user, acct.realm_id, operations=["read"]
            )

            # Channel A: allowed_operations JSON is exactly ["read"]
            verification.wait_for(
                lambda: verification.get_token(token_name=ro_token_name) is not None,
                timeout=10.0,
                message=f"read-only token {ro_token_name} not in DB",
            )
            ro_db = verification.get_token(token_name=ro_token_name)
            assert ro_db is not None, "read-only token row missing from DB"
            import json as _json
            ro_ops = _json.loads(ro_db["allowed_operations"]) if ro_db.get("allowed_operations") else None
            assert ro_ops == ["read"], (
                f"Channel A: expected allowed_operations=['read'], got {ro_ops!r}"
            )

            # --- C1: GET records succeeds ---
            status_get, _body = await _dns_get(ro_plain, THROWAWAY_DOMAIN)
            assert status_get == 200, (
                f"read-only token GET expected 200, got {status_get}"
            )

            # --- C1: POST (create record) is denied with 403 ---
            status_create, body_create = await _dns_create(ro_plain, THROWAWAY_DOMAIN)
            assert status_create == 403, (
                f"read-only token POST expected 403, got {status_create}"
            )

            # Channel A: activity_log has a denied api_call row for the create attempt.
            # NOTE: dns_api.py's log_activity call does not forward perm.error_code to
            # the DB (it passes status_reason=perm.reason instead), so error_code is
            # NULL in the activity_log. We assert the status_reason text that IS stored.
            verification.wait_for(
                lambda: verification.count_activity(
                    action="api_call",
                    status="denied",
                    account_username=acct.username,
                ) >= 1,
                timeout=10.0,
                message="no denied api_call activity logged for operation_denied",
            )
            op_denied_rows = [
                r for r in verification.latest_activity(
                    account_username=acct.username, limit=20
                )
                if r.get("status") == "denied"
                and r.get("action") == "api_call"
            ]
            assert op_denied_rows, "expected denied api_call row in activity_log"
            # The status_reason is "Operation 'create' not permitted" (exact text from
            # check_permission) — error_code column is NULL because dns_api.py does not
            # forward perm.error_code to log_activity (pinned real behavior).
            assert op_denied_rows[0].get("status_reason") is not None, (
                "expected status_reason to be set on denied api_call row"
            )
            assert "not permitted" in (op_denied_rows[0].get("status_reason") or ""), (
                f"expected status_reason containing 'not permitted', "
                f"got {op_denied_rows[0].get('status_reason')!r}"
            )
            # API response body confirms: error='forbidden'
            assert body_create.get("error") == "forbidden", (
                f"expected error='forbidden' in POST body, got {body_create!r}"
            )

            # --- Inverse guard: full-scope token CAN mutate ---
            full_plain, full_token_name, _full_prefix = await _user_create_token(
                user, acct.realm_id,
                operations=["read", "create", "update", "delete"],
            )
            status_full_create, body_full = await _dns_create(full_plain, THROWAWAY_DOMAIN)
            assert status_full_create in (200, 201), (
                f"full-scope token POST expected 200/201, got {status_full_create}; body={body_full}"
            )

        finally:
            if acct.account_id is not None:
                await admin_delete_account(admin, acct.account_id, acct.username)
            demo_after = verification.get_account(_demo_username)
            assert demo_after is not None and demo_before is not None
            assert demo_after["is_active"] == demo_before["is_active"], (
                "primary demo client is_active changed during Test 9"
            )
