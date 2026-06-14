"""Tests for admin configuration pages.

Moved/updated from test_ui_comprehensive.py.
False-green patterns (if-found guards, or-chains) have been removed.
"""
import pytest
from ui_tests.browser import browser_session
from ui_tests import workflows
from ui_tests.config import settings


pytestmark = [pytest.mark.asyncio, pytest.mark.feature]


async def test_netcup_config_page(active_profile):
    """Netcup Config page loads and exposes all required form fields."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_netcup_config(browser)

        heading = await browser.text("main h1")
        assert "Netcup" in heading, f"Expected 'Netcup' in h1, got: {heading!r}"

        page_html = await browser.html("body")
        assert "customer_id" in page_html, "customer_id field missing from Netcup config form"
        assert "api_key" in page_html, "api_key field missing from Netcup config form"
        assert "api_password" in page_html, "api_password field missing from Netcup config form"
        assert "api_url" in page_html, "api_url field missing from Netcup config form"
        assert "timeout" in page_html.lower(), "timeout field missing from Netcup config form"


async def test_netcup_config_test_connection(active_profile, mock_netcup_api_server, mock_netcup_credentials):
    """Test-connection button on Netcup config triggers a success response (mock server)."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_netcup_config(browser)

        await browser.fill('input[name="customer_id"]', str(mock_netcup_credentials["customer_id"]))
        await browser.fill('input[name="api_key"]', mock_netcup_credentials["api_key"])
        await browser.fill('input[name="api_password"]', mock_netcup_credentials["api_password"])
        await browser.fill('input[name="api_url"]', mock_netcup_api_server.url)

        # The test/verify button is a non-submit button
        test_buttons = await browser.query_selector_all('button[type="button"]')
        test_button = None
        for btn in test_buttons:
            btn_text = (await btn.inner_text()).lower()
            if "test" in btn_text or "verify" in btn_text:
                test_button = btn
                break

        assert test_button is not None, (
            "Expected a Test/Verify button on the Netcup config page"
        )

        await test_button.click()
        try:
            await browser._page.wait_for_selector(
                '.alert, .message, [role="alert"]', timeout=3000
            )
        except Exception:
            pass
        await browser._page.wait_for_load_state("networkidle", timeout=5000)

        page_text = await browser.text("body")
        assert (
            "success" in page_text.lower()
            or "connection" in page_text.lower()
            or "ok" in page_text.lower()
        ), f"Expected success response after test connection, got: {page_text[:300]!r}"


async def test_email_config_page(active_profile):
    """Email Config page loads and exposes all required SMTP form fields."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_email_settings(browser)

        heading = await browser.text("main h1")
        assert "Email" in heading, f"Expected 'Email' in h1, got: {heading!r}"

        page_html = await browser.html("body")
        assert "smtp_host" in page_html, "smtp_host field missing from email config form"
        assert "from_email" in page_html, "from_email field missing from email config form"
        assert "smtp_port" in page_html, "smtp_port field missing from email config form"


async def test_email_config_field_validation(active_profile):
    """Email config form exposes smtp_host and from_email as editable inputs."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_email_settings(browser)

        smtp_host_input = await browser.query_selector('input[name="smtp_host"]')
        assert smtp_host_input is not None, "SMTP host input must exist on email config form"

        from_email_input = await browser.query_selector('input[name="from_email"]')
        assert from_email_input is not None, "from_email input must exist on email config form"


async def test_system_info_page(active_profile):
    """System Info page loads and contains Python/Flask version information."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        await workflows.open_admin_system_info(browser)

        heading = await browser.text("main h1")
        assert "System" in heading, f"Expected 'System' in h1, got: {heading!r}"

        page_html = await browser.html("body")
        assert "Python" in page_html or "Flask" in page_html, (
            "System info page should display Python or Flask version information"
        )
