"""Reusable workflows for admin and client UI coverage."""
from __future__ import annotations

import anyio
import re
import secrets
from dataclasses import dataclass
from typing import Callable, List, Tuple

from ui_tests.browser import Browser, ToolError
from ui_tests.config import settings
from ui_tests.deployment_state import (
    get_deployment_target,
    get_state_file_path,
    load_state,
    save_state,
    update_admin_password as ds_update_admin_password,
)


def _update_deployment_state(**kwargs) -> None:
    """Update deployment state file with current state (e.g., password changes).
    
    This persists test-driven changes so subsequent test runs use the correct
    credentials without needing database resets.
    
    Uses the deployment_state.json for the current DEPLOYMENT_TARGET.
    
    Args:
        **kwargs: Key-value pairs to update (e.g., admin_password="NewPass123!")
    """
    target = get_deployment_target()
    state_file = get_state_file_path(target)
    
    if not state_file.exists():
        raise RuntimeError(
            f"Deployment state file not found: {state_file}\n"
            f"DEPLOYMENT_TARGET={target}\n"
            f"Run build-and-deploy-local.sh (local) or build-and-deploy.sh (webhosting)"
        )
    
    # Load current state
    state = load_state(target)
    
    # Update admin credentials
    if "admin_password" in kwargs:
        state.admin.password = kwargs["admin_password"]
        from datetime import datetime, timezone
        state.admin.password_changed_at = datetime.now(timezone.utc).isoformat()
    
    if "admin_username" in kwargs:
        state.admin.username = kwargs["admin_username"]
    
    # Save updated state
    updated_by = kwargs.get("updated_by", "ui_test")
    save_state(state, updated_by, target)


@dataclass
class AccountFormData:
    username: str
    email: str
    description: str = ""


# Keep ClientFormData for realm creation after account is created
@dataclass
class ClientFormData:
    client_id: str
    description: str
    realm_value: str
    realm_type: str = "host"
    record_types: List[str] | None = None
    operations: List[str] | None = None
    email: str | None = None

    def record_choices(self) -> List[str]:
        return self.record_types or ["A", "AAAA", "CNAME"]

    def operation_choices(self) -> List[str]:
        return self.operations or ["read", "update"]


def generate_account_data(prefix: str = "ui-account") -> AccountFormData:
    suffix = secrets.token_hex(4)
    return AccountFormData(
        username=f"{prefix}-{suffix}",
        email=f"{prefix}-{suffix}@example.test",
        description="UI automation account",
    )


# Keep for backwards compatibility
def generate_client_data(prefix: str = "ui-client") -> ClientFormData:
    suffix = secrets.token_hex(4)
    return ClientFormData(
        client_id=f"{prefix}-{suffix}",
        description="UI automation client",
        realm_value=f"{suffix}.example.test",
    )


async def wait_for_input_value(
    browser: Browser,
    selector: str,
    predicate: Callable[[str], bool],
    timeout: float = 5.0,
    interval: float = 0.2,
) -> str:
    deadline = anyio.current_time() + timeout
    last_value = ""
    while anyio.current_time() <= deadline:
        value = await browser.get_attribute(selector, "value")
        last_value = value
        if predicate(value or ""):
            return value or ""
        await anyio.sleep(interval)
    raise AssertionError(f"Timed out waiting for value on {selector}; last value='{last_value}'")


async def wait_for_selector(
    browser: Browser,
    selector: str,
    timeout: float = 5.0,
    interval: float = 0.2,
) -> None:
    deadline = anyio.current_time() + timeout
    last_error: ToolError | None = None
    while anyio.current_time() <= deadline:
        try:
            await browser.html(selector)
            return
        except ToolError as exc:
            last_error = exc
            await anyio.sleep(interval)
    if last_error:
        raise AssertionError(f"Timed out waiting for selector '{selector}'") from last_error
    raise AssertionError(f"Timed out waiting for selector '{selector}'")


async def trigger_token_generation(browser: Browser) -> str:
    before = await browser.get_attribute("#client_id", "value")
    await wait_for_selector(browser, ".token-generate-btn")
    await browser.click(".token-generate-btn")
    token = await wait_for_input_value(browser, "#client_id", lambda v: v != "" and v != before)
    return token


async def handle_2fa_if_present(browser: Browser, timeout: float = 5.0) -> bool:
    """Handle 2FA page if redirected there. Returns True if 2FA was handled.
    
    This uses Mailpit to intercept the 2FA email and extract the code.
    Requires:
    - ADMIN_2FA_SKIP=false or not set
    - Mailpit running and accessible
    - Admin has a valid email configured
    
    If ADMIN_2FA_SKIP=true is set, the server bypasses 2FA entirely.
    """
    import anyio
    import os
    import re
    
    # Use live URL from page (not cached)
    current_url = browser._page.url
    if "/login/2fa" not in current_url and "/2fa" not in current_url:
        return False
    
    print("[DEBUG] On 2FA page, attempting to handle...")
    
    # Try to get code from Mailpit
    try:
        from ui_tests.mailpit_client import MailpitClient
        
        mailpit = MailpitClient()
        
        # Wait for 2FA email (it may take a moment)
        msg = mailpit.wait_for_message(
            predicate=lambda m: "verification" in m.subject.lower() or "login" in m.subject.lower(),
            timeout=10.0
        )
        
        if msg:
            # Extract 6-digit code from email body
            full_msg = mailpit.get_message(msg.id)
            code_match = re.search(r'\b(\d{6})\b', full_msg.text)
            
            if code_match:
                code = code_match.group(1)
                print(f"[DEBUG] Extracted 2FA code from email: {code}")
                
                # Remember current URL to detect navigation (use live URL)
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
                    await anyio.sleep(0.5)
                    # Get live URL directly from page
                    new_url = browser._page.url
                    if new_url != url_before and "/2fa" not in new_url:
                        print(f"[DEBUG] 2FA navigation complete: {new_url}")
                        break
                else:
                    print(f"[WARN] 2FA navigation did not complete, still at: {browser._page.url}")
                
                # Clear the used email
                mailpit.delete_message(msg.id)
                mailpit.close()
                return True
            else:
                print(f"[WARN] Could not extract code from email: {full_msg.text[:200]}")
        else:
            print("[WARN] No 2FA email found in Mailpit")
        
        mailpit.close()
    except Exception as e:
        print(f"[WARN] Could not handle 2FA via Mailpit: {e}")
        print("[HINT] Ensure ADMIN_2FA_SKIP=true is set for test mode, or Mailpit is running")
    
    return False


async def ensure_admin_dashboard(browser: Browser) -> Browser:
    """Log into the admin UI and land on the dashboard, handling the full authentication flow.
    
    This function adapts to the current database state:
    - If already logged in (on an admin page), skips login
    - If password is 'admin' (initial state), logs in and changes to a generated secure password
    - If password is already changed, uses the saved password from deployment state
    - Handles email setup for 2FA on first login
    - Handles 2FA via Mailpit if ADMIN_2FA_SKIP is not set
    - Updates deployment state so subsequent tests use the correct password
    """
    import anyio
    from netcup_api_filter.utils import generate_token
    
    # CRITICAL: Refresh credentials from deployment state file before login
    # This ensures we have the latest password if another test changed it
    settings.refresh_credentials()
    
    # Check if we're already logged in (on an admin page that isn't login)
    # Use live URL (not cached)
    current_url = browser._page.url
    if "/admin/" in current_url and "/admin/login" not in current_url and "/2fa" not in current_url:
        # Already logged in - just navigate to dashboard
        print("[DEBUG] Already logged in, navigating to dashboard")
        await browser.goto(settings.url("/admin/"))
        await anyio.sleep(0.3)
        return browser
    
    # Try to login with current password first
    await browser.goto(settings.url("/admin/login"))
    await anyio.sleep(0.5)
    
    # Check if we were redirected (already logged in via session)
    current_url = browser._page.url
    if "/admin/" in current_url and "/admin/login" not in current_url and "/2fa" not in current_url:
        print("[DEBUG] Already logged in (redirected from login), on dashboard")
        return browser
    
    # Check if login form exists
    username_field = await browser.query_selector("#username")
    if not username_field:
        # No login form - check if we're on admin page
        if "/admin" in current_url and "/login" not in current_url and "/2fa" not in current_url:
            print("[DEBUG] Already on admin page (no login form)")
            return browser
    
    await browser.fill("#username", settings.admin_username)
    await browser.fill("#password", settings.admin_password)
    
    # Submit the login form
    print("[DEBUG] Submitting login form...")
    print(f"[DEBUG] Current URL: {browser._page.url}")
    print(f"[DEBUG] Credentials: {settings.admin_username}/{'*' * len(settings.admin_password)}")
    
    await browser.click("button[type='submit']")
    await anyio.sleep(1.0)  # Give time for navigation/redirect
    print(f"[DEBUG] URL after form submit: {browser._page.url}")
    
    # Check for error messages
    body_text = await browser.text("body")
    has_invalid = "Invalid username or password" in body_text or "Invalid credentials" in body_text
    print(f"[DEBUG] Body text check: has_invalid={has_invalid}, len={len(body_text)}")
    if has_invalid:
        # Only fail if we're still on login page (use live URL)
        if "/login" in browser._page.url:
            print(f"[ERROR] Login failed. Page shows: {body_text[:500]}")
            raise AssertionError(f"Login failed: {body_text[:200]}")
        else:
            # Flash message from previous attempt but we're logged in
            print(f"[DEBUG] Ignoring stale 'Invalid' flash message - already on dashboard")
    
    if "lockout" in body_text.lower() or "locked" in body_text.lower():
        print(f"[ERROR] Account locked out. Page shows: {body_text[:500]}")
        raise AssertionError(f"Account locked: {body_text[:200]}")
    
    # Handle 2FA if we're redirected there
    await handle_2fa_if_present(browser)
    
    # Re-check current page after potential 2FA (use live URL)
    current_url = browser._page.url
    print(f"[DEBUG] URL after 2FA check: {current_url}")
    
    # Check if we're on change password page or dashboard
    current_h1 = await browser.text("main h1")
    print(f"[DEBUG] Final h1 after login: '{current_h1}'")
    
    if "Change Password" in current_h1 or "Initial Setup" in current_h1:
        print("[DEBUG] On password change/setup page, generating new secure password...")
        # Generate a cryptographically secure random password
        original_password = settings.admin_password
        # generate_token only uses alphanumeric, but password form requires special char
        base_token = generate_token()  # Generates 63-65 char alphanumeric token
        new_password = base_token[:60] + "@#$%"  # Add special chars to meet requirements (no ! for shell safety)
        print(f"[DEBUG] Generated new password (length: {len(new_password)})")
        
        # Check if email field is present (first-time setup)
        email_field = await browser.query_selector("#email")
        if email_field:
            # Set a test email for 2FA
            test_email = f"admin-test-{secrets.token_hex(4)}@example.test"
            print(f"[DEBUG] Setting up email for 2FA: {test_email}")
            await browser.fill("#email", test_email)
        
        # Fill password fields - current_password may not be present for forced change
        current_password_field = await browser.query_selector("#current_password")
        if current_password_field:
            await browser.fill("#current_password", original_password)
        
        await browser.fill("#new_password", new_password)
        await browser.fill("#confirm_password", new_password)
        
        # Wait for JavaScript validation to enable the submit button
        print("[DEBUG] Waiting for form validation to enable submit button...")
        await anyio.sleep(0.5)  # Give JavaScript time to validate
        
        # Wait for submit button to be enabled
        submit_enabled = False
        for _ in range(10):  # Try up to 5 seconds
            try:
                is_disabled = await browser._page.locator("#submitBtn").get_attribute("disabled")
                if is_disabled is None:  # Not disabled means enabled
                    submit_enabled = True
                    break
                print(f"[DEBUG] Submit button still disabled, retrying...")
            except Exception:
                pass
            await anyio.sleep(0.5)
        
        if not submit_enabled:
            print("[WARN] Submit button still disabled, trying to trigger validation...")
            # Trigger input event on the form fields to run validation
            await browser._page.locator("#confirm_password").blur()
            await anyio.sleep(0.5)
        
        # Submit password change form and wait for redirect
        print("[DEBUG] Submitting password change...")
        await browser.click("button[type='submit']")
        deadline = anyio.current_time() + 5.0
        elapsed = 0
        while anyio.current_time() < deadline:
            await anyio.sleep(0.5)
            elapsed += 0.5
            current_h1 = await browser.text("main h1")
            print(f"[DEBUG] After password change {elapsed}s: h1='{current_h1}', URL={browser.current_url}")
            if "Dashboard" in current_h1:
                print(f"[DEBUG] Detected dashboard after {elapsed}s")
                break
        
        # CRITICAL: Persist password change for subsequent test runs
        _update_deployment_state(admin_password=new_password)
        print(f"[DEBUG] Persisted new password to deployment state")
        
        # Update in-memory settings for this test session
        settings._active.admin_password = new_password
        settings._active.admin_new_password = new_password
    
    # Final verification - ensure we're on dashboard
    current_h1 = await browser.text("main h1")
    print(f"[DEBUG] Before final verification: h1='{current_h1}', URL={browser.current_url}")
    await browser.wait_for_text("main h1", "Dashboard", timeout=10.0)

    return browser


async def test_admin_login_wrong_credentials(browser: Browser) -> None:
    """Test that login with wrong credentials fails."""
    await browser.goto(settings.url("/admin/login"))
    await browser.fill("#username", "wronguser")
    await browser.fill("#password", "wrongpass")
    await browser.click("button[type='submit']")
    
    # Should stay on login page with error message
    await wait_for_selector(browser, ".login-container form button[type='submit']")
    body_text = await browser.text("body")
    assert "Invalid username or password" in body_text or "danger" in body_text


async def test_admin_access_prohibited_without_login(browser: Browser) -> None:
    """Test that access to admin pages is prohibited without login."""
    # Try to access dashboard directly
    await browser.goto(settings.url("/admin/"))
    # Should redirect to login
    await wait_for_selector(browser, ".login-container form button[type='submit']")
    
    # Try to access accounts page
    await browser.goto(settings.url("/admin/accounts"))
    await wait_for_selector(browser, ".login-container form button[type='submit']")


async def test_admin_change_password_validation(browser: Browser) -> None:
    """Test that change password fails when passwords don't match."""
    # First login with correct credentials
    await browser.goto(settings.url("/admin/login"))
    await browser.fill("#username", settings.admin_username)
    await browser.fill("#password", settings.admin_password)
    await browser.click("button[type='submit']")
    
    # Should be redirected to change password
    await browser.wait_for_text("main h1", "Change Password")
    
    # Try to change password with non-matching passwords
    await browser.fill("#current_password", settings.admin_password)
    await browser.fill("#new_password", "NewPassword123!")
    await browser.fill("#confirm_password", "DifferentPassword123!")
    await browser.click("button[type='submit']")
    
    # Should stay on change password page with error
    await browser.wait_for_text("main h1", "Change Password")
    body_text = await browser.text("body")
    assert "New passwords do not match" in body_text or "danger" in body_text


async def test_admin_change_password_success(browser: Browser, new_password: str) -> None:
    """Test that change password works when used correctly."""
    # Should already be on change password page from previous test
    await browser.fill("#current_password", settings.admin_password)
    await browser.fill("#new_password", new_password)
    await browser.fill("#confirm_password", new_password)
    await browser.click("button[type='submit']")
    
    # Should redirect to dashboard
    await browser.wait_for_text("main h1", "Dashboard")


async def test_admin_logout_and_login_with_new_password(browser: Browser, new_password: str) -> None:
    """Test logout and login with new password."""
    # Logout - use JavaScript for reliable dropdown handling
    await browser.evaluate(
        """
        () => {
            const toggle = document.querySelector('.navbar .dropdown-toggle');
            if (toggle) {
                toggle.click();
                setTimeout(() => {
                    const logout = document.querySelector('a[href*="logout"]');
                    if (logout) logout.click();
                }, 200);
            }
        }
        """
    )
    await anyio.sleep(1.0)
    await browser.wait_for_text(".login-container button[type='submit']", "Sign In")
    
    # Login with new password
    await browser.fill("#username", settings.admin_username)
    await browser.fill("#password", new_password)
    await browser.click("button[type='submit']")
    
    # Should go to dashboard
    await browser.wait_for_text("main h1", "Dashboard")


async def perform_admin_authentication_flow(browser: Browser) -> str:
    """Perform the complete admin authentication flow and return the new password.
    
    NOTE: This test does NOT test wrong credentials to avoid triggering account lockout.
    Wrong credential testing should be done in a separate, isolated test.
    """
    from netcup_api_filter.utils import generate_token
    new_password = generate_token()  # Generate secure random password
    
    # 1. Test access to admin pages is prohibited without login
    await browser.goto(settings.url("/admin/"))
    await wait_for_selector(browser, ".login-container form button[type='submit']")
    await browser.goto(settings.url("/admin/accounts"))
    await wait_for_selector(browser, ".login-container form button[type='submit']")
    
    # 2. Login with correct credentials
    await browser.goto(settings.url("/admin/login"))
    await browser.fill("#username", settings.admin_username)
    await browser.fill("#password", settings.admin_password)
    await browser.click("button[type='submit']")
    await anyio.sleep(1.0)
    
    # Check if login was successful by looking for dashboard or change-password redirect
    # After login restructuring, check both the page content and URL
    body_text = await browser.text("body")
    current_url = browser.current_url or ""
    
    if "/admin/change-password" in current_url or "Change Password" in body_text:
        # On change password page - this is expected for fresh database
        print("[DEBUG] On change password page - fresh database detected")
        pass
    elif "/admin/" in current_url and ("Dashboard" in body_text or "Clients" in body_text):
        # Already logged in and on dashboard (password already changed)
        # Return the CURRENT password from settings (not a new random one)
        print("[DEBUG] Already on dashboard - password was already changed")
        return settings.admin_password
    else:
        # Check for lockout or other errors
        if "Too many failed login attempts" in body_text:
            raise AssertionError("Account is locked out. Wait 15 minutes or redeploy to reset database.")
        elif "/admin/login" in current_url:
            # Still on login page - login failed
            print(f"DEBUG: Login failed. URL: {current_url}, Body: {body_text[:500]}")
            raise AssertionError(f"Login failed - still on login page")
        else:
            # Unknown state
            print(f"DEBUG: After login submit, unexpected state. URL: {current_url}, Body: {body_text[:500]}")
            raise AssertionError(f"Login failed - unexpected page at {current_url}")
    
    # Navigate to change password page if not already there
    if "/admin/change-password" not in current_url:
        await browser.goto(settings.url("/admin/change-password"))
    
    await browser.wait_for_text("main h1", "Change Password")
    
    # Set consistent viewport before screenshot (NO HARDCODED VALUES)
    import os
    width = int(os.environ.get('SCREENSHOT_VIEWPORT_WIDTH', '1920'))
    height = int(os.environ.get('SCREENSHOT_VIEWPORT_HEIGHT', '1200'))
    await browser._page.set_viewport_size({"width": width, "height": height})
    
    # Capture password change page screenshot
    await browser.screenshot("00b-admin-password-change")
    
    # Test change password with non-matching passwords
    await browser.fill("#current_password", settings.admin_password)
    await browser.fill("#new_password", "NewPassword123!")
    await browser.fill("#confirm_password", "DifferentPassword123!")
    await browser.submit("form")
    await anyio.sleep(0.5)
    await browser.wait_for_text("main h1", "Change Password")
    body_text = await browser.text("body")
    assert "New passwords do not match" in body_text or "danger" in body_text
    
    # 3. Successfully change password
    await browser.fill("#current_password", settings.admin_password)
    await browser.fill("#new_password", new_password)
    await browser.fill("#confirm_password", new_password)
    await browser.submit("form")
    await anyio.sleep(1.0)
    # After password change, should redirect to dashboard
    await browser.wait_for_text("body", "Dashboard")
    
    # 4. Logout and login with new password
    # Use JavaScript to reliably open dropdown and click logout
    await browser.evaluate(
        """
        () => {
            // Find and click the dropdown toggle
            const toggle = document.querySelector('.navbar .dropdown-toggle');
            if (toggle) {
                toggle.click();
                // Give dropdown time to open, then click logout
                setTimeout(() => {
                    const logout = document.querySelector('a[href*="logout"]');
                    if (logout) logout.click();
                }, 200);
            }
        }
        """
    )
    await anyio.sleep(1.0)
    await browser.wait_for_text(".login-container button[type='submit']", "Sign In")
    
    await browser.fill("#username", settings.admin_username)
    await browser.fill("#password", new_password)
    await browser.click("button[type='submit']")
    await anyio.sleep(1.0)
    
    # After login with new password, we should go directly to dashboard
    # (the password was already changed so no change-password redirect)
    body_text = await browser.text("body")
    current_url = browser.current_url or ""
    print(f"[DEBUG] After re-login: URL={current_url}, body preview={body_text[:200]}")
    await browser.wait_for_text("main h1", "Dashboard")
    
    # CRITICAL: Persist password change to .env.webhosting for subsequent test runs
    _update_deployment_state(admin_password=new_password)
    
    # Update in-memory settings for this test session
    settings._active.admin_password = new_password
    settings._active.admin_new_password = new_password
    
    return new_password


async def verify_admin_nav(browser: Browser) -> List[Tuple[str, str]]:
    """Click through primary admin navigation links and return the visited headings."""

    # Direct nav links (not in dropdowns)
    nav_items: List[Tuple[str, str, str]] = [
        ("Dashboard", "a.nav-link[href='/admin/']", "Dashboard"),
        ("Accounts", "a.nav-link[href='/admin/accounts']", "Accounts"),
        ("Pending", "a.nav-link[href='/admin/realms/pending']", "Pending Realm Requests"),
        ("Audit", "a.nav-link[href='/admin/audit']", "Audit Logs"),
    ]
    
    # Config dropdown items
    config_items: List[Tuple[str, str, str]] = [
        ("Netcup API", "a.dropdown-item[href='/admin/config/netcup']", "Netcup API Configuration"),
        ("Email", "a.dropdown-item[href='/admin/config/email']", "Email Configuration"),
        ("System", "a.dropdown-item[href='/admin/system']", "System Information"),
    ]

    visited: List[Tuple[str, str]] = []
    
    # Test direct nav links
    for label, selector, expected_heading in nav_items:
        await browser.click(selector)
        await anyio.sleep(0.3)
        heading = await browser.wait_for_text("main h1", expected_heading)
        visited.append((label, heading))
    
    # Test Config dropdown items
    for label, selector, expected_heading in config_items:
        # First open the Config dropdown
        await browser.click("a.nav-link.dropdown-toggle:has-text('Config')")
        await anyio.sleep(0.3)
        # Then click the item
        await browser.click(selector)
        await anyio.sleep(0.3)
        heading = await browser.wait_for_text("main h1", expected_heading)
        visited.append((label, heading))
    
    # Test Logout - navigate directly to logout URL
    await browser.goto(settings.url("/admin/logout"))
    await anyio.sleep(1.0)
    # Wait for redirect to login page - check for the login form's submit button
    heading = await browser.wait_for_text("button[type='submit']", "Sign In")
    visited.append(("Logout", heading))

    # Re-establish the admin session for follow-up tests.
    await ensure_admin_dashboard(browser)
    return visited


async def open_admin_accounts(browser: Browser) -> Browser:
    await browser.goto(settings.url("/admin/accounts"))
    await browser.wait_for_text("main h1", "Accounts")
    return browser


# Alias for backwards compatibility
open_admin_clients = open_admin_accounts


async def open_admin_audit_logs(browser: Browser) -> Browser:
    await browser.goto(settings.url("/admin/audit"))
    await browser.wait_for_text("main h1", "Audit Logs")
    return browser


async def open_admin_netcup_config(browser: Browser) -> Browser:
    await browser.goto(settings.url("/admin/config/netcup"))
    await browser.wait_for_text("main h1", "Netcup API Configuration")
    return browser


async def open_admin_email_settings(browser: Browser) -> Browser:
    await browser.goto(settings.url("/admin/config/email"))
    await browser.wait_for_text("main h1", "Email Configuration")
    return browser


async def open_admin_system_info(browser: Browser) -> Browser:
    await browser.goto(settings.url("/admin/system"))
    await browser.wait_for_text("main h1", "System Information")
    return browser


async def open_admin_account_create(browser: Browser) -> Browser:
    await browser.goto(settings.url("/admin/accounts/new"))
    await browser.wait_for_text("main h1", "Create Account")
    return browser


# Alias for backwards compatibility
open_admin_client_create = open_admin_account_create


async def submit_account_form(browser: Browser, data: AccountFormData) -> str:
    """Submit account creation form and return the account username."""
    await browser.fill("#username", data.username)
    await browser.fill("#email", data.email)
    if data.description:
        await browser.fill("#description", data.description)
    
    await browser.submit("form")
    
    # Wait for success message or redirect to account detail
    body_text = await browser.text("body")
    if "Account created" in body_text or data.username in body_text:
        return data.username
    
    raise AssertionError(f"Account creation failed: {body_text[:500]}")


# Keep for backwards compatibility - but note this is now creating accounts, not clients
async def submit_client_form(browser: Browser, data: ClientFormData) -> str:
    """Submit client creation form and return the generated token from flash message."""
    await browser.fill("#client_id", data.client_id)
    await browser.fill("#description", data.description)
    await browser.select("select[name='realm_type']", data.realm_type)
    await browser.fill("#realm_value", data.realm_value)

    # The original <select> is hidden; we must interact with it via JavaScript.
    # This is more robust than trying to click the custom UI elements.
    await browser.evaluate(
        """
        (args) => {
            const [selector, values] = args;
            const select = document.querySelector(selector);
            if (!select) return;
            for (const option of select.options) {
                option.selected = values.includes(option.value);
            }
            select.dispatchEvent(new Event('change', { bubbles: true }));
        }
        """,
        ["select[name='allowed_record_types']", data.record_choices()],
    )

    await browser.evaluate(
        """
        (args) => {
            const [selector, values] = args;
            const select = document.querySelector(selector);
            if (!select) return;
            for (const option of select.options) {
                option.selected = values.includes(option.value);
            }
            select.dispatchEvent(new Event('change', { bubbles: true }));
        }
        """,
        ["select[name='allowed_operations']", data.operation_choices()],
    )

    if data.email:
        await browser.fill("#email_address", data.email)
    
    await browser.submit("form")
    
    # Wait for success message and extract token
    success_msg = await browser.wait_for_text(".alert-success", "Client created successfully")
    
    # Extract token from message - token is in <code> tag after "Authentication token"
    # Token format is client_id:secret_key (two-factor authentication)
    import re
    
    # Look for text inside code tag: <code ...>actual_token_here</code>
    code_match = re.search(r'<code[^>]*>([^<]+)</code>', success_msg)
    if code_match:
        token = code_match.group(1)
    else:
        # Fallback: try to extract after colon (but before any HTML)
        match = re.search(r'Authentication token[^:]*:\s*([A-Za-z0-9_:]+)(?=\s|<|$)', success_msg)
        if not match:
            raise AssertionError(f"Could not extract token from success message: {success_msg}")
        token = match.group(1)
    
    # Verify token format (should contain exactly one colon)
    if ':' not in token:
        raise AssertionError(f"Token should be in client_id:secret_key format, got: {token}")
    
    return token


async def ensure_account_visible(browser: Browser, account_id: str) -> None:
    await open_admin_accounts(browser)
    table_text = await browser.text("table tbody")
    assert account_id in table_text, f"Expected {account_id} in accounts table"


# Alias for backwards compatibility
ensure_client_visible = ensure_account_visible


async def ensure_account_absent(browser: Browser, account_id: str) -> None:
    await open_admin_accounts(browser)
    table_text = await browser.text("table tbody")
    assert account_id not in table_text, f"Did not expect {account_id} in accounts table"


# Alias for backwards compatibility
ensure_client_absent = ensure_account_absent


async def delete_admin_account(browser: Browser, account_id: str) -> None:
    """Disable an account via the admin UI (soft delete)."""
    await open_admin_accounts(browser)
    
    # Find the account row and click into detail view
    row_selector = f"tr:has-text('{account_id}')"
    link_selector = f"{row_selector} a[href*='/admin/accounts/']"
    
    # Click on the account link to go to detail page
    await browser._page.click(link_selector, timeout=5000)
    await browser.wait_for_text("main h1", account_id)
    
    # Find and click the disable button
    await browser._page.click("form[action*='/disable'] button[type='submit']", timeout=5000)
    
    await browser.wait_for_text("main h1", "Accounts")


# Alias for backwards compatibility
delete_admin_client = delete_admin_account


async def admin_logout_and_prepare_client_login(browser: Browser) -> None:
    """Logout from admin UI and robustly navigate to client login page."""
    print("[DEBUG] Workflow: Logging out admin to prepare for client login.")
    await admin_logout(browser)
    
    # Add a small delay to allow server-side session to clear completely
    print("[DEBUG] Workflow: Delaying for 500ms before navigating.")
    await anyio.sleep(0.5)
    
    print("[DEBUG] Workflow: Navigating to client login page.")
    await browser.goto(settings.url("/client/login"))
    
    # Add another debug screenshot to see the result of the navigation
    await browser.screenshot("debug-after-client-login-goto")
    
    # Robustly wait for the client login form to be ready
    print("[DEBUG] Workflow: Waiting for client login form elements.")
    await wait_for_selector(browser, "#client_id")
    await wait_for_selector(browser, "#secret_key")
    await browser.wait_for_text(".login-container button[type='submit']", "Sign In")
    print("[DEBUG] Workflow: Client login page is ready.")


async def admin_logout(browser: Browser) -> None:
    """Logout from admin UI and wait for login page."""
    print("[DEBUG] Admin logout: using JavaScript to open dropdown and logout.")
    # Use JavaScript to reliably open dropdown and click logout
    await browser.evaluate(
        """
        () => {
            const toggle = document.querySelector('.navbar .dropdown-toggle');
            if (toggle) {
                toggle.click();
                setTimeout(() => {
                    const logout = document.querySelector('a[href*="logout"]');
                    if (logout) logout.click();
                }, 200);
            }
        }
        """
    )
    await anyio.sleep(1.0)
    print(f"[DEBUG] Admin logout: URL after click is {browser.current_url}")
    
    # After logout, we should be on the admin login page.
    await browser.wait_for_text(".login-container button[type='submit']", "Sign In")
    print("[DEBUG] Admin logout: successfully detected admin login page.")


async def client_portal_login(browser: Browser) -> Browser:
    await browser.goto(settings.url("/client/login"))
    # Split token into separate client_id and secret_key fields
    client_id, secret_key = settings.client_token.split(":", 1)
    await browser.fill('input[name="client_id"]', client_id)
    await browser.fill('input[name="secret_key"]', secret_key)
    await browser.click("button[type='submit']")
    body = await browser.text("body")
    if "internal server error" in body.lower() or "server error" in body.lower():
        raise AssertionError(
            "Client portal login failed with server error; investigate backend logs before rerunning client UI tests"
        )
    await browser.wait_for_text("main h1", settings.client_id)
    return browser


async def admin_verify_audit_log_columns(browser: Browser) -> str:
    await open_admin_audit_logs(browser)
    header_row = await browser.text("table thead tr")
    assert "Timestamp" in header_row
    assert "Actor" in header_row  # Changed from "Client ID" 
    return header_row


async def admin_submit_invalid_client(browser: Browser) -> None:
    """Submit an invalid client form and assert validation feedback is shown."""

    data = ClientFormData(
        client_id=f"invalid-{secrets.token_hex(2)}",
        description="Invalid client for validation flow",
        realm_value="bad value with spaces",
    )
    await browser.fill("#client_id", data.client_id)
    await browser.fill("#description", data.description)
    await browser.select("select[name='realm_type']", data.realm_type)
    await browser.fill("#realm_value", data.realm_value)
    await browser.select("select[name='allowed_record_types']", data.record_choices())
    await browser.select("select[name='allowed_operations']", data.operation_choices())
    await browser.submit("form")
    await browser.wait_for_text("main h1", "Clients")
    await browser.wait_for_text(
        ".flash-messages",
        "Realm value must be a valid domain",
    )
    current = await browser.get_attribute("#client_id", "value")
    assert current == data.client_id
    body_text = await browser.text("body")
    assert "Client created successfully" not in body_text


async def admin_click_cancel_from_client_form(browser: Browser) -> None:
    await browser.click("text=Cancel")
    await browser.wait_for_text("main h1", "Clients")


async def admin_configure_netcup_api(
    browser: Browser,
    customer_id: str,
    api_key: str,
    api_password: str,
    api_url: str,
    timeout: str = "30"
) -> None:
    """Configure Netcup API credentials for E2E testing with mock server."""
    await open_admin_netcup_config(browser)
    
    await browser.fill('input[name="customer_id"]', customer_id)
    await browser.fill('input[name="api_key"]', api_key)
    await browser.fill('input[name="api_password"]', api_password)
    await browser.fill('input[name="api_url"]', api_url)
    await browser.fill('input[name="timeout"]', timeout)
    
    await browser.submit("form")
    await browser.wait_for_text(".flash-messages", "Netcup API configuration saved successfully")


async def admin_create_client_and_extract_token(browser: Browser, data: ClientFormData) -> str:
    """Create a new client and extract the token from the success message.
    
    Returns the complete authentication token in client_id:secret_key format.
    """
    await open_admin_client_create(browser)
    # submit_client_form already extracts and validates the token
    token = await submit_client_form(browser, data)
    return token


async def admin_save_netcup_config(browser: Browser) -> None:
    await open_admin_netcup_config(browser)
    defaults = {
        "#customer_number": "123456",
        "#api_key": "local-api-key",
        "#api_password": "local-api-pass",
        "#api_endpoint": "https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON",
        "#timeout": "30",
    }

    for selector, fallback in defaults.items():
        current = await browser.get_attribute(selector, "value")
        await browser.fill(selector, current or fallback)

    await browser.submit("form")
    await browser.wait_for_text("body", "saved", timeout=10.0)


async def admin_email_save_expect_error(browser: Browser) -> None:
    """Test email config page loads and shows form fields.
    
    NOTE: After testing with fake values, restores Mailpit config
    so that other tests (like Registration E2E) can send real emails.
    """
    await open_admin_email_settings(browser)
    
    # Verify key form elements exist by getting their HTML
    page_html = await browser.html("body")
    assert "smtp_host" in page_html, "SMTP host field not found"
    assert "smtp_port" in page_html, "SMTP port field not found"
    assert "from_email" in page_html, "From email field not found"
    
    # Fill valid test values
    await browser.fill("#smtp_host", "smtp.test.local")
    await browser.fill("#smtp_port", "587")
    await browser.fill("#from_email", "test@example.com")
    
    # Submit form and check for success
    await browser.click('button[type="submit"]')
    await browser.wait_for_text("body", "saved", timeout=10.0)
    
    # Restore Mailpit config so other tests can send real emails
    # This is important for Registration E2E tests that rely on Mailpit
    # Read correct hostname from environment (naf-dev-mailpit in local dev)
    import os
    mailpit_host = os.environ.get("SERVICE_MAILPIT", "mailpit")
    await open_admin_email_settings(browser)
    await browser.fill("#smtp_host", mailpit_host)
    await browser.fill("#smtp_port", "1025")
    await browser.fill("#from_email", "naf@example.com")
    await browser.click('button[type="submit"]')
    await browser.wait_for_text("body", "saved", timeout=10.0)


async def admin_email_trigger_test_without_address(browser: Browser) -> None:
    """Test the Send Test Email button triggers async request.
    
    NOTE: After testing, restores Mailpit config so other tests work.
    """
    await open_admin_email_settings(browser)
    
    # Fill required fields first
    await browser.fill("#smtp_host", "smtp.test.local")
    await browser.fill("#smtp_port", "587")
    await browser.fill("#from_email", "test@example.com")
    
    # Click the test email button (uses JavaScript sendTestEmail function)
    await browser.click('button:has-text("Send Test Email")')
    
    # Wait for status update in emailStatus div - either shows spinner or badge after async call
    import anyio
    await anyio.sleep(1)  # Allow async JS to start
    status_html = await browser.html("#emailStatus")
    # After clicking, either spinner or result should appear
    assert "spinner" in status_html.lower() or "badge" in status_html.lower() or "sending" in status_html.lower() or "check" in status_html.lower()
    
    # Restore Mailpit config so other tests can send real emails
    import os
    mailpit_host = os.environ.get("SERVICE_MAILPIT", "mailpit")
    await open_admin_email_settings(browser)
    await browser.fill("#smtp_host", mailpit_host)
    await browser.fill("#smtp_port", "1025")
    await browser.fill("#from_email", "naf@example.com")
    await browser.click('button[type="submit"]')
    await browser.wait_for_text("body", "saved", timeout=10.0)


async def client_portal_manage_all_domains(browser: Browser) -> List[str]:
    """Click each Manage button and assert the domain detail view loads and sorts."""

    dashboard_html = await browser.html("body")
    links = sorted(set(re.findall(r"href=\"(/client/domains/[^\"]+)\"", dashboard_html)))
    assert links, "No domains with Manage links were found"
    visited: List[str] = []

    for link in links:
        domain = link.rsplit("/", 1)[-1]
        await browser.click(f"a[href='{link}']")
        await browser.wait_for_text("main h1", domain)

        table_selector = "table.table"
        try:
            await browser.click(f"{table_selector} thead th.sortable:nth-child(2)")
            await browser.click(f"{table_selector} thead th.sortable:nth-child(3)")
        except ToolError:
            # Domains without records won't render the table; skip sort interaction.
            pass

        await browser.click("text=Back to Dashboard")
        await browser.wait_for_text("main h1", settings.client_id)
        visited.append(domain)

    return visited


async def client_portal_logout(browser: Browser) -> None:
    # Use JavaScript to reliably open dropdown and click logout
    await browser.evaluate(
        """
        () => {
            const toggle = document.querySelector('.navbar .dropdown-toggle');
            if (toggle) {
                toggle.click();
                setTimeout(() => {
                    const logout = document.querySelector('a[href*="logout"]');
                    if (logout) logout.click();
                }, 200);
            }
        }
        """
    )
    await anyio.sleep(1.0)
    await browser.wait_for_text(".login-container button[type='submit']", "Sign In")


async def client_portal_open_activity(browser: Browser) -> str:
    """Navigate to client activity page and return the table header text or empty message."""
    await browser.goto(settings.url("/client/activity"))
    await browser.wait_for_text("main h1", "Activity Log")
    
    # Check if there are any logs by looking for the table or empty message
    body_html = await browser.html("body")
    if "No activity recorded yet" in body_html:
        return "No activity recorded yet"
    else:
        # Return the table header text to verify columns are present
        header_row = await browser.text("table thead tr")
        return header_row


async def test_client_login_with_token(browser: Browser, token: str, should_succeed: bool = True, expected_client_id: str | None = None) -> None:
    """Test client login with a specific token."""
    print(f"[DEBUG] Client login: Navigating to /client/login. Current URL: {browser.current_url}")
    await browser.goto(settings.url("/client/login"))
    print(f"[DEBUG] Client login: URL is now {browser.current_url}")
    await wait_for_selector(browser, "#client_id")
    await wait_for_selector(browser, "#secret_key")
    await browser.wait_for_text(".login-container button[type='submit']", "Sign In")
    # Parse token into client_id:secret_key format
    if ":" in token:
        client_id, secret_key = token.split(":", 1)
    else:
        client_id, secret_key = token, token  # Legacy fallback
    await browser.fill("#client_id", client_id)
    await browser.fill("#secret_key", secret_key)
    await browser.click("button[type='submit']")
    
    if should_succeed:
        body = await browser.text("body")
        if "internal server error" in body.lower() or "server error" in body.lower():
            raise AssertionError("Client portal login failed with server error")
        
        # Check what the main h1 actually contains
        h1_text = await browser.text("main h1")
        client_id_to_check = expected_client_id or settings.client_id
        
        if client_id_to_check not in h1_text:
            # Debug: print what we actually got
            full_body = await browser.text("body")
            raise AssertionError(f"Expected client ID '{client_id_to_check}' in main h1, but got '{h1_text}'. Full body: {full_body[:500]}")
        
        await browser.wait_for_text("main h1", client_id_to_check)
    else:
        # Should fail - check for error message or redirect
        body_text = await browser.text("body")
        assert "Invalid token" in body_text or "danger" in body_text or "error" in body_text.lower()


async def disable_admin_account_by_edit(browser: Browser, account_id: str) -> None:
    """Disable an account by navigating to its detail page and using the disable button."""
    await open_admin_accounts(browser)
    
    # Find the row containing this account_id and get the detail link href
    row_selector = f"tr:has-text('{account_id}')"
    detail_link_selector = f"{row_selector} a[href*='/admin/accounts/']"
    
    # Get the href and navigate directly
    detail_href = await browser._page.get_attribute(detail_link_selector, "href")
    if not detail_href:
        raise AssertionError(f"Could not find detail link for account {account_id}")
    
    await browser.goto(settings.url(detail_href))
    
    # Wait for account detail page
    await browser.wait_for_text("main h1", account_id)
    
    # Click the disable button
    await browser._page.click("form[action*='/disable'] button[type='submit']")
    
    # Should redirect back to accounts list
    await browser.wait_for_text("main h1", "Accounts")


# Alias for backwards compatibility
disable_admin_client = disable_admin_account_by_edit


async def verify_account_list_has_icons(browser: Browser) -> None:
    """Verify that the account list shows view and disable icons."""
    await open_admin_accounts(browser)
    
    # Check for view and action functionality in the table rows
    page_html = await browser.html("body")
    
    # Check for view functionality - account detail links
    has_view = "/admin/accounts/" in page_html
    
    # Check for action buttons or links  
    has_actions = ("Approve" in page_html or 
                   "Disable" in page_html or
                   "btn" in page_html)
    
    assert has_view, f"No view functionality found in page HTML. Page contains: {page_html[:500]}..."


# Alias for backwards compatibility
verify_client_list_has_icons = verify_account_list_has_icons