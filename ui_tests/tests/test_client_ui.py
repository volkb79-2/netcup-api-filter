import pytest

from ui_tests import workflows
from ui_tests.browser import browser_session
from ui_tests.config import settings

pytestmark = pytest.mark.asyncio


async def test_client_portal_login_and_stats(active_profile):
    async with browser_session() as browser:
        await workflows.client_portal_login(browser)

        welcome = await browser.text("main h1")
        assert settings.client_id in welcome

        stat_operations = await browser.text(".stat-card:nth-child(1) .stat-value")
        assert stat_operations.isdigit()

        screenshot_path = await browser.screenshot(f"{settings.screenshot_prefix}-client-dashboard")
        assert screenshot_path.endswith(".png")


async def test_client_domain_manage_button(active_profile):
    async with browser_session() as browser:
        await workflows.client_portal_login(browser)

        manage_selector = f"a[href='/client/domains/{settings.client_domain}']"
        await browser.click(manage_selector)
        heading = await browser.wait_for_text("main h1", settings.client_domain)
        assert settings.client_domain in heading


async def test_client_manage_buttons_and_logout(active_profile):
    async with browser_session() as browser:
        await workflows.client_portal_login(browser)
        visited = await workflows.client_portal_manage_all_domains(browser)
        assert visited, "expected at least one domain to manage"
        await workflows.client_portal_logout(browser)
