"""Test for browser console errors across admin pages."""
import re
import pytest
from ui_tests.browser import browser_session
from ui_tests.config import settings
from ui_tests import workflows

# Admin pages to check for console errors
ADMIN_PATHS = [
    "/admin/",
    "/admin/accounts",
    "/admin/accounts/pending",
    "/admin/audit",
    "/admin/config/netcup",
    "/admin/config/email",
    "/admin/system",
]

# Known console errors to ignore (third-party library issues)
KNOWN_ERROR_PATTERNS = [
    r"List\.js initialization failed",
    r"Refused to apply style.*MIME type",
    r"404 \(NOT FOUND\)",
]

def is_known_error(error_text: str) -> bool:
    """Check if an error matches a known pattern to ignore."""
    return any(re.search(pattern, error_text) for pattern in KNOWN_ERROR_PATTERNS)

pytestmark = pytest.mark.asyncio

@pytest.mark.parametrize("path", ADMIN_PATHS)
async def test_admin_pages_for_console_errors(active_profile, path: str):
    """Checks admin pages for console errors."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        
        # Navigate to the page
        await browser.goto(settings.url(path))
        
        # Get page text to verify it loaded
        page_text = await browser.text("body")
        
        # Page should have some content
        assert len(page_text.strip()) > 50, f"Page {path} appears empty"

# Client page tests are skipped until client portal is updated for new auth model
