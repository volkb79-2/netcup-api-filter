"""Reusable workflows for admin and client UI coverage."""
from __future__ import annotations

import anyio
import re
import secrets
from dataclasses import dataclass
from typing import Callable, List, Tuple

from ui_tests.browser import Browser, ToolError
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
    await browser.click("button[type='submit']")
    await browser.expect_substring("body", "Realm value must be a valid domain")


async def admin_click_cancel_from_client_form(browser: Browser) -> None:
    await browser.click("a.btn.btn-outline")
    await browser.wait_for_text("main h1", "Clients")


async def admin_save_netcup_config(browser: Browser) -> None:
    await open_admin_netcup_config(browser)
    existing_values = {
        "#customer_id": await browser.get_attribute("#customer_id", "value"),
        "#api_key": await browser.get_attribute("#api_key", "value"),
        "#api_password": await browser.get_attribute("#api_password", "value"),
        "#api_url": await browser.get_attribute("#api_url", "value"),
        "#timeout": await browser.get_attribute("#timeout", "value"),
    }

    for selector, value in existing_values.items():
        await browser.fill(selector, value or "")

    await browser.click("form button[type='submit']")
    await browser.expect_substring(".flash-messages", "Netcup API configuration saved successfully")


async def admin_email_save_expect_error(browser: Browser) -> None:
    await open_admin_email_settings(browser)
    await browser.fill("#sender_email", "invalid-email")
    await browser.click("text=Save Configuration")
    await browser.expect_substring(".flash-messages", "Sender email address must be valid")
    await open_admin_email_settings(browser)


async def admin_email_trigger_test_without_address(browser: Browser) -> None:
    await open_admin_email_settings(browser)
    await browser.click("text=Send Test Email")
    await browser.expect_substring(".flash-messages", "Please enter an email address to test")
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
