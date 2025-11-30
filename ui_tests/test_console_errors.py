"""
Test for browser console errors across all pages.
"""
import pytest
from playwright.sync_api import Page, expect

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
    "/client/domains",
]


@pytest.mark.parametrize("path", ADMIN_PAGES)
def test_admin_pages_for_console_errors(admin_page: Page, path: str):
    """
    Checks admin pages for console errors.

    Args:
        admin_page: The admin page fixture.
        path: The path to the page to check.
    """
    console_errors = []
    admin_page.on("console", lambda msg: console_errors.append(msg) if msg.type == "error" else None)

    admin_page.goto(path)
    expect(admin_page).to_have_title(re.compile(".*"))  # Wait for page to load

    assert not console_errors, f"Console errors found on {path}: {console_errors}"


@pytest.mark.parametrize("path", CLIENT_PAGES)
def test_client_pages_for_console_errors(client_page: Page, path: str):
    """
    Checks client pages for console errors.

    Args:
        client_page: The client page fixture.
        path: The path to the page to check.
    """
    console_errors = []
    client_page.on("console", lambda msg: console_errors.append(msg) if msg.type == "error" else None)

    client_page.goto(path)
    expect(client_page).to_have_title(re.compile(".*"))  # Wait for page to load

    assert not console_errors, f"Console errors found on {path}: {console_errors}"
