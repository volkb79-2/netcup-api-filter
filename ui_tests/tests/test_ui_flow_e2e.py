"""UI Flow E2E (Live)

This file exists because deploy.sh references it as the "UI Flow E2E" suite.

Goal
- Provide a small, live-mode smoke test that exercises the admin UI in a way
  that is safe and broadly applicable.

Notes
- This suite is marked live in deploy.sh and should only run when
  DEPLOYMENT_MODE=live.
- It intentionally avoids making DNS changes directly; the dedicated live DNS
  verification suite covers record lifecycle.
"""

import os

import pytest

from ui_tests import workflows
from ui_tests.config import settings


@pytest.fixture
def skip_unless_live():
    mode = os.environ.get("DEPLOYMENT_MODE", "mock")
    if mode != "live":
        pytest.skip("Test requires DEPLOYMENT_MODE=live")


@pytest.mark.live
class TestUIFlowE2E:
    async def _ensure_admin_or_skip_2fa(self, browser) -> None:
        try:
            await workflows.ensure_admin_dashboard(browser)
        except Exception as exc:
            if "/2fa" in getattr(browser._page, "url", ""):
                pytest.skip(
                    "Admin login requires 2FA, but automation is not configured to retrieve codes. "
                    "Set ADMIN_2FA_SKIP=true for local test runs, or route SMTP to Mailpit and pass MAILPIT_* env vars. "
                    f"url={browser._page.url} error={exc!r}"
                )
            raise

    async def test_admin_can_reach_backends_page(self, browser, skip_unless_live):
        """Smoke test: admin login → backends list page loads."""
        await self._ensure_admin_or_skip_2fa(browser)
        await browser.goto(settings.url("/admin/backends"))
        await browser.wait_for_text("main h1", "Backend Services", timeout=10.0)

    async def test_admin_can_reach_settings_email_section(self, browser, skip_unless_live):
        """Smoke test: settings page loads and includes SMTP fields."""
        await self._ensure_admin_or_skip_2fa(browser)
        await browser.goto(settings.url("/admin/settings"))
        await browser.wait_for_text("main h1", "Settings", timeout=10.0)

        assert await browser.query_selector("#smtp_host") is not None
        assert await browser.query_selector("#smtp_port") is not None
