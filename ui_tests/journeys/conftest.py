"""
Fixtures for journey-based testing.

These fixtures are designed to work across all journey tests, providing:
- Screenshot capture helpers
- Persistent state between journeys (via database)
- Email verification via Mailpit
- Route discovery for auth testing
"""
import os
import re
from pathlib import Path
from typing import Callable, Optional

import pytest
import pytest_asyncio
import httpx

# Import shared fixtures from parent conftest
from ui_tests.conftest import (
    playwright_client,
    browser,
    refresh_credentials_before_test,
    mailpit,
)
from ui_tests.config import settings
from ui_tests.browser import Browser


# ============================================================================
# Screenshot Configuration
# ============================================================================

# Use deploy-local/screenshots for output (writable in Playwright container)
_SCREENSHOT_DIR = Path(os.environ.get(
    'SCREENSHOT_DIR', 
    '/workspaces/netcup-api-filter/deploy-local/screenshots/journeys'
))


def ensure_screenshot_dir():
    """Ensure screenshot directory exists."""
    global _SCREENSHOT_DIR
    try:
        _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        # Fall back to /tmp if we can't write to the expected location
        _SCREENSHOT_DIR = Path('/tmp/screenshots/journeys')
        _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def get_screenshot_dir() -> Path:
    """Get the screenshot directory path."""
    return _SCREENSHOT_DIR


@pytest.fixture(scope='session', autouse=True)
def setup_screenshot_dir():
    """Create screenshot directory once per session."""
    ensure_screenshot_dir()


# ============================================================================
# Screenshot Capture Decorator/Helper
# ============================================================================

class ScreenshotHelper:
    """Helper for capturing screenshots during journey tests."""
    
    def __init__(self, browser: Browser, journey_prefix: str):
        self.browser = browser
        self.journey_prefix = journey_prefix
        self._step = 0
    
    async def capture(self, name: str, description: str = ""):
        """Capture a screenshot with journey prefix and step number.
        
        Args:
            name: Screenshot name (e.g., 'login-page')
            description: Optional description for logging
        
        Returns:
            Path to saved screenshot
        """
        self._step += 1
        filename = f"{self.journey_prefix}-{self._step:02d}-{name}.png"
        filepath = get_screenshot_dir() / filename
        
        await self.browser.screenshot(str(filepath))
        
        if description:
            print(f"📸 {filename}: {description}")
        else:
            print(f"📸 {filename}")
        
        return filepath


@pytest.fixture
def screenshot_helper(browser):
    """Factory fixture to create screenshot helpers for each journey."""
    def _create_helper(journey_prefix: str) -> ScreenshotHelper:
        return ScreenshotHelper(browser, journey_prefix)
    return _create_helper


# ============================================================================
# Route Discovery for Auth Testing
# ============================================================================

PUBLIC_ROUTES = {
    '/',
    '/health',
    '/component-demo',
    '/component-demo-bs5',
    '/theme-demo',
    '/admin/login',
    '/account/login',
    '/account/register',
    '/account/forgot-password',
}

# Routes that require path parameters (use pattern matching)
PARAMETERIZED_ROUTES = [
    r'/account/reset-password/[a-zA-Z0-9]+',
    r'/account/register/verify',
    r'/account/register/pending',
]


def is_public_route(path: str) -> bool:
    """Check if a route is public (no auth required)."""
    if path in PUBLIC_ROUTES:
        return True
    
    for pattern in PARAMETERIZED_ROUTES:
        if re.match(pattern, path):
            return True
    
    return False


@pytest.fixture
def admin_routes() -> list[str]:
    """List of admin routes to test for auth enforcement."""
    return [
        '/admin/',
        '/admin/accounts',
        '/admin/accounts/1',
        '/admin/accounts/new',
        '/admin/accounts/pending',
        '/admin/realms',
        '/admin/realms/1',
        '/admin/realms/pending',
        '/admin/tokens/1',
        '/admin/audit',
        '/admin/audit/export',
        '/admin/config/netcup',
        '/admin/config/email',
        '/admin/system',
        '/admin/change-password',
    ]


@pytest.fixture
def account_routes() -> list[str]:
    """List of account portal routes to test for auth enforcement."""
    return [
        '/account/dashboard',
        '/account/realms',
        '/account/tokens',
        '/account/settings',
        '/account/change-password',
    ]


@pytest.fixture
def api_routes() -> list[str]:
    """List of API routes to test for auth enforcement.
    
    Note: /api/myip is intentionally public (for DDNS clients to check their IP).
    """
    return [
        '/api/dns/example.com/records',
        '/api/ddns/example.com/home',
        # '/api/myip',  # Intentionally public
    ]


# ============================================================================
# HTTP Client for API Testing
# ============================================================================

@pytest.fixture
def api_client():
    """HTTP client for API testing without browser."""
    base_url = settings.url('')
    with httpx.Client(base_url=base_url, timeout=30.0, follow_redirects=False) as client:
        yield client


@pytest_asyncio.fixture
async def async_api_client():
    """Async HTTP client for API testing."""
    base_url = settings.url('')
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0, follow_redirects=False) as client:
        yield client


# ============================================================================
# Email Verification Helpers
# ============================================================================

@pytest.fixture
def extract_reset_link():
    """Factory to extract password reset link from email body."""
    def _extract(email_text: str) -> Optional[str]:
        # Match various reset link formats
        patterns = [
            r'https?://[^\s]+/account/reset-password/[a-zA-Z0-9_-]+',
            r'https?://[^\s]+/reset-password/[a-zA-Z0-9_-]+',
        ]
        for pattern in patterns:
            match = re.search(pattern, email_text)
            if match:
                return match.group()
        return None
    return _extract


@pytest.fixture
def extract_invite_link():
    """Factory to extract invite link from email body."""
    def _extract(email_text: str) -> Optional[str]:
        patterns = [
            r'https?://[^\s]+/account/register\?invite=[a-zA-Z0-9_-]+',
            r'https?://[^\s]+/register\?invite=[a-zA-Z0-9_-]+',
        ]
        for pattern in patterns:
            match = re.search(pattern, email_text)
            if match:
                return match.group()
        return None
    return _extract


@pytest.fixture
def extract_verification_code():
    """Factory to extract verification code from email body."""
    def _extract(email_text: str) -> Optional[str]:
        # 6-character alphanumeric code (typically uppercase)
        match = re.search(r'\b([A-Z0-9]{6})\b', email_text)
        if match:
            return match.group(1)
        
        # Also try lowercase
        match = re.search(r'\b([a-zA-Z0-9]{6})\b', email_text)
        if match:
            return match.group(1)
        
        return None
    return _extract


# ============================================================================
# Admin Session Helper
# ============================================================================

@pytest_asyncio.fixture
async def admin_session(browser):
    """Ensure browser is logged in as admin and return browser."""
    from ui_tests.workflows import ensure_admin_dashboard
    await ensure_admin_dashboard(browser)
    return browser


# ============================================================================
# Test Data Generators
# ============================================================================

@pytest.fixture
def unique_username():
    """Generate unique username for testing."""
    import uuid
    return f"testuser_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def unique_email():
    """Generate unique email for testing."""
    import uuid
    return f"test_{uuid.uuid4().hex[:8]}@example.com"
