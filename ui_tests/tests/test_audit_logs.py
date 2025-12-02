"""Tests for audit log functionality."""
import pytest
from ui_tests.browser import browser_session
from ui_tests.config import settings
from ui_tests import workflows


pytestmark = pytest.mark.asyncio


async def test_audit_logs_page_accessible(active_profile):
    """Test that the audit logs page is accessible."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_audit_logs(browser)
        
        # Verify we're on the audit logs page
        heading = await browser.text("main h1")
        assert "Audit" in heading or "Log" in heading


async def test_audit_logs_shows_login_events(active_profile):
    """Test that login events appear in audit logs."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_audit_logs(browser)
        
        # Check the table has login events (from our session)
        table_text = await browser.text("table tbody")
        assert "Login" in table_text or "login" in table_text


async def test_audit_logs_record_api_requests(active_profile):
    """Test that API requests are logged in audit logs."""
    import httpx
    import anyio
    
    # Make a valid API request (new REST API format)
    url = settings.url(f"/api/dns/{settings.client_domain}/records")
    headers = {
        "Authorization": f"Bearer {settings.client_token}",
    }
    
    async with httpx.AsyncClient(verify=False) as client:
        await client.get(url, headers=headers)
    
    # Wait a moment for log to be written
    await anyio.sleep(1)
    
    # Check audit logs
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_audit_logs(browser)
        
        # Check that API activity appears - could be various action types
        table_text = await browser.text("table tbody")
        # The API request should be logged - check for any evidence
        api_logged = any(term in table_text for term in [
            "Api", "API", "dns", "DNS", "auth", "Auth", "read", "Read"
        ])
        assert api_logged, f"Expected API activity in logs: {table_text[:500]}"


async def test_audit_logs_has_filter_controls(active_profile):
    """Test that audit logs page has filter controls."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_audit_logs(browser)
        
        # Check for filter elements
        page_html = await browser.html("body")
        assert 'name="range"' in page_html or 'name="action"' in page_html
        assert 'name="search"' in page_html or 'Search' in page_html


async def test_audit_logs_has_stats_cards(active_profile):
    """Test that audit logs page shows statistics cards."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_audit_logs(browser)
        
        # Check for stats cards
        page_html = await browser.html("body")
        assert "Today" in page_html or "today" in page_html
        assert "Login" in page_html or "login" in page_html
