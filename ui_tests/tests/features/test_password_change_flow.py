"""Voluntary admin password change + dashboard rendering after it.

The password-changing test owns its own fresh instance with a throwaway admin
(ui_tests/personas.provision_throwaway_admin): the session's admin persona is never
touched, and nothing is persisted. The forced first-login change of the shipped admin is
tested once, in smoke/test_installation_workflow.py.
"""
import sqlite3
import logging
from dataclasses import replace

import bcrypt
import pytest

from ui_tests.browser import Browser, browser_session
from ui_tests.config import settings
from ui_tests.e2e_env import app_instance
from ui_tests.personas import new_password, provision_throwaway_admin
from ui_tests.playwright_client import PlaywrightClient

logger = logging.getLogger(__name__)

pytestmark = [pytest.mark.asyncio, pytest.mark.feature]


async def test_password_change_redirects_to_dashboard_successfully():
    """A logged-in admin changes its password; the redirect lands on a healthy dashboard."""
    with app_instance(prepare=provision_throwaway_admin) as (instance, admin):
        with settings.use_profile(replace(settings.profile("primary"), base_url=instance.base_url)):
            async with PlaywrightClient(headless=settings.playwright_headless) as client:
                browser = Browser(client.page)
                await browser.goto(settings.url("/admin/login"), wait_until="domcontentloaded")
                await browser.fill("#username", admin.username)
                await browser.fill("#password", admin.password)
                await browser.click("form[action*='/admin/login'] button[type='submit']")
                await browser._page.wait_for_url(lambda url: "/admin/login" not in url, timeout=10_000)

                await browser.goto(settings.url("/admin/change-password"), wait_until="domcontentloaded")
                chosen = new_password()
                await browser.fill("#current_password", admin.password)
                await browser.fill("#new_password", chosen)
                await browser.evaluate(
                    "document.getElementById('new_password').dispatchEvent(new Event('input', { bubbles: true }))")
                await browser.fill("#confirm_password", chosen)
                await browser.evaluate(
                    "document.getElementById('confirm_password').dispatchEvent(new Event('input', { bubbles: true }))")
                await browser._page.wait_for_function(
                    "document.getElementById('submitBtn') && !document.getElementById('submitBtn').disabled",
                    timeout=5000,
                )
                url_before = browser._page.url
                await browser.click("#submitBtn")
                await browser._page.wait_for_url(
                    lambda url: url != url_before and "/change-password" not in url, timeout=10_000)

                await browser.wait_for_text("h1", "Dashboard", timeout=10.0)
                body_text = await browser.text("body")
                for marker in ("Internal Server Error", "UndefinedError", "jinja2.exceptions"):
                    assert marker not in body_text, f"dashboard after password change shows {marker}"
                assert await browser.query_selector(".card, .dashboard-stats, .stat-card") is not None
                assert await browser.query_selector("footer") is not None

        conn = sqlite3.connect(f"file:{instance.db_path}?mode=ro", uri=True)
        try:
            (password_hash,) = conn.execute(
                "SELECT password_hash FROM accounts WHERE username = ?", (admin.username,)).fetchone()
        finally:
            conn.close()
        assert bcrypt.checkpw(chosen.encode(), password_hash.encode())
        assert not bcrypt.checkpw(admin.password.encode(), password_hash.encode())


async def test_dashboard_components_render_without_error():
    """Verify all dashboard components render without Jinja errors.
    
    This test checks for template rendering issues that might be hidden
    in production but not caught by navigation tests.
    """
    async with browser_session("admin") as browser:
        from ui_tests import workflows
        
        # Login and navigate to dashboard
        await workflows.ensure_admin_dashboard(browser)
        
        # Get page source to check for Jinja errors
        page_source = await browser.page_content()
        
        # Check for Jinja error markers
        assert "jinja2.exceptions" not in page_source, "Found Jinja2 exception in page"
        assert "UndefinedError" not in page_source, "Found UndefinedError in page"
        assert "TemplateNotFound" not in page_source, "Found TemplateNotFound error"
        assert "TemplateSyntaxError" not in page_source, "Found template syntax error"
        
        # Verify key components exist
        h1 = await browser.query_selector("h1")
        assert h1 is not None, "H1 heading not found"
        
        footer = await browser.query_selector("footer")
        assert footer is not None, "Footer not found"
        
        nav = await browser.query_selector("nav")
        assert nav is not None, "Navigation not found"
        
        logger.info("✓ Dashboard components render test PASSED")


async def test_all_admin_pages_accessible_after_password_change():
    """Verify all admin pages accessible after password change.
    
    This ensures that session persistence works correctly after
    password change and all routes render without errors.
    """
    async with browser_session("admin") as browser:
        from ui_tests import workflows

        await workflows.ensure_admin_dashboard(browser)
        
        # Test all major admin routes
        admin_routes = [
            ("/admin/", "Dashboard"),
            ("/admin/accounts", "Accounts"),
            ("/admin/realms", "Realms"),
            ("/admin/audit", "Audit"),
            ("/admin/config/netcup", "Netcup"),
            ("/admin/config/email", "Email"),
            ("/admin/system", "System"),
        ]
        
        for route, page_name in admin_routes:
            await browser.goto(settings.url(route))
            await browser._page.wait_for_load_state('domcontentloaded')
            
            # Verify no 500 error
            body_text = await browser.text("body")
            assert "500 Internal Server Error" not in body_text, f"500 Internal Server Error on {route}"
            assert "Internal Server Error" not in body_text, f"Internal Server Error on {route}"
            
            # Verify not redirected to login (session still valid)
            current_url = browser._page.url
            assert "/login" not in current_url, f"Redirected to login from {route}"
            
            logger.info(f"✓ {page_name} page accessible")
        
        logger.info("✓ All admin pages accessible test PASSED")
