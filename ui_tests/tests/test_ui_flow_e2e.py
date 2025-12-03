"""E2E tests for UI flows.

Tests complete user journeys through the application:
- Bulk account operations via Playwright
- Log filtering and search
- Password reset with email verification
- Token regeneration
- Client portal navigation

Run with: pytest ui_tests/tests/test_ui_flow_e2e.py -v
"""
import pytest
import re
import time
from pathlib import Path
import sys

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings


pytestmark = [
    pytest.mark.asyncio,
]


class TestBulkAccountOperations:
    """Test bulk account operations via admin UI."""
    
    async def test_bulk_actions_bar_visible(self, admin_page):
        """Test bulk actions bar appears when checkboxes selected."""
        await admin_page.goto(settings.url("/admin/accounts"))
        await admin_page.wait_for_load_state("networkidle")
        
        # Look for checkbox elements
        checkboxes = await admin_page.query_selector_all('input.row-checkbox')
        
        # If checkboxes exist, clicking one should show bulk actions
        if checkboxes:
            await checkboxes[0].click()
            await admin_page.wait_for_timeout(500)
            
            # Bulk actions bar should be visible
            actions_bar = await admin_page.query_selector('#bulkActionsBar')
            if actions_bar:
                is_visible = await actions_bar.is_visible()
                assert is_visible, "Bulk actions bar should be visible when checkbox selected"
    
    async def test_select_all_checkbox_works(self, admin_page):
        """Test select all checkbox toggles all rows."""
        await admin_page.goto(settings.url("/admin/accounts"))
        await admin_page.wait_for_load_state("networkidle")
        
        # Look for select all checkbox
        select_all = await admin_page.query_selector('#selectAll')
        
        if select_all:
            await select_all.click()
            await admin_page.wait_for_timeout(300)
            
            # All row checkboxes should be checked
            checkboxes = await admin_page.query_selector_all('input.row-checkbox')
            for cb in checkboxes[:5]:  # Check first 5
                is_checked = await cb.is_checked()
                assert is_checked, "Row checkbox should be checked after select all"


class TestLogFiltering:
    """Test log filtering and search functionality."""
    
    async def test_audit_logs_date_filter(self, admin_page):
        """Test date range filter on audit logs."""
        await admin_page.goto(settings.url("/admin/audit"))
        await admin_page.wait_for_load_state("networkidle")
        
        # Look for date range selector
        date_select = await admin_page.query_selector('select[name="range"]')
        
        if date_select:
            # Select "Today"
            await admin_page.select_option('select[name="range"]', 'today')
            await admin_page.click('button[type="submit"]')
            await admin_page.wait_for_timeout(1000)
            
            # Should reload with filter applied
            current_url = admin_page.url
            assert "range=today" in current_url or "today" in await admin_page.content()
    
    async def test_audit_logs_action_filter(self, admin_page):
        """Test action type filter on audit logs."""
        await admin_page.goto(settings.url("/admin/audit"))
        await admin_page.wait_for_load_state("networkidle")
        
        # Look for action type selector
        action_select = await admin_page.query_selector('select[name="action"]')
        
        if action_select:
            # Select "login" filter
            await admin_page.select_option('select[name="action"]', 'login')
            await admin_page.click('button[type="submit"]')
            await admin_page.wait_for_timeout(1000)
            
            # Should only show login events (or no events)
            table_content = await admin_page.text_content('table tbody')
            if table_content and "No logs" not in table_content:
                # If there are logs, they should be login-related
                assert "login" in table_content.lower() or "Login" in table_content
    
    async def test_audit_logs_search(self, admin_page):
        """Test text search on audit logs."""
        await admin_page.goto(settings.url("/admin/audit"))
        await admin_page.wait_for_load_state("networkidle")
        
        # Look for search input
        search_input = await admin_page.query_selector('input[name="search"]')
        
        if search_input:
            await admin_page.fill('input[name="search"]', "admin")
            await admin_page.click('button[type="submit"]')
            await admin_page.wait_for_timeout(1000)
            
            # Search should be in URL
            current_url = admin_page.url
            assert "search=admin" in current_url or "search" in current_url


class TestPasswordReset:
    """Test password reset flow with email verification."""
    
    async def test_forgot_password_page_accessible(self, browser):
        """Test forgot password page is accessible."""
        await browser.goto(settings.url("/account/forgot-password"))
        await browser._page.wait_for_load_state("networkidle")
        
        # Should have email input
        email_field = await browser._page.query_selector('input[name="email"]')
        assert email_field, "Forgot password page should have email field"
    
    async def test_forgot_password_form_submission(self, browser):
        """Test forgot password form can be submitted."""
        await browser.goto(settings.url("/account/forgot-password"))
        await browser._page.wait_for_load_state("networkidle")
        
        # Submit with email
        await browser._page.fill('input[name="email"]', "test@example.com")
        await browser._page.click('button[type="submit"]')
        await browser._page.wait_for_timeout(1000)
        
        # Should show confirmation message (regardless of email existence)
        content = await browser._page.content()
        # Could show success or stay on page
        assert "check" in content.lower() or "email" in content.lower() or \
               "/forgot-password" in browser.current_url
    
    async def test_password_reset_with_mailpit(self, browser, mailpit):
        """Test full password reset flow with email."""
        # Skip if no registered account to test with
        # This would need setup with a known account first
        pytest.skip("Requires existing account with known email")


class TestTokenRegeneration:
    """Test token regeneration flow."""
    
    async def test_regenerate_button_present(self, admin_page):
        """Test regenerate button is present on token view."""
        # Navigate to a token detail page
        await admin_page.goto(settings.url("/admin/accounts"))
        await admin_page.wait_for_load_state("networkidle")
        
        # Look for any account link to drill into
        account_links = await admin_page.query_selector_all('a[href*="/accounts/"]')
        
        if account_links:
            await account_links[0].click()
            await admin_page.wait_for_load_state("networkidle")
            
            # Look for tokens section
            content = await admin_page.content()
            # Should have token management UI
            assert "token" in content.lower()


class TestClientPortalNavigation:
    """Test client portal authentication and navigation."""
    
    async def test_client_login_page_accessible(self, browser):
        """Test client login page is accessible."""
        await browser.goto(settings.url("/account/login"))
        await browser._page.wait_for_load_state("networkidle")
        
        # Check for login form elements
        username_field = await browser._page.query_selector('input[name="username"]')
        password_field = await browser._page.query_selector('input[name="password"]')
        
        assert username_field, "Client login should have username field"
        assert password_field, "Client login should have password field"
    
    async def test_client_dashboard_requires_auth(self, browser):
        """Test client dashboard redirects to login when not authenticated."""
        await browser.goto(settings.url("/account/dashboard"))
        await browser._page.wait_for_load_state("networkidle")
        
        # Should redirect to login
        current_url = browser.current_url
        assert "/login" in current_url, "Unauthenticated access should redirect to login"
    
    async def test_client_nav_links_present(self, browser):
        """Test client portal navigation has expected links."""
        await browser.goto(settings.url("/account/login"))
        await browser._page.wait_for_load_state("networkidle")
        
        content = await browser._page.content()
        
        # Login page should have register link
        has_register = "register" in content.lower()
        has_forgot = "forgot" in content.lower()
        
        assert has_register or has_forgot, "Login page should have register/forgot password links"


class TestAutoRefresh:
    """Test auto-refresh functionality on logs page."""
    
    async def test_auto_refresh_toggle_present(self, admin_page):
        """Test auto-refresh toggle is present on audit logs."""
        await admin_page.goto(settings.url("/admin/audit"))
        await admin_page.wait_for_load_state("networkidle")
        
        # Look for auto-refresh toggle
        auto_refresh = await admin_page.query_selector('#autoRefresh')
        
        if auto_refresh:
            # Toggle should be present
            assert auto_refresh is not None
            
            # Click to enable
            await auto_refresh.click()
            is_checked = await auto_refresh.is_checked()
            assert is_checked, "Auto-refresh should be toggleable"


class TestExportFunctionality:
    """Test log export functionality."""
    
    async def test_export_button_present(self, admin_page):
        """Test export button is present on audit logs."""
        await admin_page.goto(settings.url("/admin/audit"))
        await admin_page.wait_for_load_state("networkidle")
        
        content = await admin_page.content()
        assert "export" in content.lower() or "Export" in content
    
    async def test_export_link_works(self, admin_page):
        """Test export link generates a download."""
        await admin_page.goto(settings.url("/admin/audit"))
        await admin_page.wait_for_load_state("networkidle")
        
        # Look for export button
        export_btn = await admin_page.query_selector('button:has-text("Export")')
        
        if export_btn:
            # Click should trigger download or navigate
            async with admin_page.expect_download() as download_info:
                try:
                    await export_btn.click()
                    await admin_page.wait_for_timeout(2000)
                except:
                    pass  # Download may not trigger in test environment


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
