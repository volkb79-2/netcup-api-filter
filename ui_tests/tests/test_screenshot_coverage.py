"""
Comprehensive Screenshot Coverage Tests

This module captures screenshots for ALL routes with ALL states:
- Happy path (success states)
- Negative testing (invalid inputs, unauthorized access)
- Boundary testing (edge cases, limits)
- Error states (4xx, 5xx)

Each test captures webp screenshots named according to:
  {route}_{state}_{variant}.webp

The screenshots provide visual documentation and regression testing.

Requirements:
- SCREENSHOT_DIR environment variable
- DEPLOYED_ADMIN_PASSWORD for admin routes
- Pre-seeded demo data (via --seed-demo)

Run with: pytest ui_tests/tests/test_screenshot_coverage.py -v
"""
import pytest
import asyncio
import os
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from ui_tests.config import settings
from browser import browser_session, Browser
import workflows


pytestmark = pytest.mark.asyncio


# =============================================================================
# Configuration
# =============================================================================

# Screenshot format is controlled by SCREENSHOT_FORMAT env var (default: webp)
# Quality is controlled by SCREENSHOT_QUALITY env var (default: 85)
SCREENSHOT_FORMAT = os.environ.get('SCREENSHOT_FORMAT', 'webp')  # For report generation


async def capture_screenshot(browser: Browser, name: str, full_page: bool = True) -> str:
    """Capture screenshot using browser.screenshot (handles webp conversion).
    
    Args:
        browser: Browser instance
        name: Screenshot name (without extension)
        full_page: Whether to capture full page
        
    Returns:
        Path to saved screenshot
    """
    # Use browser.screenshot which handles PNG→WebP conversion via PIL
    return await browser.screenshot(name)


async def wait_for_page_load(browser: Browser, timeout: float = 1.0):
    """Wait for page to fully load."""
    await asyncio.sleep(timeout)


# =============================================================================
# Admin Portal - Public Routes
# =============================================================================

class TestAdminPublicScreenshots:
    """Screenshots for admin portal public/unauthenticated routes."""

    async def test_admin_login_default(self, active_profile):
        """Screenshot: Admin login page - default state."""
        async with browser_session() as browser:
            await browser.goto(settings.url("/admin/login"))
            await wait_for_page_load(browser)
            
            await capture_screenshot(browser, "admin_login_default")
    
    async def test_admin_login_error_invalid_credentials(self, active_profile):
        """Screenshot: Admin login - invalid credentials error."""
        async with browser_session() as browser:
            await browser.goto(settings.url("/admin/login"))
            await wait_for_page_load(browser, 0.5)
            
            # Submit with wrong password
            await browser.fill("#username", "admin")
            await browser.fill("#password", "wrongpassword123")
            await browser.click("button[type='submit']")
            await wait_for_page_load(browser)
            
            await capture_screenshot(browser, "admin_login_error_invalid")

    async def test_admin_login_error_empty_fields(self, active_profile):
        """Screenshot: Admin login - empty fields validation."""
        async with browser_session() as browser:
            await browser.goto(settings.url("/admin/login"))
            await wait_for_page_load(browser, 0.5)
            
            # Try to submit empty form
            await browser.click("button[type='submit']")
            await wait_for_page_load(browser, 0.3)
            
            await capture_screenshot(browser, "admin_login_error_empty")


# =============================================================================
# Admin Portal - Authenticated Routes
# =============================================================================

class TestAdminDashboardScreenshots:
    """Screenshots for admin dashboard with various states."""

    async def test_dashboard_default(self, active_profile):
        """Screenshot: Admin dashboard - default state with stats."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await wait_for_page_load(browser)
            
            await capture_screenshot(browser, "admin_dashboard_default")
    
    async def test_dashboard_with_pending_alerts(self, active_profile):
        """Screenshot: Dashboard showing pending approvals alert."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await wait_for_page_load(browser)
            
            # Check if pending alert exists
            body = await browser.text("body")
            if "Pending" in body:
                await capture_screenshot(browser, "admin_dashboard_pending_alert")


class TestAdminAccountsScreenshots:
    """Screenshots for admin account management."""

    async def test_accounts_list_populated(self, active_profile):
        """Screenshot: Accounts list with multiple accounts."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/accounts"))
            await wait_for_page_load(browser)
            
            await capture_screenshot(browser, "admin_accounts_list")

    async def test_accounts_list_with_bulk_selection(self, active_profile):
        """Screenshot: Accounts list with bulk selection active."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/accounts"))
            await wait_for_page_load(browser, 0.5)
            
            # Select first checkbox if exists
            checkbox = await browser.query_selector("table tbody input[type='checkbox']")
            if checkbox:
                await checkbox.click()
                await wait_for_page_load(browser, 0.3)
                await capture_screenshot(browser, "admin_accounts_bulk_selected")

    async def test_account_detail_active(self, active_profile):
        """Screenshot: Account detail page - active account."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/accounts"))
            await wait_for_page_load(browser, 0.5)
            
            # Find first account link
            html = await browser.html("body")
            import re
            match = re.search(r'/admin/accounts/(\d+)', html)
            if match:
                account_id = match.group(1)
                await browser.goto(settings.url(f"/admin/accounts/{account_id}"))
                await wait_for_page_load(browser)
                
                await capture_screenshot(browser, "admin_account_detail")

    async def test_account_create_form(self, active_profile):
        """Screenshot: Account creation form - empty."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/accounts/new"))
            await wait_for_page_load(browser)
            
            await capture_screenshot(browser, "admin_account_create")

    async def test_account_create_validation_error(self, active_profile):
        """Screenshot: Account creation - validation errors."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/accounts/new"))
            await wait_for_page_load(browser, 0.5)
            
            # Fill invalid data - with JS validation, button stays disabled
            await browser.fill("#username", "x")  # Too short
            await browser.fill("#email", "invalid-email")
            
            # Trigger field blur to show validation feedback
            await browser.click("body")  # Blur the field to trigger validation
            await wait_for_page_load(browser, 0.3)
            
            # Screenshot shows disabled submit button and validation state
            await capture_screenshot(browser, "admin_account_create_validation")

    async def test_accounts_pending_list(self, active_profile):
        """Screenshot: Pending accounts awaiting approval (with sample pending accounts)."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            # Navigate to account creation page and create a pending account
            await browser.goto(settings.url("/admin/accounts/new"))
            await wait_for_page_load(browser)
            
            # Fill in account details
            await browser.fill("#username", "pending_user1")
            await browser.fill("#email", "pending1@example.test")
            
            # Uncheck "skip approval" to make it pending
            skip_approval = await browser._page.query_selector("#skip_approval")
            if skip_approval:
                is_checked = await skip_approval.is_checked()
                if is_checked:
                    await browser.click("#skip_approval")
            
            # Don't include realm - just create a basic pending account
            # The form requires: username + email (when include_realm is unchecked)
            
            # Wait for JS validation to enable submit button
            await asyncio.sleep(0.5)
            
            # Submit the form - use force click if button is disabled
            submit_btn = await browser._page.query_selector("button[type='submit']")
            if submit_btn:
                is_disabled = await submit_btn.get_attribute("disabled")
                if is_disabled:
                    # Skip this test if form validation prevents submission
                    pytest.skip("Account creation form validation prevents submission")
                await submit_btn.click()
            else:
                await browser.click("button[type='submit']")
            await wait_for_page_load(browser)
            
            # Now navigate to pending accounts page
            await browser.goto(settings.url("/admin/accounts/pending"))
            await wait_for_page_load(browser)
            
            await capture_screenshot(browser, "admin_accounts_pending")


class TestAdminRealmsScreenshots:
    """Screenshots for admin realm management."""

    async def test_realms_list(self, active_profile):
        """Screenshot: Realms list."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/realms"))
            await wait_for_page_load(browser)
            
            await capture_screenshot(browser, "admin_realms_list")

    async def test_realms_pending(self, active_profile):
        """Screenshot: Pending realms awaiting approval."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/realms/pending"))
            await wait_for_page_load(browser)
            
            await capture_screenshot(browser, "admin_realms_pending")

    async def test_realm_detail(self, active_profile):
        """Screenshot: Realm detail page."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/realms"))
            await wait_for_page_load(browser, 0.5)
            
            html = await browser.html("body")
            import re
            match = re.search(r'/admin/realms/(\d+)', html)
            if match:
                realm_id = match.group(1)
                await browser.goto(settings.url(f"/admin/realms/{realm_id}"))
                await wait_for_page_load(browser)
                
                await capture_screenshot(browser, "admin_realm_detail")


class TestAdminTokensScreenshots:
    """Screenshots for admin token management."""

    async def test_token_detail(self, active_profile):
        """Screenshot: Token detail page."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            # Navigate through realms to find a token
            await browser.goto(settings.url("/admin/realms"))
            await wait_for_page_load(browser, 0.5)
            
            html = await browser.html("body")
            import re
            match = re.search(r'/admin/tokens/(\d+)', html)
            if match:
                token_id = match.group(1)
                await browser.goto(settings.url(f"/admin/tokens/{token_id}"))
                await wait_for_page_load(browser)
                
                await capture_screenshot(browser, "admin_token_detail")


class TestAdminAuditScreenshots:
    """Screenshots for admin audit logs."""

    async def test_audit_default(self, active_profile):
        """Screenshot: Audit log - default view."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/audit"))
            await wait_for_page_load(browser)
            
            await capture_screenshot(browser, "admin_audit_default")

    async def test_audit_filtered_by_action(self, active_profile):
        """Screenshot: Audit log - filtered by action type."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/audit"))
            await wait_for_page_load(browser, 0.5)
            
            # Select action filter if available
            action_select = await browser.query_selector("select[name='action']")
            if action_select:
                await browser.select("select[name='action']", "Login")
                await browser.click("button[type='submit']")
                await wait_for_page_load(browser)
                
                await capture_screenshot(browser, "admin_audit_filtered_action")

    async def test_audit_filtered_by_time(self, active_profile):
        """Screenshot: Audit log - filtered by time range."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/audit?range=last_7_days"))
            await wait_for_page_load(browser)
            
            await capture_screenshot(browser, "admin_audit_filtered_time")


class TestAdminConfigScreenshots:
    """Screenshots for admin configuration pages."""

    async def test_config_netcup(self, active_profile):
        """Screenshot: Netcup API configuration."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/config/netcup"))
            await wait_for_page_load(browser)
            
            await capture_screenshot(browser, "admin_config_netcup")

    async def test_config_email(self, active_profile):
        """Screenshot: Email/SMTP configuration."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/config/email"))
            await wait_for_page_load(browser)
            
            await capture_screenshot(browser, "admin_config_email")

    async def test_system_info(self, active_profile):
        """Screenshot: System information."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/system"))
            await wait_for_page_load(browser)
            
            await capture_screenshot(browser, "admin_system")

    async def test_change_password(self, active_profile):
        """Screenshot: Change password form."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/change-password"))
            await wait_for_page_load(browser)
            
            await capture_screenshot(browser, "admin_change_password")

    async def test_change_password_validation(self, active_profile):
        """Screenshot: Change password - validation state with weak password."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/change-password"))
            await wait_for_page_load(browser, 0.5)
            
            # Fill with weak passwords to trigger client-side entropy validation display
            await browser.fill("#current_password", "currentpass")
            await browser.fill("#new_password", "weak123")  # Low entropy - shows warning
            await browser.fill("#confirm_password", "weak123")
            
            await asyncio.sleep(0.5)  # Wait for entropy calculation
            
            # Screenshot shows the entropy warning and disabled submit button
            await capture_screenshot(browser, "admin_change_password_validation")


# =============================================================================
# Account Portal - Public Routes  
# =============================================================================

class TestAccountPublicScreenshots:
    """Screenshots for account portal public routes."""

    async def test_account_login(self, active_profile):
        """Screenshot: Account login page."""
        async with browser_session() as browser:
            await browser.goto(settings.url("/account/login"))
            await wait_for_page_load(browser)
            
            await capture_screenshot(browser, "account_login")

    async def test_account_login_error(self, active_profile):
        """Screenshot: Account login - error state."""
        async with browser_session() as browser:
            await browser.goto(settings.url("/account/login"))
            await wait_for_page_load(browser, 0.5)
            
            await browser.fill("#username", "nonexistent")
            await browser.fill("#password", "wrongpass")
            await browser.click("button[type='submit']")
            await wait_for_page_load(browser)
            
            await capture_screenshot(browser, "account_login_error")

    async def test_account_register(self, active_profile):
        """Screenshot: Account registration form."""
        async with browser_session() as browser:
            await browser.goto(settings.url("/account/register"))
            await wait_for_page_load(browser)
            
            await capture_screenshot(browser, "account_register")

    async def test_account_register_validation(self, active_profile):
        """Screenshot: Account registration - validation errors."""
        async with browser_session() as browser:
            await browser.goto(settings.url("/account/register"))
            await wait_for_page_load(browser, 0.5)
            
            # Fill with invalid data
            await browser.fill("#username", "ab")  # Too short
            await browser.fill("#email", "invalid")
            await browser.fill("#password", "weak")
            await browser.fill("#confirm_password", "different")
            
            await browser.click("button[type='submit']")
            await wait_for_page_load(browser)
            
            await capture_screenshot(browser, "account_register_validation")

    async def test_account_forgot_password(self, active_profile):
        """Screenshot: Forgot password page."""
        async with browser_session() as browser:
            await browser.goto(settings.url("/account/forgot-password"))
            await wait_for_page_load(browser)
            
            await capture_screenshot(browser, "account_forgot_password")

    async def test_account_forgot_password_submitted(self, active_profile):
        """Screenshot: Forgot password - after submission."""
        async with browser_session() as browser:
            await browser.goto(settings.url("/account/forgot-password"))
            await wait_for_page_load(browser, 0.5)
            
            await browser.fill("#email", "test@example.com")
            await browser.click("button[type='submit']")
            await wait_for_page_load(browser)
            
            await capture_screenshot(browser, "account_forgot_password_submitted")


# =============================================================================
# Error Pages
# =============================================================================

class TestErrorPageScreenshots:
    """Screenshots for error pages."""

    async def test_error_404(self, active_profile):
        """Screenshot: 404 Not Found error."""
        async with browser_session() as browser:
            await browser.goto(settings.url("/nonexistent-page-xyz"))
            await wait_for_page_load(browser)
            
            await capture_screenshot(browser, "error_404")

    async def test_error_403_unauthorized(self, active_profile):
        """Screenshot: 403 Forbidden - unauthorized access attempt."""
        async with browser_session() as browser:
            # Try to access admin page without auth
            await browser.goto(settings.url("/admin/accounts"))
            await wait_for_page_load(browser)
            
            # Should redirect to login (or show 403)
            current_url = browser.current_url or ""
            if "/login" in current_url:
                await capture_screenshot(browser, "admin_redirect_to_login")
            else:
                await capture_screenshot(browser, "error_403")


# =============================================================================
# Theme Reference Screenshots
# =============================================================================

class TestThemeReferenceScreenshots:
    """Screenshots of component demo with different themes."""

    async def test_component_demo_cobalt2(self, active_profile):
        """Screenshot: Component demo - Cobalt 2 (default) theme."""
        async with browser_session() as browser:
            await browser.goto(settings.url("/component-demo-bs5"))
            await wait_for_page_load(browser)
            
            await capture_screenshot(browser, "reference_bs5_cobalt2")

    async def test_component_demo_obsidian_noir(self, active_profile):
        """Screenshot: Component demo - Obsidian Noir theme."""
        async with browser_session() as browser:
            await browser.goto(settings.url("/component-demo-bs5"))
            await wait_for_page_load(browser, 0.5)
            
            # Click theme link
            try:
                await browser._page.click('a.nav-link:has-text("Obsidian Noir")')
                await wait_for_page_load(browser, 0.3)
            except Exception:
                pass
            
            await capture_screenshot(browser, "reference_bs5_obsidian_noir")

    async def test_component_demo_gold_dust(self, active_profile):
        """Screenshot: Component demo - Gold Dust theme."""
        async with browser_session() as browser:
            await browser.goto(settings.url("/component-demo-bs5"))
            await wait_for_page_load(browser, 0.5)
            
            try:
                await browser._page.click('a.nav-link:has-text("Gold Dust")')
                await wait_for_page_load(browser, 0.3)
            except Exception:
                pass
            
            await capture_screenshot(browser, "reference_bs5_gold_dust")

    async def test_component_demo_ember(self, active_profile):
        """Screenshot: Component demo - Ember theme."""
        async with browser_session() as browser:
            await browser.goto(settings.url("/component-demo-bs5"))
            await wait_for_page_load(browser, 0.5)
            
            try:
                await browser._page.click('a.nav-link:has-text("Ember")')
                await wait_for_page_load(browser, 0.3)
            except Exception:
                pass
            
            await capture_screenshot(browser, "reference_bs5_ember")


# =============================================================================
# API States - Audit Log Evidence
# =============================================================================

class TestAPIStateScreenshots:
    """
    Capture API states via audit log after API calls.
    
    These tests make API calls with various tokens/states and then
    capture the audit log showing the result.
    """

    async def test_api_call_success_audit(self, active_profile):
        """Screenshot: Audit log showing successful API call."""
        import httpx
        
        # Make an API call with valid token
        async with httpx.AsyncClient(verify=False) as client:
            url = settings.url("/api/myip")
            await client.get(url)
        
        # Capture audit log
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/audit"))
            await wait_for_page_load(browser)
            
            await capture_screenshot(browser, "audit_api_success")

    async def test_api_call_invalid_token_audit(self, active_profile):
        """Screenshot: Audit log showing rejected invalid token."""
        import httpx
        
        # Make API call with invalid token
        async with httpx.AsyncClient(verify=False) as client:
            url = settings.url(f"/api/dns/{settings.client_domain}/records")
            headers = {"Authorization": "Bearer invalid-token-xyz"}
            try:
                await client.get(url, headers=headers)
            except Exception:
                pass
        
        # Capture audit log
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/audit"))
            await wait_for_page_load(browser)
            
            await capture_screenshot(browser, "audit_api_invalid_token")

    async def test_api_call_unauthorized_domain_audit(self, active_profile):
        """Screenshot: Audit log showing domain permission denied."""
        import httpx
        
        # Make API call to unauthorized domain
        async with httpx.AsyncClient(verify=False) as client:
            url = settings.url("/api/dns/unauthorized-domain.com/records")
            headers = {"Authorization": f"Bearer {settings.client_token}"}
            try:
                await client.get(url, headers=headers)
            except Exception:
                pass
        
        # Capture audit log
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/audit"))
            await wait_for_page_load(browser)
            
            await capture_screenshot(browser, "audit_api_unauthorized_domain")


# =============================================================================
# Screenshot Summary Report
# =============================================================================

@pytest.fixture(scope="session", autouse=True)
def generate_screenshot_report(request):
    """Generate a summary report of all captured screenshots."""
    yield
    
    # After all tests complete
    screenshot_dir = os.environ.get('SCREENSHOT_DIR', '/workspaces/netcup-api-filter/deploy-local/screenshots')
    if not os.path.exists(screenshot_dir):
        return
    
    # List all screenshots
    screenshots = sorted([f for f in os.listdir(screenshot_dir) if f.endswith(f'.{SCREENSHOT_FORMAT}')])
    
    report = {
        "generated_at": datetime.now().isoformat(),
        "format": SCREENSHOT_FORMAT,
        "total_count": len(screenshots),
        "screenshots": screenshots,
        "categories": {}
    }
    
    # Categorize by prefix
    for ss in screenshots:
        prefix = ss.split('_')[0]
        if prefix not in report["categories"]:
            report["categories"][prefix] = []
        report["categories"][prefix].append(ss)
    
    # Write report
    report_path = os.path.join(screenshot_dir, "screenshot_inventory.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    
    print(f"\n📊 Screenshot Report: {len(screenshots)} screenshots captured")
    for cat, files in report["categories"].items():
        print(f"   {cat}: {len(files)} files")
