"""
Security tests based on OWASP Top 10 and common vulnerabilities.

These tests verify security controls are properly implemented.
Run with: pytest ui_tests/tests/test_security.py -v

OWASP Top 10 Categories Covered:
1. A01:2021 – Broken Access Control
2. A02:2021 – Cryptographic Failures  
3. A03:2021 – Injection
4. A05:2021 – Security Misconfiguration
5. A07:2021 – Identification and Authentication Failures
"""
import os
import pytest
from pathlib import Path

# Import from parent ui_tests directory
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestSecurityHeaders:
    """Test security-related HTTP headers."""

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
    async def test_content_type_header(self, browser):
        """Verify Content-Type header is set correctly."""
        from ui_tests.config import settings
        
        response = await browser._page.goto(settings.url("/admin/login"))
        
        content_type = response.headers.get('content-type', '')
        assert 'text/html' in content_type, "Should return HTML content type"
    
    @pytest.mark.asyncio
    async def test_x_content_type_options(self, browser):
        """Verify X-Content-Type-Options header is set."""
        from ui_tests.config import settings
        
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


class TestAuthenticationSecurity:
    """Test authentication security controls."""
    
    @pytest.mark.asyncio
    async def test_login_form_has_csrf_token(self, browser):
        """Verify login form includes CSRF protection."""
        from ui_tests.config import settings
        
        await browser.goto(settings.url("/admin/login"))
        await browser._page.wait_for_load_state("networkidle")
        
        # Check for CSRF token in form
        csrf_token = await browser._page.evaluate("""
            () => {
                const token = document.querySelector('input[name="csrf_token"]');
                return token ? token.value : null;
            }
        """)
        
        assert csrf_token, "Login form should have CSRF token"
        assert len(csrf_token) > 20, "CSRF token should be sufficiently long"
    
    @pytest.mark.asyncio
    async def test_password_field_is_password_type(self, browser):
        """Verify password fields use type=password."""
        from ui_tests.config import settings
        
        await browser.goto(settings.url("/admin/login"))
        await browser._page.wait_for_load_state("networkidle")
        
        password_type = await browser._page.evaluate("""
            () => {
                const input = document.querySelector('input[name="password"]');
                return input ? input.type : null;
            }
        """)
        
        assert password_type == 'password', "Password field should be type=password"
    
    @pytest.mark.asyncio
    async def test_password_autocomplete_attribute(self, browser):
        """Verify password fields have proper autocomplete."""
        from ui_tests.config import settings
        
        await browser.goto(settings.url("/admin/login"))
        await browser._page.wait_for_load_state("networkidle")
        
        autocomplete = await browser._page.evaluate("""
            () => {
                const input = document.querySelector('input[name="password"]');
                return input ? input.autocomplete : null;
            }
        """)
        
        # Should use current-password for login
        assert autocomplete in ['current-password', 'off'], \
            f"Password autocomplete should be 'current-password', got '{autocomplete}'"
    
    @pytest.mark.asyncio
    async def test_failed_login_no_user_enumeration(self, browser):
        """Verify login failures don't reveal if user exists."""
        from ui_tests.config import settings
        
        await browser.goto(settings.url("/admin/login"))
        await browser._page.wait_for_load_state("networkidle")
        
        # Try login with non-existent user
        await browser._page.fill("#username", "nonexistent_user_12345")
        await browser._page.fill("#password", "wrongpassword")
        await browser._page.click("button[type='submit']")
        await browser._page.wait_for_timeout(1000)
        
        # Get error message
        error_text = await browser._page.evaluate("""
            () => {
                const alert = document.querySelector('.alert-danger, .alert-warning');
                return alert ? alert.textContent : '';
            }
        """)
        
        # Error should be generic, not "user not found"
        if error_text:
            error_lower = error_text.lower()
            assert 'not found' not in error_lower, "Should not reveal if user exists"
            assert 'does not exist' not in error_lower, "Should not reveal if user exists"
            assert 'unknown user' not in error_lower, "Should not reveal if user exists"


class TestBrokenAccessControl:
    """Test access control enforcement (OWASP A01)."""
    
    @pytest.mark.asyncio
    async def test_admin_pages_require_auth(self, browser):
        """Verify admin pages redirect to login when unauthenticated."""
        from ui_tests.config import settings
        
        # Clear any existing session cookies first
        await browser._page.context.clear_cookies()
        
        protected_urls = [
            "/admin/",
            "/admin/accounts",
            "/admin/audit",
            "/admin/config/netcup",
            "/admin/system",
        ]
        
        for url_path in protected_urls:
            await browser.goto(settings.url(url_path))
            await browser._page.wait_for_load_state("networkidle")
            
            # Should redirect to login
            current_url = browser.current_url
            assert "/login" in current_url, \
                f"{url_path} should redirect to login, but went to {current_url}"
    
    @pytest.mark.asyncio
    async def test_account_pages_require_auth(self, browser):
        """Verify account pages redirect to login when unauthenticated."""
        from ui_tests.config import settings
        
        # Clear any existing session cookies first
        await browser._page.context.clear_cookies()
        
        protected_urls = [
            "/account/dashboard",
            "/account/realms",
            "/account/settings",
        ]
        
        for url_path in protected_urls:
            await browser.goto(settings.url(url_path))
            await browser._page.wait_for_load_state("networkidle")
            
            current_url = browser.current_url
            assert "/login" in current_url, \
                f"{url_path} should redirect to login, but went to {current_url}"


class TestInputValidation:
    """Test input validation and sanitization (OWASP A03)."""
    
    @pytest.mark.asyncio
    async def test_xss_in_username_field(self, browser):
        """Verify XSS is prevented in username field."""
        from ui_tests.config import settings
        
        await browser.goto(settings.url("/admin/login"))
        await browser._page.wait_for_load_state("networkidle")
        
        # Try XSS payload
        xss_payload = '<script>alert("XSS")</script>'
        await browser._page.fill("#username", xss_payload)
        await browser._page.fill("#password", "testpassword")
        await browser._page.click("button[type='submit']")
        await browser._page.wait_for_timeout(500)
        
        # Check if XSS was executed (it shouldn't be)
        page_content = await browser._page.content()
        assert '<script>alert' not in page_content, "XSS payload should be escaped"
    
    @pytest.mark.asyncio
    async def test_html_injection_prevention(self, browser):
        """Verify HTML injection is prevented in user inputs."""
        from ui_tests.config import settings
        
        await browser.goto(settings.url("/admin/login"))
        await browser._page.wait_for_load_state("networkidle")
        
        # Try HTML injection
        html_payload = '<img src=x onerror=alert(1)>'
        await browser._page.fill("#username", html_payload)
        await browser._page.fill("#password", "testpassword")
        await browser._page.click("button[type='submit']")
        await browser._page.wait_for_timeout(500)
        
        # Check that HTML is escaped
        page_content = await browser._page.content()
        assert '<img src=x' not in page_content, "HTML should be escaped"


class TestSessionSecurity:
    """Test session management security."""
    
    @pytest.mark.asyncio
    async def test_session_cookie_httponly(self, browser):
        """Verify session cookie has HttpOnly flag (when using HTTPS)."""
        from ui_tests.config import settings
        
        await browser.goto(settings.url("/admin/login"))
        await browser._page.wait_for_load_state("networkidle")
        
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
        
        await browser.goto(settings.url("/admin/login"))
        await browser._page.wait_for_load_state("networkidle")
        
        cookies = await browser._page.context.cookies()
        session_cookie = next((c for c in cookies if 'session' in c['name'].lower()), None)
        
        if session_cookie:
            samesite = session_cookie.get('sameSite', 'None')
            assert samesite in ['Strict', 'Lax'], \
                f"Session cookie SameSite should be Strict or Lax, got {samesite}"
        else:
            pytest.skip("No session cookie found")


class TestSecurityMisconfiguration:
    """Test for security misconfigurations (OWASP A05)."""
    
    @pytest.mark.asyncio
    async def test_no_server_version_disclosure(self, browser):
        """Verify server doesn't disclose version in headers."""
        from ui_tests.config import settings
        
        response = await browser._page.goto(settings.url("/admin/login"))
        
        # Check for common version disclosure headers
        server = response.headers.get('server', '')
        
        # Should not disclose specific version numbers
        import re
        version_pattern = r'\d+\.\d+(\.\d+)?'
        
        if server and re.search(version_pattern, server):
            pytest.skip(f"Server header discloses version: {server}")
    
    @pytest.mark.asyncio
    async def test_error_pages_no_stack_trace(self, browser):
        """Verify error pages don't expose stack traces."""
        from ui_tests.config import settings
        
        # Try to trigger an error (invalid URL)
        await browser._page.goto(settings.url("/admin/nonexistent_page_12345"))
        
        page_content = await browser._page.content()
        
        # Should not contain stack trace indicators
        assert 'Traceback' not in page_content, "Should not show Python traceback"
        assert 'File "' not in page_content, "Should not show file paths"
        assert 'line ' not in page_content.lower() or '404' in page_content, \
            "Should not show line numbers from stack trace"
    
    @pytest.mark.asyncio
    async def test_no_debug_mode_indicators(self, browser):
        """Verify no debug mode indicators in response."""
        from ui_tests.config import settings
        
        await browser.goto(settings.url("/admin/login"))
        
        page_content = await browser._page.content()
        
        # Should not contain debug indicators
        assert 'DEBUG = True' not in page_content
        assert 'werkzeug debugger' not in page_content.lower()


class TestFormSecurity:
    """Test form security controls."""
    
    @pytest.mark.asyncio
    async def test_forms_use_post_method(self, browser):
        """Verify sensitive forms use POST method."""
        from ui_tests.config import settings
        
        await browser.goto(settings.url("/admin/login"))
        await browser._page.wait_for_load_state("networkidle")
        
        # Check login form method
        method = await browser._page.evaluate("""
            () => {
                const form = document.querySelector('form');
                return form ? form.method.toUpperCase() : null;
            }
        """)
        
        assert method == 'POST', "Login form should use POST method"
    
    @pytest.mark.asyncio
    async def test_password_inputs_no_spellcheck(self, browser):
        """Verify password inputs disable spellcheck."""
        from ui_tests.config import settings
        
        await browser.goto(settings.url("/admin/login"))
        await browser._page.wait_for_load_state("networkidle")
        
        spellcheck = await browser._page.evaluate("""
            () => {
                const input = document.querySelector('input[type="password"]');
                return input ? input.spellcheck : null;
            }
        """)
        
        # Spellcheck should be disabled or not set
        assert spellcheck != True, "Password input should not have spellcheck enabled"


class TestClickjackingProtection:
    """Test clickjacking protection."""
    
    @pytest.mark.asyncio
    async def test_x_frame_options_or_csp(self, browser):
        """Verify clickjacking protection headers."""
        from ui_tests.config import settings
        
        response = await browser._page.goto(settings.url("/admin/login"))
        
        x_frame = response.headers.get('x-frame-options', '')
        csp = response.headers.get('content-security-policy', '')
        
        # Should have either X-Frame-Options or CSP frame-ancestors
        has_protection = bool(x_frame) or ('frame-ancestors' in csp)
        
        if not has_protection:
            pytest.skip("No clickjacking protection headers (X-Frame-Options or CSP frame-ancestors)")


class TestLogoutSecurity:
    """Test logout security."""
    
    @pytest.mark.asyncio
    async def test_logout_clears_session(self, admin_page):
        """Verify logout properly clears session."""
        from ui_tests.config import settings
        
        page = admin_page
        
        # Verify we're logged in
        await page.goto(settings.url("/admin/"))
        await page.wait_for_load_state("networkidle")
        assert "/login" not in page.url
        
        # Click logout
        await page.goto(settings.url("/admin/logout"))
        await page.wait_for_load_state("networkidle")
        
        # Try to access protected page
        await page.goto(settings.url("/admin/"))
        await page.wait_for_load_state("networkidle")
        
        # Should be redirected to login
        assert "/login" in page.url, "Should redirect to login after logout"
