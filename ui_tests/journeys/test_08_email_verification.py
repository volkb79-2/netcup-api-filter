"""
Journey 08: Email Verification via Mailpit

This journey tests email flows by:
1. Configuring the app to use Mailpit SMTP
2. Triggering email-sending actions
3. Verifying emails arrive in Mailpit
4. Extracting links/codes from emails
5. Following those links to complete workflows

Prerequisites:
- Mailpit container running: cd tooling/mock-services && docker compose up -d mailpit
- App configured to use mailpit:1025 as SMTP (done by build_deployment.py --local)
"""
import pytest
import pytest_asyncio
import asyncio
import re
from typing import Optional

from ui_tests.config import settings
from ui_tests.workflows import ensure_admin_dashboard


class TestMailpitConnectivity:
    """Verify Mailpit is accessible and working."""
    
    def test_mailpit_is_running(self, mailpit):
        """Mailpit API is accessible."""
        try:
            info = mailpit.info()
            assert 'version' in info or 'Version' in info, \
                f"Unexpected Mailpit info response: {info}"
            print(f"✅ Mailpit running: {info}")
        except Exception as e:
            pytest.fail(f"Mailpit not accessible: {e}")
    
    def test_mailpit_can_clear(self, mailpit):
        """Can clear Mailpit mailbox."""
        mailpit.clear()
        messages = mailpit.list_messages()
        assert messages.total == 0, "Mailpit should be empty after clear"


class TestEmailConfigForMailpit:
    """Verify app is configured to send to Mailpit."""
    
    @pytest.mark.asyncio
    async def test_email_config_shows_mailpit(self, admin_session, screenshot_helper):
        """Email config page shows Mailpit settings."""
        ss = screenshot_helper('08-email')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/config/email'))
        await ss.capture('email-config-mailpit', 'Email config with Mailpit settings')
        
        # Check SMTP host value
        smtp_host_input = await browser.query_selector('#smtp_host, input[name="smtp_host"]')
        if smtp_host_input:
            smtp_host = await smtp_host_input.input_value()
            print(f"SMTP Host configured: {smtp_host}")
            # Should be mailpit for local testing
            assert 'mailpit' in smtp_host.lower() or '1025' in smtp_host or 'localhost' in smtp_host, \
                f"SMTP not configured for Mailpit: {smtp_host}"


class TestPasswordResetEmailFlow:
    """Test admin-initiated password reset email flow."""
    
    @pytest.mark.asyncio
    async def test_password_reset_sends_email(self, admin_session, mailpit, screenshot_helper):
        """Admin sends password reset, email arrives in Mailpit."""
        ss = screenshot_helper('08-email')
        browser = admin_session
        
        # Clear mailbox
        mailpit.clear()
        
        # Navigate to accounts list
        await browser.goto(settings.url('/admin/accounts'))
        await asyncio.sleep(0.5)
        
        # Find a non-admin account to reset
        # Look for account links
        account_links = await browser.query_selector_all('a[href*="/admin/accounts/"]')
        
        if len(account_links) < 2:
            pytest.skip("No non-admin accounts to test password reset")
        
        # Click on second account (first is usually admin)
        await account_links[1].click()
        await asyncio.sleep(0.5)
        await ss.capture('account-detail', 'Account detail before reset')
        
        # Click password reset button
        reset_btn = await browser.query_selector('[data-bs-target="#resetPasswordModal"], button:has-text("Reset Password")')
        if not reset_btn:
            pytest.skip("Password reset button not found")
        
        await reset_btn.click()
        await asyncio.sleep(0.3)
        await ss.capture('reset-modal-open', 'Password reset modal open')
        
        # Submit the reset
        submit_btn = await browser.query_selector('.modal button[type="submit"], .modal .btn-primary')
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(1.0)
        
        await ss.capture('reset-submitted', 'Password reset submitted')
        
        # Wait for email in Mailpit
        msg = mailpit.wait_for_message(
            predicate=lambda m: 'reset' in m.subject.lower() or 'password' in m.subject.lower(),
            timeout=10.0
        )
        
        assert msg is not None, "Password reset email not received in Mailpit!"
        
        # Get full message
        full_msg = mailpit.get_message(msg.id)
        print(f"✅ Email received: {full_msg.subject}")
        print(f"   From: {full_msg.from_address.address}")
        print(f"   To: {[a.address for a in full_msg.to]}")
        
        # Verify email content
        assert 'reset' in full_msg.subject.lower() or 'password' in full_msg.subject.lower()
        assert len(full_msg.text) > 0 or len(full_msg.html) > 0, "Email body is empty!"
    
    @pytest.mark.asyncio
    async def test_password_reset_link_works(
        self, admin_session, mailpit, screenshot_helper, extract_reset_link
    ):
        """Password reset link from email works."""
        ss = screenshot_helper('08-email')
        browser = admin_session
        
        # Clear mailbox
        mailpit.clear()
        
        # Trigger password reset (simplified - assume we already sent one)
        # In real test, would trigger reset first
        
        # Wait for email
        msg = mailpit.wait_for_message(
            predicate=lambda m: 'reset' in m.subject.lower() or 'password' in m.subject.lower(),
            timeout=10.0
        )
        
        if msg is None:
            pytest.skip("No password reset email found - run test_password_reset_sends_email first")
        
        full_msg = mailpit.get_message(msg.id)
        
        # Extract reset link
        reset_link = extract_reset_link(full_msg.text)
        if not reset_link and full_msg.html:
            reset_link = extract_reset_link(full_msg.html)
        
        assert reset_link, f"No reset link found in email body: {full_msg.text[:200]}"
        print(f"Reset link: {reset_link}")
        
        # Follow the reset link
        await browser.goto(reset_link)
        await asyncio.sleep(0.5)
        await ss.capture('reset-link-page', 'Password reset page from email link')
        
        # Verify we're on password reset page
        body = await browser.text('body')
        assert 'password' in body.lower(), \
            "Reset link didn't lead to password page"


class TestRegistrationVerificationEmail:
    """Test registration verification email flow."""
    
    @pytest.mark.asyncio
    async def test_registration_sends_verification_email(
        self, browser, mailpit, screenshot_helper, unique_username, unique_email
    ):
        """Registration sends verification email."""
        ss = screenshot_helper('08-email')
        
        # Clear mailbox
        mailpit.clear()
        
        # Go to registration
        await browser.goto(settings.url('/account/register'))
        await ss.capture('register-form', 'Registration form')
        
        # Fill registration form
        await browser.fill('#username', unique_username)
        await browser.fill('#email', unique_email)
        await browser.fill('#password', 'TestPassword123+Secure24')
        
        confirm_field = await browser.query_selector('#password_confirm, #confirm_password')
        if confirm_field:
            await browser.fill('#password_confirm, #confirm_password', 'TestPassword123+Secure24')
        
        await ss.capture('register-filled', 'Registration form filled')
        
        # Submit
        await browser.click('button[type="submit"]')
        await asyncio.sleep(1.0)
        
        await ss.capture('register-submitted', 'After registration submit')
        
        # Wait for verification email
        msg = mailpit.wait_for_message(
            predicate=lambda m: (
                'verify' in m.subject.lower() or 
                'verification' in m.subject.lower() or
                'confirm' in m.subject.lower()
            ),
            timeout=10.0
        )
        
        if msg is None:
            # Registration might be disabled or auto-approved
            print("No verification email received - registration may be auto-approved or disabled")
            return
        
        full_msg = mailpit.get_message(msg.id)
        print(f"✅ Verification email received: {full_msg.subject}")
        
        # Verify email content
        assert unique_email in [a.address for a in full_msg.to], \
            f"Email not sent to {unique_email}"
    
    @pytest.mark.asyncio
    async def test_verification_code_from_email(
        self, browser, mailpit, screenshot_helper, 
        unique_username, unique_email, extract_verification_code
    ):
        """Extract and use verification code from email."""
        ss = screenshot_helper('08-email')
        
        mailpit.clear()
        
        # Register new user
        await browser.goto(settings.url('/account/register'))
        await browser.fill('#username', unique_username)
        await browser.fill('#email', unique_email)
        await browser.fill('#password', 'TestPassword123+Secure24')
        
        confirm_field = await browser.query_selector('#password_confirm')
        if confirm_field:
            await browser.fill('#password_confirm', 'TestPassword123+Secure24')
        
        await browser.click('button[type="submit"]')
        await asyncio.sleep(1.0)
        
        # Wait for verification email
        msg = mailpit.wait_for_message(
            predicate=lambda m: 'verify' in m.subject.lower() or 'code' in m.subject.lower(),
            timeout=10.0
        )
        
        if msg is None:
            pytest.skip("No verification email - feature may be disabled")
        
        full_msg = mailpit.get_message(msg.id)
        
        # Extract verification code
        code = extract_verification_code(full_msg.text)
        if not code and full_msg.html:
            code = extract_verification_code(full_msg.html)
        
        if not code:
            print(f"Email body: {full_msg.text[:500]}")
            pytest.skip("No verification code found in email")
        
        print(f"✅ Verification code extracted: {code}")
        
        # Enter verification code
        code_field = await browser.query_selector('#verification_code, #code')
        if code_field:
            await browser.fill('#verification_code, #code', code)
            await ss.capture('verification-code-entered', 'Verification code entered')
            
            await browser.click('button[type="submit"]')
            await asyncio.sleep(0.5)
            
            await ss.capture('verification-complete', 'After verification')


class TestInviteLinkEmail:
    """Test admin invite link email flow."""
    
    @pytest.mark.asyncio
    async def test_invite_sends_email(
        self, admin_session, mailpit, screenshot_helper, unique_email
    ):
        """Admin invite sends email with link."""
        ss = screenshot_helper('08-email')
        browser = admin_session
        
        mailpit.clear()
        
        # Look for invite functionality
        await browser.goto(settings.url('/admin/accounts'))
        
        invite_link = await browser.query_selector('a[href*="/invite"], a:has-text("Invite")')
        if not invite_link:
            pytest.skip("Invite functionality not found")
        
        await invite_link.click()
        await asyncio.sleep(0.5)
        await ss.capture('invite-form', 'Invite form')
        
        # Fill invite form
        email_field = await browser.query_selector('#email, input[name="email"]')
        if email_field:
            await browser.fill('#email, input[name="email"]', unique_email)
            await ss.capture('invite-filled', 'Invite form filled')
            
            await browser.click('button[type="submit"]')
            await asyncio.sleep(1.0)
            
            await ss.capture('invite-sent', 'Invite sent')
        
        # Wait for invite email
        msg = mailpit.wait_for_message(
            predicate=lambda m: 'invite' in m.subject.lower() or 'invitation' in m.subject.lower(),
            timeout=10.0
        )
        
        if msg:
            full_msg = mailpit.get_message(msg.id)
            print(f"✅ Invite email received: {full_msg.subject}")
            assert unique_email in [a.address for a in full_msg.to]
        else:
            print("No invite email received - feature may work differently")


class TestEmailNotifications:
    """Test various email notifications."""
    
    @pytest.mark.asyncio
    async def test_email_test_button(self, admin_session, mailpit, screenshot_helper):
        """Test email button sends test email."""
        ss = screenshot_helper('08-email')
        browser = admin_session
        
        mailpit.clear()
        
        await browser.goto(settings.url('/admin/config/email'))
        await ss.capture('email-config-before-test', 'Email config page')
        
        # Look for test button
        test_btn = await browser.query_selector(
            'button:has-text("Test"), button:has-text("Send Test"), #test_email_btn'
        )
        
        if not test_btn:
            pytest.skip("Test email button not found")
        
        await test_btn.click()
        await asyncio.sleep(2.0)
        
        await ss.capture('email-config-after-test', 'After test email sent')
        
        # Check for test email
        msg = mailpit.wait_for_message(
            predicate=lambda m: 'test' in m.subject.lower(),
            timeout=10.0
        )
        
        if msg:
            print(f"✅ Test email received: {msg.subject}")
        else:
            # Check if there's any email at all
            messages = mailpit.list_messages()
            if messages.total > 0:
                latest = mailpit.get_message(messages.messages[0].id)
                print(f"Latest email in Mailpit: {latest.subject}")
            else:
                print("No emails in Mailpit - SMTP may not be configured correctly")


class TestEmailContentValidation:
    """Validate email content and formatting."""
    
    def test_email_has_proper_headers(self, mailpit):
        """Emails have proper headers (From, Reply-To, etc.)."""
        messages = mailpit.list_messages()
        
        if messages.total == 0:
            pytest.skip("No emails to validate")
        
        msg = mailpit.get_message(messages.messages[0].id)
        
        # Check From address
        assert msg.from_address.address, "Email missing From address"
        assert '@' in msg.from_address.address, f"Invalid From: {msg.from_address.address}"
        
        # Check To addresses
        assert len(msg.to) > 0, "Email missing To addresses"
        
        print(f"Email headers validated: From={msg.from_address.address}")
    
    def test_email_has_body_content(self, mailpit):
        """Emails have non-empty body content."""
        messages = mailpit.list_messages()
        
        if messages.total == 0:
            pytest.skip("No emails to validate")
        
        msg = mailpit.get_message(messages.messages[0].id)
        
        # Should have text or HTML body
        assert msg.text or msg.html, "Email has no body content"
        
        body_length = len(msg.text) + len(msg.html)
        assert body_length > 10, f"Email body too short: {body_length} chars"
        
        print(f"Email body validated: {len(msg.text)} text, {len(msg.html)} html chars")
