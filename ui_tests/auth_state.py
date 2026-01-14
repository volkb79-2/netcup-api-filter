"""
Authentication state management for persistent sessions across tests.

Solves HTTPS cookie issues by saving/restoring browser storage state.
Integrates with deployment_state_*.json for credential management.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from playwright.async_api import BrowserContext, Page


# Storage state files (Playwright session cookies/localStorage)
AUTH_STATE_DIR = Path(__file__).parent.parent / "tmp" / "auth-states"
AUTH_STATE_DIR.mkdir(parents=True, exist_ok=True)

# Deployment state files (credentials and metadata)
DEPLOYMENT_STATE_DIR = Path(__file__).parent.parent
DEPLOYMENT_STATE_LOCAL = DEPLOYMENT_STATE_DIR / "deployment_state_local.json"
DEPLOYMENT_STATE_WEBHOSTING = DEPLOYMENT_STATE_DIR / "deployment_state_webhosting.json"


def get_deployment_state_path(target: str = "local") -> Path:
    """Get path to deployment state file for target environment.
    
    Args:
        target: Deployment target ('local' or 'webhosting')
    
    Returns:
        Path to deployment_state_{target}.json
    """
    if target == "webhosting":
        return DEPLOYMENT_STATE_WEBHOSTING
    return DEPLOYMENT_STATE_LOCAL


def load_deployment_credentials(target: str = "local") -> dict:
    """Load admin credentials from deployment state file.
    
    Args:
        target: Deployment target ('local' or 'webhosting')
    
    Returns:
        Dict with admin credentials: {'username': str, 'password': str}
    """
    state_file = get_deployment_state_path(target)
    
    if not state_file.exists():
        # Fallback to default credentials for fresh deployments
        return {
            'username': os.environ.get('DEFAULT_ADMIN_USERNAME', 'admin'),
            'password': os.environ.get('DEFAULT_ADMIN_PASSWORD', 'admin')
        }
    
    with open(state_file) as f:
        state = json.load(f)
    
    return {
        'username': state.get('admin', {}).get('username', 'admin'),
        'password': state.get('admin', {}).get('password', 'admin')
    }


def save_deployment_credentials(
    username: str,
    password: str,
    target: str = "local",
    updated_by: str = "auth_state"
) -> None:
    """Save admin credentials to deployment state file.
    
    Args:
        username: Admin username
        password: Admin password (current, after change)
        target: Deployment target ('local' or 'webhosting')
        updated_by: Source of update ('auth_state', 'ui_test', 'manual')
    """
    state_file = get_deployment_state_path(target)
    
    # Load existing state or create new
    if state_file.exists():
        with open(state_file) as f:
            state = json.load(f)
    else:
        state = {
            'target': target,
            'admin': {},
            'last_updated_at': None,
            'updated_by': None
        }
    
    # Update admin credentials
    state['admin'] = {
        'username': username,
        'password': password,
        'password_changed_at': datetime.now(timezone.utc).isoformat()
    }
    state['last_updated_at'] = datetime.now(timezone.utc).isoformat()
    state['updated_by'] = updated_by
    
    # Write atomically (write to temp, then rename)
    temp_file = state_file.with_suffix('.tmp')
    with open(temp_file, 'w') as f:
        json.dump(state, f, indent=2)
    temp_file.rename(state_file)
    
    print(f"✓ Updated deployment state: {state_file}")


async def save_auth_state(
    context: BrowserContext,
    name: str = "admin",
    target: str = "local"
) -> Path:
    """Save authentication state (cookies, localStorage, etc.) to file.
    
    Args:
        context: Playwright browser context after successful login
        name: Name for the auth state file (e.g., "admin", "user")
        target: Deployment target ('local' or 'webhosting')
    
    Returns:
        Path to saved state file
    """
    state_file = AUTH_STATE_DIR / f"{target}_{name}_auth_state.json"
    await context.storage_state(path=str(state_file))
    print(f"✓ Saved auth state to: {state_file}")
    return state_file


async def load_auth_state(
    context: BrowserContext,
    name: str = "admin",
    target: str = "local"
) -> bool:
    """Load authentication state from file into browser context.
    
    Args:
        context: Playwright browser context to load state into
        name: Name of the auth state file
        target: Deployment target ('local' or 'webhosting')
    
    Returns:
        True if state loaded successfully, False if not found
    """
    state_file = AUTH_STATE_DIR / f"{target}_{name}_auth_state.json"
    
    if not state_file.exists():
        return False
    
    # Load state from file
    with open(state_file) as f:
        state = json.load(f)
    
    # Add cookies to context
    if 'cookies' in state:
        await context.add_cookies(state['cookies'])
        print(f"✓ Loaded {len(state['cookies'])} cookies from {state_file}")
    
    return True


def clear_auth_state(name: str = "admin", target: str = "local") -> None:
    """Delete saved authentication state.
    
    Args:
        name: Name of the auth state file to delete
        target: Deployment target ('local' or 'webhosting')
    """
    state_file = AUTH_STATE_DIR / f"{target}_{name}_auth_state.json"
    if state_file.exists():
        state_file.unlink()
        print(f"✓ Cleared auth state: {state_file}")


async def ensure_authenticated(
    context: BrowserContext,
    page: Page,
    login_url: str,
    auth_state_name: str = "admin",
    target: str = "local",
    force_login: bool = False
) -> bool:
    """Ensure browser context is authenticated, using saved state or logging in.
    
    This function:
    1. Loads credentials from deployment_state_{target}.json
    2. Tries to load saved Playwright auth state (session cookies)
    3. If no saved state or force_login=True, performs fresh login
    4. Saves new auth state for future use
    5. Verifies authentication worked
    
    Args:
        context: Playwright browser context
        page: Playwright page
        login_url: URL to login page (e.g., "/admin/login")
        auth_state_name: Name for saving/loading auth state
        target: Deployment target ('local' or 'webhosting')
        force_login: Force fresh login even if saved state exists
    
    Returns:
        True if authenticated successfully
    """
    # Load credentials from deployment state
    creds = load_deployment_credentials(target)
    username = creds['username']
    password = creds['password']
    
    print(f"Using credentials: {username} / {'*' * len(password)} (target={target})")
    
    # Try loading existing auth state (unless forcing login)
    if not force_login and await load_auth_state(context, auth_state_name, target):
        # Verify it works by visiting a protected page
        await page.goto(login_url.replace('/login', '/dashboard'))
        await page.wait_for_load_state('networkidle')
        
        # If we're still authenticated, we're done
        if '/dashboard' in page.url:
            print("✓ Using saved authentication state")
            return True
        
        # Saved state expired or invalid
        print("⚠️  Saved auth state invalid, performing fresh login")
        clear_auth_state(auth_state_name, target)
    
    # Perform fresh login
    await page.goto(login_url)
    await page.wait_for_load_state('networkidle')
    
    await page.fill("#username", username)
    await page.fill("#password", password)
    
    # Handle 2FA if needed
    async with page.expect_navigation(wait_until="networkidle"):
        await page.click("button[type='submit']")
    
    if '/2fa' in page.url:
        print("⚠️  2FA required - handle manually or via email")
        # For automated testing, you'd extract code from email here
        return False
    
    # Check if password change is required
    if '/change-password' in page.url:
        print("⚠️  Password change required (fresh deployment)")
        # Caller should handle password change flow
        return False
    
    # Save auth state for future use
    await save_auth_state(context, auth_state_name, target)
    
    return '/dashboard' in page.url or '/admin' in page.url

