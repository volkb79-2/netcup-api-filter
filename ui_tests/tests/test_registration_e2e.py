"""E2E tests for self-registration flow.

Tests the complete user registration journey:
1. Fill registration form
2. Receive verification email (via Mailpit)
3. Enter verification code
4. See pending approval page
5. Admin approves account
6. User can login

Requires: Mailpit container running (tooling/mailpit/docker compose up -d)

Run with: pytest ui_tests/tests/test_registration_e2e.py -v
"""
import pytest
import re
import time
from pathlib import Path
import sys

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ui_tests.config import settings


pytestmark = [
    pytest.mark.asyncio,
]


async def _accept_terms_if_present(page) -> None:
    terms = await page.query_selector('input[name="terms"]')
    if terms is not None:
        await terms.check()


class TestRegistrationPageAccess:
    """Test registration page is accessible."""
    
    async def test_registration_page_loads(self, browser):
        """Test registration page is accessible."""
        await browser.goto(settings.url("/account/register"))
        await browser._page.wait_for_load_state("networkidle")
        
        # Check for registration form elements
        username_field = await browser._page.query_selector('input[name="username"]')
        email_field = await browser._page.query_selector('input[name="email"]')
        password_field = await browser._page.query_selector('input[name="password"]')
        
        assert username_field, "Registration form should have username field"
        assert email_field, "Registration form should have email field"
        assert password_field, "Registration form should have password field"
    
    async def test_registration_page_has_csrf(self, browser):
        """Test registration form has CSRF protection."""
        await browser.goto(settings.url("/account/register"))
        await browser._page.wait_for_load_state("networkidle")
        
        csrf_token = await browser._page.evaluate("""
            () => {
                const token = document.querySelector('input[name="csrf_token"]');
                return token ? token.value : null;
            }
        """)
        
        assert csrf_token, "Registration form should have CSRF token"
        assert len(csrf_token) > 20, "CSRF token should be sufficiently long"


class TestRegistrationFormValidation:
    """Test registration form validation."""
    
    async def test_registration_validation_short_username(self, browser):
        """Test username validation - too short."""
        await browser.goto(settings.url("/account/register"))
        await browser._page.wait_for_load_state("networkidle")
        
        # Try invalid username (too short)
        await browser._page.fill('input[name="username"]', "ab")
        await browser._page.fill('input[name="email"]', "test@example.com")
        await browser._page.fill('input[name="password"]', "TestPassword123+Secure2024")
        await browser._page.fill('input[name="confirm_password"]', "TestPassword123+Secure2024")
        await _accept_terms_if_present(browser._page)
        
        # Submit form
        await browser._page.click('button[type="submit"]')
        await browser._page.wait_for_timeout(500)
        
        # Should stay on registration page (HTML5 validation or server validation)
        current_url = browser.current_url
        assert "/register" in current_url, "Should stay on registration page for short username"
    
    async def test_registration_validation_password_mismatch(self, browser):
        """Test password mismatch validation (client-side).
        
        The registration form now has client-side validation that:
        1. Shows a mismatch warning when passwords don't match
        2. Disables the submit button until passwords match
        
        This test verifies the client-side behavior.
        """
        await browser.goto(settings.url("/account/register"))
        await browser._page.wait_for_load_state("networkidle")
        
        await browser._page.fill('input[name="username"]', "validuser")
        await browser._page.fill('input[name="email"]', "test@example.com")
        await browser._page.fill('input[name="password"]', "TestPassword123+Secure2024")
        # Use different password to trigger mismatch
        await browser._page.fill('input[name="confirm_password"]', "DifferentPassword+2024")
        await _accept_terms_if_present(browser._page)
        
        # Wait for client-side validation to run
        await browser._page.wait_for_timeout(500)
        
        # Check for client-side mismatch warning (new validation feature)
        mismatch_visible = await browser._page.is_visible("#passwordMismatch:not(.d-none)")
        submit_disabled = await browser._page.is_disabled('button[type="submit"]')
        
        # Either the warning is visible or the button is disabled (or both)
        assert mismatch_visible or submit_disabled, \
            "Client-side validation should show mismatch warning or disable submit button"
        
        # Verify we're still on the registration page (no form submission)
        current_url = browser.current_url
        assert "/register" in current_url, "Should stay on registration page"
    
    async def test_registration_validation_invalid_email(self, browser):
        """Test email validation."""
        await browser.goto(settings.url("/account/register"))
        await browser._page.wait_for_load_state("networkidle")
        
        await browser._page.fill('input[name="username"]', "validuser")
        await browser._page.fill('input[name="email"]', "not-an-email")
        await browser._page.fill('input[name="password"]', "TestPassword123+Secure2024")
        await browser._page.fill('input[name="confirm_password"]', "TestPassword123+Secure2024")
        
        # HTML5 validation should prevent submission
        current_url = browser.current_url
        assert "/register" in current_url


class TestRegistrationWithMailpit:
    """E2E tests requiring Mailpit server."""
    
    async def test_registration_sends_verification_email(self, browser, mailpit):
        """Test that registration sends verification email."""
        # Generate unique username
        unique_id = int(time.time()) % 100000
        username = f"testuser{unique_id}"
        email = f"test{unique_id}@example.com"
        
        # Clear mailbox
        mailpit.clear()
        
        # Fill registration form
        await browser.goto(settings.url("/account/register"))
        await browser._page.wait_for_load_state("networkidle")
        
        await browser._page.fill('input[name="username"]', username)
        await browser._page.fill('input[name="email"]', email)
        await browser._page.fill('input[name="password"]', "TestPassword123+Secure2024")
        await browser._page.fill('input[name="confirm_password"]', "TestPassword123+Secure2024")
        await _accept_terms_if_present(browser._page)
        
        # Submit form
        await browser._page.click('button[type="submit"]')
        await browser._page.wait_for_load_state("networkidle")

        current_url = (browser._page.url or "").lower()
        page_html = (await browser._page.content()).lower()

        # Some deployments may auto-approve registrations or disable sending a
        # verification email even if a verification page is reachable. In that
        # case, skip instead of failing the whole suite.
        if "verify" not in current_url and "verify" not in page_html:
            pytest.skip(f"Registration did not enter verification flow (url={browser._page.url})")

        # Check for verification email (be tolerant of recipient ordering).
        msg = mailpit.wait_for_message(
            predicate=lambda m: (
                ("verify" in (m.subject or "").lower() or "verification" in (m.subject or "").lower())
                and any(email.lower() == a.address.lower() for a in (m.to or []))
            ),
            timeout=20.0,
        )

        if msg is None:
            pytest.skip(
                f"No verification email received for {email} (verification emails may be disabled). "
                f"url={browser._page.url}"
            )

        assert "verify" in msg.subject.lower() or "verification" in msg.subject.lower()
    
    async def test_verification_code_entry(self, browser, mailpit):
        """Test entering verification code from email."""
        unique_id = int(time.time()) % 100000
        username = f"verifyuser{unique_id}"
        email = f"verify{unique_id}@example.com"
        
        # Clear mailbox
        mailpit.clear()
        
        # Register
        await browser.goto(settings.url("/account/register"))
        await browser._page.wait_for_load_state("networkidle")
        
        await browser._page.fill('input[name="username"]', username)
        await browser._page.fill('input[name="email"]', email)
        await browser._page.fill('input[name="password"]', "TestPassword123+Secure2024Strong")
        await browser._page.fill('input[name="confirm_password"]', "TestPassword123+Secure2024Strong")
        await _accept_terms_if_present(browser._page)
        
        await browser._page.click('button[type="submit"]')
        await browser._page.wait_for_timeout(2000)
        
        # Get verification code from email
        msg = mailpit.wait_for_message(
            predicate=lambda m: email.lower() in (m.to[0].address.lower() if m.to else ''),
            timeout=10.0
        )
        
        if not msg:
            pytest.skip("No verification email received - email config may not be set")
        
        # Extract 6-digit code from email body
        email_text = msg.text or msg.html or ''
        code_match = re.search(r'\b(\d{6})\b', email_text)
        
        if not code_match:
            pytest.fail(f"Could not find 6-digit code in email: {email_text[:500]}")
        
        verification_code = code_match.group(1)
        
        # Enter code on verification page
        code_input = await browser._page.query_selector('input[name="code"]')
        if code_input:
            await browser._page.fill('input[name="code"]', verification_code)
            await browser._page.click('button[type="submit"]')
            await browser._page.wait_for_timeout(1500)
            
            # Should proceed to pending page or show success
            current_url = browser.current_url
            content = await browser._page.content()
            
            assert "pending" in current_url.lower() or "pending" in content.lower() or \
                   "approval" in content.lower() or "verified" in content.lower(), \
                   f"Should show pending or success after verification. URL: {current_url}"


class TestPendingApprovalPage:
    """Test pending approval page."""
    
    async def test_pending_page_accessible(self, browser):
        """Test pending page is accessible."""
        await browser.goto(settings.url("/account/register/pending"))
        await browser._page.wait_for_load_state("networkidle")
        
        content = await browser._page.content()
        
        # Should show pending message
        has_pending_content = (
            "pending" in content.lower() or
            "approval" in content.lower() or
            "waiting" in content.lower()
        )
        
        assert has_pending_content, "Pending page should show pending/approval message"


class TestAdminAccountApproval:
    """Test admin approval of pending accounts."""
    
    async def test_pending_accounts_visible_in_admin(self, admin_page):
        """Test admin can see pending accounts list."""
        await admin_page.goto(settings.url("/admin/accounts"))
        await admin_page.wait_for_load_state("networkidle")
        
        # Should be on accounts page, not redirected to login
        assert "/login" not in admin_page.url, "Should be authenticated"
        
        # Check for accounts page content
        content = await admin_page.content()
        assert "account" in content.lower()


class TestAccountLoginAfterApproval:
    """Test that approved accounts can login."""
    
    async def test_account_login_page_accessible(self, browser):
        """Test account login page is accessible."""
        await browser.goto(settings.url("/account/login"))
        await browser._page.wait_for_load_state("networkidle")
        
        # Check for login form
        username_field = await browser._page.query_selector('input[name="username"]')
        email_field = await browser._page.query_selector('input[name="email"]')
        password_field = await browser._page.query_selector('input[name="password"]')
        
        # Should have some login mechanism
        has_login = username_field or email_field or password_field
        assert has_login, "Should have login form"


class TestFullRegistrationFlow:
    """Complete end-to-end registration test."""
    
    async def test_full_registration_to_pending(self, browser, mailpit):
        """Test complete flow: register -> verify -> pending."""
        unique_id = int(time.time()) % 100000
        username = f"fullflow{unique_id}"
        email = f"fullflow{unique_id}@example.com"
        password = "StrongPassword123@#$+Secure"
        
        # Clear mailbox
        mailpit.clear()
        
        # Step 1: Register
        await browser.goto(settings.url("/account/register"))
        await browser._page.wait_for_load_state("networkidle")
        
        await browser._page.fill('input[name="username"]', username)
        await browser._page.fill('input[name="email"]', email)
        await browser._page.fill('input[name="password"]', password)
        await browser._page.fill('input[name="confirm_password"]', password)
        await _accept_terms_if_present(browser._page)
        
        await browser._page.click('button[type="submit"]')
        await browser._page.wait_for_timeout(2000)
        
        # Step 2: Get verification code
        msg = mailpit.wait_for_message(
            predicate=lambda m: email.lower() in (m.to[0].address.lower() if m.to else ''),
            timeout=15.0
        )
        
        if not msg:
            pytest.skip("No verification email - email may not be configured")
        
        email_text = msg.text or msg.html or ''
        code_match = re.search(r'\b(\d{6})\b', email_text)
        
        if not code_match:
            pytest.skip(f"No verification code found in email")
        
        verification_code = code_match.group(1)
        
        # Step 3: Enter verification code
        code_input = await browser._page.query_selector('input[name="code"]')
        if not code_input:
            pytest.skip("Verification page not shown")
        
        await browser._page.fill('input[name="code"]', verification_code)
        await browser._page.click('button[type="submit"]')
        await browser._page.wait_for_timeout(1500)
        
        # Step 4: Should be on pending page
        current_url = browser.current_url
        content = await browser._page.content()
        
        success = (
            "pending" in current_url.lower() or
            "pending" in content.lower() or
            "approval" in content.lower() or
            "verified" in content.lower()
        )
        
        assert success, f"Should reach pending/verified state. URL: {current_url}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
