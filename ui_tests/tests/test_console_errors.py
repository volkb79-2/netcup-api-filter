"""
Test for browser console errors across all pages.
"""
import re
import pytest
from playwright.async_api import Page, expect
import os

# A list of admin pages to check for console errors
ADMIN_PAGES = [
    "/admin/",
    "/admin/client/",
    "/admin/client/new/",
    "/admin/auditlog/",
    "/admin/netcupsettings/",
    "/admin/emailsettings/",
    "/admin/systeminfo/",
]

# A list of client pages to check for console errors
# These will be parameterized with different client logins
CLIENT_PAGES = [
    "/client/dashboard",
    "/client/activity",
]

# Known console errors to ignore (third-party library issues or expected behaviors)
KNOWN_ERROR_PATTERNS = [
    # List.js fails on pages without proper table structure (Dashboard, config pages)
    r"List\.js initialization failed",
    # Flask-Admin vendor CSS files may not be served correctly in local dev mode
    r"Refused to apply style.*MIME type",
    # Static resource 404s - Flask-Admin vendor files not included in deployment
    r"404 \(NOT FOUND\)",
]


def is_known_error(error_text: str) -> bool:
    """Check if an error matches a known pattern to ignore."""
    return any(re.search(pattern, error_text) for pattern in KNOWN_ERROR_PATTERNS)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ADMIN_PAGES)
async def test_admin_pages_for_console_errors(admin_page: Page, path: str):
    """
    Checks admin pages for console errors.

    Args:
        admin_page: The admin page fixture from conftest.py.
        path: The path to the page to check.
    """
    page = admin_page  # Already awaited by fixture
    base_url = os.environ.get("UI_BASE_URL", "http://localhost:5100")
    
    console_errors = []
    page.on("console", lambda msg: console_errors.append(f"({msg.type}) {msg.text}") if msg.type in ["error"] else None)

    await page.goto(f"{base_url}{path}")
    await expect(page).to_have_title(re.compile(".*"))  # Wait for page to load

    # Filter out known errors
    unexpected_errors = [e for e in console_errors if not is_known_error(e)]
    
    assert not unexpected_errors, f"Console errors found on admin page {path}:\\n" + "\\n".join(unexpected_errors)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", CLIENT_PAGES)
async def test_client_pages_readonly_for_console_errors(client_page_readonly, path: str):
    """
    Checks client pages for console errors using readonly client.

    Args:
        client_page_readonly: The readonly client page fixture.
        path: The path to the page to check.
    """
    page = client_page_readonly  # Already awaited by fixture
    base_url = os.environ.get("UI_BASE_URL", "http://localhost:5100")
    
    console_errors = []
    page.on("console", lambda msg: console_errors.append(f"({msg.type}) {msg.text}") if msg.type in ["error"] else None)

    await page.goto(f"{base_url}{path}")
    await expect(page).to_have_title(re.compile(".*"))  # Wait for page to load

    # Filter out known errors
    unexpected_errors = [e for e in console_errors if not is_known_error(e)]
    
    assert not unexpected_errors, f"Console errors/warnings found on client page {path} for readonly:\\n" + "\\n".join(unexpected_errors)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", CLIENT_PAGES)
async def test_client_pages_fullcontrol_for_console_errors(client_page_fullcontrol, path: str):
    """
    Checks client pages for console errors using fullcontrol client.

    Args:
        client_page_fullcontrol: The fullcontrol client page fixture.
        path: The path to the page to check.
    """
    page = client_page_fullcontrol  # Already awaited by fixture
    base_url = os.environ.get("UI_BASE_URL", "http://localhost:5100")
    
    console_errors = []
    page.on("console", lambda msg: console_errors.append(f"({msg.type}) {msg.text}") if msg.type in ["error"] else None)

    await page.goto(f"{base_url}{path}")
    await expect(page).to_have_title(re.compile(".*"))  # Wait for page to load

    # Filter out known errors
    unexpected_errors = [e for e in console_errors if not is_known_error(e)]
    
    assert not unexpected_errors, f"Console errors/warnings found on client page {path} for fullcontrol:\\n" + "\\n".join(unexpected_errors)
