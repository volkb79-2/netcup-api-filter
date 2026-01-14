"""Tests for admin configuration pages."""
import pytest
from ui_tests.browser import browser_session
from ui_tests import workflows
from ui_tests.config import settings


pytestmark = pytest.mark.asyncio


async def test_netcup_config_page(active_profile):
    """Test that the Netcup Config page loads and displays the form."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_netcup_config(browser)
        
        # Check page heading
        heading = await browser.text("main h1")
        assert "Netcup" in heading
        
        # Check form fields exist
        page_html = await browser.html("body")
        assert "customer_id" in page_html
        assert "api_key" in page_html
        assert "api_password" in page_html
        assert "api_url" in page_html


async def test_email_config_page(active_profile):
    """Test that the Email Config page loads and displays the form."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_email_settings(browser)
        
        # Check page heading
        heading = await browser.text("main h1")
        assert "Email" in heading
        
        # Check form fields exist
        page_html = await browser.html("body")
        assert "smtp_host" in page_html
        assert "from_email" in page_html
        assert "smtp_port" in page_html


async def test_system_info_page(active_profile):
    """Test that the System Info page loads with status information."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_system_info(browser)
        
        # Check page heading  
        heading = await browser.text("main h1")
        assert "System" in heading
        
        # Check for system info sections
        page_html = await browser.html("body")
        assert "Python" in page_html or "Flask" in page_html
