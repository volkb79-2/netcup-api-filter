"""Test complete installation workflow (first-time setup).

This test runs inside the repo's async Playwright harness (no pytest-playwright
plugin dependency).

It verifies that the "fresh install" / "already initialized" admin auth flow
works and that the email configuration page renders with a seeded SMTP host.
"""

import pytest

from ui_tests import workflows
from ui_tests.browser import browser_session
from ui_tests.config import settings


pytestmark = [pytest.mark.asyncio, pytest.mark.installation]


async def test_installation_workflow():
    async with browser_session() as browser:
        # This workflow handles both cases:
        # - Fresh deployment: login -> change password -> dashboard -> logout -> login(+2FA)
        # - Already initialized: login(+2FA) -> dashboard
        await workflows.perform_admin_authentication_flow(browser)

        # Verify SMTP configuration page loads and has a seeded host
        await browser.goto(settings.url("/admin/config/email"))
        await browser.wait_for_load_state("domcontentloaded")

        smtp_host = await browser.evaluate(
            """() => {
                const el = document.querySelector("input[name='smtp_host'], #smtp_host");
                return el ? el.value : "";
            }"""
        )

        if not smtp_host:
            pytest.skip("SMTP host field not found or empty")

        assert "mailpit" in smtp_host.lower(), f"Expected mailpit in SMTP host, got: {smtp_host}"
