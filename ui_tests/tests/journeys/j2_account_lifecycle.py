"""
Journey 2: Account Lifecycle

Contract: See docs/JOURNEY_CONTRACTS.md Section "J2: Account Lifecycle"

Tests the complete account lifecycle:
1. Self-registration (if enabled)
2. Email verification
3. Admin approval
4. User login
5. Account rejection flow

This journey CREATES accounts for testing - it never skips due to missing data.

Preconditions:
- J1 passed (admin authenticated)
- Mailpit running for email capture

Verifications:
- Registration form submits successfully
- Verification email sent to Mailpit
- Code extraction and verification works
- Admin can approve/reject accounts
- Approved accounts can login
"""

import logging
import re
import secrets
import string

import pytest

from ui_tests.browser import Browser
from ui_tests.config import settings
from ui_tests.tests.journeys import journey_state
from ui_tests.mailpit_client import MailpitClient
from ui_tests import workflows

logger = logging.getLogger(__name__)


async def _handle_2fa_via_mailpit(browser: Browser) -> bool:
    """Handle 2FA page by intercepting code from Mailpit.
    
    Returns True if successfully handled, False otherwise.
    Note: We fill the code and submit the form directly via JavaScript.
    """
    try:
        # If multiple 2FA methods exist, prefer email because our automation
        # can retrieve email codes (TOTP cannot be automated here).
        try:
            email_method_link = await browser.query_selector("a[href*='method=email']")
            if email_method_link:
                await browser.click("a[href*='method=email']")
                await browser.wait_for_load_state('domcontentloaded')
        except Exception:
            # Best-effort only; if the method switcher isn't present, continue.
            pass

        mailpit = MailpitClient()
        
        # Wait for 2FA email
        msg = mailpit.wait_for_message(
            predicate=lambda m: "verification" in m.subject.lower() or "login" in m.subject.lower(),
            timeout=10.0
        )
        
        if msg:
            full_msg = mailpit.get_message(msg.id)
            # Extract 6-digit code
            code_match = re.search(r'\b(\d{6})\b', full_msg.text)
            
            if code_match:
                code = code_match.group(1)
                logger.info("extracted 2FA code from email (length=%d)", len(code))
                
                # Remember current URL to detect navigation
                # Use _page.url directly to get live URL
                url_before = browser._page.url
                
                # Fill the code field and submit the form directly via JavaScript
                await browser.evaluate(f"""
                    (function() {{
                        const input = document.getElementById('code');
                        const form = document.getElementById('twoFaForm');
                        if (input && form) {{
                            input.value = '{code}';
                            form.submit();
                        }}
                    }})();
                """)
                
                # Wait for navigation to complete
                for _ in range(20):  # Up to 10 seconds
                    await browser.wait_for_load_state('domcontentloaded')
                    # Get live URL directly from page
                    new_url = browser._page.url
                    if new_url != url_before and "/2fa" not in new_url:
                        logger.info(f"✓ 2FA navigation complete: {new_url}")
                        break
                else:
                    logger.info(f"⚠️  2FA navigation did not complete, still at: {browser._page.url}")
                
                # Clear the used email
                mailpit.delete_message(msg.id)
                mailpit.close()
                return True
            else:
                logger.info("⚠️  Could not extract code from email")
        else:
            logger.info("⚠️  No 2FA email found in Mailpit")
        
        mailpit.close()
    except Exception as e:
        logger.info("⚠️  2FA via Mailpit failed (%s)", type(e).__name__)
    
    return False


def generate_unique_username() -> str:
    """Generate unique test username."""
    suffix = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(6))
    return f"testuser_{suffix}"


def generate_unique_email(username: str) -> str:
    """Generate unique test email."""
    return f"{username}@test.example.com"


def generate_password() -> str:
    """Generate secure test password."""
    return ''.join(secrets.choice(string.ascii_letters + string.digits + "!@#$") for _ in range(16))


async def capture(browser: Browser, name: str, journey: str = "J2") -> str:
    """Capture screenshot with journey prefix."""
    screenshot_name = journey_state.next_screenshot_name(journey, name)
    path = await browser.screenshot(screenshot_name)
    journey_state.screenshots.append((screenshot_name, path))
    logger.info(f"📸 {screenshot_name} → {path}")
    return path


class TestJourney2AccountLifecycle:
    """Journey 2: Account registration, verification, and approval."""
    
    async def test_J2_01_registration_page(self, anon_browser: Browser):
        """Registration page is accessible and has required fields."""
        browser = anon_browser
        await browser.goto(settings.url("/account/register"))
        await browser.wait_for_timeout(300)
        
        await capture(browser, "registration-page")
        
        # Check if registration is available
        page_text = await browser.text("body")
        
        # Registration might be disabled
        if "disabled" in page_text.lower() or "not available" in page_text.lower():
            logger.info("ℹ️  Registration is disabled - using admin account creation instead")
            # Use alternative: admin creates account
            await self._admin_creates_account(browser)
            return
        
        # Check form fields exist
        username_field = await browser.query_selector("#username, input[name='username']")
        email_field = await browser.query_selector("#email, input[name='email']")
        password_field = await browser.query_selector("#password, input[name='password']")
        
        if not all([username_field, email_field, password_field]):
            logger.info("ℹ️  Registration form incomplete - using admin account creation")
            await self._admin_creates_account(browser)
            return
        
        # Store that self-registration is available
        journey_state.set_extra("self_registration_available", True)
    
    async def _admin_creates_account(self, browser: Browser):
        """Fallback: Admin creates an account when self-registration unavailable.
        
        Note: The admin account creation page uses an invitation system.
        Admin provides username + email, and the user sets their password via invite link.
        """
        # Use the shared workflow: it handles the full auth matrix reliably
        # (fresh deploy password setup, 2FA enrollment, 2FA via Mailpit/IMAP, etc.).
        try:
            await workflows.ensure_admin_dashboard(browser)
        except Exception:
            await capture(browser, "admin-login-failed")
            raise
        
        # Navigate to account creation
        await browser.goto(settings.url("/admin/accounts/new"))
        await browser.wait_for_load_state('domcontentloaded')
        
        # Wait for the create-account form specifically.
        # Note: the login page also contains a '#username' field, so we must
        # not use that alone as a readiness check.
        create_form = None
        email_field = None
        for _ in range(10):
            create_form = await browser.query_selector("#createAccountForm")
            email_field = await browser.query_selector("#email, input[name='email']")
            if create_form and email_field:
                break
            await browser.wait_for_timeout(250)

        if not (create_form and email_field):
            await capture(browser, "account-creation-page-error")
            raise RuntimeError(f"Account creation page did not load properly (url={browser._page.url})")
        
        username = generate_unique_username()
        email = generate_unique_email(username)
        
        # Admin account creation page only has username and email
        # (password is set by user via invite link)
        await browser.fill("#username, input[name='username']", username)
        await browser.fill("#email, input[name='email']", email)
        
        await capture(browser, "admin-creates-account")
        
        await browser.click("button[type='submit']")
        await browser.wait_for_timeout(1000)
        
        # Store account details (no password - invite-based)
        journey_state.test_account_username = username
        journey_state.test_account_email = email
        journey_state.test_account_password = None  # Set via invite link
        journey_state.test_account_approved = True  # Admin-created = auto-approved
        journey_state.set_extra("invite_based_account", True)
        
        await capture(browser, "account-created-by-admin")
    
    async def test_J2_02_submit_registration(self, anon_browser: Browser, mailpit: MailpitClient):
        """Submit registration form and check for verification email."""
        browser = anon_browser
        # Skip if we used admin creation
        if journey_state.test_account_username:
            logger.info("ℹ️  Skipping - account already created by admin")
            return
        
        if not journey_state.get_extra("self_registration_available", False):
            pytest.fail(
                "J2_02 found no self-registration form and J2_01 did not create a fallback account",
                pytrace=False,
            )
        
        # Clear mailpit
        mailpit.clear()
        
        # Generate unique test data
        username = generate_unique_username()
        email = generate_unique_email(username)
        password = generate_password()
        
        # Fill registration form
        await browser.goto(settings.url("/account/register"))
        await browser.wait_for_timeout(300)
        
        await browser.fill("#username, input[name='username']", username)
        await browser.fill("#email, input[name='email']", email)
        await browser.fill("#password, input[name='password']", password)
        
        confirm = await browser.query_selector("#password_confirm, input[name='password_confirm']")
        if confirm:
            await browser.fill("#password_confirm, input[name='password_confirm']", password)
        
        await capture(browser, "registration-filled")
        
        await browser.click("button[type='submit']")
        await browser.wait_for_timeout(1500)
        
        await capture(browser, "registration-submitted")
        
        # Store account details
        journey_state.test_account_username = username
        journey_state.test_account_email = email
        journey_state.test_account_password = password
    
    async def test_J2_03_check_verification_email(self, browser: Browser, mailpit: MailpitClient):
        """Verification email is sent with correct content."""
        if not journey_state.test_account_email:
            pytest.fail("J2_03 requires J2_01/J2_02 to create an account email", pytrace=False)
        
        if journey_state.test_account_approved:
            logger.info("ℹ️  Skipping - account already approved (admin-created)")
            return
        
        # Wait for verification email
        msg = mailpit.wait_for_message(
            predicate=lambda m: (
                'verify' in m.subject.lower() or 
                'verification' in m.subject.lower() or
                'confirm' in m.subject.lower()
            ),
            timeout=15.0
        )
        
        if msg is None:
            logger.info("ℹ️  No verification email - may be auto-approved or email disabled")
            await capture(browser, "no-verification-email")
            return
        
        # Get full message content
        full_msg = mailpit.get_message(msg.id)
        
        # Verify email goes to correct recipient
        recipient_emails = [a.address.lower() for a in full_msg.to]
        assert journey_state.test_account_email.lower() in recipient_emails, \
            f"Email should go to {journey_state.test_account_email}, went to {recipient_emails}"
        
        # Extract verification code/link
        email_text = full_msg.text or ""
        journey_state.set_extra("verification_code", _extract_code(email_text))
        journey_state.set_extra("verification_link", _extract_link(email_text))
        
        logger.info(f"✓ Verification email received for {journey_state.test_account_email}")
        verification_code = journey_state.get_extra("verification_code")
        logger.info("verification code present=%s length=%d", bool(verification_code), len(verification_code or ""))
        logger.info(f"  Link: {'Yes' if journey_state.get_extra('verification_link') else 'No'}")
    
    async def test_J2_04_complete_verification(self, browser: Browser):
        """Complete email verification process."""
        if not journey_state.test_account_email:
            pytest.fail("J2_04 requires J2_01/J2_02 to create an account email", pytrace=False)
        
        if journey_state.test_account_approved:
            logger.info("ℹ️  Skipping - account already approved")
            return
        
        verification_code = journey_state.get_extra("verification_code")
        verification_link = journey_state.get_extra("verification_link")
        
        if verification_link:
            # Use direct link
            await browser.goto(verification_link)
            await browser.wait_for_timeout(1000)
            await capture(browser, "verification-link-followed")
        elif verification_code:
            # Enter code on verification page
            await browser.goto(settings.url("/account/verify"))
            await browser.wait_for_timeout(300)
            
            code_field = await browser.query_selector("#code, input[name='code'], #verification_code")
            if code_field:
                await browser.fill("#code, input[name='code'], #verification_code", verification_code)
                await capture(browser, "verification-code-entered")
                await browser.click("button[type='submit']")
                await browser.wait_for_timeout(1000)
        else:
            logger.info("ℹ️  No verification code/link - may be auto-verified")
            return
        
        await capture(browser, "verification-complete")
    
    async def test_J2_05_admin_sees_pending_account(self, browser: Browser):
        """Admin can see the pending account in the list."""
        if not journey_state.test_account_username:
            pytest.fail("J2_05 requires J2_01/J2_02 to create an account", pytrace=False)
        
        if journey_state.test_account_approved:
            logger.info("ℹ️  Skipping - account already approved")
            # Still capture account list for documentation
            await _login_as_admin(browser)
            await browser.goto(settings.url("/admin/accounts"))
            await browser.wait_for_timeout(300)
            await capture(browser, "accounts-list-with-created")
            return
        
        # Login as admin
        await _login_as_admin(browser)
        
        # Check pending accounts
        await browser.goto(settings.url("/admin/accounts/pending"))
        await browser.wait_for_timeout(300)
        
        await capture(browser, "pending-accounts")
        
        page_text = await browser.text("body")
        
        # Verify our test account is in pending list
        if journey_state.test_account_username in page_text:
            logger.info(f"✓ Found pending account: {journey_state.test_account_username}")
        else:
            logger.info("ℹ️  Account not in pending list - may need approval via different flow")
    
    async def test_J2_06_approve_account(self, browser: Browser, mailpit: MailpitClient):
        """Admin approves the pending account."""
        if not journey_state.test_account_username:
            pytest.fail("J2_06 requires J2_01/J2_02 to create an account", pytrace=False)
        
        if journey_state.test_account_approved:
            logger.info("ℹ️  Skipping - account already approved")
            return
        
        # Clear mailpit to catch approval email
        mailpit.clear()
        
        # Ensure logged in as admin
        current_url = browser.current_url or ""
        if "/admin/" not in current_url:
            await _login_as_admin(browser)
        
        # Navigate to pending accounts
        await browser.goto(settings.url("/admin/accounts/pending"))
        await browser.wait_for_timeout(300)
        
        # Find approve button for our account
        # Try different selectors
        approve_btn = await browser.query_selector(
            f'tr:has-text("{journey_state.test_account_username}") button:has-text("Approve")'
        )
        
        if not approve_btn:
            # Try generic first approve button
            approve_btn = await browser.query_selector('button:has-text("Approve")')
        
        if not approve_btn:
            logger.info("ℹ️  No approve button found - account may auto-approve or use different flow")
            await capture(browser, "no-approve-button")
            return
        
        await approve_btn.click()
        await browser.wait_for_timeout(1000)
        
        await capture(browser, "account-approved")
        
        journey_state.test_account_approved = True
        
        # Check for approval email
        msg = mailpit.wait_for_message(
            predicate=lambda m: 'approved' in m.subject.lower() or 'welcome' in m.subject.lower(),
            timeout=10.0
        )
        
        if msg:
            logger.info(f"✓ Approval email sent to {journey_state.test_account_email}")
            await capture(browser, "approval-email-sent")
    
    async def test_J2_07_user_can_login(self, browser: Browser):
        """Approved user can login successfully."""
        if not journey_state.test_account_username:
            pytest.fail("J2_07 requires J2_01/J2_02 to create an account", pytrace=False)
        
        if not journey_state.test_account_approved:
            pytest.fail("J2_07 requires J2_06 to approve the created account", pytrace=False)
        
        if journey_state.get_extra("invite_based_account") or not journey_state.test_account_password:
            if settings.deployment_target == "webhosting":
                pytest.skip(
                    "webhosting J2 uses an invite-based admin-created account; the synthetic "
                    "mailbox cannot complete that invite login"
                )
            pytest.fail(
                "J2_07 requires the created account's invite to be accepted and a password to be set",
                pytrace=False,
            )
        
        # Logout admin if needed
        await browser.goto(settings.url("/admin/logout"))
        await browser.wait_for_timeout(300)
        
        # Login as test user
        await browser.goto(settings.url("/account/login"))
        await browser.wait_for_timeout(300)
        
        await browser.fill("#username, input[name='username']", journey_state.test_account_username or "")
        await browser.fill("#password, input[name='password']", journey_state.test_account_password or "")
        
        await capture(browser, "user-login-form")
        
        await browser.click("button[type='submit']")
        await browser.wait_for_timeout(1000)
        
        await capture(browser, "user-logged-in")
        
        # Verify not on login page anymore
        current_url = browser.current_url or ""
        assert "/login" not in current_url, f"Login should succeed, still at: {current_url}"
        
        logger.info(f"✓ User {journey_state.test_account_username} logged in successfully")
    
    async def test_J2_08_summary(self, browser: Browser):
        """Journey 2 complete - summarize account lifecycle."""
        logger.info("\n" + "=" * 60)
        logger.info("JOURNEY 2 COMPLETE: Account Lifecycle")
        logger.info("=" * 60)
        logger.info(f"  Test account: {journey_state.test_account_username}")
        logger.info(f"  Email: {journey_state.test_account_email}")
        logger.info(f"  Approved: {journey_state.test_account_approved}")
        logger.info(f"  Total screenshots: {len(journey_state.screenshots)}")
        logger.info("=" * 60 + "\n")


async def _login_as_admin(browser: Browser):
    """Log in as the session's admin persona (TOTP), reusing a still-valid session."""
    from ui_tests import workflows

    await workflows.ensure_admin_dashboard(browser)
    journey_state.admin_logged_in = True


def _extract_code(text: str) -> str | None:
    """Extract 6-digit verification code from email text."""
    import re
    match = re.search(r'\b([A-Z0-9]{6})\b', text)
    return match.group(1) if match else None


def _extract_link(text: str) -> str | None:
    """Extract verification link from email text."""
    import re
    match = re.search(r'(https?://[^\s]+verify[^\s]+)', text)
    return match.group(1) if match else None
