"""Recovery codes tests.

These are account-portal UI coverage tests for:
- /account/settings/recovery-codes (GET)
- /account/settings/recovery-codes/generate (POST)
- /account/settings/recovery-codes/display (GET)

Design goal: validate the end-user workflow without forcing fresh login/2FA
unless required (session reuse is allowed).
"""

import os
import re

import pytest

from ui_tests import workflows
from ui_tests.browser import browser_session
from ui_tests.config import settings
from ui_tests.env_defaults import get_env_default


pytestmark = pytest.mark.asyncio


class TestRecoveryCodesAccountUI:
    async def test_generate_recovery_codes_wrong_password_shows_error(self, active_profile):
        """Wrong password should not generate codes and should show an error."""
        async with browser_session() as browser:
            await workflows.ensure_user_dashboard(browser)

            await browser.goto(settings.url("/account/settings/recovery-codes"))
            await browser.wait_for_text("h2.mb-0", "Recovery Codes", timeout=10.0)

            await browser.fill("#password", "not-the-password")
            await browser.click("#generate-codes-form button[type='submit']")

            # Redirect back to view page with flash.
            await browser.wait_for_text(".alert", "Invalid password", timeout=10.0)
            assert "/account/settings/recovery-codes" in browser._page.url

    async def test_generate_and_display_recovery_codes_one_time(self, active_profile):
        """Generate shows codes once; subsequent display redirects with warning."""
        # Keep these as literals so the route coverage audit can match them.
        generate_path = "/account/settings/recovery-codes/generate"
        display_path = "/account/settings/recovery-codes/display"

        async with browser_session() as browser:
            await workflows.ensure_user_dashboard(browser)

            # Navigate to recovery codes page.
            await browser.goto(settings.url("/account/settings/recovery-codes"))
            await browser.wait_for_text("h2.mb-0", "Recovery Codes", timeout=10.0)

            # Generate new codes (invalidates old ones).
            # The form posts to generate_path.
            form_action = await browser.get_attribute("#generate-codes-form", "action")
            assert generate_path in (form_action or "")

            demo_password = os.environ.get("DEFAULT_TEST_ACCOUNT_PASSWORD") or get_env_default(
                "DEFAULT_TEST_ACCOUNT_PASSWORD"
            )
            if not demo_password:
                # ensure_user_dashboard() already skips if defaults are missing
                raise AssertionError("DEFAULT_TEST_ACCOUNT_PASSWORD missing; ensure_user_dashboard should have skipped")

            await browser.fill("#password", demo_password)
            await browser.click("#generate-codes-form button[type='submit']")

            # The server redirects to display page for one-time view.
            await browser.wait_for_text("h2.mb-2", "Save Your Recovery Codes", timeout=10.0)
            assert display_path in browser._page.url

            # Validate we got 10 codes in XXXX-XXXX format.
            grid_text = await browser.text("#recovery-codes-grid")
            codes = re.findall(r"\b[A-Z0-9]{4}-[A-Z0-9]{4}\b", grid_text or "")
            expected_count_str = os.environ.get("RECOVERY_CODE_COUNT") or get_env_default("RECOVERY_CODE_COUNT")
            expected_count = int(expected_count_str or "3")
            assert len(set(codes)) == expected_count

            # Display page must be one-time: revisiting should redirect back.
            await browser.goto(settings.url(display_path))
            await browser.wait_for_text(".alert", "No recovery codes to display", timeout=10.0)
            assert "/account/settings/recovery-codes" in browser._page.url
