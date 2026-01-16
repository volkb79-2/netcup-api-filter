"""Coverage tests for public/misc routes flagged by the route audit.

Target routes:
- /
- /theme-demo2
- /theme-demo2/<path:filename>
"""

import pytest

from ui_tests.browser import browser_session
from ui_tests.config import settings


pytestmark = pytest.mark.asyncio


class TestPublicMiscRoutes:
    async def test_root_redirects_to_account_login(self, active_profile):
        async with browser_session() as browser:
            await browser.reset()
            await browser._page.context.clear_cookies()

            nav = await browser.goto(settings.url("/"), wait_until="domcontentloaded")
            assert nav.get("status") == 200

            current_path = await browser.evaluate("() => window.location.pathname")
            assert current_path.startswith("/account/login")

    async def test_theme_demo2_page_loads(self, active_profile):
        async with browser_session() as browser:
            await browser.reset()
            await browser._page.context.clear_cookies()

            nav = await browser.goto(settings.url("/theme-demo2"), wait_until="domcontentloaded")
            assert nav.get("status") == 200

            body = await browser.text("body")
            assert body

    async def test_theme_demo2_static_asset_serves(self, active_profile):
        async with browser_session() as browser:
            await browser.reset()
            await browser._page.context.clear_cookies()

            # This file exists under src/netcup_api_filter/demos/theme-demo2/.
            resp = await browser.request_get_bytes(settings.url("/theme-demo2/bootstrap.min.css"))
            assert resp["status"] == 200
            assert resp["bytes"].startswith(b"/*") or resp["bytes"].startswith(b"@") or len(resp["bytes"]) > 100
