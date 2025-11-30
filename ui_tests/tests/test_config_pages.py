import pytest
from playwright.async_api import Page, expect
from ui_tests.config import settings

@pytest.mark.asyncio
async def test_netcup_config_page(admin_page):
    """Test that the Netcup Config page loads and displays the form."""
    page = admin_page  # Already awaited by fixture
    base_url = settings.base_url
    
    await page.goto(f"{base_url}/admin/netcup_config/")
    
    # Check title
    await expect(page.locator("h1")).to_contain_text("Netcup API Configuration")
    
    # Check form fields
    await expect(page.locator("input[name='customer_id']")).to_be_visible()
    await expect(page.locator("input[name='api_key']")).to_be_visible()
    await expect(page.locator("input[name='api_password']")).to_be_visible()
    
    # Check submit button (renders as button element)
    await expect(page.locator("button[type='submit']")).to_be_visible()

@pytest.mark.asyncio
async def test_email_config_page(admin_page):
    """Test that the Email Config page loads and displays the form with two buttons."""
    page = admin_page  # Already awaited by fixture
    base_url = settings.base_url
    
    await page.goto(f"{base_url}/admin/email_config/")
    
    # Check title
    await expect(page.locator("h1")).to_contain_text("Email Configuration")
    
    # Check form fields
    await expect(page.locator("input[name='smtp_server']")).to_be_visible()
    await expect(page.locator("input[name='test_email']")).to_be_visible()
    
    # Check buttons (Save and Test)
    await expect(page.locator("button[value='save']")).to_be_visible()
    await expect(page.locator("button[value='test']")).to_be_visible()
