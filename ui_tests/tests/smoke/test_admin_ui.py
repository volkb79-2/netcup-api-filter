import pytest

from ui_tests import workflows
from ui_tests.browser import browser_session
from ui_tests.config import settings

pytestmark = [pytest.mark.asyncio, pytest.mark.smoke]

# The forced first-login password change has exactly one test:
# smoke/test_installation_workflow.py (own fresh instance). Admin tests here log in as the
# session's admin persona and never change a password.

async def test_admin_dashboard_and_footer(active_profile):
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        # Verify page loaded successfully (HTTP 200)
        await browser.verify_status(200)
        
        heading = await browser.text("main h1")
        assert "Dashboard" in heading

        footer_text = await browser.expect_substring("footer", "Netcup API Filter")
        assert len(footer_text) > 10

        screenshot_path = await browser.screenshot(f"{settings.screenshot_prefix}-admin-dashboard")
        assert screenshot_path.endswith((".png", ".webp")), f"Expected .png or .webp, got {screenshot_path}"

async def test_admin_navigation_links(active_profile):
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        visited = await workflows.verify_admin_nav(browser)
        # 4 direct nav links + 3 config dropdown items + 1 logout = 8 items
        assert len(visited) == 8
        assert visited[0][0] == "Dashboard"
        assert visited[1][0] == "Accounts"  # Changed from "Clients"
        assert visited[-1][0] == "Logout"

async def test_admin_audit_logs_headers(active_profile):
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        header = await workflows.admin_verify_audit_log_columns(browser)
        # Verify audit logs page loaded successfully (catch template errors)
        await browser.verify_status(200)
        assert "Action" in header  # Changed from "Operation"

async def test_admin_accounts_table_lists_preseeded_account(active_profile):
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_accounts(browser)
        # Verify account list page loaded successfully (catch template errors)
        await browser.verify_status(200)

        table_text = await browser.text("table tbody")
        # The session's portal personas (ui_tests/personas.py) are listed; the accounts
        # table lists non-admin accounts only (api/admin.py filters is_admin=0).
        assert "There are no items in the table" not in table_text
        assert settings.user_username in table_text
        assert settings.admin_username not in table_text

        screenshot_path = await browser.screenshot(f"{settings.screenshot_prefix}-admin-accounts")
        assert screenshot_path.endswith((".png", ".webp")), f"Expected .png or .webp, got {screenshot_path}"


async def test_admin_email_buttons_show_feedback(active_profile):
    if not active_profile.allow_writes:
        pytest.skip("profile is read-only; skipping email config mutations")

    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.admin_email_save_expect_error(browser)
        await workflows.admin_email_trigger_test_without_address(browser)

async def test_admin_netcup_config_save_roundtrip(active_profile):
    if not active_profile.allow_writes:
        pytest.skip("profile is read-only for configuration changes")

    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.admin_save_netcup_config(browser)


async def test_create_account_form_has_fields(active_profile):
    """Account creation form exposes username and email fields (moved from test_ui_ux_validation)."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await browser.goto(settings.url("/admin/accounts/new"))
        await browser.verify_status(200)

        page_html = await browser.html("form")
        assert 'name="username"' in page_html or 'id="username"' in page_html, (
            "Username field not found in account creation form"
        )
        assert 'name="email"' in page_html or 'id="email"' in page_html, (
            "Email field not found in account creation form"
        )
