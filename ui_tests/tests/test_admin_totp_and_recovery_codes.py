"""Admin security UX coverage: TOTP setup page and recovery code lifecycle.

Target routes (from coverage audit):
- /admin/security/totp
- /admin/security/recovery-codes

These tests avoid relying on optional deps (pyotp/qrcode) being installed.
"""

import pytest

from ui_tests import workflows
from ui_tests.browser import browser_session
from ui_tests.config import settings


pytestmark = pytest.mark.asyncio


class TestAdminTotpPage:
    async def test_admin_totp_setup_page_loads(self, active_profile):
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)

            nav = await browser.goto(settings.url("/admin/security/totp"), wait_until="domcontentloaded")
            assert nav.get("status") == 200

            body = await browser.html("body")
            assert "Authenticator" in body


class TestAdminRecoveryCodes:
    async def test_admin_recovery_codes_generate_and_confirm(self, active_profile):
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)

            nav = await browser.goto(settings.url("/admin/security/recovery-codes"), wait_until="domcontentloaded")
            assert nav.get("status") == 200

            # Generate new codes.
            await browser.submit('form:has(input[name="action"][value="generate"])')

            # Codes should be displayed once generated.
            codes = await browser.query_selector_all(".recovery-codes-box code")
            assert codes, "Expected recovery codes to be displayed after generation"

            # Confirm we saved them and return to dashboard.
            await browser.click("#confirm_saved")
            await browser.submit('form:has(input[name="action"][value="confirm"])')

            h1 = await browser.text("h1")
            assert "Dashboard" in h1
