"""Reusable workflows for admin and client UI coverage."""
from __future__ import annotations

from typing import List, Tuple

from ui_tests.browser import Browser
from ui_tests.config import settings


async def ensure_admin_dashboard(browser: Browser) -> Browser:
    """Log into the admin UI and land on the dashboard, rotating the password if needed."""
    await browser.goto(settings.url("/admin/login"))
    await browser.fill("#username", settings.admin_username)
    await browser.fill("#password", settings.admin_password)
    response = await browser.click("button[type='submit']")
    destination = response.get("url", "")

    if "change-password" in destination or "Change Password" in await browser.text("main h1"):
        if not settings.admin_new_password:
            raise AssertionError(
                "Server requested a password change but UI_ADMIN_NEW_PASSWORD was not provided"
            )
        await browser.fill("#current_password", settings.admin_password)
        await browser.fill("#new_password", settings.admin_new_password)
        await browser.fill("#confirm_password", settings.admin_new_password)
        await browser.click("button[type='submit']")
        settings.note_password_change()

    await browser.wait_for_text("main h1", "Dashboard")
    return browser


async def verify_admin_nav(browser: Browser) -> List[Tuple[str, str]]:
    """Click through primary admin navigation links and return the visited headings."""
    nav_items = [
        ("a.nav-link[href='/admin/']", "Dashboard"),
        ("a.nav-link[href='/admin/netcup_config/']", "Netcup API Configuration"),
        ("a.nav-link[href='/admin/email_config/']", "Email Configuration"),
        ("a.nav-link[href='/admin/system_info/']", "System Information"),
    ]

    visited: List[Tuple[str, str]] = []
    for selector, expected_heading in nav_items:
        await browser.click(selector)
        heading = await browser.wait_for_text("main h1", expected_heading)
        visited.append((selector, heading))
    return visited


async def open_admin_clients(browser: Browser) -> Browser:
    await browser.goto(settings.url("/admin/client/"))
    await browser.wait_for_text("main h1", "Clients")
    return browser


async def client_portal_login(browser: Browser) -> Browser:
    await browser.goto(settings.url("/client/login"))
    await browser.fill("#token", settings.client_token)
    await browser.click("button[type='submit']")
    body = await browser.text("body")
    if "internal server error" in body.lower():
        raise AssertionError(
            "Client portal login failed with server error; investigate backend logs before rerunning client UI tests"
        )
    await browser.wait_for_text("main h1", settings.client_id)
    return browser
