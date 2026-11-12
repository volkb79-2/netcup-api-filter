"""
Journey 1: Admin Authentication & System State

Contract: See docs/JOURNEY_CONTRACTS.md Section "J1: Fresh Deployment"

1. Login page is accessible
2. The session's admin PERSONA (ui_tests/personas.py) authenticates (TOTP 2FA)
3. Dashboard shows current state
4. All admin pages render

The shipped admin's forced first-login password change is NOT part of this journey: it has
exactly one dedicated test on its own fresh instance (smoke/test_installation_workflow.py).
No credential is changed or persisted here.
"""

import logging

from ui_tests.browser import Browser
from ui_tests.config import settings
from ui_tests.tests.journeys import journey_state

logger = logging.getLogger(__name__)


async def capture(browser: Browser, name: str, journey: str = "J1") -> str:
    """Capture screenshot with journey prefix."""
    screenshot_name = journey_state.next_screenshot_name(journey, name)
    path = await browser.screenshot(screenshot_name)
    journey_state.screenshots.append((screenshot_name, path))
    logger.info(f"📸 {screenshot_name} → {path}")
    return path


class TestJourney1FreshDeployment:
    """Journey 1: Admin authentication and system state validation."""
    
    async def test_J1_01_login_page_accessible(self, anon_browser: Browser):
        """System shows login page."""
        browser = anon_browser
        await browser.goto(settings.url("/admin/login"), wait_until="domcontentloaded")
        await browser.wait_for_timeout(300)

        # If a persisted admin session is present, /admin/login may redirect to
        # the dashboard. This journey is specifically validating the logged-out
        # login page, so force an explicit logout and retry.
        current_url = browser._page.url
        if "/admin/login" not in current_url:
            await browser.goto(settings.url("/admin/logout"), wait_until="domcontentloaded")
            await browser.wait_for_timeout(200)
            await browser.goto(settings.url("/admin/login"), wait_until="domcontentloaded")
            await browser.wait_for_timeout(300)
        
        await capture(browser, "login-page")
        
        # Validate login page structure - h1 shows app name, form has login elements
        h1_text = await browser.text("h1")
        assert any(text in h1_text for text in ["Netcup API Filter", "Login", "Admin Portal"]), f"Expected login page header, got: {h1_text}"
        
        # Check form elements exist - this confirms it's the login page.
        # This is a hard gate: the admin login page MUST render #username,
        # #password and a submit button. A broken/empty login page is a genuine
        # product regression and must FAIL this fresh-deployment gate (it must
        # not be downgraded to a skip, which would hide the breakage).
        username_field = await browser.query_selector("#username, input[name='username']")
        password_field = await browser.query_selector("#password, input[name='password']")
        submit_btn = await browser.query_selector("button[type='submit']")

        body_preview = (await browser.text("body"))[:800]
        assert username_field is not None, (
            f"Admin login page must render a username field (#username / input[name='username']). "
            f"url={browser._page.url} preview={body_preview!r}"
        )
        assert password_field is not None, (
            f"Admin login page must render a password field (#password / input[name='password']). "
            f"url={browser._page.url} preview={body_preview!r}"
        )
        assert submit_btn is not None, (
            f"Admin login page must render a submit button (button[type='submit']). "
            f"url={browser._page.url} preview={body_preview!r}"
        )
    
    async def test_J1_02_admin_persona_authenticates(self, anon_browser: Browser):
        """The admin persona logs in through the real form + TOTP and lands on the dashboard."""
        from ui_tests import workflows

        browser = anon_browser
        await browser.goto(settings.url("/admin/logout"), wait_until="domcontentloaded")
        await browser.goto(settings.url("/admin/login"), wait_until="domcontentloaded")
        await capture(browser, "login-page-empty")
        await workflows.admin_login(
            browser, settings.admin_username, settings.admin_password, totp_secret=settings.admin_totp_secret
        )
        await browser.wait_for_text("h1", "Dashboard", timeout=10.0)
        await capture(browser, "dashboard-after-login")
        journey_state.admin_password = settings.admin_password
        journey_state.admin_logged_in = True

    async def test_J1_04_dashboard_state(self, browser: Browser):
        """Dashboard shows current state (validates structure, not specific values)."""
        # Login first (each test is independent with fresh browser)
        from ui_tests import workflows
        await workflows.ensure_admin_dashboard(browser)
        
        await capture(browser, "dashboard")
        
        # Check for dashboard elements
        page_text = await browser.text("body")
        
        # Dashboard should be visible
        h1_text = await browser.text("h1")
        assert "Dashboard" in h1_text or "Admin" in h1_text, f"Expected dashboard, got: {h1_text}"
        
        # Stats should exist (even if zero)
        # Common stat patterns: "Accounts: 0", "Active Tokens: 0", etc.
        stats_area = await browser.query_selector(".stats, .dashboard-stats, .stat-card, .card")
        if stats_area:
            logger.info("✓ Stats area found")
        
        # Navigation should be present
        nav = await browser.query_selector("nav, .navbar, .sidebar")
        assert nav is not None, "Navigation not found on dashboard"
    
    async def test_J1_05_admin_pages_accessible(self, browser: Browser):
        """All admin pages are accessible without 500 errors."""
        # Login first
        from ui_tests import workflows
        await workflows.ensure_admin_dashboard(browser)
        
        admin_pages = [
            ("/admin/accounts", "accounts-list"),
            ("/admin/realms", "realms-list"),
            ("/admin/audit", "audit-logs"),
            ("/admin/config/netcup", "config-netcup"),
            ("/admin/config/email", "config-email"),
            ("/admin/system", "system-info"),
        ]
        
        for path, screenshot_name in admin_pages:
            await browser.goto(settings.url(path))
            await browser.wait_for_timeout(300)
            
            # Check for 500 error
            page_text = await browser.text("body")
            assert "500" not in page_text or "Internal Server Error" not in page_text, \
                f"500 error on {path}"
            
            # Verify we're not redirected to login
            current_url = browser.current_url or ""
            assert "/login" not in current_url, \
                f"Redirected to login from {path} - session lost?"
            
            await capture(browser, screenshot_name)
        
        logger.info(f"✓ All {len(admin_pages)} admin pages accessible")
    
    async def test_J1_06_summary(self, browser: Browser):
        """Journey 1 complete - summarize state."""
        logger.info("\n" + "=" * 60)
        logger.info("JOURNEY 1 COMPLETE: Fresh Deployment")
        logger.info("=" * 60)
        logger.info(f"  Screenshots: {len(journey_state.screenshots)}")
        logger.info(f"  State: {journey_state.to_dict()}")
        logger.info("=" * 60 + "\n")
        
        # Login and capture final dashboard screenshot
        from ui_tests import workflows
        await workflows.ensure_admin_dashboard(browser)
        await capture(browser, "journey-complete")
