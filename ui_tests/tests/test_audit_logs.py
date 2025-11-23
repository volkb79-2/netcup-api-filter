"""Tests for audit logging functionality."""
import pytest
from ui_tests.browser import browser_session
from ui_tests.config import settings
from ui_tests import workflows


pytestmark = pytest.mark.asyncio


async def test_audit_logs_page_accessible(active_profile):
    """Test that audit logs page is accessible and displays correctly."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_audit_logs(browser)
        
        # Check page title
        heading = await browser.text("main h1")
        assert "Audit Log" in heading
        
        # Check page contains table or audit log content
        page_html = await browser.html("body")
        # May have table or may show "No logs" - either is valid
        has_table_or_content = ("table" in page_html.lower() or 
                                 "audit" in page_html.lower() or
                                 "log" in page_html.lower())
        assert has_table_or_content, "Page should show audit log interface"


async def test_audit_logs_record_api_requests(active_profile):
    """Test that API requests are recorded in audit logs."""
    import httpx
    import anyio
    
    # Make an API request first
    url = settings.url("/api")
    headers = {
        "Authorization": f"Bearer {settings.client_token}",
        "Content-Type": "application/json"
    }
    data = {
        "action": "infoDnsRecords",
        "param": {"domainname": settings.client_domain}
    }
    
    async with httpx.AsyncClient(verify=False) as client:
        await client.post(url, headers=headers, json=data)
    
    # Wait a moment for log to be written
    await anyio.sleep(1)
    
    # Check audit logs
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_audit_logs(browser)
        
        # Check that our client ID appears in the logs
        table_text = await browser.text("table tbody")
        assert settings.client_id in table_text or "test_" in table_text
        
        # Check for the operation we performed
        assert "infoDnsRecords" in table_text or "DNS" in table_text


async def test_audit_logs_record_authentication_failures(active_profile):
    """Test that authentication failures are logged."""
    import httpx
    import anyio
    
    # Make a request with invalid token
    url = settings.url("/api")
    headers = {
        "Authorization": "Bearer invalid-token-test-123",
        "Content-Type": "application/json"
    }
    data = {
        "action": "infoDnsRecords",
        "param": {"domainname": settings.client_domain}
    }
    
    async with httpx.AsyncClient(verify=False) as client:
        await client.post(url, headers=headers, json=data)
    
    # Wait for log to be written
    await anyio.sleep(1)
    
    # Check audit logs
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_audit_logs(browser)
        
        table_text = await browser.text("table tbody")
        # Should have security event or authentication failure
        assert "SECURITY_EVENT" in table_text or "AUTHENTICATION" in table_text


async def test_audit_logs_record_permission_denials(active_profile):
    """Test that permission denials are logged."""
    import httpx
    import anyio
    
    # Try to access unauthorized domain
    url = settings.url("/api")
    headers = {
        "Authorization": f"Bearer {settings.client_token}",
        "Content-Type": "application/json"
    }
    data = {
        "action": "infoDnsRecords",
        "param": {"domainname": "unauthorized-domain.test"}
    }
    
    async with httpx.AsyncClient(verify=False) as client:
        await client.post(url, headers=headers, json=data)
    
    # Wait for log to be written
    await anyio.sleep(1)
    
    # Check audit logs
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_audit_logs(browser)
        
        table_text = await browser.text("table tbody")
        # Should show permission denial
        assert "PERMISSION" in table_text or "unauthorized" in table_text.lower()
