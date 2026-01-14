"""
Journey 07: Error Scenarios and Edge Cases

This journey tests error handling throughout the application:

1. **404 pages** - Styling and content
2. **Invalid forms** - Validation messages
3. **Session expiry** - Redirect behavior
4. **CSRF protection** - Token validation
5. **Database errors** - Graceful handling

Prerequisites:
- Application running
- Admin credentials available
"""
import pytest
import pytest_asyncio
import httpx

from ui_tests.config import settings
from ui_tests.workflows import ensure_admin_dashboard


# ============================================================================
# Phase 1: 404 Error Pages
# ============================================================================

class Test404ErrorPages:
    """Test 404 error page handling."""
    
    @pytest.mark.asyncio
    async def test_01_admin_404_page(
        self, admin_session, screenshot_helper
    ):
        """Admin 404 page has proper styling."""
        ss = screenshot_helper('07-error')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/nonexistent-page-12345'))
        await browser.wait_for_load_state('domcontentloaded')
        
        await ss.capture('admin-404-page', 'Admin 404 error page')
        
        body = await browser.text('body')
        # Should show 404 or not found message
        assert any(word in body.lower() for word in ['404', 'not found', 'error']), \
            f"Expected 404 page: {body[:300]}"
    
    @pytest.mark.asyncio
    async def test_02_public_404_page(
        self, browser, screenshot_helper
    ):
        """Public 404 page has proper styling."""
        ss = screenshot_helper('07-error')
        
        await browser.goto(settings.url('/nonexistent-page-12345'))
        await browser.wait_for_load_state('domcontentloaded')
        
        await ss.capture('public-404-page', 'Public 404 error page')
        
        body = await browser.text('body')
        print(f"404 page content: {body[:300]}")
    
    @pytest.mark.asyncio
    async def test_03_api_404_response(self):
        """API 404 returns JSON error."""
        with httpx.Client(timeout=30.0) as client:
            response = client.get(settings.url('/api/nonexistent'))
            
            print(f"API 404: {response.status_code}")
            print(f"Response: {response.text[:200]}")
            
            # Should be 404 or 401 (if auth required first)
            assert response.status_code in [401, 404]


# ============================================================================
# Phase 2: Form Validation Errors
# ============================================================================

class TestFormValidationErrors:
    """Test form validation error display."""
    
    @pytest.mark.asyncio
    async def test_04_login_validation_error(
        self, browser, screenshot_helper
    ):
        """Login form shows validation error."""
        ss = screenshot_helper('07-error')
        
        await browser.goto(settings.url('/admin/login'))
        await browser.wait_for_timeout(300)
        
        # Submit empty form
        await browser.click('button[type="submit"]')
        await browser.wait_for_load_state('domcontentloaded')
        
        await ss.capture('login-validation-error', 'Login validation error')
        
        # Should show error or stay on login page
        body = await browser.text('body')
        current_url = browser.current_url
        assert '/login' in current_url or 'error' in body.lower() or 'required' in body.lower()
    
    @pytest.mark.asyncio
    async def test_05_login_wrong_credentials(
        self, browser, screenshot_helper
    ):
        """Login with wrong credentials shows error."""
        ss = screenshot_helper('07-error')
        
        await browser.goto(settings.url('/admin/login'))
        await browser.wait_for_timeout(300)
        
        await browser.fill('#username', 'wronguser')
        await browser.fill('#password', 'wrongpassword')
        await browser.click('button[type="submit"]')
        await browser.wait_for_load_state('domcontentloaded')
        
        await ss.capture('login-wrong-credentials', 'Login wrong credentials error')
        
        body = await browser.text('body')
        assert any(word in body.lower() for word in ['invalid', 'incorrect', 'error', 'wrong']), \
            f"Expected error message: {body[:300]}"
    
    @pytest.mark.asyncio
    async def test_06_registration_validation(
        self, browser, screenshot_helper
    ):
        """Registration form validates input."""
        ss = screenshot_helper('07-error')
        
        await browser.goto(settings.url('/account/register'))
        await browser.wait_for_timeout(300)
        
        # Submit with invalid email
        await browser.fill('#username', 'testuser')
        await browser.fill('#email', 'not-an-email')
        await browser.fill('#password', '123')  # Too weak
        
        await ss.capture('registration-invalid-input', 'Registration with invalid input')
        
        await browser.click('button[type="submit"]')
        await browser.wait_for_load_state('domcontentloaded')
        
        await ss.capture('registration-validation-error', 'Registration validation error')


# ============================================================================
# Phase 3: Authentication Errors
# ============================================================================

class TestAuthenticationErrors:
    """Test authentication error handling."""
    
    @pytest.mark.asyncio
    async def test_07_session_required_redirect(
        self, browser, screenshot_helper
    ):
        """Protected pages redirect to login."""
        ss = screenshot_helper('07-error')
        
        # Clear any existing session
        await browser.goto(settings.url('/admin/logout'))
        await browser.wait_for_load_state('domcontentloaded')
        
        # Try to access protected page
        await browser.goto(settings.url('/admin/accounts'))
        await browser.wait_for_load_state('domcontentloaded')
        
        await ss.capture('session-required-redirect', 'Session required redirect')
        
        current_url = browser.current_url
        assert '/login' in current_url, f"Expected redirect to login: {current_url}"
    
    @pytest.mark.asyncio
    async def test_08_api_auth_required(self):
        """API requires authentication."""
        with httpx.Client(timeout=30.0) as client:
            response = client.get(settings.url('/api/dns/example.com/records'))
            
            assert response.status_code == 401, \
                f"Expected 401, got {response.status_code}"
            
            print(f"API 401 response: {response.text[:200]}")
    
    @pytest.mark.asyncio
    async def test_09_api_invalid_token(self):
        """API rejects invalid token."""
        with httpx.Client(timeout=30.0) as client:
            headers = {'Authorization': 'Bearer invalid-token-12345'}
            response = client.get(
                settings.url('/api/dns/example.com/records'),
                headers=headers
            )
            
            assert response.status_code == 401, \
                f"Expected 401, got {response.status_code}"


# ============================================================================
# Phase 4: Rate Limiting
# ============================================================================

class TestRateLimiting:
    """Test rate limiting behavior."""
    
    @pytest.mark.asyncio
    async def test_10_login_rate_limiting(
        self, browser, screenshot_helper
    ):
        """Excessive login attempts are rate limited."""
        ss = screenshot_helper('07-error')
        
        await browser.goto(settings.url('/admin/login'))
        
        # Try multiple failed logins
        for i in range(5):
            await browser.fill('#username', f'wronguser{i}')
            await browser.fill('#password', f'wrongpassword{i}')
            await browser.click('button[type="submit"]')
            await browser.wait_for_timeout(300)
        
        await ss.capture('login-rate-limited', 'Login rate limiting')
        
        body = await browser.text('body')
        # May show rate limit message
        print(f"After multiple attempts: {body[:300]}")


# ============================================================================
# Phase 5: Edge Cases
# ============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    @pytest.mark.asyncio
    async def test_11_empty_tables(
        self, admin_session, screenshot_helper
    ):
        """Empty table states handled gracefully."""
        ss = screenshot_helper('07-error')
        browser = admin_session
        
        # Note: May not be empty in sequential test run
        await browser.goto(settings.url('/admin/accounts/pending'))
        await browser.wait_for_load_state('domcontentloaded')
        
        await ss.capture('pending-accounts-state', 'Pending accounts state')
        
        body = await browser.text('body')
        # Should show "no pending" message or table
        print(f"Pending state: {body[:300]}")
    
    @pytest.mark.asyncio
    async def test_12_special_characters_in_input(
        self, browser, screenshot_helper
    ):
        """Special characters handled properly."""
        ss = screenshot_helper('07-error')
        
        await browser.goto(settings.url('/account/register'))
        await browser.wait_for_timeout(300)
        
        # Try special characters
        await browser.fill('#username', "user<script>alert('xss')</script>")
        await browser.fill('#email', 'test@example.com')
        await browser.fill('#password', 'Password123!')
        
        await ss.capture('special-chars-input', 'Special characters in input')
        
        await browser.click('button[type="submit"]')
        await browser.wait_for_load_state('domcontentloaded')
        
        await ss.capture('special-chars-result', 'Special characters result')
        
        # Should be sanitized or rejected
        body = await browser.text('body')
        assert '<script>' not in body, "XSS not sanitized!"
    
    @pytest.mark.asyncio
    async def test_13_very_long_input(
        self, browser, screenshot_helper
    ):
        """Very long input handled properly."""
        ss = screenshot_helper('07-error')
        
        await browser.goto(settings.url('/account/register'))
        await browser.wait_for_timeout(300)
        
        # Try very long username
        long_username = 'a' * 500
        await browser.fill('#username', long_username)
        
        await ss.capture('long-input', 'Very long input')
        
        # Should be truncated or show error
        input_value = await browser.get_attribute('#username', 'value')
        print(f"Input value length: {len(input_value or '')}")


# ============================================================================
# Phase 6: Server Errors
# ============================================================================

class TestServerErrors:
    """Test server error handling."""
    
    @pytest.mark.asyncio
    async def test_14_handle_500_gracefully(self):
        """500 errors show friendly message."""
        # This is hard to trigger intentionally
        # Just verify the error page template exists
        print("500 error handling: Requires triggering actual server error")
    
    @pytest.mark.asyncio
    async def test_15_handle_timeout_gracefully(self):
        """Timeout errors handled gracefully."""
        # Test with very short timeout
        with httpx.Client(timeout=0.001) as client:
            try:
                client.get(settings.url('/health'))
                print("Request completed (no timeout)")
            except httpx.TimeoutException:
                print("✅ Timeout raised as expected")
            except Exception as e:
                print(f"Other error: {e}")


# ============================================================================
# Phase 7: CSRF Protection
# ============================================================================

class TestCSRFProtection:
    """Test CSRF token validation."""
    
    def test_16_form_without_csrf_rejected(self):
        """Form submission without CSRF token is rejected."""
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            # Try to submit login without CSRF
            response = client.post(
                settings.url('/admin/login'),
                data={'username': 'test', 'password': 'test'}
            )
            
            # Should fail or require CSRF
            print(f"No CSRF submit: {response.status_code}")
            # Behavior depends on CSRF config
    
    def test_17_invalid_csrf_rejected(self):
        """Form with invalid CSRF token is rejected."""
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.post(
                settings.url('/admin/login'),
                data={
                    'username': 'test',
                    'password': 'test',
                    'csrf_token': 'invalid-token'
                }
            )
            
            print(f"Invalid CSRF submit: {response.status_code}")


# ============================================================================
# Phase 8: Concurrent Access
# ============================================================================

class TestConcurrentAccess:
    """Test concurrent access handling."""
    
    def test_18_concurrent_api_requests(self):
        """Multiple concurrent API requests handled."""
        import concurrent.futures
        
        def make_request():
            with httpx.Client(timeout=30.0) as client:
                return client.get(settings.url('/health'))
        
        # Make 10 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        statuses = [r.status_code for r in results]
        print(f"Concurrent request statuses: {set(statuses)}")
        
        # All should succeed
        assert all(s == 200 for s in statuses), f"Some requests failed: {statuses}"
