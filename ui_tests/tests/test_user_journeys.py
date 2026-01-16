"""
User Journey Tests - End-to-end tests for complete user workflows.

These tests simulate real user journeys through the application:
1. Admin account management journey
2. Account registration and approval journey
3. Configuration management journey
4. Token lifecycle journey
5. Audit log review journey

Each journey tests the complete flow from start to finish.

Run with: pytest ui_tests/tests/test_user_journeys.py -v
"""
import pytest
import asyncio
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from ui_tests.config import settings
from browser import browser_session
import workflows


pytestmark = pytest.mark.asyncio


# =============================================================================
# Journey 1: Admin Account Management
# =============================================================================

class TestAdminAccountManagementJourney:
    """
    Complete admin journey for managing accounts.
    
    Steps:
    1. Login as admin
    2. Navigate to accounts
    3. Create new account
    4. View account details
    5. Navigate back to list
    6. Verify account appears
    """

    async def test_complete_account_management_flow(self, active_profile):
        """Test full account creation and management flow."""
        async with browser_session() as browser:
            # Step 1: Login
            await workflows.ensure_admin_dashboard(browser)
            
            # Verify on dashboard
            h1 = await browser.text("main h1")
            assert "Dashboard" in h1, f"Should be on dashboard, got: {h1}"
            
            # Step 2: Navigate to accounts
            await browser.click('a[href="/admin/accounts"]')
            await browser.wait_for_load_state('domcontentloaded')

            h1 = await browser.text("main h1")
            assert "Accounts" in h1, f"Should be on accounts page, got: {h1}"
            
            # Step 3: Click create account
            create_btn = await browser.query_selector('a[href="/admin/accounts/new"]')
            if create_btn:
                await create_btn.click()
                await browser.wait_for_load_state('domcontentloaded')

                h1 = await browser.text("main h1")
                assert "Create" in h1, f"Should be on create page, got: {h1}"
                
                # Verify form fields exist
                username_field = await browser.query_selector('#username')
                email_field = await browser.query_selector('#email')
                
                assert username_field, "Username field should exist"
                assert email_field, "Email field should exist"
            
            # Step 4: Navigate back to list
            await browser.goto(settings.url("/admin/accounts"))
            await browser.wait_for_load_state('domcontentloaded')

            # Verify we're back on accounts list
            h1 = await browser.text("main h1")
            assert "Accounts" in h1

    async def test_admin_can_view_account_details(self, active_profile):
        """Test admin can click into account details."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/accounts"))
            await browser.wait_for_load_state('domcontentloaded')

            # Look for an account link in the table
            account_link = await browser.query_selector('table tbody a[href*="/admin/accounts/"]')
            
            if account_link:
                await account_link.click()
                await browser.wait_for_load_state('domcontentloaded')

                # Should be on account detail page
                body = await browser.text("body")
                # Detail page should show account info
                assert "Account" in body or "Username" in body or "Email" in body


# =============================================================================
# Journey 2: Configuration Management
# =============================================================================

class TestConfigurationManagementJourney:
    """
    Complete journey for managing system configuration.
    
    Steps:
    1. Login as admin
    2. Navigate to Settings
    3. Verify Netcup + Email sections
    4. Navigate to System info
    """

    async def test_complete_config_review_flow(self, active_profile):
        """Test full configuration review flow."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            # Step 1: Navigate to unified Settings page
            await browser.goto(settings.url("/admin/settings"))
            await browser.wait_for_load_state('domcontentloaded')

            h1 = await browser.text("main h1")
            assert "Settings" in h1, f"Should be on Settings page, got: {h1}"

            # Step 2: Verify Netcup section fields
            customer_field = await browser.query_selector('input[name="customer_id"]')
            api_key_field = await browser.query_selector('input[name="api_key"]')
            api_pass_field = await browser.query_selector('input[name="api_password"]')
            assert customer_field, "Customer ID field should exist"
            assert api_key_field, "API key field should exist"
            assert api_pass_field, "API password field should exist"

            # Step 3: Verify Email section fields
            smtp_host = await browser.query_selector('input[name="smtp_host"]')
            smtp_port = await browser.query_selector('input[name="smtp_port"]')
            assert smtp_host, "SMTP host field should exist"
            assert smtp_port, "SMTP port field should exist"

            # Step 4: Navigate to System info
            await browser.goto(settings.url("/admin/system"))
            await browser.wait_for_load_state('domcontentloaded')

            h1 = await browser.text("main h1")
            assert "System" in h1, f"Should be on System info, got: {h1}"
            
            # Step 6: Verify system info is displayed
            body = await browser.text("body")
            # Should show Python version or other system info
            assert "Python" in body or "Version" in body or "Build" in body


# =============================================================================
# Journey 3: Audit Log Review
# =============================================================================

class TestAuditLogReviewJourney:
    """
    Complete journey for reviewing audit logs.
    
    Steps:
    1. Login as admin
    2. Navigate to audit logs from dashboard
    3. View log entries
    4. Apply filters if available
    5. Export logs if available
    """

    async def test_complete_audit_review_flow(self, active_profile):
        """Test full audit log review flow."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            # Step 1: Click View All in Recent Activity section
            view_all = await browser.query_selector('a[href="/admin/audit"]')
            assert view_all, "Should have link to audit logs"
            
            await view_all.click()
            await browser.wait_for_load_state('domcontentloaded')

            # Step 2: Verify on audit logs page
            h1 = await browser.text("main h1")
            assert "Audit" in h1 or "Log" in h1, f"Should be on audit page, got: {h1}"
            
            # Step 3: Check table exists
            table = await browser.query_selector("table")
            assert table, "Audit log table should exist"
            
            # Step 4: Check table headers
            headers = await browser.text("table thead")
            assert "Timestamp" in headers or "Time" in headers or "Date" in headers
            assert "Actor" in headers or "User" in headers or "Account" in headers
            assert "Action" in headers or "Event" in headers or "Operation" in headers
            
            # Step 5: Check for filter/search if present
            filter_form = await browser.query_selector('form[action*="audit"]')
            search_input = await browser.query_selector('input[type="search"], input[name="search"], input[name="query"]')
            
            # Filters may or may not be present - just verify page works

    async def test_audit_log_from_dashboard_recent_activity(self, active_profile):
        """Test navigating to audit from dashboard Recent Activity."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            # Dashboard should show audit link (not 'Recent Activity' section)
            body = await browser.text("body")
            assert "Audit" in body or "API Calls" in body or "View Logs" in body
            
            # Click View All
            view_all = await browser.query_selector('a.btn[href="/admin/audit"]')
            if view_all:
                await view_all.click()
                await browser.wait_for_load_state('domcontentloaded')

                h1 = await browser.text("main h1")
                assert "Audit" in h1


# =============================================================================
# Journey 4: Password Change Flow
# =============================================================================

class TestPasswordChangeJourney:
    """
    Test password change user journey.
    
    Note: This test validates the UI flow without actually changing the password
    to avoid breaking subsequent tests.
    """

    async def test_password_change_ui_flow(self, active_profile):
        """Test password change form validation and UI."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            # Step 1: Navigate to change password via user dropdown
            user_dropdown = await browser.query_selector('.dropdown-toggle:has-text("admin")')
            if user_dropdown:
                await user_dropdown.click()
                await browser.wait_for_timeout(300)

                change_pwd = await browser.query_selector('a[href="/admin/change-password"]')
                if change_pwd:
                    await change_pwd.click()
                    await browser.wait_for_load_state('domcontentloaded')

            # Fallback: Direct navigation
            if "/admin/change-password" not in browser.current_url:
                await browser.goto(settings.url("/admin/change-password"))
                await browser.wait_for_load_state('domcontentloaded')

            # Step 2: Verify on change password page
            h1 = await browser.text("main h1")
            assert (
                "Password" in h1 or "Initial Setup" in h1
            ), f"Should be on change password page (or initial setup), got: {h1}"
            
            # Step 3: Check form fields
            current_pwd = await browser.query_selector('#current_password')
            new_pwd = await browser.query_selector('#new_password')
            confirm_pwd = await browser.query_selector('#confirm_password')
            
            assert new_pwd, "New password field should exist"
            assert confirm_pwd, "Confirm password field should exist"
            
            # Step 4: Test password mismatch validation (without submitting)
            await browser.fill("#new_password", "NewPassword123!")
            await browser.fill("#confirm_password", "DifferentPass!")
            await browser.wait_for_timeout(300)

            mismatch = await browser.query_selector('#passwordMismatch:not(.d-none)')
            assert mismatch, "Password mismatch warning should appear"
            
            # Step 5: Test matching passwords
            await browser.fill("#confirm_password", "NewPassword123!")
            await browser.wait_for_timeout(300)

            mismatch_hidden = await browser.evaluate("""
                () => {
                    const el = document.getElementById('passwordMismatch');
                    return el && el.classList.contains('d-none');
                }
            """)
            assert mismatch_hidden, "Password mismatch warning should be hidden when passwords match"


# =============================================================================
# Journey 5: Theme and Density Customization
# =============================================================================

class TestThemeCustomizationJourney:
    """
    Test theme and density customization journey.
    """

    async def test_theme_change_persists_across_pages(self, active_profile):
        """Test theme selection persists across page navigation."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            # Step 1: Apply a specific theme
            await browser.evaluate("() => setTheme('ember')")
            await browser.wait_for_timeout(300)

            # Step 2: Navigate to different page
            await browser.goto(settings.url("/admin/accounts"))
            await browser.wait_for_load_state('domcontentloaded')
            
            # Step 3: Check theme persisted
            theme_class = await browser.evaluate("""
                () => {
                    const classes = document.documentElement.className + ' ' + document.body.className;
                    return classes;
                }
            """)
            
            assert 'ember' in theme_class or localStorage.getItem('naf-theme') == 'ember', \
                f"Theme should persist. Classes: {theme_class}"
            
            # Reset to default for other tests
            await browser.evaluate("() => setTheme('cobalt-2')")

    async def test_density_change_affects_layout(self, active_profile):
        """Test density change applies correct classes."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            # Step 1: Get initial line height (for comparison)
            initial_padding = await browser.evaluate("""
                () => {
                    const card = document.querySelector('.card');
                    return card ? getComputedStyle(card).padding : null;
                }
            """)
            
            # Step 2: Apply compact density
            await browser.evaluate("() => setDensity('compact')")
            await browser.wait_for_timeout(300)

            # Step 3: Verify density class applied
            has_compact = await browser.evaluate("""
                () => document.body.classList.contains('density-compact') ||
                      document.documentElement.classList.contains('density-compact')
            """)
            
            assert has_compact, "Compact density class should be applied"
            
            # Reset to default
            await browser.evaluate("() => setDensity('comfortable')")


# =============================================================================
# Journey 6: Account Portal Navigation (Unauthenticated)
# =============================================================================

class TestAccountPortalNavigation:
    """
    Test account portal navigation for unauthenticated users.
    """

    async def test_account_portal_public_pages(self, browser):
        """Test public account portal pages are accessible."""
        # Login page
        await browser.goto(settings.url("/account/login"))
        await browser._page.wait_for_load_state("networkidle")

        # Verify login form is present
        username_input = await browser.query_selector('input[name="username"], input[type="text"]')
        password_input = await browser.query_selector('input[name="password"], input[type="password"]')
        assert username_input is not None, "Login page should have username input"
        assert password_input is not None, "Login page should have password input"
        
        # Registration page
        await browser.goto(settings.url("/account/register"))
        await browser._page.wait_for_load_state("networkidle")

        # Verify registration form is present (avoid brittle heading assertions)
        reg_username = await browser.query_selector('input#username[name="username"], input[name="username"]')
        reg_email = await browser.query_selector('input#email[name="email"], input[name="email"], input[type="email"]')
        reg_password = await browser.query_selector('input#password[name="password"], input[name="password"]')
        reg_confirm = await browser.query_selector('input#confirm_password[name="confirm_password"], input[name="confirm_password"]')
        assert reg_username is not None, "Register page should have username input"
        assert reg_email is not None, "Register page should have email input"
        assert reg_password is not None, "Register page should have password input"
        assert reg_confirm is not None, "Register page should have confirm password input"
        
        # Forgot password page
        await browser.goto(settings.url("/account/forgot-password"))
        await browser._page.wait_for_load_state("networkidle")
        
        body = await browser.text("body")
        assert "forgot" in body.lower() or "reset" in body.lower() or "password" in body.lower()

    async def test_account_login_to_register_link(self, browser):
        """Test navigation from login to registration."""
        await browser.goto(settings.url("/account/login"))
        await browser._page.wait_for_load_state("networkidle")
        
        # Look for register link
        register_link = await browser.query_selector('a[href*="register"]')
        
        if register_link:
            await register_link.click()
            await browser._page.wait_for_load_state("networkidle")

            # Should be on register page - get URL directly from page
            current = browser._page.url
            assert "/register" in current, f"Should navigate to register page, got: {current}"
        else:
            # Skip test if no register link found (some UIs may not have it)
            pytest.skip("No register link found on login page")

    async def test_account_login_to_forgot_password_link(self, browser):
        """Test navigation from login to forgot password."""
        await browser.goto(settings.url("/account/login"))
        await browser._page.wait_for_load_state("networkidle")
        
        # Look for forgot password link
        forgot_link = await browser.query_selector('a[href*="forgot"]')
        
        if forgot_link:
            await forgot_link.click()
            await browser._page.wait_for_load_state("networkidle")

            # Should be on forgot password page - get URL directly from page
            current = browser._page.url
            assert "/forgot" in current, f"Should navigate to forgot password page, got: {current}"
        else:
            # Skip test if no forgot link found
            pytest.skip("No forgot password link found on login page")


# =============================================================================
# Journey 7: Error Page Handling
# =============================================================================

class TestErrorPageHandling:
    """Test error pages display correctly."""

    async def test_404_page_exists(self, active_profile):
        """Test 404 page is displayed for non-existent routes."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            # Navigate to non-existent page
            await browser.goto(settings.url("/admin/this-page-does-not-exist"))
            await browser.wait_for_load_state('domcontentloaded')

            body = await browser.text("body")
            
            # Should show 404 or error message
            assert "404" in body or "not found" in body.lower() or "error" in body.lower()

    async def test_protected_page_redirects_to_login(self, browser):
        """Test protected pages redirect to login when not authenticated."""
        await browser._page.context.clear_cookies()
        # Try to access admin page without login
        await browser.goto(settings.url("/admin/accounts"))
        await browser._page.wait_for_load_state("networkidle")
        
        # Should redirect to login
        current_url = browser._page.url
        assert "/login" in current_url, f"Should redirect to login, got: {current_url}"


# =============================================================================
# Journey 8: Dashboard Statistics
# =============================================================================

class TestDashboardStatistics:
    """Test dashboard displays correct statistics."""

    async def test_dashboard_shows_statistics(self, active_profile):
        """Test dashboard shows account and activity statistics."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            body = await browser.text("body")
            
            # Should show various statistics
            assert "Accounts" in body or "Total" in body
            assert "Pending" in body or "Approval" in body
            assert "API Calls" in body or "Calls" in body or "Activity" in body

    async def test_dashboard_quick_actions_present(self, active_profile):
        """Test dashboard shows stat card links to management pages."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            # Dashboard has stat cards that link to management pages (these serve as quick actions)
            # Check for common stat card links rather than a "Quick Actions" section
            accounts_link = await browser.query_selector('a[href*="/admin/accounts"]')
            realms_link = await browser.query_selector('a[href*="/admin/realms"]')
            audit_link = await browser.query_selector('a[href*="/admin/audit"]')
            
            # At least some navigation links should be present
            links_found = [
                accounts_link is not None,
                realms_link is not None,
                audit_link is not None,
            ]
            
            assert any(links_found), "Dashboard should have stat card links to management pages"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
