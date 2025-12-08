"""
Journey 1: Admin Authentication & System State

Contract: See docs/JOURNEY_CONTRACTS.md Section "J1: Fresh Deployment"

Tests admin authentication and system state:
1. Login page is accessible
2. Admin credentials from state file work
3. Handle password change if required (fresh deployment)
4. Dashboard shows current state (may have existing data)

This journey establishes authenticated admin session for subsequent journeys.
It works on BOTH fresh deployments AND existing deployments with data.

Preconditions:
- Flask running with fresh preseeded database
- deployment_state_local.json has admin credentials

Verifications:
- Login page is accessible (HTTP 200)
- Dashboard loads after authentication
- Password change flow works if must_change_password=true
- State file updated with new password
"""

import asyncio
import os
import secrets
import string
from pathlib import Path

from ui_tests.browser import Browser
from ui_tests.config import settings
from ui_tests.tests.journeys import journey_state
from ui_tests.deployment_state import load_state, get_deployment_target


def generate_secure_password(length: int = 24) -> str:
    """Generate a cryptographically secure password.
    
    Default length of 24 characters with mixed charset provides ~140 bits entropy,
    exceeding the 100-bit minimum requirement.
    """
    # Use safe printable ASCII charset matching server validation
    # Excludes: ! (shell history), ` (command substitution), ' " (quoting), \\ (escape)
    alphabet = string.ascii_letters + string.digits + "-=_+;:,.|/?@#$%^&*()[]{}~<>"
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def get_current_credentials() -> tuple[str, str]:
    """Get current admin credentials from state file (single source of truth)."""
    try:
        target = get_deployment_target()
        state = load_state(target)
        return state.admin.username, state.admin.password
    except Exception as e:
        print(f"⚠️  Could not load state file, using defaults: {e}")
        return "admin", "admin"


async def capture(browser: Browser, name: str, journey: str = "J1") -> str:
    """Capture screenshot with journey prefix."""
    screenshot_name = journey_state.next_screenshot_name(journey, name)
    path = await browser.screenshot(screenshot_name)
    journey_state.screenshots.append((screenshot_name, path))
    print(f"📸 {screenshot_name} → {path}")
    return path


async def _handle_2fa_via_mailpit(browser: Browser) -> bool:
    """Handle 2FA page by intercepting code from Mailpit.
    
    Returns True if successfully handled, False otherwise.
    Note: We fill the code and submit the form directly via JavaScript
    to avoid race conditions with the auto-submit feature.
    """
    import re
    try:
        from ui_tests.mailpit_client import MailpitClient
        
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
                print(f"✓ Extracted 2FA code from email: {code}")
                
                # Remember current URL to detect navigation (use live URL)
                url_before = browser._page.url
                
                # Fill the code field and submit the form directly via JavaScript
                # This avoids race conditions with the auto-submit feature
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
                    await asyncio.sleep(0.5)
                    # Get live URL directly from page
                    new_url = browser._page.url
                    if new_url != url_before and "/2fa" not in new_url:
                        print(f"✓ 2FA navigation complete: {new_url}")
                        break
                else:
                    print(f"⚠️  2FA navigation did not complete, still at: {browser._page.url}")
                
                mailpit.delete_message(msg.id)
                mailpit.close()
                return True
            else:
                print(f"⚠️  Could not extract code from email")
        else:
            print("⚠️  No 2FA email found in Mailpit")
        
        mailpit.close()
    except Exception as e:
        print(f"⚠️  2FA via Mailpit failed: {e}")
        print("   Hint: Set ADMIN_2FA_SKIP=true for test mode, or ensure Mailpit is running")
    
    return False


class TestJourney1FreshDeployment:
    """Journey 1: Admin authentication and system state validation."""
    
    async def test_J1_01_login_page_accessible(self, browser: Browser):
        """System shows login page."""
        await browser.goto(settings.url("/admin/login"))
        await asyncio.sleep(0.3)
        
        await capture(browser, "login-page")
        
        # Validate login page structure - h1 shows app name, form has login elements
        h1_text = await browser.text("h1")
        assert "Netcup API Filter" in h1_text or "Login" in h1_text, f"Expected login page header, got: {h1_text}"
        
        # Check form elements exist - this confirms it's the login page
        username_field = await browser.query_selector("#username, input[name='username']")
        password_field = await browser.query_selector("#password, input[name='password']")
        submit_btn = await browser.query_selector("button[type='submit']")
        
        assert username_field is not None, "Username field not found"
        assert password_field is not None, "Password field not found"
        assert submit_btn is not None, "Submit button not found"
    
    async def test_J1_02_default_credentials_work(self, browser: Browser):
        """Admin credentials from state file authenticate successfully."""
        await browser.goto(settings.url("/admin/login"))
        await asyncio.sleep(0.3)
        
        # Get credentials from state file (single source of truth)
        username, password = get_current_credentials()
        print(f"ℹ️  Using credentials from state file: {username}/*****")
        
        # Fill with credentials from state file
        await browser.fill("#username, input[name='username']", username)
        await browser.fill("#password, input[name='password']", password)
        
        await capture(browser, "login-filled")
        
        await browser.click("button[type='submit']")
        await asyncio.sleep(1.0)
        
        # Check result - might redirect to 2FA, password change, or dashboard
        # Use live URL (not cached)
        current_url = browser._page.url
        
        # Handle 2FA if redirected there (when ADMIN_2FA_SKIP is not set)
        if "/2fa" in current_url or "/login/2fa" in current_url:
            print("ℹ️  Redirected to 2FA - attempting to handle via Mailpit")
            await _handle_2fa_via_mailpit(browser)
            await asyncio.sleep(1.0)
            current_url = browser._page.url
        
        if "/admin/login" in current_url:
            # Login failed - try default credentials for fresh deployment
            print("⚠️  State file credentials failed, trying default 'admin/admin'")
            await browser.fill("#username, input[name='username']", "admin")
            await browser.fill("#password, input[name='password']", "admin")
            await browser.click("button[type='submit']")
            await asyncio.sleep(1.0)
            
            current_url = browser._page.url
            
            # Handle 2FA again if needed
            if "/2fa" in current_url or "/login/2fa" in current_url:
                print("ℹ️  Redirected to 2FA - attempting to handle via Mailpit")
                await _handle_2fa_via_mailpit(browser)
                await asyncio.sleep(1.0)
                current_url = browser._page.url
            
            assert "/admin/login" not in current_url, f"Login failed with both state file and default credentials"
            
            # Mark that we're using default credentials (fresh deployment)
            journey_state.set_extra("using_default_credentials", True)
        else:
            journey_state.set_extra("using_default_credentials", False)
            
        journey_state.admin_password = password
    
    async def test_J1_03_forced_password_change(self, browser: Browser):
        """Handle password change if required (fresh deployment only)."""
        # Check if already logged in (when running sequentially via journey master)
        # Use live URL (not cached)
        current_url = browser._page.url
        
        # If we're already on an admin page (not login), skip the login step
        if "/admin/" in current_url and "/admin/login" not in current_url:
            print("ℹ️  Already logged in (sequential execution), checking for password change")
            h1_text = await browser.text("h1")
        else:
            # Navigate to login page and authenticate
            await browser.goto(settings.url("/admin/login"))
            await asyncio.sleep(0.3)
            
            username, password = get_current_credentials()
            await browser.fill("#username, input[name='username']", username)
            await browser.fill("#password, input[name='password']", password)
            await browser.click("button[type='submit']")
            await asyncio.sleep(1.0)
            
            # Handle 2FA if redirected there (use live URL)
            current_url = browser._page.url
            if "/2fa" in current_url or "/login/2fa" in current_url:
                await _handle_2fa_via_mailpit(browser)
                await asyncio.sleep(1.0)
            
            current_url = browser._page.url
            h1_text = await browser.text("h1")
        
        await capture(browser, "post-login-state")
        
        # Check for password change indicators (including "Initial Setup")
        is_password_change = (
            "change" in h1_text.lower() and "password" in h1_text.lower()
        ) or (
            "initial setup" in h1_text.lower()
        ) or (
            "/change-password" in current_url
        ) or (
            "/admin/" in current_url and "must change" in (await browser.text("body")).lower()
        )
        
        if is_password_change:
            print("ℹ️  Password change required (fresh deployment detected)")
            
            # Perform password change
            new_password = generate_secure_password()
            
            # Check if email field is present (first-time setup for 2FA)
            email_field = await browser.query_selector("#email, input[name='email']")
            if email_field:
                test_email = f"admin-test-{secrets.token_hex(4)}@example.test"
                print(f"ℹ️  Setting up email for 2FA: {test_email}")
                await browser.fill("#email, input[name='email']", test_email)
            
            # Handle different form structures
            current_password_field = await browser.query_selector("#current_password, input[name='current_password']")
            new_password_field = await browser.query_selector("#new_password, input[name='new_password']")
            confirm_field = await browser.query_selector("#confirm_password, input[name='confirm_password'], #password_confirm")
            
            # Get the current password (either from state or default)
            current_password = journey_state.admin_password or "admin"
            
            if current_password_field:
                await browser.fill("#current_password, input[name='current_password']", current_password)
            if new_password_field:
                await browser.fill("#new_password", new_password)
                # Trigger input event to run checkPasswordStrength()
                await browser.evaluate("document.getElementById('new_password').dispatchEvent(new Event('input', { bubbles: true }))")
            if confirm_field:
                await browser.fill("#confirm_password", new_password)
                # Trigger input event to run checkPasswordMatch() and updateSubmitButton()
                await browser.evaluate("document.getElementById('confirm_password').dispatchEvent(new Event('input', { bubbles: true }))")
            
            # Small delay to let validation complete
            await asyncio.sleep(0.5)
            
            # Wait for client-side validation to enable submit button
            # The form validates: min 20 chars, min 100-bit entropy, passwords match
            try:
                await browser.wait_for_enabled("#submitBtn", timeout=5.0)
                print("✓ Submit button enabled (password meets requirements)")
            except Exception as e:
                # Debug: check what's wrong with validation
                entropy_badge = await browser.text("#entropyBadge")
                hint_text = await browser.text("#passwordHint")
                new_pw_val = await browser.evaluate("document.getElementById('new_password').value")
                confirm_val = await browser.evaluate("document.getElementById('confirm_password').value")
                btn_disabled = await browser.evaluate("document.getElementById('submitBtn').disabled")
                mismatch_visible = await browser.evaluate("!document.getElementById('passwordMismatch').classList.contains('d-none')")
                print(f"⚠️  Submit button not enabled:")
                print(f"   - Entropy: {entropy_badge}")
                print(f"   - Hint: {hint_text}")
                print(f"   - New password length: {len(new_pw_val) if new_pw_val else 0}")
                print(f"   - Confirm password length: {len(confirm_val) if confirm_val else 0}")
                print(f"   - Passwords match: {new_pw_val == confirm_val}")
                print(f"   - Button disabled: {btn_disabled}")
                print(f"   - Mismatch warning visible: {mismatch_visible}")
                raise
            
            await capture(browser, "password-change-form")
            
            await browser.click("#submitBtn, button[type='submit']")
            await asyncio.sleep(1.0)
            
            journey_state.admin_password = new_password
            
            await capture(browser, "password-changed")
            
            # Update deployment state file
            await _update_deployment_state(new_password)
        else:
            # No password change required - using existing credentials
            print("✓ No password change required - using existing credentials")
            # Keep the password from test_J1_02
        
        journey_state.admin_logged_in = True
    
    async def test_J1_04_dashboard_state(self, browser: Browser):
        """Dashboard shows current state (validates structure, not specific values)."""
        # Login first (each test is independent with fresh browser)
        from ui_tests import workflows
        await workflows.ensure_admin_dashboard(browser)
        
        await capture(browser, "dashboard")
        
        # Check for dashboard elements
        page_text = await browser.text("body")
        
        # Dashboard should be visible
        h1_text = await browser.text("h1")
        assert "Dashboard" in h1_text or "Admin" in h1_text, f"Expected dashboard, got: {h1_text}"
        
        # Stats should exist (even if zero)
        # Common stat patterns: "Accounts: 0", "Active Tokens: 0", etc.
        stats_area = await browser.query_selector(".stats, .dashboard-stats, .stat-card, .card")
        if stats_area:
            print("✓ Stats area found")
        
        # Navigation should be present
        nav = await browser.query_selector("nav, .navbar, .sidebar")
        assert nav is not None, "Navigation not found on dashboard"
    
    async def test_J1_05_admin_pages_accessible(self, browser: Browser):
        """All admin pages are accessible without 500 errors."""
        # Login first
        from ui_tests import workflows
        await workflows.ensure_admin_dashboard(browser)
        
        admin_pages = [
            ("/admin/accounts", "accounts-list"),
            ("/admin/realms", "realms-list"),
            ("/admin/audit", "audit-logs"),
            ("/admin/config/netcup", "config-netcup"),
            ("/admin/config/email", "config-email"),
            ("/admin/system", "system-info"),
        ]
        
        for path, screenshot_name in admin_pages:
            await browser.goto(settings.url(path))
            await asyncio.sleep(0.3)
            
            # Check for 500 error
            page_text = await browser.text("body")
            assert "500" not in page_text or "Internal Server Error" not in page_text, \
                f"500 error on {path}"
            
            # Verify we're not redirected to login
            current_url = browser.current_url or ""
            assert "/login" not in current_url, \
                f"Redirected to login from {path} - session lost?"
            
            await capture(browser, screenshot_name)
        
        print(f"✓ All {len(admin_pages)} admin pages accessible")
    
    async def test_J1_06_summary(self, browser: Browser):
        """Journey 1 complete - summarize state."""
        print("\n" + "=" * 60)
        print("JOURNEY 1 COMPLETE: Fresh Deployment")
        print("=" * 60)
        print(f"  Admin password: {'Changed' if journey_state.admin_password != 'admin' else 'Default'}")
        print(f"  Screenshots: {len(journey_state.screenshots)}")
        print(f"  State: {journey_state.to_dict()}")
        print("=" * 60 + "\n")
        
        # Login and capture final dashboard screenshot
        from ui_tests import workflows
        await workflows.ensure_admin_dashboard(browser)
        await capture(browser, "journey-complete")


async def _update_deployment_state(new_password: str):
    """Update deployment state file with new password."""
    from ui_tests.deployment_state import update_admin_password, get_state_file_path
    
    state_file = get_state_file_path()
    if not state_file.exists():
        print(f"⚠️  State file not found: {state_file}")
        return
    
    try:
        update_admin_password(new_password)
        print(f"✓ Updated deployment state: {state_file}")
        
        # Also update settings so subsequent tests use new password
        settings._active.admin_password = new_password
    except Exception as e:
        print(f"⚠️  Failed to update deployment state: {e}")
