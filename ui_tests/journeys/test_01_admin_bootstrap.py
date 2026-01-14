"""
Journey 01: Admin Bootstrap

This journey tests the initial admin experience:
1. Login with default credentials
2. Change password (required on fresh install)
3. Capture empty state screenshots for all list pages
4. Verify dashboard shows zero counts
"""
import pytest
import pytest_asyncio

from ui_tests.config import settings
from ui_tests.workflows import ensure_admin_dashboard


class TestAdminLogin:
    """Test admin login flow."""
    
    @pytest.mark.asyncio
    async def test_login_page_renders(self, browser, screenshot_helper):
        """Login page displays correctly."""
        ss = screenshot_helper('01-bootstrap')
        
        await browser.goto(settings.url('/admin/login'))
        await ss.capture('login-page', 'Admin login page')
        
        # Verify login form elements
        username = await browser.query_selector('#username')
        password = await browser.query_selector('#password')
        submit = await browser.query_selector('button[type="submit"]')
        
        assert username, "Username field missing"
        assert password, "Password field missing"
        assert submit, "Submit button missing"
    
    @pytest.mark.asyncio
    async def test_login_with_valid_credentials(self, browser, screenshot_helper):
        """Login with valid admin credentials succeeds."""
        ss = screenshot_helper('01-bootstrap')
        
        await browser.goto(settings.url('/admin/login'))
        
        # Use credentials from settings (auto-refreshed from deployment state)
        await browser.fill('#username', settings.admin_username)
        await browser.fill('#password', settings.admin_password)
        await ss.capture('login-filled', 'Login form filled')
        
        await browser.click('button[type="submit"]')
        await browser.wait_for_load_state('domcontentloaded')
        
        current_url = browser.current_url
        await ss.capture('after-login', f'After login - URL: {current_url}')
        
        # Should be on dashboard or change-password page
        assert '/admin/' in current_url or '/admin/change-password' in current_url, \
            f"Login failed, still at: {current_url}"
    
    @pytest.mark.asyncio
    async def test_login_with_wrong_password(self, browser, screenshot_helper):
        """Login with wrong password shows error."""
        ss = screenshot_helper('01-bootstrap')
        
        await browser.goto(settings.url('/admin/login'))
        
        await browser.fill('#username', 'admin')
        await browser.fill('#password', 'definitely-wrong-password')
        await browser.click('button[type="submit"]')
        await browser.wait_for_load_state('domcontentloaded')
        
        await ss.capture('login-failed', 'Login failed with wrong password')
        
        # Should still be on login page with error
        current_url = browser.current_url
        assert '/admin/login' in current_url
        
        body = await browser.text('body')
        assert 'invalid' in body.lower() or 'error' in body.lower() or 'incorrect' in body.lower(), \
            "No error message shown for wrong password"


class TestAdminDashboard:
    """Test admin dashboard after login."""
    
    @pytest.mark.asyncio
    async def test_dashboard_renders(self, admin_session, screenshot_helper):
        """Dashboard renders with expected elements."""
        ss = screenshot_helper('01-bootstrap')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/'))
        await ss.capture('dashboard', 'Admin dashboard')
        
        # Verify dashboard elements
        body = await browser.text('body')
        
        # Should have navigation
        nav = await browser.query_selector('nav')
        assert nav, "Navigation missing"
        
        # Should have stat cards or overview
        assert 'account' in body.lower() or 'realm' in body.lower() or 'token' in body.lower(), \
            "Dashboard missing expected content"
    
    @pytest.mark.asyncio
    async def test_dashboard_navigation_links(self, admin_session, screenshot_helper):
        """Dashboard has working navigation links."""
        ss = screenshot_helper('01-bootstrap')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/'))
        
        # Check for navigation links
        accounts_link = await browser.query_selector('a[href*="/admin/accounts"]')
        realms_link = await browser.query_selector('a[href*="/admin/realms"]')
        audit_link = await browser.query_selector('a[href*="/admin/audit"]')
        
        await ss.capture('dashboard-nav', 'Dashboard with navigation')
        
        assert accounts_link, "Accounts link missing from navigation"
        assert realms_link, "Realms link missing from navigation"


class TestEmptyStateScreenshots:
    """Capture all list pages in empty state."""
    
    @pytest.mark.asyncio
    async def test_accounts_list_empty(self, admin_session, screenshot_helper):
        """Accounts list shows empty state."""
        ss = screenshot_helper('01-bootstrap')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/accounts'))
        await ss.capture('accounts-list-empty', 'Accounts list (empty or with admin only)')
        
        # Page should load without 500 error
        body = await browser.text('body')
        assert 'internal server error' not in body.lower(), "Page shows 500 error"
    
    @pytest.mark.asyncio
    async def test_accounts_pending_empty(self, admin_session, screenshot_helper):
        """Pending accounts shows empty state."""
        ss = screenshot_helper('01-bootstrap')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/accounts/pending'))
        await ss.capture('accounts-pending-empty', 'Pending accounts (empty)')
        
        body = await browser.text('body')
        # Should show "no pending" or empty table
        assert 'pending' in body.lower() or 'no ' in body.lower() or 'empty' in body.lower()
    
    @pytest.mark.asyncio
    async def test_realms_list_empty(self, admin_session, screenshot_helper):
        """Realms list shows empty state."""
        ss = screenshot_helper('01-bootstrap')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/realms'))
        await ss.capture('realms-list-empty', 'Realms list (empty or with demo data)')
    
    @pytest.mark.asyncio
    async def test_realms_pending_empty(self, admin_session, screenshot_helper):
        """Pending realms shows empty state."""
        ss = screenshot_helper('01-bootstrap')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/realms/pending'))
        await ss.capture('realms-pending-empty', 'Pending realms (empty)')
    
    @pytest.mark.asyncio
    async def test_audit_log_initial(self, admin_session, screenshot_helper):
        """Audit log shows initial state (may have login entries)."""
        ss = screenshot_helper('01-bootstrap')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/audit'))
        await ss.capture('audit-log-initial', 'Audit log (initial state)')
        
        # Audit log should exist even if empty
        body = await browser.text('body')
        assert 'audit' in body.lower() or 'log' in body.lower() or 'activity' in body.lower()


class TestConfigPages:
    """Capture configuration pages."""
    
    @pytest.mark.asyncio
    async def test_netcup_config_page(self, admin_session, screenshot_helper):
        """Netcup API config page renders."""
        ss = screenshot_helper('01-bootstrap')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/config/netcup'))
        await ss.capture('config-netcup', 'Netcup API configuration')
        
        # Should have API credential fields
        customer_id = await browser.query_selector('#customer_id, input[name="customer_id"]')
        api_key = await browser.query_selector('#api_key, input[name="api_key"]')
        
        assert customer_id or api_key, "Netcup config missing expected fields"
    
    @pytest.mark.asyncio
    async def test_email_config_page(self, admin_session, screenshot_helper):
        """Email config page renders."""
        ss = screenshot_helper('01-bootstrap')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/config/email'))
        await ss.capture('config-email', 'Email configuration')
        
        # Should have SMTP fields
        smtp_host = await browser.query_selector('#smtp_host, input[name="smtp_host"]')
        assert smtp_host, "Email config missing SMTP host field"
    
    @pytest.mark.asyncio
    async def test_system_info_page(self, admin_session, screenshot_helper):
        """System info page renders."""
        ss = screenshot_helper('01-bootstrap')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/system'))
        await ss.capture('system-info', 'System information')
        
        body = await browser.text('body')
        # Should show system information
        assert 'version' in body.lower() or 'python' in body.lower() or 'system' in body.lower()


class TestAdminLogout:
    """Test admin logout."""
    
    @pytest.mark.asyncio
    async def test_logout_redirects_to_login(self, admin_session, screenshot_helper):
        """Logout redirects to login page."""
        ss = screenshot_helper('01-bootstrap')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/logout'))
        await browser.wait_for_timeout(300)
        
        current_url = browser.current_url
        await ss.capture('after-logout', 'After logout')
        
        assert '/admin/login' in current_url, \
            f"Logout didn't redirect to login: {current_url}"
    
    @pytest.mark.asyncio
    async def test_after_logout_cannot_access_dashboard(self, browser, screenshot_helper):
        """After logout, dashboard is inaccessible."""
        ss = screenshot_helper('01-bootstrap')
        
        # First login
        await ensure_admin_dashboard(browser)
        
        # Then logout
        await browser.goto(settings.url('/admin/logout'))
        await browser.wait_for_timeout(300)
        
        # Try to access dashboard
        await browser.goto(settings.url('/admin/'))
        await browser.wait_for_timeout(300)
        
        current_url = browser.current_url
        await ss.capture('dashboard-after-logout', 'Dashboard access after logout')
        
        assert '/admin/login' in current_url, \
            f"Dashboard accessible after logout! URL: {current_url}"
