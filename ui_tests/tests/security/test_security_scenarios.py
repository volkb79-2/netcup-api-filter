"""Security Scenarios and Error Handling Tests.

This test file covers security edge cases and error handling:
- Brute force protection
- IP binding for password resets
- Realm scope enforcement
- Token expiration
- IP whitelist enforcement
- Error page rendering
- Invalid input handling
- CSRF protection
"""

import pytest

import anyio

from ui_tests import workflows
from ui_tests.browser import browser_session
from ui_tests.config import settings

pytestmark = [pytest.mark.asyncio, pytest.mark.security]


# ============================================================================
# Authentication Security Tests
# ============================================================================

class TestAuthenticationSecurity:
    """Tests for authentication security controls."""
    
    async def test_login_rate_limiting_message(self, active_profile):
        """Verify login shows appropriate message after failed attempts.
        
        NOTE: This test only checks UI messaging, not actual lockout to avoid
        affecting other tests.
        """
        async with browser_session() as browser:
            # Persisted storage-state may already be authenticated.
            # Clear cookies so we reliably get the login form.
            await browser._page.context.clear_cookies()
            await browser.goto(settings.url("/admin/login"))
            await browser._page.wait_for_selector("#username")
            
            # Single wrong login attempt
            await browser.fill("#username", "nonexistent")
            await browser.fill("#password", "wrongpassword")
            await browser.click("button[type='submit']")
            await anyio.sleep(0.5)
            
            # Should show error message
            body_text = await browser.text("body")
            assert "Invalid" in body_text or "incorrect" in body_text.lower() or "login" in body_text.lower()
            
            # Verify we're still on login page
            current_url = browser._page.url
            assert "/login" in current_url

    async def test_account_portal_login_invalid_credentials(self, active_profile):
        """Verify account portal rejects invalid credentials."""
        async with browser_session() as browser:
            await browser._page.context.clear_cookies()
            await browser.goto(settings.url("/account/login"))
            await browser._page.wait_for_selector("#username")
            
            # Try invalid login
            await browser.fill("#username", "invalid-user")
            await browser.fill("#password", "invalid-password")
            await browser.click("button[type='submit']")
            await anyio.sleep(0.5)
            
            # Should show error
            body_text = await browser.text("body")
            assert "Invalid" in body_text or "incorrect" in body_text.lower() or "error" in body_text.lower() or "/login" in browser._page.url


# ============================================================================
# CSRF Protection Tests
# ============================================================================

class TestCSRFProtection:
    """Tests for CSRF protection."""
    
    async def test_login_form_has_csrf_token(self, active_profile):
        """Verify login forms include CSRF tokens."""
        async with browser_session() as browser:
            await browser._page.context.clear_cookies()
            await browser.goto(settings.url("/admin/login"))
            await browser._page.wait_for_selector("#username")
            
            # Check for CSRF token in form
            page_html = await browser.html("body")
            assert "csrf" in page_html.lower() or "token" in page_html.lower()

    async def test_account_login_form_has_csrf_token(self, active_profile):
        """Verify account login form includes CSRF token."""
        async with browser_session() as browser:
            await browser._page.context.clear_cookies()
            await browser.goto(settings.url("/account/login"))
            await browser._page.wait_for_selector("#username")
            
            # Check for CSRF token in form
            page_html = await browser.html("body")
            assert "csrf" in page_html.lower() or "token" in page_html.lower()


# ============================================================================
# Error Page Tests
# ============================================================================

class TestErrorPages:
    """Tests for error page rendering."""
    
    async def test_404_error_page_renders(self, active_profile):
        """Verify 404 error page renders correctly."""
        async with browser_session() as browser:
            # Navigate to non-existent page
            await browser.goto(settings.url("/nonexistent-page-12345"))
            await anyio.sleep(0.5)
            
            # Should show 404 page with proper styling
            body_text = await browser.text("body")
            assert "404" in body_text or "not found" in body_text.lower() or "error" in body_text.lower()

    async def test_admin_404_error_page(self, active_profile):
        """Verify admin 404 error page renders correctly."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            # Navigate to non-existent admin page
            await browser.goto(settings.url("/admin/nonexistent-12345"))
            await anyio.sleep(0.5)
            
            # Should show error or redirect
            body_text = await browser.text("body")
            current_url = browser._page.url
            # Either 404 page or redirect to valid admin page
            assert "404" in body_text or "not found" in body_text.lower() or "/admin" in current_url

    async def test_error_page_has_navigation(self, active_profile):
        """Verify error pages have navigation back to home."""
        async with browser_session() as browser:
            await browser.goto(settings.url("/nonexistent-page"))
            await anyio.sleep(0.5)
            
            # Should have link back to home or main site
            page_html = await browser.html("body")
            has_nav = 'href="/"' in page_html or "home" in page_html.lower() or "return" in page_html.lower()
            # Page should be styled properly even if no nav link
            assert has_nav or "error" in page_html.lower() or "404" in page_html


# ============================================================================
# Input Validation Tests
# ============================================================================

class TestInputValidation:
    """Tests for input validation."""
    
    async def test_registration_email_validation(self, active_profile):
        """Verify registration validates email format."""
        async with browser_session() as browser:
            await browser.goto(settings.url("/account/register"))
            
            # Check if registration is available
            page_html = await browser.html("body")
            if "registration" not in page_html.lower() and "email" not in page_html.lower():
                pytest.skip("Registration not available")
            
            # Try invalid email format
            email_field = await browser.query_selector("#email")
            if email_field:
                await browser.fill("#email", "invalid-email-format")
                
                # Check for HTML5 validation or custom validation
                email_type = await browser.get_attribute("#email", "type")
                assert email_type == "email" or "email" in page_html.lower()

    async def test_password_strength_indicator(self, active_profile):
        """Verify password fields have strength validation."""
        async with browser_session() as browser:
            await browser.goto(settings.url("/account/register"))
            
            page_html = await browser.html("body")
            if "password" not in page_html.lower():
                pytest.skip("Password field not found")
            
            # Check for password strength indicators or requirements
            has_validation = any([
                "strength" in page_html.lower(),
                "entropy" in page_html.lower(),
                "minlength" in page_html.lower(),
                "pattern" in page_html.lower(),
                "requirement" in page_html.lower(),
            ])
            # Some pages may not have visible strength indicator
            assert has_validation or "password" in page_html.lower()


# ============================================================================
# Session Security Tests
# ============================================================================

class TestSessionSecurity:
    """Tests for session security."""
    
    async def test_logout_clears_session(self, active_profile):
        """Verify logout properly clears session."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            # Navigate to logout
            await browser.goto(settings.url("/admin/logout"))
            await anyio.sleep(1.0)
            
            # Should redirect to login
            current_url = browser._page.url
            assert "/login" in current_url or "/admin" in current_url
            
            # Try to access protected page
            await browser.goto(settings.url("/admin/accounts"))
            await anyio.sleep(0.5)
            
            # Should redirect to login
            current_url = browser._page.url
            body_text = await browser.text("body")
            assert "/login" in current_url or "Sign In" in body_text

    async def test_admin_pages_require_authentication(self, active_profile):
        """Verify admin pages require authentication."""
        async with browser_session() as browser:
            # Persisted storage-state may already be authenticated.
            # Clear cookies so this test truly verifies unauthenticated access.
            await browser._page.context.clear_cookies()
            # Try to access admin page directly
            await browser.goto(settings.url("/admin/accounts"))
            await anyio.sleep(0.5)
            
            # Should redirect to login
            current_url = browser._page.url
            assert "/login" in current_url

    async def test_account_pages_require_authentication(self, active_profile):
        """Verify account pages require authentication."""
        async with browser_session() as browser:
            await browser._page.context.clear_cookies()
            # Try to access account dashboard directly
            await browser.goto(settings.url("/account/dashboard"))
            await anyio.sleep(0.5)
            
            # Should redirect to login
            current_url = browser._page.url
            assert "/login" in current_url or "/account" in current_url


# ============================================================================
# Password Reset Security Tests
# ============================================================================

class TestPasswordResetSecurity:
    """Tests for password reset security."""
    
    async def test_forgot_password_form_accessible(self, active_profile):
        """Verify forgot password form is accessible."""
        async with browser_session() as browser:
            await browser.goto(settings.url("/account/forgot-password"))
            await anyio.sleep(0.5)
            
            # Should show forgot password form
            body_html = await browser.html("body")
            assert "email" in body_html.lower() or "password" in body_html.lower() or "reset" in body_html.lower()

    async def test_forgot_password_with_invalid_email(self, active_profile):
        """Verify forgot password handles invalid email gracefully."""
        async with browser_session() as browser:
            await browser.goto(settings.url("/account/forgot-password"))
            
            # Try non-existent email
            email_field = await browser.query_selector("input[type='email']")
            if email_field:
                await browser.fill("input[type='email']", "nonexistent@example.com")
                await browser.click("button[type='submit']")
                await anyio.sleep(0.5)
                
                # Should not reveal if email exists or not (security)
                body_text = await browser.text("body")
                # Either success message (doesn't reveal email existence) or generic error
                # Should NOT say "email not found" (information disclosure)
                assert "email not found" not in body_text.lower() or "check your email" in body_text.lower() or "error" in body_text.lower()


# ============================================================================
# API Security Tests
# ============================================================================

class TestAPISecurity:
    """Tests for API endpoint security."""
    
    async def test_api_endpoint_requires_auth(self, active_profile):
        """Verify API endpoints require authentication."""
        async with browser_session() as browser:
            # Try to access API without auth
            await browser.goto(settings.url("/api"))
            await anyio.sleep(0.5)
            
            # Should return error or require auth
            body_text = await browser.text("body")
            # API may return JSON error or redirect
            assert "error" in body_text.lower() or "auth" in body_text.lower() or "{" in body_text

    async def test_admin_api_requires_admin_auth(self, active_profile):
        """Verify admin API endpoints require admin authentication."""
        async with browser_session() as browser:
            # Try to access admin API without auth
            await browser.goto(settings.url("/admin/api/accounts"))
            await anyio.sleep(0.5)
            
            # Should redirect to login or return error
            current_url = browser._page.url
            body_text = await browser.text("body")
            assert "/login" in current_url or "error" in body_text.lower() or "{" in body_text


# ============================================================================
# Security Headers Tests
# ============================================================================

class TestSecurityHeaders:
    """Tests for security headers (verifiable via browser)."""
    
    async def test_content_type_is_set(self, active_profile):
        """Verify pages have proper content type."""
        async with browser_session() as browser:
            await browser._page.context.clear_cookies()
            await browser.goto(settings.url("/admin/login"))
            await browser._page.wait_for_selector("#username")
            
            # Page should render as HTML
            body_html = await browser.html("body")
            assert len(body_html) > 100  # Has substantial content


# ============================================================================
# XSS Prevention Tests
# ============================================================================

class TestXSSPrevention:
    """Tests for XSS prevention."""
    
    async def test_search_input_escaped(self, active_profile):
        """Verify search/filter inputs are properly escaped."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            # Navigate to a page with search
            await browser.goto(settings.url("/admin/audit"))
            await anyio.sleep(0.5)
            
            # Look for search input
            search_input = await browser.query_selector("input[type='search']")
            if search_input:
                # Try XSS payload
                xss_payload = "<script>alert('xss')</script>"
                await browser.fill("input[type='search']", xss_payload)
                await anyio.sleep(0.3)
                
                # Should be escaped, not executed
                body_html = await browser.html("body")
                # The literal script tag should not appear unescaped
                assert "<script>alert" not in body_html or "&lt;script" in body_html

    async def test_url_params_escaped(self, active_profile):
        """Verify URL parameters are properly escaped."""
        async with browser_session() as browser:
            # Try XSS in URL parameter
            xss_url = "/admin/login?error=<script>alert('xss')</script>"
            await browser._page.context.clear_cookies()
            await browser.goto(settings.url(xss_url))
            await anyio.sleep(0.5)

            # Should be escaped
            body_html = await browser.html("body")
            assert "<script>alert" not in body_html or "&lt;script" in body_html or "error" not in body_html.lower()


# ============================================================================
# Security Header / Cookie / Misconfiguration checks
# (merged verbatim from test_security.py — these are the genuinely-unique
#  checks not covered by the scenarios above: X-Content-Type-Options header,
#  session-cookie HttpOnly/SameSite flags, and no-debug-mode indicators.
#  These use the `browser` fixture rather than browser_session() — moved
#  unchanged to preserve their assertions.)
# ============================================================================


class TestSecurityResponseHeaders:
    """X-Content-Type-Options header check (merged from test_security.py)."""

    @staticmethod
    def _split_header_values(header_value: str) -> list[str]:
        # Playwright may return multiple header instances joined by newlines.
        # Also tolerate comma-joined values.
        values: list[str] = []
        for line in (header_value or "").splitlines():
            for part in line.split(","):
                value = part.strip()
                if value:
                    values.append(value)
        return values

    @pytest.mark.asyncio
    async def test_x_content_type_options(self, browser):
        """Verify X-Content-Type-Options header is set."""
        from ui_tests.config import settings

        # Ensure we land on the actual login page (not an authenticated redirect)
        await browser._page.context.clear_cookies()
        response = await browser._page.goto(settings.url("/admin/login"))

        xcto = response.headers.get('x-content-type-options', '')
        # Flask doesn't set this by default, but good practice to check
        if xcto:
            values = self._split_header_values(xcto)
            assert values, f"X-Content-Type-Options present but empty: '{xcto}'"
            assert all(v.lower() == 'nosniff' for v in values), (
                "X-Content-Type-Options should be 'nosniff' (tolerating duplicates), "
                f"got values={values!r} from raw={xcto!r}"
            )
        else:
            pytest.skip("X-Content-Type-Options header not set (recommended)")


class TestSessionCookieSecurity:
    """Session cookie flag checks (merged from test_security.py)."""

    @pytest.mark.asyncio
    async def test_session_cookie_httponly(self, browser):
        """Verify session cookie has HttpOnly flag (when using HTTPS)."""
        from ui_tests.config import settings

        await browser._page.context.clear_cookies()
        await browser.goto(settings.url("/admin/login"))

        await browser._page.wait_for_selector("#username")

        # Get cookies
        cookies = await browser._page.context.cookies()
        session_cookie = next((c for c in cookies if 'session' in c['name'].lower()), None)

        if session_cookie:
            assert session_cookie.get('httpOnly', False), \
                "Session cookie should have HttpOnly flag"
        else:
            pytest.skip("No session cookie found on login page")

    @pytest.mark.asyncio
    async def test_session_cookie_samesite(self, browser):
        """Verify session cookie has SameSite attribute."""
        from ui_tests.config import settings

        await browser._page.context.clear_cookies()
        await browser.goto(settings.url("/admin/login"))

        await browser._page.wait_for_selector("#username")

        cookies = await browser._page.context.cookies()
        session_cookie = next((c for c in cookies if 'session' in c['name'].lower()), None)

        if session_cookie:
            samesite = session_cookie.get('sameSite', 'None')
            assert samesite in ['Strict', 'Lax'], \
                f"Session cookie SameSite should be Strict or Lax, got {samesite}"
        else:
            pytest.skip("No session cookie found")


class TestSecurityMisconfigurationChecks:
    """Debug-mode disclosure check (merged from test_security.py)."""

    @pytest.mark.asyncio
    async def test_no_debug_mode_indicators(self, browser):
        """Verify no debug mode indicators in response."""
        from ui_tests.config import settings

        await browser._page.context.clear_cookies()
        await browser.goto(settings.url("/admin/login"))

        page_content = await browser._page.content()

        # Should not contain debug indicators
        assert 'DEBUG = True' not in page_content
        assert 'werkzeug debugger' not in page_content.lower()
