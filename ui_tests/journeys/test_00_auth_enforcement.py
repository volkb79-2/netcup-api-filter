"""
Journey 00: Authentication Enforcement Testing

CRITICAL: This runs BEFORE any other tests to verify security.

Tests that ALL non-public routes require proper authentication:
- Admin routes redirect to /admin/login
- Account routes redirect to /account/login  
- API routes return 401 without Bearer token
"""
import pytest
import pytest_asyncio

from ui_tests.config import settings


class TestAuthEnforcementAdmin:
    """Verify all admin routes require authentication."""
    
    @pytest_asyncio.fixture(autouse=True)
    async def setup(self, browser):
        """Ensure we start unauthenticated."""
        # Clear any existing session by visiting logout
        await browser.goto(settings.url('/admin/logout'))
        # Wait a moment for session to be cleared
        import asyncio
        await browser.wait_for_timeout(300)
    
    @pytest.mark.asyncio
    async def test_admin_dashboard_requires_auth(self, browser, screenshot_helper):
        """Admin dashboard redirects to login."""
        ss = screenshot_helper('00-auth')
        
        await browser.goto(settings.url('/admin/'))
        await ss.capture('admin-dashboard-redirect', 'Admin dashboard redirects to login')
        
        current_url = browser.current_url
        assert '/admin/login' in current_url, \
            f"Admin dashboard accessible without auth! URL: {current_url}"
    
    @pytest.mark.asyncio
    async def test_admin_accounts_requires_auth(self, browser):
        """Accounts list redirects to login."""
        await browser.goto(settings.url('/admin/accounts'))
        
        current_url = browser.current_url
        assert '/admin/login' in current_url, \
            f"SECURITY: /admin/accounts accessible without auth! URL: {current_url}"
    
    @pytest.mark.asyncio
    async def test_admin_accounts_new_requires_auth(self, browser):
        """New account form redirects to login."""
        await browser.goto(settings.url('/admin/accounts/new'))
        
        current_url = browser.current_url
        assert '/admin/login' in current_url, \
            f"SECURITY: /admin/accounts/new accessible without auth!"
    
    @pytest.mark.asyncio
    async def test_admin_realms_requires_auth(self, browser):
        """Realms list redirects to login."""
        await browser.goto(settings.url('/admin/realms'))
        
        current_url = browser.current_url
        assert '/admin/login' in current_url, \
            f"SECURITY: /admin/realms accessible without auth!"
    
    @pytest.mark.asyncio
    async def test_admin_audit_requires_auth(self, browser):
        """Audit log redirects to login."""
        await browser.goto(settings.url('/admin/audit'))
        
        current_url = browser.current_url
        assert '/admin/login' in current_url, \
            f"SECURITY: /admin/audit accessible without auth!"
    
    @pytest.mark.asyncio
    async def test_admin_config_netcup_requires_auth(self, browser):
        """Netcup config redirects to login."""
        await browser.goto(settings.url('/admin/config/netcup'))
        
        current_url = browser.current_url
        assert '/admin/login' in current_url, \
            f"SECURITY: /admin/config/netcup accessible without auth!"
    
    @pytest.mark.asyncio
    async def test_admin_config_email_requires_auth(self, browser):
        """Email config redirects to login."""
        await browser.goto(settings.url('/admin/config/email'))
        
        current_url = browser.current_url
        assert '/admin/login' in current_url, \
            f"SECURITY: /admin/config/email accessible without auth!"
    
    @pytest.mark.asyncio
    async def test_admin_system_requires_auth(self, browser):
        """System info redirects to login."""
        await browser.goto(settings.url('/admin/system'))
        
        current_url = browser.current_url
        assert '/admin/login' in current_url, \
            f"SECURITY: /admin/system accessible without auth!"
    
    @pytest.mark.asyncio
    async def test_admin_routes_bulk(self, browser, admin_routes, screenshot_helper):
        """Test all admin routes in bulk for efficiency."""
        ss = screenshot_helper('00-auth')
        failed_routes = []
        
        for route in admin_routes:
            await browser.goto(settings.url(route))
            current_url = browser.current_url
            
            if '/admin/login' not in current_url:
                failed_routes.append(route)
        
        if failed_routes:
            await ss.capture('auth-failures', f'Routes accessible without auth: {failed_routes}')
        
        assert not failed_routes, \
            f"SECURITY: These admin routes are accessible without auth: {failed_routes}"


class TestAuthEnforcementAccount:
    """Verify all account portal routes require authentication."""
    
    @pytest_asyncio.fixture(autouse=True)
    async def setup(self, browser):
        """Ensure we start unauthenticated."""
        await browser.goto(settings.url('/account/logout'))
        import asyncio
        await browser.wait_for_timeout(300)
    
    @pytest.mark.asyncio
    async def test_account_dashboard_requires_auth(self, browser, screenshot_helper):
        """Account dashboard redirects to login."""
        ss = screenshot_helper('00-auth')
        
        await browser.goto(settings.url('/account/dashboard'))
        await ss.capture('account-dashboard-redirect', 'Account dashboard redirects to login')
        
        current_url = browser.current_url
        assert '/account/login' in current_url, \
            f"Account dashboard accessible without auth! URL: {current_url}"
    
    @pytest.mark.asyncio
    async def test_account_routes_bulk(self, browser, account_routes):
        """Test all account routes in bulk."""
        failed_routes = []
        
        for route in account_routes:
            await browser.goto(settings.url(route))
            current_url = browser.current_url
            
            if '/account/login' not in current_url:
                failed_routes.append(route)
        
        assert not failed_routes, \
            f"SECURITY: These account routes are accessible without auth: {failed_routes}"


class TestAuthEnforcementAPI:
    """Verify all API routes require Bearer token."""
    
    @pytest.mark.asyncio
    async def test_api_dns_requires_token(self, api_client, screenshot_helper):
        """API DNS endpoint returns 401 without token."""
        response = api_client.get('/api/dns/example.com/records')
        
        assert response.status_code == 401, \
            f"SECURITY: /api/dns accessible without token! Status: {response.status_code}"
    
    @pytest.mark.asyncio
    async def test_api_ddns_requires_token(self, api_client):
        """API DDNS endpoint returns 401 without token."""
        response = api_client.post('/api/ddns/example.com/home')
        
        assert response.status_code == 401, \
            f"SECURITY: /api/ddns accessible without token! Status: {response.status_code}"
    
    @pytest.mark.asyncio
    async def test_api_with_invalid_token(self, api_client):
        """API rejects invalid Bearer token."""
        response = api_client.get(
            '/api/dns/example.com/records',
            headers={'Authorization': 'Bearer invalid-token-12345'}
        )
        
        assert response.status_code == 401, \
            f"SECURITY: API accepts invalid token! Status: {response.status_code}"
    
    @pytest.mark.asyncio
    async def test_api_routes_bulk(self, api_client, api_routes):
        """Test all API routes in bulk."""
        failed_routes = []
        
        for route in api_routes:
            response = api_client.get(route)
            if response.status_code != 401:
                failed_routes.append((route, response.status_code))
        
        assert not failed_routes, \
            f"SECURITY: These API routes don't require auth: {failed_routes}"


class TestPublicRoutesAccessible:
    """Verify public routes ARE accessible without auth."""
    
    @pytest.mark.asyncio
    async def test_admin_login_accessible(self, browser, screenshot_helper):
        """Admin login page is accessible."""
        ss = screenshot_helper('00-auth')
        
        await browser.goto(settings.url('/admin/login'))
        await ss.capture('admin-login-public', 'Admin login page accessible')
        
        current_url = browser.current_url
        assert '/admin/login' in current_url, "Admin login should be accessible"
        
        # Verify login form elements exist
        username_field = await browser.query_selector('#username')
        password_field = await browser.query_selector('#password')
        assert username_field, "Login form missing username field"
        assert password_field, "Login form missing password field"
    
    @pytest.mark.asyncio
    async def test_account_login_accessible(self, browser, screenshot_helper):
        """Account login page is accessible."""
        ss = screenshot_helper('00-auth')
        
        await browser.goto(settings.url('/account/login'))
        await ss.capture('account-login-public', 'Account login page accessible')
        
        # Should stay on login page, not redirect
        current_url = browser.current_url
        assert '/account/login' in current_url, "Account login should be accessible"
    
    @pytest.mark.asyncio
    async def test_account_register_accessible(self, browser, screenshot_helper):
        """Account registration page is accessible."""
        ss = screenshot_helper('00-auth')
        
        await browser.goto(settings.url('/account/register'))
        await ss.capture('account-register-public', 'Account registration page accessible')
        
        current_url = browser.current_url
        # Should be on register page (or redirect to login if registration disabled)
        assert '/account/register' in current_url or '/account/login' in current_url
    
    @pytest.mark.asyncio
    async def test_forgot_password_accessible(self, browser, screenshot_helper):
        """Forgot password page is accessible."""
        ss = screenshot_helper('00-auth')
        
        await browser.goto(settings.url('/account/forgot-password'))
        await ss.capture('forgot-password-public', 'Forgot password page accessible')
        
        current_url = browser.current_url
        assert '/account/forgot-password' in current_url or '/account/login' in current_url
    
    @pytest.mark.asyncio
    async def test_health_endpoint_accessible(self, api_client):
        """Health endpoint is accessible without auth."""
        response = api_client.get('/health')
        
        assert response.status_code == 200, \
            f"Health endpoint should be accessible! Status: {response.status_code}"
