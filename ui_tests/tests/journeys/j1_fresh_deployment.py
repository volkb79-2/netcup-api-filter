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

import os
import secrets
import string
from pathlib import Path

from ui_tests.browser import Browser
from ui_tests.config import settings
from ui_tests.tests.journeys import journey_state
from ui_tests.deployment_state import load_state, get_deployment_target, update_admin_email


def _imap_configured() -> bool:
    return bool(
        (os.environ.get("IMAP_HOST") or "").strip()
        and (os.environ.get("IMAP_USER") or "").strip()
        and (os.environ.get("IMAP_PASSWORD") or "").strip()
    )


def _select_admin_email_for_2fa() -> str:
    """Pick an email address that the current environment can actually receive.

    - Local/dev: synthetic addresses are fine (Mailpit inbox).
    - Webhosting/live: Mailpit is not in the remote SMTP path; use a real mailbox
      and retrieve codes via IMAP.
    """
    explicit = (os.environ.get("UI_ADMIN_2FA_EMAIL") or "").strip()
    if explicit:
        return explicit

    # Prefer the persisted deployment state, if present.
    try:
        target = get_deployment_target()
        state = load_state(target)
        if (state.admin.email or "").strip():
            return (state.admin.email or "").strip()
    except Exception:
        pass

    if _imap_configured():
        return (os.environ.get("IMAP_USER") or "").strip()

    return f"admin-test-{secrets.token_hex(4)}@example.test"


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


def _verify_password_after_change_enabled() -> bool:
    """Whether Journey 1 should logout+relogin to verify the new admin password.

    This is helpful for local testing, but on webhosting/live it can trigger an
    extra email-based 2FA send which may hit SMTP rate limits.
    """

    explicit = (os.environ.get("UI_J1_VERIFY_PASSWORD_AFTER_CHANGE") or "").strip()
    if explicit:
        return explicit.lower() in {"1", "true", "yes", "on"}

    # Default to skipping in webhosting/live to reduce SMTP pressure.
    try:
        target = get_deployment_target()
    except Exception:
        target = ""
    mode = (os.environ.get("DEPLOYMENT_MODE") or "").strip().lower()
    return not (target == "webhosting" and mode == "live")


async def capture(browser: Browser, name: str, journey: str = "J1") -> str:
    """Capture screenshot with journey prefix."""
    screenshot_name = journey_state.next_screenshot_name(journey, name)
    path = await browser.screenshot(screenshot_name)
    journey_state.screenshots.append((screenshot_name, path))
    print(f"📸 {screenshot_name} → {path}")
    return path


async def _handle_2fa_via_mailpit(browser: Browser) -> bool:
    """Handle 2FA page.

    Delegates to the shared workflow which tries Mailpit first and falls back
    to IMAP when configured (required for webhosting/live deployments).
    """
    from ui_tests import workflows

    handled = await workflows.handle_2fa_if_present(browser, timeout=10.0)
    if handled:
        return True

    current_url = browser._page.url
    if "/login/2fa" in current_url or "/2fa" in current_url:
        body_preview = (await browser.text("body"))[:800]
        raise AssertionError(
            "2FA page present, but could not retrieve/submit verification code. "
            f"url={current_url} preview={body_preview!r}"
        )

    return False


class TestJourney1FreshDeployment:
    """Journey 1: Admin authentication and system state validation."""
    
    async def test_J1_01_login_page_accessible(self, browser: Browser):
        """System shows login page."""
        await browser.goto(settings.url("/admin/login"))
        await browser.wait_for_timeout(300)
        
        await capture(browser, "login-page")
        
        # Validate login page structure - h1 shows app name, form has login elements
        h1_text = await browser.text("h1")
        assert any(text in h1_text for text in ["Netcup API Filter", "Login", "Admin Portal"]), f"Expected login page header, got: {h1_text}"
        
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
        await browser.wait_for_timeout(300)
        
        # Get credentials from state file (single source of truth)
        username, password = get_current_credentials()
        print(f"ℹ️  Using credentials from state file: {username}/*****")
        
        # Fill with credentials from state file
        await browser.fill("#username, input[name='username']", username)
        await browser.fill("#password, input[name='password']", password)
        
        await capture(browser, "login-filled")
        
        await browser.click("button[type='submit']")
        await browser.wait_for_timeout(1000)
        
        # Check result - might redirect to 2FA, password change, or dashboard
        # Use live URL (not cached)
        current_url = browser._page.url
        
        # Handle 2FA if redirected there (when ADMIN_2FA_SKIP is not set)
        if "/2fa" in current_url or "/login/2fa" in current_url:
            print("ℹ️  Redirected to 2FA - attempting to handle via Mailpit")
            await capture(browser, "2fa-page")
            await _handle_2fa_via_mailpit(browser)
            await browser.wait_for_timeout(1000)
            current_url = browser._page.url
        
        if "/admin/login" in current_url:
            # Login failed - try default credentials for fresh deployment
            print("⚠️  State file credentials failed, trying default 'admin/admin'")
            await browser.fill("#username, input[name='username']", "admin")
            await browser.fill("#password, input[name='password']", "admin")
            await browser.click("button[type='submit']")
            await browser.wait_for_timeout(1000)
            
            current_url = browser._page.url
            
            # Handle 2FA again if needed
            if "/2fa" in current_url or "/login/2fa" in current_url:
                print("ℹ️  Redirected to 2FA - attempting to handle via Mailpit")
                await capture(browser, "2fa-page")
                await _handle_2fa_via_mailpit(browser)
                await browser.wait_for_timeout(1000)
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
            await browser.wait_for_timeout(300)
            
            username, password = get_current_credentials()
            await browser.fill("#username, input[name='username']", username)
            await browser.fill("#password, input[name='password']", password)
            await browser.click("button[type='submit']")
            await browser.wait_for_timeout(1000)
            
            # Handle 2FA if redirected there (use live URL)
            current_url = browser._page.url
            if "/2fa" in current_url or "/login/2fa" in current_url:
                await _handle_2fa_via_mailpit(browser)
                await browser.wait_for_timeout(1000)
            
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
                # NOTE: On webhosting deployments, the app cannot deliver email to local Mailpit.
                # Use IMAP-backed mailbox when configured; otherwise fail-fast with guidance.
                if settings.deployment_target == "webhosting" and not _imap_configured():
                    raise RuntimeError(
                        "Webhosting Journey 1 requires IMAP to be configured so admin email 2FA can be received. "
                        "Set IMAP_HOST, IMAP_USER, IMAP_PASSWORD (and optionally IMAP_* settings) in your environment."
                    )

                admin_email = _select_admin_email_for_2fa()
                print(f"ℹ️  Setting up email for 2FA: {admin_email}")
                await browser.fill("#email, input[name='email']", admin_email)
                # Persist for subsequent journeys/tests and for human visibility.
                try:
                    update_admin_email(
                        admin_email,
                        updated_by="ui_tests/journeys/j1_fresh_deployment",
                        target=get_deployment_target(),
                    )
                except Exception:
                    # Don't fail the journey if state write is unavailable.
                    pass
            
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
            await browser.wait_for_load_state('domcontentloaded')
            
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
            await browser.wait_for_timeout(750)

            # Password change must actually succeed before we persist it.
            # In some environments the POST can fail silently (validation/CSRF/etc)
            # and we'd otherwise poison deployment_state for subsequent journeys.
            current_url_after_submit = browser._page.url
            if "/admin/login" in current_url_after_submit:
                body_preview = (await browser.text("body"))[:500]
                raise AssertionError(
                    "Password change submission returned to login unexpectedly. "
                    f"url={current_url_after_submit} preview={body_preview!r}"
                )

            # Handle an unexpected 2FA prompt after password change.
            current_url_after_submit = browser._page.url
            if "/2fa" in current_url_after_submit or "/login/2fa" in current_url_after_submit:
                print("ℹ️  Redirected to 2FA after password change - attempting to handle via Mailpit")
                await _handle_2fa_via_mailpit(browser)
                await browser.wait_for_timeout(1000)

            try:
                await browser.wait_for_text("h1", "Dashboard", timeout=12.0)
            except Exception:
                h1_now = ""
                try:
                    h1_now = await browser.text("h1")
                except Exception:
                    pass
                body_preview = (await browser.text("body"))[:600]
                raise AssertionError(
                    "Password change did not reach dashboard (unexpected post-submit state). "
                    f"url={browser._page.url} h1={h1_now!r} preview={body_preview!r}"
                )

            await capture(browser, "password-changed")

            # Persist immediately to keep deployment_state in sync even if the
            # subsequent logout+relogin + 2FA verification fails.
            journey_state.admin_password = new_password
            await _update_deployment_state(new_password)

            if not _verify_password_after_change_enabled():
                print(
                    "ℹ️  Skipping logout+relogin password verification "
                    "(UI_J1_VERIFY_PASSWORD_AFTER_CHANGE disabled)"
                )
                journey_state.admin_logged_in = True
                return

            # Verify the new password actually works in a fresh session.
            print("ℹ️  Verifying new admin password via logout+relogin")
            await browser.goto(settings.url("/admin/logout"), wait_until="domcontentloaded")
            await browser.wait_for_timeout(500)

            await browser.goto(settings.url("/admin/login"), wait_until="domcontentloaded")
            await browser.wait_for_timeout(300)
            relogin_username, _ = get_current_credentials()
            await browser.fill("#username, input[name='username']", relogin_username)
            await browser.fill("#password, input[name='password']", new_password)
            await capture(browser, "relogin-filled")

            # Submitting can involve redirects (to 2FA), and email delivery can add latency.
            # Avoid fixed sleeps; wait for navigation or surface useful diagnostics.
            try:
                async with browser._page.expect_navigation(wait_until="domcontentloaded", timeout=15_000):
                    await browser._page.click("button[type='submit']")
            except Exception:
                # Some pages might not trigger a full navigation event; fall back to a click + load wait.
                await browser._page.click("button[type='submit']")
                await browser._page.wait_for_load_state("domcontentloaded", timeout=15_000)

            try:
                import re

                await browser._page.wait_for_url(
                    re.compile(r".*/admin/(login/2fa|dashboard|change-password)"),
                    timeout=15_000,
                )
            except Exception:
                await capture(browser, "relogin-unknown-state")
                body_preview = (await browser.text("body"))[:800]
                raise AssertionError(
                    "Re-login did not reach a post-login route (dashboard/2FA/change-password). "
                    f"url={browser._page.url} preview={body_preview!r}"
                )

            current_url = browser._page.url
            if "/2fa" in current_url or "/login/2fa" in current_url:
                print("ℹ️  Redirected to 2FA after relogin - attempting to handle via Mailpit")
                await _handle_2fa_via_mailpit(browser)
                await browser.wait_for_timeout(1000)

            assert "/admin/login" not in browser._page.url, (
                "Re-login failed after password change (new password not accepted). "
                f"url={browser._page.url}"
            )
            await browser.wait_for_text("h1", "Dashboard", timeout=12.0)

            # At this point we have verified the new password works.
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
            await browser.wait_for_timeout(300)
            
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
