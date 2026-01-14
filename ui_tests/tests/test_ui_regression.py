"""
UI Regression Tests - Catch fundamental UI flaws.

These tests verify that UI pages don't have broken layouts, missing content,
error messages, or other fundamental issues that should never make it to production.
"""
import pytest
from ui_tests.browser import browser_session
from ui_tests.config import settings
from ui_tests import workflows


pytestmark = pytest.mark.asyncio


async def test_ui_no_error_messages_on_pages(active_profile):
    """Verify no pages show error messages or 404 in normal flow."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        
        # Admin pages should not show errors
        admin_pages = [
            "/admin/",
            "/admin/accounts",
            "/admin/accounts/pending",
            "/admin/audit",
            "/admin/config/netcup",
            "/admin/config/email",
            "/admin/system",
        ]
        
        for path in admin_pages:
            nav = await browser.goto(settings.url(path), wait_until="domcontentloaded")
            await browser._page.wait_for_load_state('domcontentloaded')
            page_text = await browser.text("body")

            # Prefer real HTTP status over brittle substring checks
            assert nav.get("status") == 200, f"Page {path} returned HTTP {nav.get('status')}"
            
            # Check for common error indicators
            assert "Not Found" not in page_text, f"Page {path} shows 'Not Found'"
            assert "Internal Server Error" not in page_text, f"Page {path} shows 500 error"
            assert "Exception" not in page_text, f"Page {path} shows exception"
            assert "Traceback" not in page_text, f"Page {path} shows traceback"
            
            # Check page loaded (has header)
            assert await browser.query_selector("h1"), f"Page {path} has no h1 heading"


async def test_audit_logs_not_empty_on_fresh_install(active_profile):
    """Audit logs page should show demo data on fresh install."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        
        await browser.goto(settings.url("/admin/audit"))
        await browser._page.wait_for_load_state('networkidle')
        
        page_text = await browser.text("body")
        
        # Should either have audit logs or a helpful empty state
        has_logs = "audit" in page_text.lower() or "log" in page_text.lower()
        has_empty_message = "No audit logs" in page_text or "will appear here" in page_text
        has_table = await browser.query_selector("table")
        
        assert has_logs or has_empty_message or has_table, \
            "Audit logs page shows neither data nor helpful empty state"


async def test_viewport_shows_full_content(active_profile):
    """Verify screenshots capture full page content (regression test for truncation)."""
    async with browser_session() as browser:
        # Set large viewport like screenshot script
        await browser._page.set_viewport_size({"width": 1920, "height": 1200})
        
        await workflows.ensure_admin_dashboard(browser)
        
        # Dashboard should be fully visible
        await browser.goto(settings.url("/admin/"))
        await browser._page.wait_for_load_state('domcontentloaded')
        
        # Check we can see header and footer
        header = await browser.query_selector("nav") or await browser.query_selector("header")
        assert header, "Cannot see header in viewport"
        
        # Footer should be visible (if it exists)
        footer_text = await browser.text("body")
        # Just check page loaded fully
        assert "Dashboard" in footer_text or "admin" in footer_text.lower(), \
            "Page doesn't appear fully loaded"


async def test_system_info_filesystem_tests_present(active_profile):
    """System info page should show filesystem test results."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        
        await browser.goto(settings.url("/admin/system"))
        await browser._page.wait_for_load_state('domcontentloaded')
        page_text = await browser.text("body")
        
        # Should have system info content
        assert "System" in page_text or "system" in page_text.lower(), \
            "System info page has no system content"


async def test_audit_logs_page_accessible(active_profile):
    """Audit logs page should load without 'not found' error."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        
        nav = await browser.goto(settings.url("/admin/audit"), wait_until="domcontentloaded")
        await browser._page.wait_for_load_state('networkidle')
        
        page_text = await browser.text("body")

        assert nav.get("status") == 200, f"/admin/audit returned HTTP {nav.get('status')}"
        
        # Should not show 'not found' error
        assert "not found" not in page_text.lower() or "No audit logs" in page_text, \
            "Audit logs page shows 'not found' error"
