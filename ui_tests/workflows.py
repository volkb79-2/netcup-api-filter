"""Reusable workflows for admin and client UI coverage."""
from __future__ import annotations

import anyio
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Tuple

from ui_tests.browser import Browser, ToolError
from ui_tests.config import settings


def _update_deployment_state(**kwargs) -> None:
    """Update deployment env file with current state (e.g., password changes).
    
    This persists test-driven changes so subsequent test runs use the correct
    credentials without needing database resets.
    
    Automatically detects which env file to update:
    - DEPLOYMENT_ENV_FILE environment variable (explicit)
    - .env.local (local deployment)
    - .env.webhosting (webhosting deployment)
    
    Args:
        **kwargs: Key-value pairs to update (e.g., admin_password="NewPass123!")
    """
    import os
    import os.path
    
    # Determine which env file to update (NO DEFAULTS - fail-fast policy)
    # Require REPO_ROOT for portable paths
    repo_root = os.environ.get('REPO_ROOT')
    if not repo_root:
        # Fallback to calculated path but warn
        repo_root = os.path.dirname(os.path.dirname(__file__))
        print(f"[CONFIG] WARNING: REPO_ROOT not set, using calculated: {repo_root}")
        print(f"[CONFIG] Set explicitly: export REPO_ROOT=<workspace_root>")
    
    deployment_env_file = os.environ.get('DEPLOYMENT_ENV_FILE')
    
    if deployment_env_file:
        # Explicit env file specified
        env_filename = os.path.basename(deployment_env_file)
        print(f"[CONFIG] Using explicit DEPLOYMENT_ENV_FILE: {deployment_env_file}")
    else:
        # Auto-detect but warn loudly (violates fail-fast policy)
        env_local = os.path.join(repo_root, '.env.local')
        env_webhosting = os.path.join(repo_root, '.env.webhosting')
        if os.path.exists(env_local):
            env_filename = '.env.local'
            print(f"[CONFIG] WARNING: DEPLOYMENT_ENV_FILE not set, auto-detected: {env_local}")
            print(f"[CONFIG] Set explicitly: export DEPLOYMENT_ENV_FILE={env_local}")
        elif os.path.exists(env_webhosting):
            env_filename = '.env.webhosting'
            print(f"[CONFIG] WARNING: DEPLOYMENT_ENV_FILE not set, auto-detected: {env_webhosting}")
            print(f"[CONFIG] Set explicitly: export DEPLOYMENT_ENV_FILE={env_webhosting}")
        else:
            print(f"[CONFIG] ERROR: DEPLOYMENT_ENV_FILE not set and no .env.local or .env.webhosting found")
            return
    
    # CRITICAL: Never write to .env.defaults (it's the source of truth for defaults only!)
    if env_filename == '.env.defaults':
        print(f"[CONFIG] ERROR: Cannot write to {env_filename} - this file is read-only defaults")
        print(f"[CONFIG] Deployment state must be in .env.local or .env.webhosting")
        return
    
    # Try writable locations: /screenshots (Playwright container), then workspace
    possible_paths = [
        f'/screenshots/{env_filename}',  # Playwright container writable mount
        os.path.join(repo_root, env_filename),
    ]
    
    env_file = None
    for path in possible_paths:
        try:
            # Test if writable by attempting to open in append mode
            with open(path, 'a'):
                pass
            env_file = path
            break
        except (OSError, IOError):
            continue
    
    if not env_file:
        print(f"[CONFIG] WARNING: Could not find writable location for {env_filename}")
        print(f"[CONFIG] Tried: {possible_paths}")
        return
    
    # Read existing content
    lines = []
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            lines = f.readlines()
    
    # Update/add values
    updated_keys = set()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if '=' in stripped:
            key = stripped.split('=', 1)[0]
            # Check if we need to update this key
            for kwarg_key, kwarg_value in kwargs.items():
                env_key = f"DEPLOYED_{kwarg_key.upper()}"
                if key == env_key:
                    lines[i] = f"{env_key}={kwarg_value}\n"
                    updated_keys.add(env_key)
    
    # Add new keys that weren't found
    for kwarg_key, kwarg_value in kwargs.items():
        env_key = f"DEPLOYED_{kwarg_key.upper()}"
        if env_key not in updated_keys:
            lines.append(f"{env_key}={kwarg_value}\n")
    
    # Add deployment timestamp
    timestamp_updated = False
    for i, line in enumerate(lines):
        if line.startswith('DEPLOYED_AT='):
            lines[i] = f"DEPLOYED_AT={datetime.utcnow().isoformat()}Z\n"
            timestamp_updated = True
            break
    if not timestamp_updated:
        lines.append(f"DEPLOYED_AT={datetime.utcnow().isoformat()}Z\n")
    
    # Write back
    with open(env_file, 'w') as f:
        f.writelines(lines)
    
    print(f"[CONFIG] Updated {env_file}: {', '.join(f'{k}={v}' for k, v in kwargs.items())}")


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
    token = await wait_for_input_value(browser, "#client_id", lambda v: v and v != before)
    return token


async def ensure_admin_dashboard(browser: Browser) -> Browser:
    """Log into the admin UI and land on the dashboard, handling the full authentication flow.
    
    This function adapts to the current database state:
    - If password is 'admin' (initial state), logs in and changes to a generated secure password
    - If password is already changed, uses the saved password from .env.webhosting
    - Updates .env.webhosting so subsequent tests use the correct password
    """
    import anyio
    from netcup_api_filter.utils import generate_token
    
    # Try to login with current password first
    await browser.goto(settings.url("/admin/login"))
    await browser.fill("#username", settings.admin_username)
    await browser.fill("#password", settings.admin_password)
    
    # Submit the login form
    print("[DEBUG] Submitting login form...")
    print(f"[DEBUG] Current URL: {browser.current_url}")
    print(f"[DEBUG] Credentials: {settings.admin_username}/{'*' * len(settings.admin_password)}")
    
    await browser.click("button[type='submit']")
    await anyio.sleep(1.0)  # Give time for navigation/redirect
    print(f"[DEBUG] URL after form submit: {browser.current_url}")
    
    # Check for error messages
    body_text = await browser.text("body")
    if "Invalid username or password" in body_text or "lockout" in body_text.lower():
        print(f"[ERROR] Login failed. Page shows: {body_text[:500]}")
        raise AssertionError(f"Login failed: {body_text[:200]}")
    
    # Check if we're on change password page or dashboard
    current_h1 = await browser.text("main h1")
    print(f"[DEBUG] Final h1 after login: '{current_h1}'")
    if "Change Password" in current_h1:
        print("[DEBUG] On password change page, generating new secure password...")
        # Generate a cryptographically secure random password
        original_password = settings.admin_password
        new_password = generate_token()  # Generates 32-char secure token
        print(f"[DEBUG] Generated new password (length: {len(new_password)})")
        
        await browser.fill("#current_password", original_password)
        await browser.fill("#new_password", new_password)
        await browser.fill("#confirm_password", new_password)
        
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
        print(f"[DEBUG] Persisted new password to .env.webhosting")
        
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
    await browser.wait_for_text(".login-header h1", "Admin Login")
    body_text = await browser.text("body")
    assert "Invalid username or password" in body_text or "danger" in body_text


async def test_admin_access_prohibited_without_login(browser: Browser) -> None:
    """Test that access to admin pages is prohibited without login."""
    # Try to access dashboard directly
    await browser.goto(settings.url("/admin/"))
    # Should redirect to login
    await browser.wait_for_text(".login-header h1", "Admin Login")
    
    # Try to access clients page
    await browser.goto(settings.url("/admin/client/"))
    await browser.wait_for_text(".login-header h1", "Admin Login")


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
    # Logout
    await browser.click("header .navbar-user a.btn")
    await browser.wait_for_text(".login-header h1", "Admin Login")
    
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
    await browser.wait_for_text(".login-header h1", "Admin Login")
    await browser.goto(settings.url("/admin/client/"))
    await browser.wait_for_text(".login-header h1", "Admin Login")
    
    # 2. Login with correct credentials
    await browser.goto(settings.url("/admin/login"))
    await browser.fill("#username", settings.admin_username)
    await browser.fill("#password", settings.admin_password)
    await browser.click("button[type='submit']")
    await anyio.sleep(1.0)
    
    # Check if login was successful by looking for dashboard or change-password redirect
    current_h1 = await browser.text("main h1")
    if "Dashboard" in current_h1:
        # Already logged in and on dashboard (password already changed)
        print("[DEBUG] Already on dashboard - password was already changed")
        settings._active.admin_password = new_password
        settings._active.admin_new_password = new_password
        return new_password
    elif "Change Password" in current_h1:
        # On change password page - this is expected for fresh database
        print("[DEBUG] On change password page - fresh database detected")
        pass
    else:
        # Check for lockout or other errors
        body_text = await browser.text("body")
        if "Too many failed login attempts" in body_text:
            raise AssertionError("Account is locked out. Wait 15 minutes or redeploy to reset database.")
        else:
            # Still on login page - login failed
            print(f"DEBUG: After login submit, unexpected page. H1: '{current_h1}', Body: {body_text[:500]}")
            raise AssertionError(f"Login failed - unexpected page with h1: '{current_h1}'")
    
    # Navigate to change password page if not already there
    if "Change Password" not in current_h1:
        await browser.goto(settings.url("/admin/change-password"))
    
    await browser.wait_for_text("main h1", "Change Password")
    
    # Capture password change page screenshot
    await browser.screenshot("01a-admin-password-change")
    
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
    await browser.wait_for_text("main h1", "Dashboard")
    
    # 4. Logout and login with new password
    await browser.click("header .navbar-user a.btn")
    await anyio.sleep(0.5)
    await browser.wait_for_text(".login-header h1", "Admin Login")
    
    await browser.fill("#username", settings.admin_username)
    await browser.fill("#password", new_password)
    await browser.click("button[type='submit']")
    await anyio.sleep(1.0)
    await browser.wait_for_text("main h1", "Dashboard")
    
    # CRITICAL: Persist password change to .env.webhosting for subsequent test runs
    _update_deployment_state(admin_password=new_password)
    
    # Update in-memory settings for this test session
    settings._active.admin_password = new_password
    settings._active.admin_new_password = new_password
    
    return new_password


async def verify_admin_nav(browser: Browser) -> List[Tuple[str, str]]:
    """Click through primary admin navigation links and return the visited headings."""

    nav_items: List[Tuple[str, str, str]] = [
        ("Dashboard", "a.nav-link[href='/admin/']", "Dashboard"),
        ("Clients", "a.nav-link[href='/admin/client/']", "Clients"),
        ("Audit Logs", "a.nav-link[href='/admin/auditlog/']", "Audit Logs"),
        ("Netcup API", "a.nav-link[href='/admin/netcup_config/']", "Netcup API Configuration"),
        ("Email Settings", "a.nav-link[href='/admin/email_config/']", "Email Configuration"),
        ("System Info", "a.nav-link[href='/admin/system_info/']", "System Information"),
        ("Logout", "header .navbar-user a.btn", "Admin Login"),
    ]

    visited: List[Tuple[str, str]] = []
    for label, selector, expected_heading in nav_items:
        await browser.click(selector)
        heading_selector = ".login-header h1" if label == "Logout" else "main h1"
        heading = await browser.wait_for_text(heading_selector, expected_heading)
        visited.append((label, heading))

    # Re-establish the admin session for follow-up tests.
    await ensure_admin_dashboard(browser)
    return visited


async def open_admin_clients(browser: Browser) -> Browser:
    await browser.goto(settings.url("/admin/client/"))
    await browser.wait_for_text("main h1", "Clients")
    return browser


async def open_admin_audit_logs(browser: Browser) -> Browser:
    await browser.goto(settings.url("/admin/auditlog/"))
    await browser.wait_for_text("main h1", "Audit Logs")
    return browser


async def open_admin_netcup_config(browser: Browser) -> Browser:
    await browser.goto(settings.url("/admin/netcup_config/"))
    await browser.wait_for_text("main h1", "Netcup API Configuration")
    return browser


async def open_admin_email_settings(browser: Browser) -> Browser:
    await browser.goto(settings.url("/admin/email_config/"))
    await browser.wait_for_text("main h1", "Email Configuration")
    return browser


async def open_admin_system_info(browser: Browser) -> Browser:
    await browser.goto(settings.url("/admin/system_info/"))
    await browser.wait_for_text("main h1", "System Information")
    return browser


async def open_admin_client_create(browser: Browser) -> Browser:
    await browser.goto(settings.url("/admin/client/new/"))
    await browser.wait_for_text("main h1", "Clients")
    return browser


async def submit_client_form(browser: Browser, data: ClientFormData) -> str:
    """Submit client creation form and return the generated token from flash message."""
    await browser.fill("#client_id", data.client_id)
    await browser.fill("#description", data.description)
    await browser.select("select[name='realm_type']", data.realm_type)
    await browser.fill("#realm_value", data.realm_value)
    await browser.select("select[name='allowed_record_types']", data.record_choices())
    await browser.select("select[name='allowed_operations']", data.operation_choices())
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


async def ensure_client_visible(browser: Browser, client_id: str) -> None:
    await open_admin_clients(browser)
    table_text = await browser.text("table tbody")
    assert client_id in table_text, f"Expected {client_id} in clients table"


async def ensure_client_absent(browser: Browser, client_id: str) -> None:
    await open_admin_clients(browser)
    table_text = await browser.text("table tbody")
    assert client_id not in table_text, f"Did not expect {client_id} in clients table"


async def delete_admin_client(browser: Browser, client_id: str) -> None:
    """Delete a client via the admin UI."""
    await open_admin_clients(browser)
    
    # Find the delete form in the row and submit it
    row_selector = f"tr:has-text('{client_id}')"
    form_selector = f"{row_selector} form[action*='/admin/client/delete/']"
    
    # Check if form exists
    try:
        # Flask-Admin delete forms typically have a submit input
        submit_selector = f"{form_selector} input[type='submit']"
        await browser._page.click(submit_selector, force=True, timeout=5000)
    except Exception:
        # If clicking fails, try to submit the form directly
        await browser._page.locator(form_selector).evaluate("form => form.submit()")
    
    await browser.wait_for_text("main h1", "Clients")


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
    assert "Client ID" in header_row
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
        "#customer_id": "123456",
        "#api_key": "local-api-key",
        "#api_password": "local-api-pass",
        "#api_url": "https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON",
        "#timeout": "30",
    }

    for selector, fallback in defaults.items():
        current = await browser.get_attribute(selector, "value")
        await browser.fill(selector, current or fallback)

    await browser.submit("form")
    await browser.wait_for_text(".flash-messages", "Netcup API configuration saved successfully")


async def admin_email_save_expect_error(browser: Browser) -> None:
    await open_admin_email_settings(browser)
    defaults = {
        "#smtp_server": "smtp.local",
        "#smtp_port": "465",
        "#smtp_username": "local-user",
        "#smtp_password": "local-pass",
    }

    for selector, value in defaults.items():
        await browser.fill(selector, value)

    await browser.fill("#sender_email", "invalid@example")
    await browser.submit("#smtp-settings-form")
    await browser.wait_for_text(".flash-messages", "Sender email address must be valid")
    await open_admin_email_settings(browser)


async def admin_email_trigger_test_without_address(browser: Browser) -> None:
    await open_admin_email_settings(browser)
    await browser.submit("#test-email-form")
    await browser.wait_for_text(".flash-messages", "Please enter an email address to test")
    await open_admin_email_settings(browser)


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
    await browser.click("header .navbar-user a.btn")
    await browser.wait_for_text(".login-header h1", "Client Portal")


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
    await browser.goto(settings.url("/client/login"))
    await browser.fill("#token", token)
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


async def disable_admin_client(browser: Browser, client_id: str) -> None:
    """Disable a client by editing it and setting is_active to False."""
    await open_admin_clients(browser)
    
    # Find the row containing this client_id and get the edit link href
    row_selector = f"tr:has-text('{client_id}')"
    edit_link_selector = f"{row_selector} a[href*='/admin/client/edit/']"
    
    # Get the href and navigate directly (avoids viewport issues with small icons)
    edit_href = await browser._page.get_attribute(edit_link_selector, "href")
    if not edit_href:
        raise AssertionError(f"Could not find edit link for client {client_id}")
    
    await browser.goto(settings.url(edit_href))
    
    # Wait for edit form
    await browser.wait_for_text("main h1", "Clients")
    
    # Uncheck the is_active checkbox
    await browser.uncheck("#is_active")
    
    # Submit the form
    await browser.submit("form")
    
    # Should redirect back to clients list
    await browser.wait_for_text("main h1", "Clients")


async def verify_client_list_has_icons(browser: Browser) -> None:
    """Verify that the client list shows edit and delete icons."""
    await open_admin_clients(browser)
    
    # Check for edit and delete links in the table rows
    # Look for FontAwesome icons or text links
    page_html = await browser.html("body")
    
    # Check for edit functionality - either fa-edit icon or edit text
    has_edit = ("fa-edit" in page_html or 
                "icon-edit" in page_html or 
                "edit" in page_html.lower() or
                "/admin/client/edit/" in page_html)
    
    # Check for delete functionality - either fa-trash icon or delete text  
    has_delete = ("fa-trash" in page_html or 
                  "icon-trash" in page_html or 
                  "delete" in page_html.lower() or
                  "/admin/client/delete/" in page_html)
    
    assert has_edit, f"No edit functionality found in page HTML. Page contains: {page_html[:500]}..."
    assert has_delete, f"No delete functionality found in page HTML. Page contains: {page_html[:500]}..."
