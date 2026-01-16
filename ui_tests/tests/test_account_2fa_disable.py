"""Account portal 2FA disable E2E.

Covers:
- Enable TOTP via /account/settings/totp/setup
- Disable 2FA via /account/security/2fa/disable

This test is auth-boundary related and uses an isolated account session.
"""

from __future__ import annotations

import os
import re

import pyotp
import pytest

from ui_tests import workflows
from ui_tests.browser import Browser
from ui_tests.config import settings
from ui_tests.env_defaults import get_env_default


pytestmark = pytest.mark.asyncio


async def test_account_totp_enable_then_disable(active_profile, session_manager):
    if not active_profile.allow_writes:
        pytest.skip("profile is read-only")

    handle = await session_manager.create_session(role="account", session_id="acct_totp_disable")
    browser = Browser(handle.page)
    await browser.reset()
    await workflows.ensure_user_dashboard(browser)

    demo_password = (os.environ.get("DEFAULT_TEST_ACCOUNT_PASSWORD") or get_env_default("DEFAULT_TEST_ACCOUNT_PASSWORD") or "").strip()
    if not demo_password:
        pytest.skip("DEFAULT_TEST_ACCOUNT_PASSWORD not configured")

    demo_username = (os.environ.get("DEFAULT_TEST_CLIENT_ID") or get_env_default("DEFAULT_TEST_CLIENT_ID") or "").strip()
    if not demo_username:
        pytest.skip("DEFAULT_TEST_CLIENT_ID not configured")

    # Enable TOTP
    await browser.goto(settings.url("/account/settings/totp/setup"), wait_until="domcontentloaded")
    await browser.wait_for_text("h2", "Set Up Two-Factor Authentication", timeout=10.0)

    secret = (await browser.text("#setup-key")).strip()
    assert secret

    code = pyotp.TOTP(secret).now()
    await browser.fill("#verification-code", code)
    await browser.submit("#verify-2fa-form")

    # Confirm enabled (settings page should reflect it)
    await browser.goto(settings.url("/account/security"), wait_until="domcontentloaded")
    body = await browser.text("body")
    assert "two-factor authentication" in (body or "").lower()
    assert "disable 2fa" in (body or "").lower()

    # Prove TOTP works for login while enabled.
    await browser.goto(settings.url("/account/logout"), wait_until="domcontentloaded")
    await browser.goto(settings.url("/account/login"), wait_until="domcontentloaded")
    await browser.fill("#username", demo_username)
    await browser.fill("#password", demo_password)
    await browser.submit("form")
    await browser._page.wait_for_url(re.compile(r".*/account/login/2fa.*"), timeout=10000)

    # Switch 2FA method to TOTP (ensures verify_2fa uses TOTP path).
    csrf_token = await browser.evaluate(
        """
        () => document.querySelector("form[action*='/account/login/2fa'] input[name='csrf_token']")?.value || ''
        """
    )
    assert csrf_token
    async with browser._page.expect_navigation(wait_until="domcontentloaded", timeout=10000):
        await browser._page.evaluate(
            """
            ({ csrfToken }) => {
                const form = document.createElement('form');
                form.method = 'POST';
                form.action = '/account/2fa/resend';

                const csrf = document.createElement('input');
                csrf.type = 'hidden';
                csrf.name = 'csrf_token';
                csrf.value = csrfToken;

                const method = document.createElement('input');
                method.type = 'hidden';
                method.name = 'method';
                method.value = 'totp';

                form.appendChild(csrf);
                form.appendChild(method);
                document.body.appendChild(form);
                form.submit();
            }
            """,
            {"csrfToken": csrf_token},
        )

    await browser.fill("#code", pyotp.TOTP(secret).now())
    async with browser._page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
        await browser._page.click("form[action='/account/login/2fa'] button[type='submit']")
    await browser._page.wait_for_url(re.compile(r".*/account/(dashboard|realms|tokens).*"), timeout=15000)

    # Return to security settings (needed for the disable form extraction).
    await browser.goto(settings.url("/account/security"), wait_until="domcontentloaded")

    disable_form = await browser.evaluate(
        """
        () => {
            const form = document.querySelector("form[action*='/security/2fa/disable']");
            if (!form) return null;
            const csrf = form.querySelector("input[name='csrf_token']")?.value || '';
            const action = form.getAttribute('action') || '';
            return { csrf, action };
        }
        """
    )
    assert disable_form and disable_form.get("csrf") and disable_form.get("action")

    action_url = disable_form["action"] if disable_form["action"].startswith("http") else settings.url(disable_form["action"])

    resp = await browser.request_post_form(
        action_url,
        {
            "csrf_token": disable_form["csrf"],
            "password": demo_password,
            # Route currently ignores this field, but UI requires it.
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert resp["status"] in {200, 302}

    await browser.goto(settings.url("/account/security"), wait_until="domcontentloaded")
    body2 = await browser.text("body")
    lowered = (body2 or "").lower()
    assert "two-factor authentication has been disabled" in lowered or "disabled" in lowered
    assert "enable 2fa" in lowered

    # Prove TOTP no longer works for login after disable.
    await browser.goto(settings.url("/account/logout"), wait_until="domcontentloaded")
    await browser.goto(settings.url("/account/login"), wait_until="domcontentloaded")
    await browser.fill("#username", demo_username)
    await browser.fill("#password", demo_password)
    await browser.submit("form")
    await browser._page.wait_for_url(re.compile(r".*/account/login/2fa.*"), timeout=10000)

    csrf_token2 = await browser.evaluate(
        """
        () => document.querySelector("form[action*='/account/login/2fa'] input[name='csrf_token']")?.value || ''
        """
    )
    assert csrf_token2
    async with browser._page.expect_navigation(wait_until="domcontentloaded", timeout=10000):
        await browser._page.evaluate(
            """
            ({ csrfToken }) => {
                const form = document.createElement('form');
                form.method = 'POST';
                form.action = '/account/2fa/resend';

                const csrf = document.createElement('input');
                csrf.type = 'hidden';
                csrf.name = 'csrf_token';
                csrf.value = csrfToken;

                const method = document.createElement('input');
                method.type = 'hidden';
                method.name = 'method';
                method.value = 'totp';

                form.appendChild(csrf);
                form.appendChild(method);
                document.body.appendChild(form);
                form.submit();
            }
            """,
            {"csrfToken": csrf_token2},
        )

    await browser.fill("#code", pyotp.TOTP(secret).now())
    async with browser._page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
        await browser._page.click("form[action='/account/login/2fa'] button[type='submit']")

    error_body = (await browser.text("body") or "").lower()
    assert "totp not configured" in error_body
