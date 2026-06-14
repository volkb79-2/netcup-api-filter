"""Admin security settings form test.

Covers:
- GET /admin/settings
- POST /admin/system/security

Round-trip grade: the admin POST submits a CHANGED admin_rate_limit value and
Channel A (settings table) confirms the new value was actually persisted by the
handler (not just that the UI flashed success). The original value is restored in
a finally block so the deployment is left unchanged.
"""

from __future__ import annotations

import secrets

import pytest

from ui_tests import verification, workflows
from ui_tests.browser import Browser
from ui_tests.config import settings


pytestmark = [pytest.mark.asyncio, pytest.mark.feature]

# The admin rate-limit setting is stored in the `settings` table under this key
# as a JSON string (verified against the live schema + admin.update_security_settings).
ADMIN_RATE_LIMIT_KEY = "admin_rate_limit"


async def test_admin_system_security_settings_post(active_profile, session_manager):
    if not active_profile.allow_writes:
        pytest.skip("profile is read-only")

    admin_handle = await session_manager.admin_session()
    browser = Browser(admin_handle.page)
    await browser.reset()
    await workflows.ensure_admin_dashboard(browser)

    await browser.goto(settings.url("/admin/settings"), wait_until="domcontentloaded")
    await browser.wait_for_text("h1", "Settings")

    form_state = await browser.evaluate(
        """
        () => {
            const form = document.querySelector("form[action*='/system/security']");
            if (!form) return null;
            const getVal = (sel) => {
                const el = document.querySelector(sel);
                return el ? (el.value || '') : '';
            };
            return {
                action: form.getAttribute('action') || '',
                csrf_token: getVal("form[action*='/system/security'] input[name='csrf_token']"),
                password_reset_expiry_hours: getVal('#password_reset_expiry'),
                invite_expiry_hours: getVal('#invite_expiry'),
                admin_rate_limit: getVal('#admin_rate_limit'),
                account_rate_limit: getVal('#account_rate_limit'),
                api_rate_limit: getVal('#api_rate_limit'),
            };
        }
        """
    )

    assert form_state and form_state.get("csrf_token")
    action_raw = form_state.get("action") or ""
    assert action_raw

    action_url = action_raw if action_raw.startswith("http") else settings.url(action_raw)

    # Channel A precondition: capture the current persisted value so we can both
    # assert the change AND restore it afterwards.
    verification.require_db()
    original_admin_rate_limit = verification.get_setting_value(ADMIN_RATE_LIMIT_KEY)

    # Submit a DISTINCT admin_rate_limit value (a valid Flask-Limiter string that
    # is guaranteed different from whatever is currently stored). All other fields
    # are re-posted unchanged so the test mutates exactly one setting.
    new_admin_rate_limit = f"{secrets.randbelow(40) + 11} per minute"
    while new_admin_rate_limit == original_admin_rate_limit:
        new_admin_rate_limit = f"{secrets.randbelow(40) + 11} per minute"

    try:
        resp = await browser.request_post_form(
            action_url,
            {
                "csrf_token": form_state["csrf_token"],
                "password_reset_expiry_hours": form_state["password_reset_expiry_hours"],
                "invite_expiry_hours": form_state["invite_expiry_hours"],
                "admin_rate_limit": new_admin_rate_limit,
                "account_rate_limit": form_state["account_rate_limit"],
                "api_rate_limit": form_state["api_rate_limit"],
            },
        )

        assert resp["status"] in {200, 302}, f"unexpected POST status {resp['status']}"

        # Channel A (authoritative): the handler actually persisted the submitted
        # value to the settings table — NOT merely flashed a success message.
        verification.wait_for(
            lambda: verification.get_setting_value(ADMIN_RATE_LIMIT_KEY) == new_admin_rate_limit,
            timeout=10.0,
            message=(
                f"admin_rate_limit was not persisted as {new_admin_rate_limit!r}; "
                f"DB still has {verification.get_setting_value(ADMIN_RATE_LIMIT_KEY)!r}"
            ),
        )

        # UI feedback (kept as a secondary signal, not the load-bearing assertion).
        if resp["status"] == 200:
            assert "security settings updated" in (resp.get("text") or "").lower()
        else:
            await browser.goto(settings.url("/admin/system"), wait_until="domcontentloaded")
            body = await browser.text("body")
            assert "security settings updated" in (body or "").lower()

    finally:
        # Restore the original value so the deployment is left untouched. Re-fetch
        # a fresh CSRF token (the page may have changed) to make the restore POST.
        await browser.goto(settings.url("/admin/settings"), wait_until="domcontentloaded")
        restore_state = await browser.evaluate(
            """
            () => {
                const form = document.querySelector("form[action*='/system/security']");
                if (!form) return null;
                const getVal = (sel) => { const el = document.querySelector(sel); return el ? (el.value || '') : ''; };
                return {
                    csrf_token: getVal("form[action*='/system/security'] input[name='csrf_token']"),
                    password_reset_expiry_hours: getVal('#password_reset_expiry'),
                    invite_expiry_hours: getVal('#invite_expiry'),
                    account_rate_limit: getVal('#account_rate_limit'),
                    api_rate_limit: getVal('#api_rate_limit'),
                };
            }
            """
        )
        if restore_state and restore_state.get("csrf_token") and original_admin_rate_limit is not None:
            await browser.request_post_form(
                action_url,
                {
                    "csrf_token": restore_state["csrf_token"],
                    "password_reset_expiry_hours": restore_state["password_reset_expiry_hours"],
                    "invite_expiry_hours": restore_state["invite_expiry_hours"],
                    "admin_rate_limit": original_admin_rate_limit,
                    "account_rate_limit": restore_state["account_rate_limit"],
                    "api_rate_limit": restore_state["api_rate_limit"],
                },
            )
            verification.wait_for(
                lambda: verification.get_setting_value(ADMIN_RATE_LIMIT_KEY) == original_admin_rate_limit,
                timeout=10.0,
                message="failed to restore original admin_rate_limit",
            )
