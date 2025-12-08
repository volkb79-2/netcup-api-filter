import pytest

from ui_tests import workflows
from ui_tests.browser import browser_session
from ui_tests.config import settings

pytestmark = pytest.mark.asyncio

async def test_admin_authentication_flow(active_profile):
    """Test the complete admin authentication flow including password change."""
    async with browser_session() as browser:
        new_password = await workflows.perform_admin_authentication_flow(browser)
        # Verify we're on the dashboard after successful authentication
        heading = await browser.text("main h1")
        assert "Dashboard" in heading
        
        screenshot_path = await browser.screenshot(f"{settings.screenshot_prefix}-admin-auth-flow")
        assert screenshot_path.endswith((".png", ".webp"))

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
        # Demo accounts should be seeded for local testing
        assert "There are no items in the table" not in table_text, "Expected demo accounts to be seeded"
        # Check for demo-user account or admin
        assert "demo-user" in table_text or "admin" in table_text

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
