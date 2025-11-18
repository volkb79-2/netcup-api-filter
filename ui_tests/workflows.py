"""Reusable workflows for admin and client UI coverage."""
from __future__ import annotations

import anyio
import secrets
from dataclasses import dataclass
from typing import Callable, List, Tuple

from ui_tests.browser import Browser
from ui_tests.config import settings


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


async def trigger_token_generation(browser: Browser) -> str:
    before = await browser.get_attribute("#client_id", "value")
    await browser.click(".token-generate-btn")
    token = await wait_for_input_value(browser, "#client_id", lambda v: v and v != before)
    return token


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


async def open_admin_client_create(browser: Browser) -> Browser:
    await browser.goto(settings.url("/admin/client/new/"))
    await browser.wait_for_text("main h1", "Clients")
    return browser


async def submit_client_form(browser: Browser, data: ClientFormData) -> str:
    await browser.fill("#client_id", data.client_id)
    await browser.fill("#description", data.description)
    await browser.select("select[name='realm_type']", data.realm_type)
    await browser.fill("#realm_value", data.realm_value)
    await browser.select("select[name='allowed_record_types']", data.record_choices())
    await browser.select("select[name='allowed_operations']", data.operation_choices())
    if data.email:
        await browser.fill("#email_address", data.email)
    await browser.click("button[type='submit']")
    return await browser.wait_for_text(".alert-success", "Client created successfully")


async def ensure_client_visible(browser: Browser, client_id: str) -> None:
    await open_admin_clients(browser)
    table_text = await browser.text("table tbody")
    assert client_id in table_text, f"Expected {client_id} in clients table"


async def ensure_client_absent(browser: Browser, client_id: str) -> None:
    await open_admin_clients(browser)
    table_text = await browser.text("table tbody")
    assert client_id not in table_text, f"Did not expect {client_id} in clients table"


async def delete_admin_client(browser: Browser, client_id: str) -> None:
    await open_admin_clients(browser)
    row_selector = f"tr:has-text('{client_id}')"
    form_selector = f"{row_selector} form[action='/admin/client/delete/']"
    await browser.submit(form_selector)
    await browser.wait_for_text("main h1", "Clients")


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
