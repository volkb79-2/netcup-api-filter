"""
UX validation tests for UI elements presence and behavior.

These tests verify that UI features are present and functioning:
- Navigation links in admin panel
- Page headings and structure
- Form elements on key pages
"""

import pytest
from ui_tests import workflows
from ui_tests.browser import browser_session
from ui_tests.config import settings

pytestmark = pytest.mark.asyncio


async def test_accounts_list_has_rows(active_profile):
    """Verify accounts list page renders with at least one account."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await browser.goto(settings.url("/admin/accounts"))
        await browser.verify_status(200)
        
        page_html = await browser.html("body")
        
        # Check for table with accounts
        assert '<table' in page_html, "Accounts table not found"
        # Should have at least demo-user account
        assert 'demo-user' in page_html or 'admin' in page_html, \
            "No accounts found in table"


async def test_account_detail_page_loads(active_profile):
    """Verify account detail page renders correctly."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await browser.goto(settings.url("/admin/accounts"))
        
        # Get the first account link
        page_html = await browser.html("body")
        
        # Look for a link to an account detail page
        import re
        match = re.search(r'href="(/admin/accounts/\d+)"', page_html)
        if match:
            detail_url = match.group(1)
            await browser.goto(settings.url(detail_url))
            await browser.verify_status(200)
            
            # Should show account details
            heading = await browser.text("main h1")
            assert heading, "Account detail page should have a heading"


async def test_dashboard_has_stats_cards(active_profile):
    """Verify dashboard shows statistics cards."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        
        page_html = await browser.html("body")
        
        # Dashboard should show stats cards
        assert 'card' in page_html, "No cards found on dashboard"
        # Should mention accounts or some statistics
        assert 'Account' in page_html or 'Realm' in page_html or 'Token' in page_html, \
            "Dashboard should show account-related statistics"


async def test_audit_logs_page_structure(active_profile):
    """Verify audit logs page has proper structure."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await browser.goto(settings.url("/admin/audit"))
        await browser.verify_status(200)
        
        heading = await browser.text("main h1")
        assert "Audit" in heading, f"Expected 'Audit' in heading, got '{heading}'"


async def test_system_info_page_loads(active_profile):
    """Verify system info page loads correctly."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await browser.goto(settings.url("/admin/system"))
        await browser.verify_status(200)
        
        heading = await browser.text("main h1")
        assert "System" in heading, f"Expected 'System' in heading, got '{heading}'"
        
        # Should show some system information
        page_html = await browser.html("body")
        assert 'Python' in page_html or 'Database' in page_html, \
            "System info should display system details"


async def test_config_pages_load(active_profile):
    """Verify configuration pages load correctly."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        
        # Test Netcup API config
        await browser.goto(settings.url("/admin/config/netcup"))
        await browser.verify_status(200)
        heading = await browser.text("main h1")
        assert "Netcup" in heading, f"Expected 'Netcup' in heading, got '{heading}'"
        
        # Test Email config
        await browser.goto(settings.url("/admin/config/email"))
        await browser.verify_status(200)
        heading = await browser.text("main h1")
        assert "Email" in heading, f"Expected 'Email' in heading, got '{heading}'"


async def test_navigation_links_work(active_profile):
    """Verify all navigation links are present and working."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        
        page_html = await browser.html("nav")
        
        # Check for key navigation links
        expected_links = [
            '/admin/',           # Dashboard
            '/admin/accounts',   # Accounts
            '/admin/audit',      # Audit Logs
            '/admin/config/',    # Config (netcup or email)
            '/admin/system',     # System Info
        ]
        
        for link in expected_links:
            assert link in page_html, f"Navigation link {link} not found"


async def test_create_account_form_has_fields(active_profile):
    """Verify account creation form has required fields."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await browser.goto(settings.url("/admin/accounts/new"))
        await browser.verify_status(200)
        
        page_html = await browser.html("form")
        
        # Check for required form fields
        assert 'id="username"' in page_html or 'name="username"' in page_html, \
            "Username field not found"
        assert 'id="email"' in page_html or 'name="email"' in page_html, \
            "Email field not found"


async def test_theme_demo_page_loads(active_profile):
    """Verify theme demo page loads correctly."""
    async with browser_session() as browser:
        await browser.goto(settings.url("/theme-demo"))
        await browser.verify_status(200)
        
        # Check for theme demo elements (the page shows demo content with "Clients" h1)
        page_html = await browser.html("body")
        # Theme demo has theme selector and demo content
        assert "theme-demo" in page_html.lower() or "Theme Demo" in page_html or "Clients" in page_html, \
            "Expected theme demo page content"


async def test_no_500_errors_on_admin_pages(active_profile):
    """Verify no 500 errors on any admin pages."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        
        pages_to_test = [
            "/admin/",
            "/admin/accounts",
            "/admin/accounts/pending",
            "/admin/audit",
            "/admin/config/netcup",
            "/admin/config/email",
            "/admin/system",
            "/admin/change-password",
        ]
        
        for page in pages_to_test:
            await browser.goto(settings.url(page))
            body = await browser.text("body")
            assert "Internal Server Error" not in body, f"500 error on {page}"
            assert "500" not in await browser.text("title"), f"500 error on {page}"
