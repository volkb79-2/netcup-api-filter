"""Admin security settings form test.

Covers:
- GET /admin/settings
- POST /admin/system/security

This is intentionally non-destructive:
- It re-posts the current values from the form.
"""

from __future__ import annotations

import pytest

from ui_tests import workflows
from ui_tests.browser import Browser
from ui_tests.config import settings


pytestmark = pytest.mark.asyncio


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

    resp = await browser.request_post_form(
        action_url,
        {
            "csrf_token": form_state["csrf_token"],
            "password_reset_expiry_hours": form_state["password_reset_expiry_hours"],
            "invite_expiry_hours": form_state["invite_expiry_hours"],
            "admin_rate_limit": form_state["admin_rate_limit"],
            "account_rate_limit": form_state["account_rate_limit"],
            "api_rate_limit": form_state["api_rate_limit"],
        },
    )

    assert resp["status"] in {200, 302}

    # Depending on Playwright behavior, the request client may follow the redirect
    # and return the final HTML (200), which also consumes the flash message.
    if resp["status"] == 200:
        assert "security settings updated" in (resp.get("text") or "").lower()
        return

    # Otherwise, verify the success flash is visible after navigating.
    await browser.goto(settings.url("/admin/system"), wait_until="domcontentloaded")
    body = await browser.text("body")
    assert "security settings updated" in (body or "").lower()
