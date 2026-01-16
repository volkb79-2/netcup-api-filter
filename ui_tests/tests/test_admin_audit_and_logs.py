"""Coverage tests for admin AJAX/JSON endpoints not hit by page navigation.

These tests exist primarily to cover routes that are part of the admin UI
but are called via fetch/AJAX rather than direct links.

Target routes (from coverage audit):
- /admin/audit/data
- /admin/audit/trim
- /admin/system/logs
"""

import pytest

from ui_tests import workflows
from ui_tests.browser import browser_session
from ui_tests.config import settings


pytestmark = pytest.mark.asyncio


class TestAdminAuditAjaxEndpoints:
    async def test_admin_audit_data_returns_html_fragment(self, active_profile):
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)

            # Ensure the main audit page is reachable first.
            nav = await browser.goto(settings.url("/admin/audit"), wait_until="domcontentloaded")
            assert nav.get("status") == 200

            resp = await browser.request_get_text(settings.url("/admin/audit/data"), params={"page": 1})
            assert resp["status"] == 200

            # The endpoint returns <tr> rows (or an empty-state <tr>).
            body = resp["text"]
            assert "<tr" in body.lower(), "Expected HTML <tr> rows in /admin/audit/data response"

    async def test_admin_audit_trim_accepts_csrf_post(self, active_profile):
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)

            # Get a CSRF token from any admin form.
            nav = await browser.goto(settings.url("/admin/settings"), wait_until="domcontentloaded")
            assert nav.get("status") == 200

            csrf_token = await browser.get_attribute('input[name="csrf_token"]', "value")
            assert csrf_token, "Expected CSRF token on /admin/settings"

            # Use a very large 'days' value so the trim operation deletes nothing in practice.
            resp = await browser.request_post_form(
                settings.url("/admin/audit/trim"),
                data={"days": "36500", "csrf_token": csrf_token},
            )
            assert resp["status"] in (200, 302)

            # If redirects are followed, we should land back on the audit page.
            if resp["status"] == 200:
                assert "Audit Logs" in resp["text"]


class TestAdminSystemLogs:
    async def test_admin_system_logs_returns_json(self, active_profile):
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)

            resp = await browser.request_get_json(
                settings.url("/admin/system/logs"),
                params={"page": 1, "per_page": 5},
            )
            assert resp["status"] == 200

            payload = resp["json"]
            assert isinstance(payload, dict)
            for key in ("logs", "total_lines", "page", "per_page", "has_more"):
                assert key in payload
            assert isinstance(payload["logs"], list)
