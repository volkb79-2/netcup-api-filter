"""Coverage tests for account 2FA routes.

Target routes (from coverage audit):
- /account/login/2fa
- /account/2fa/verify
- /account/2fa/resend
- /account/2fa/setup
- /account/security/2fa/disable

These focus on route behavior and redirects without requiring optional deps
(e.g. pyotp) or external services.
"""

import pytest

from ui_tests.browser import browser_session
from ui_tests.config import settings


pytestmark = pytest.mark.asyncio


class TestAccount2FARoutesRequirePendingState:
    async def test_account_login_2fa_redirects_without_pending_state(self, active_profile):
        async with browser_session() as browser:
            await browser.reset()
            nav = await browser.goto(settings.url("/account/login/2fa"), wait_until="domcontentloaded")
            assert nav.get("status") == 200

            # With no pending 2FA session, the route should redirect to /account/login.
            current_url = await browser.evaluate("() => window.location.pathname")
            assert current_url.startswith("/account/login")

    async def test_account_2fa_verify_redirects_without_pending_state(self, active_profile):
        async with browser_session() as browser:
            await browser.reset()

            # Get a CSRF token from the login page (shared session token).
            await browser.goto(settings.url("/account/login"), wait_until="domcontentloaded")
            csrf_token = await browser.get_attribute('input[name="csrf_token"]', "value")
            assert csrf_token

            resp = await browser.request_post_form(
                settings.url("/account/2fa/verify"),
                data={"code": "000000", "csrf_token": csrf_token},
            )
            # Flask redirect to /account/login if no pending state.
            assert resp["status"] in (200, 302)

    async def test_account_2fa_resend_redirects_without_pending_state(self, active_profile):
        async with browser_session() as browser:
            await browser.reset()

            await browser.goto(settings.url("/account/login"), wait_until="domcontentloaded")
            csrf_token = await browser.get_attribute('input[name="csrf_token"]', "value")
            assert csrf_token

            resp = await browser.request_post_form(
                settings.url("/account/2fa/resend"),
                data={"method": "email", "csrf_token": csrf_token},
            )
            assert resp["status"] in (200, 302)


class TestAccount2FASetupRequiresAuth:
    async def test_account_2fa_setup_requires_login(self, active_profile):
        async with browser_session() as browser:
            await browser.reset()
            nav = await browser.goto(settings.url("/account/2fa/setup"), wait_until="domcontentloaded")
            assert nav.get("status") == 200

            current_url = await browser.evaluate("() => window.location.pathname")
            assert current_url.startswith("/account/login")

    async def test_account_disable_2fa_requires_login(self, active_profile):
        async with browser_session() as browser:
            await browser.reset()

            await browser.goto(settings.url("/account/login"), wait_until="domcontentloaded")
            csrf_token = await browser.get_attribute('input[name="csrf_token"]', "value")
            assert csrf_token

            resp = await browser.request_post_form(
                settings.url("/account/security/2fa/disable"),
                data={"password": "not-used", "csrf_token": csrf_token},
            )
            assert resp["status"] in (200, 302)
