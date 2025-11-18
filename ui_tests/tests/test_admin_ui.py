import pytest

from ui_tests import workflows
from ui_tests.browser import browser_session
from ui_tests.config import settings

pytestmark = pytest.mark.asyncio


async def test_admin_dashboard_and_footer():
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        heading = await browser.text("main h1")
        assert "Dashboard" in heading

        footer_text = await browser.expect_substring("footer .text-muted.small", "Build")
        assert len(footer_text) > 10

        screenshot_path = await browser.screenshot(f"{settings.screenshot_prefix}-admin-dashboard")
        assert screenshot_path.endswith(".png")


async def test_admin_navigation_links():
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        visited = await workflows.verify_admin_nav(browser)
        assert len(visited) == 4
        assert visited[0][1] == "Dashboard"


async def test_admin_clients_table_lists_preseeded_client():
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_clients(browser)

        table_text = await browser.text("table tbody")
        assert settings.client_id in table_text
        assert settings.client_domain in table_text

        screenshot_path = await browser.screenshot(f"{settings.screenshot_prefix}-admin-clients")
        assert screenshot_path.endswith(".png")


async def test_admin_can_create_and_delete_client():
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_client_create(browser)

        generated_token = await workflows.trigger_token_generation(browser)
        assert len(generated_token) >= 10

        client_data = workflows.generate_client_data()
        await workflows.submit_client_form(browser, client_data)
        await workflows.ensure_client_visible(browser, client_data.client_id)

        await workflows.delete_admin_client(browser, client_data.client_id)
        await workflows.ensure_client_absent(browser, client_data.client_id)
