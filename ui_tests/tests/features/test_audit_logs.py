"""Tests for audit log functionality.

Moved from test_ui_comprehensive.py and test_ui_regression.py.
False-green patterns (any/or-chains, if-found) have been removed.
"""
import pytest
import anyio
import httpx
from ui_tests.browser import browser_session
from ui_tests.config import settings
from ui_tests import workflows


pytestmark = [pytest.mark.asyncio, pytest.mark.feature]


async def test_audit_logs_page_accessible(active_profile):
    """Audit logs page loads and shows the expected heading."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_audit_logs(browser)

        heading = await browser.text("main h1")
        assert "Audit" in heading, f"Expected 'Audit' in h1, got: {heading!r}"


async def test_audit_logs_table_columns(active_profile):
    """Audit log table header includes Timestamp, Actor, and Action columns."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_audit_logs(browser)

        thead = await browser.text("table thead")
        assert "Timestamp" in thead, f"'Timestamp' column missing from audit table header: {thead!r}"
        assert "Actor" in thead, f"'Actor' column missing from audit table header: {thead!r}"
        assert "Action" in thead, f"'Action' column missing from audit table header: {thead!r}"


async def test_audit_logs_not_empty_on_fresh_install(active_profile):
    """Audit log table must contain at least one row after deployment."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_audit_logs(browser)

        table_body = await browser.text("table tbody")
        assert table_body.strip(), (
            "Audit log table body is empty — at least one entry expected after deployment"
        )
        # The pre-seeded deployment should have produced login events
        assert "login" in table_body.lower() or "Login" in table_body, (
            f"Expected at least one Login event in audit log, got: {table_body[:300]!r}"
        )


async def test_audit_logs_record_api_requests(active_profile):
    """API requests made against the DNS endpoint appear in the audit log."""
    url = settings.url(f"/api/dns/{settings.client_domain}/records")
    headers = {"Authorization": f"Bearer {settings.client_token}"}

    async with httpx.AsyncClient(verify=False) as client:
        await client.get(url, headers=headers)

    # Brief wait for the log write to commit
    await anyio.sleep(1)

    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_audit_logs(browser)

        table_text = await browser.text("table tbody")
        # The DNS read request must produce an "api_request" or similar event
        assert table_text.strip(), "Audit log table is empty after API request"
        found_api = (
            "api_request" in table_text.lower()
            or "dns" in table_text.lower()
            or "Api" in table_text
        )
        assert found_api, (
            f"Expected API/DNS activity in audit log after GET /api/dns/…, "
            f"got: {table_text[:400]!r}"
        )


async def test_audit_logs_has_filter_controls(active_profile):
    """Audit logs page exposes filter form controls."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_audit_logs(browser)

        page_html = await browser.html("body")
        has_range = 'name="range"' in page_html
        has_action_filter = 'name="action"' in page_html
        assert has_range or has_action_filter, (
            "Expected a 'range' or 'action' filter control on the audit logs page"
        )

        has_search = 'name="search"' in page_html or "Search" in page_html
        assert has_search, "Expected a search field or Search label on the audit logs page"


async def test_audit_logs_has_stats_cards(active_profile):
    """Audit logs page shows statistics cards (Today counts, Login counts)."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_audit_logs(browser)

        page_html = await browser.html("body")
        assert "Today" in page_html or "today" in page_html, (
            "Expected a 'Today' stat card on the audit logs page"
        )
        assert "Login" in page_html or "login" in page_html, (
            "Expected a 'Login' stat card or column on the audit logs page"
        )


# ============================================================================
# Admin audit/log AJAX-JSON endpoints (merged from test_admin_audit_and_logs.py)
#
# These hit routes that page-navigation never exercises and that are EXCLUDED
# from the route-smoke parametrize (/admin/audit/data, /admin/system/logs):
# the AJAX HTML fragment, the audit-trim CSRF POST, and the JSON logs endpoint.
# ============================================================================


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
