"""GeoIP admin + API coverage tests.

Covers:
- GET  /admin/config/geoip (redirects to /admin/settings)
- POST /admin/config/geoip (via the /admin/settings form)
- GET  /admin/api/geoip/<ip_address>
- GET  /api/geoip/<ip>

Design goal: validate basic behavior without requiring real MaxMind credentials.
"""

import json
import os

import pytest

from ui_tests import workflows
from ui_tests.browser import browser_session
from ui_tests.config import settings



pytestmark = pytest.mark.asyncio


class TestGeoIPAdminAndAPI:
    async def test_admin_geoip_config_redirect_and_save(self, active_profile):
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)

            # GET route should exist and redirect to the unified settings page.
            await browser.goto(settings.url("/admin/config/geoip"), wait_until="domcontentloaded")
            assert "/admin/settings" in browser._page.url

            # Save an empty GeoIP config (feature is optional).
            form_action = await browser.get_attribute("form[action*='/admin/config/geoip']", "action")
            assert "/admin/config/geoip" in (form_action or "")

            await browser.fill("#geoip_account_id", "")
            await browser.fill("#geoip_license_key", "")
            await browser.fill("#geoip_api_url", "")
            await browser.click("form[action*='/admin/config/geoip'] button[type='submit']")

            await browser.wait_for_text(".alert", "GeoIP configuration saved", timeout=10.0)
            assert "/admin/settings" in browser._page.url

            # With an empty DB setting, the UI should fall back to env defaults.
            # Runtime config should come from environment variables; in the
            # production-parity deployment, .env.defaults is not present.
            expected_default_api_url = (os.environ.get("MAXMIND_API_URL") or "").strip()
            rendered_api_url = await browser._page.input_value("#geoip_api_url")
            assert (rendered_api_url or "").strip() == expected_default_api_url

    async def test_admin_geoip_api_returns_not_configured_error(self, active_profile):
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)

            await browser.goto(settings.url("/admin/api/geoip/8.8.8.8"), wait_until="domcontentloaded")
            body = (await browser.text("body")) or ""
            payload = json.loads(body)

            assert payload["success"] is False
            assert "not configured" in payload.get("error", "").lower()
            assert payload.get("ip") == "8.8.8.8"

    async def test_public_geoip_api_returns_not_configured_error(self, active_profile):
        async with browser_session() as browser:
            await browser.goto(settings.url("/api/geoip/8.8.8.8"), wait_until="domcontentloaded")
            body = (await browser.text("body")) or ""
            payload = json.loads(body)

            assert payload.get("ip") == "8.8.8.8"
            assert "not configured" in payload.get("error", "").lower()
