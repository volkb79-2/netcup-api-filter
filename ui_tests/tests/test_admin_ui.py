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
        assert screenshot_path.endswith(".png")


async def test_admin_dashboard_and_footer(active_profile):
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        heading = await browser.text("main h1")
        assert "Dashboard" in heading

        footer_text = await browser.expect_substring("footer", "Netcup API Filter")
        assert len(footer_text) > 10

        screenshot_path = await browser.screenshot(f"{settings.screenshot_prefix}-admin-dashboard")
        assert screenshot_path.endswith(".png")


async def test_admin_navigation_links(active_profile):
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        visited = await workflows.verify_admin_nav(browser)
        assert len(visited) == 7
        assert visited[0][0] == "Dashboard"
        assert visited[-1][0] == "Logout"


async def test_admin_audit_logs_headers(active_profile):
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        header = await workflows.admin_verify_audit_log_columns(browser)
        assert "Operation" in header


async def test_admin_clients_table_lists_preseeded_client(active_profile):
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_clients(browser)

        table_text = await browser.text("table tbody")
        assert settings.client_id in table_text
        assert settings.client_domain in table_text

        screenshot_path = await browser.screenshot(f"{settings.screenshot_prefix}-admin-clients")
        assert screenshot_path.endswith(".png")


async def test_admin_can_create_and_delete_client(active_profile):
    if not active_profile.allow_writes:
        pytest.skip("profile is read-only; skipping create/delete flow")

    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_client_create(browser)

        generated_token = await workflows.trigger_token_generation(browser)
        assert len(generated_token) >= 10

        client_data = workflows.generate_client_data()
        await workflows.submit_client_form(browser, client_data)
        await workflows.ensure_client_visible(browser, client_data.client_id)

        # Verify edit and delete icons are present
        await workflows.verify_client_list_has_icons(browser)

        # Test client login with the new token (should succeed)
        await workflows.test_client_login_with_token(browser, generated_token, should_succeed=True, expected_client_id=client_data.client_id)

        # Disable the client
        await workflows.disable_admin_client(browser, client_data.client_id)
        await workflows.ensure_client_visible(browser, client_data.client_id)  # Still visible but disabled

        # Test client login with disabled token (should fail)
        await workflows.test_client_login_with_token(browser, generated_token, should_succeed=False)

        # Delete the client
        await workflows.delete_admin_client(browser, client_data.client_id)
        await workflows.ensure_client_absent(browser, client_data.client_id)


async def test_admin_client_form_validation(active_profile):
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_client_create(browser)
        await workflows.admin_submit_invalid_client(browser)


async def test_admin_client_form_cancel_button(active_profile):
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_client_create(browser)
        await workflows.admin_click_cancel_from_client_form(browser)


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
