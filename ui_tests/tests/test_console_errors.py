"""
Test for browser console errors across all pages.
"""
import re
import pytest
from playwright.sync_api import Page, expect
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


@pytest.mark.parametrize("path", ADMIN_PAGES)
def test_admin_pages_for_console_errors(admin_page: Page, path: str):
    """
    Checks admin pages for console errors.

    Args:
        admin_page: The admin page fixture from conftest.py.
        path: The path to the page to check.
    """
    console_errors = []
    admin_page.on("console", lambda msg: console_errors.append(f"({msg.type}) {msg.text}") if msg.type in ["error"] else None)

    admin_page.goto(path)
    expect(admin_page).to_have_title(re.compile(".*"))  # Wait for page to load

    assert not console_errors, f"Console errors found on admin page {path}:\\n" + "\\n".join(console_errors)


@pytest.mark.parametrize("client_fixture_name", ["client_page_readonly", "client_page_fullcontrol"])
@pytest.mark.parametrize("path", CLIENT_PAGES)
def test_client_pages_for_console_errors(request, client_fixture_name: str, path: str):
    """
    Checks client pages for console errors using different client roles.

    Args:
        request: The pytest request object to get fixtures dynamically.
        client_fixture_name: The name of the client page fixture to use.
        path: The path to the page to check.
    """
    client_page: Page = request.getfixturevalue(client_fixture_name)
    
    console_errors = []
    client_page.on("console", lambda msg: console_errors.append(f"({msg.type}) {msg.text}") if msg.type in ["error"] else None)

    client_page.goto(path)
    expect(client_page).to_have_title(re.compile(".*"))  # Wait for page to load

    assert not console_errors, f"Console errors/warnings found on client page {path} for {client_fixture_name}:\\n" + "\\n".join(console_errors)
