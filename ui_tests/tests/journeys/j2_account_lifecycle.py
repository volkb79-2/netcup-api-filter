"""
Journey 2: Admin Invite and Login

Contract: See docs/JOURNEY_CONTRACTS.md Section "J2: Admin Invite and Login"

Tests the complete account lifecycle:
1. Admin creates an account and sends an invite
2. The user accepts the invite and sets a password
3. The user logs in

This journey CREATES accounts for testing - it never skips due to missing data.

Preconditions:
- J1 passed (admin authenticated)
- Mailpit running for email capture

Verifications:
- Admin-created account and invite are available
- Invite acceptance sets a password
- The invited account can log in
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
from ui_tests.personas import new_password
from ui_tests import workflows

logger = logging.getLogger(__name__)

async def _handle_2fa_via_mailpit(browser: Browser) -> bool:
    """Handle a login 2FA page with its emailed code and verify the redirect."""
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
        try:
            msg = mailpit.wait_for_message(
                predicate=lambda m: "verification" in m.subject.lower() or "login" in m.subject.lower(),
                timeout=10.0,
            )
            if not msg:
                logger.info("No 2FA email found in Mailpit")
                return False

            code_match = re.search(r"\b(\d{6})\b", msg.text or msg.html or "")
            if not code_match:
                logger.info("Could not extract a 2FA code from the Mailpit message")
                return False

            code = code_match.group(1)
            logger.info("extracted 2FA code from email (length=%d)", len(code))
            url_before = browser._page.url
            await browser.fill("#code", code)
            async with browser._page.expect_navigation(
                wait_until="domcontentloaded",
                timeout=10000,
            ):
                await browser.click("form button[type='submit']")

            new_url = browser._page.url
            mailpit.delete_message(msg.id)
            if new_url == url_before or "/2fa" in new_url:
                logger.info("2FA submission did not leave the verification page")
                return False

            logger.info("2FA navigation completed")
            return True
        finally:
            mailpit.close()
    except Exception as e:
        logger.info("2FA via Mailpit failed (%s)", type(e).__name__)
    
    return False


def generate_unique_username() -> str:
    """Generate unique test username."""
    suffix = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(6))
    return f"testuser_{suffix}"


def generate_unique_email(username: str) -> str:
    """Generate unique test email."""
    return f"{username}@test.example.com"


async def capture(browser: Browser, name: str, journey: str = "J2") -> str:
    """Capture screenshot with journey prefix."""
    screenshot_name = journey_state.next_screenshot_name(journey, name)
    path = await browser.screenshot(screenshot_name)
    journey_state.screenshots.append((screenshot_name, path))
    logger.info(f"📸 {screenshot_name} → {path}")
    return path


class TestJourney2AccountLifecycle:
    """Journey 2: Admin invite acceptance and account login."""
    
    async def test_J2_01_admin_invite_account_created(self, anon_browser: Browser):
        """Create an approved account through the admin invite flow."""
        browser = anon_browser
        await self._admin_creates_account(browser)
        assert journey_state.test_account_username, "J2_01 did not create an invited account"
        assert journey_state.test_account_email, "J2_01 did not record the invite recipient"
    
    async def _admin_creates_account(self, browser: Browser):
        """Create an account through the admin invite flow.
        
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
    
    async def test_J2_07_user_can_login(self, browser: Browser, mailpit: MailpitClient):
        """Accept the local admin invite, then prove the invited user can log in."""
        if not journey_state.test_account_username:
            pytest.fail("J2_07 requires J2_01 to create an account", pytrace=False)
        
        if not journey_state.test_account_approved:
            pytest.fail("J2_07 requires J2_01 to create an approved admin-invite account", pytrace=False)
        
        if journey_state.get_extra("invite_based_account") or not journey_state.test_account_password:
            if settings.deployment_target == "webhosting":
                pytest.skip(
                    "webhosting J2 uses an invite-based admin-created account; the synthetic "
                    "mailbox cannot complete that invite login"
                )
            await self._accept_admin_invite(browser, mailpit)
        
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

        if "/2fa" in (browser.current_url or ""):
            if not await _handle_2fa_via_mailpit(browser):
                pytest.fail("J2_07 login reached 2FA but Mailpit verification did not complete", pytrace=False)
            await browser.wait_for_timeout(300)
        
        await capture(browser, "user-logged-in")
        
        # Verify not on login page anymore
        current_url = browser._page.url
        assert "/login" not in current_url, f"Login should succeed, still at: {current_url}"
        journey_state.set_extra("j2_user_login_verified", True)
        
        logger.info(f"✓ User {journey_state.test_account_username} logged in successfully")

    async def _accept_admin_invite(self, browser: Browser, mailpit: MailpitClient) -> None:
        """Accept the local admin-created account's Mailpit invite and set its password."""
        email = journey_state.test_account_email
        if not email:
            pytest.fail("J2_07 invite acceptance requires the created account email", pytrace=False)

        message = mailpit.wait_for_message(
            predicate=lambda item: email.lower() in [address.address.lower() for address in item.to],
            timeout=10.0,
        )
        if message is None:
            pytest.fail("J2_07 could not find the account invite in Mailpit", pytrace=False)

        invite_match = re.search(
            r"https?://[^\s]+/account/invite/[A-Za-z0-9_-]+",
            message.text or "",
        )
        if not invite_match:
            pytest.fail("J2_07 Mailpit message did not contain an account invite link", pytrace=False)

        password = new_password()
        # The account invite requires an anonymous account-portal session.
        await browser.goto(settings.url("/account/logout"), wait_until="domcontentloaded")
        await browser.goto(invite_match.group(0), wait_until="domcontentloaded")
        password_field = await browser.query_selector("#new_password, input[name='new_password']")
        if not password_field:
            pytest.fail("J2_07 invite page did not expose its password field", pytrace=False)

        await browser.fill("#new_password, input[name='new_password']", password)
        await browser.fill("#confirm_password, input[name='confirm_password']", password)
        await browser.click("button[type='submit']")
        await browser.wait_for_load_state("domcontentloaded")

        journey_state.test_account_password = password
        journey_state.set_extra("invite_based_account", False)
    
    async def test_J2_08_summary(self, browser: Browser):
        """Journey 2 complete - summarize account lifecycle."""
        logger.info("\n" + "=" * 60)
        logger.info("JOURNEY 2 COMPLETE: Admin Invite and Login")
        logger.info("=" * 60)
        logger.info(f"  Test account: {journey_state.test_account_username}")
        logger.info(f"  Email: {journey_state.test_account_email}")
        logger.info(f"  Approved: {journey_state.test_account_approved}")
        logger.info(f"  Total screenshots: {len(journey_state.screenshots)}")
        logger.info("=" * 60 + "\n")
