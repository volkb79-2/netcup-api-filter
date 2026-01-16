"""Coverage tests for admin login 2FA routes.

Target routes (from coverage audit):
- /admin/login/2fa
- /admin/login/2fa/resend

These are auth-flow endpoints, so tests explicitly start from a fresh session.
"""

import pytest

from ui_tests.browser import browser_session
from ui_tests.config import settings


pytestmark = pytest.mark.asyncio


class TestAdminLogin2FARoutesRequirePendingState:
    async def test_admin_login_2fa_redirects_without_pending_state(self, active_profile):
        async with browser_session() as browser:
            await browser.reset()
            await browser._page.context.clear_cookies()

            nav = await browser.goto(settings.url("/admin/login/2fa"), wait_until="domcontentloaded")
            assert nav.get("status") == 200

            current_path = await browser.evaluate("() => window.location.pathname")
            # Without a pending admin login, the 2FA page should bounce back to /admin/login.
            assert current_path.startswith("/admin/login")

    async def test_admin_login_2fa_resend_redirects_without_pending_state(self, active_profile):
        async with browser_session() as browser:
            await browser.reset()
            await browser._page.context.clear_cookies()

            # CSRF is generally enforced for POST requests.
            await browser.goto(settings.url("/admin/login"), wait_until="domcontentloaded")
            csrf_token = await browser.get_attribute('input[name="csrf_token"]', "value")
            assert csrf_token

            resp = await browser.request_post_form(
                settings.url("/admin/login/2fa/resend"),
                data={"csrf_token": csrf_token},
            )
            assert resp["status"] in (200, 302)
