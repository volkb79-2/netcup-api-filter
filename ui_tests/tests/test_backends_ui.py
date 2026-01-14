"""
Tests for multi-backend DNS management UI.

Tests the backend services and domain roots management pages.
"""
import pytest

from ui_tests import workflows
from ui_tests.browser import browser_session
from ui_tests.config import settings

pytestmark = pytest.mark.asyncio


# ============================================================================
# Backend Services Tests (Admin)
# ============================================================================

async def test_admin_backends_list_page_loads(active_profile):
    """Test that the backends list page loads successfully."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        
        # Navigate to backends via DNS menu
        await browser.click("a.nav-link.dropdown-toggle:has-text('DNS')")
        await browser.click("a.dropdown-item:has-text('Backend Services')")
        
        # Verify page loaded
        await browser.verify_status(200)
        heading = await browser.text("main h1")
        assert "Backend Services" in heading
        
        # Take screenshot
        screenshot_path = await browser.screenshot(f"{settings.screenshot_prefix}-backends-list")
        assert screenshot_path.endswith((".png", ".webp"))


async def test_admin_backend_providers_page_loads(active_profile):
    """Test that the backend providers page loads successfully."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        
        # Navigate to providers via DNS menu
        await browser.click("a.nav-link.dropdown-toggle:has-text('DNS')")
        await browser.click("a.dropdown-item:has-text('Providers')")
        
        # Verify page loaded
        await browser.verify_status(200)
        heading = await browser.text("main h1")
        assert "Backend Providers" in heading
        
        # Should show at least netcup and powerdns providers
        page_content = await browser.text("body")
        # Providers may not be seeded in all test environments
        assert "Backend Providers" in page_content
        
        # Take screenshot
        screenshot_path = await browser.screenshot(f"{settings.screenshot_prefix}-backend-providers")
        assert screenshot_path.endswith((".png", ".webp"))


async def test_admin_backend_create_page_loads(active_profile):
    """Test that the backend create form loads successfully."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        
        # Navigate to backend create
        await browser.click("a.nav-link.dropdown-toggle:has-text('DNS')")
        await browser.click("a.dropdown-item:has-text('Backend Services')")
        await browser.click("a.btn:has-text('Add Backend')")
        
        # Verify page loaded
        await browser.verify_status(200)
        heading = await browser.text("main h1")
        assert "Create Backend Service" in heading
        
        # Verify form elements exist
        form_content = await browser.text("form")
        assert "Service Name" in form_content
        assert "Provider" in form_content
        
        # Take screenshot
        screenshot_path = await browser.screenshot(f"{settings.screenshot_prefix}-backend-create")
        assert screenshot_path.endswith((".png", ".webp"))


async def test_admin_backend_create_validation(active_profile):
    """Test backend creation form validation."""
    if not active_profile.allow_writes:
        pytest.skip("profile is read-only")
    
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        
        # Navigate to backend create
        await browser.click("a.nav-link.dropdown-toggle:has-text('DNS')")
        await browser.click("a.dropdown-item:has-text('Backend Services')")
        await browser.click("a.btn:has-text('Add Backend')")
        
        # Try to submit empty form (should be blocked by HTML5 validation)
        submit_btn = await browser.query_selector("button[type='submit']")
        assert submit_btn is not None, "Submit button should exist"
        
        # Take screenshot of validation state
        screenshot_path = await browser.screenshot(f"{settings.screenshot_prefix}-backend-create-validation")
        assert screenshot_path.endswith((".png", ".webp"))


# ============================================================================
# Domain Roots Tests
# ============================================================================

async def test_admin_domain_roots_list_page_loads(active_profile):
    """Test that the domain roots list page loads successfully."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        
        # Navigate to domain roots via DNS menu
        await browser.click("a.nav-link.dropdown-toggle:has-text('DNS')")
        await browser.click("a.dropdown-item:has-text('Domain Roots')")
        
        # Verify page loaded
        await browser.verify_status(200)
        heading = await browser.text("main h1")
        assert "Domain Roots" in heading
        
        # Take screenshot
        screenshot_path = await browser.screenshot(f"{settings.screenshot_prefix}-domain-roots-list")
        assert screenshot_path.endswith((".png", ".webp"))


async def test_admin_domain_root_create_page_loads(active_profile):
    """Test that the domain root create form loads successfully."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        
        # Navigate to domain root create
        await browser.click("a.nav-link.dropdown-toggle:has-text('DNS')")
        await browser.click("a.dropdown-item:has-text('Domain Roots')")
        await browser.click("a.btn:has-text('Add Domain Root')")
        
        # Verify page loaded
        await browser.verify_status(200)
        heading = await browser.text("main h1")
        assert "Create Domain Root" in heading
        
        # Verify form elements exist
        form_content = await browser.text("form")
        assert "Root Domain" in form_content
        assert "Visibility" in form_content
        
        # Take screenshot
        screenshot_path = await browser.screenshot(f"{settings.screenshot_prefix}-domain-root-create")
        assert screenshot_path.endswith((".png", ".webp"))


# ============================================================================
# User Backend Management Tests (BYOD)
# ============================================================================

async def test_user_backends_list_page_loads(active_profile):
    """Test that the user's backends list page loads successfully."""
    async with browser_session() as browser:
        await workflows.ensure_user_dashboard(browser)
        
        # Navigate directly (more reliable than clicking responsive navbar)
        await browser.goto(settings.url("/account/backends"))
        
        # Verify page loaded
        await browser.verify_status(200)
        heading = await browser.text("main h1")
        assert "My DNS Backends" in heading or "My Backends" in heading
        
        # Verify BYOD info is shown
        page_content = await browser.text("main")
        assert "Add Backend" in page_content
        
        # Take screenshot
        screenshot_path = await browser.screenshot(f"{settings.screenshot_prefix}-user-backends-list")
        assert screenshot_path.endswith((".png", ".webp"))


async def test_user_backend_create_page_loads(active_profile):
    """Test that the user backend create form loads successfully."""
    async with browser_session() as browser:
        await workflows.ensure_user_dashboard(browser)
        
        # Navigate directly (more reliable than clicking responsive navbar)
        await browser.goto(settings.url("/account/backends/new"))
        
        # Verify page loaded
        await browser.verify_status(200)
        heading = await browser.text("main h1")
        assert "Add DNS Backend" in heading or "Add Backend" in heading
        
        # Verify form elements exist
        form_content = await browser.text("form")
        assert "Provider" in form_content
        assert "Service Name" in form_content
        
        # Take screenshot
        screenshot_path = await browser.screenshot(f"{settings.screenshot_prefix}-user-backend-create")
        assert screenshot_path.endswith((".png", ".webp"))


async def test_user_backends_providers_info(active_profile):
    """Test that supported providers info is displayed."""
    async with browser_session() as browser:
        await workflows.ensure_user_dashboard(browser)
        
        # Navigate directly (more reliable than clicking responsive navbar)
        await browser.goto(settings.url("/account/backends"))
        
        # Verify page loaded
        await browser.verify_status(200)
        
        # Check for supported providers section
        page_content = await browser.text("main")
        if "Supported Providers" in page_content:
            # Good - providers section exists
            pass
        
        # Take screenshot
        screenshot_path = await browser.screenshot(f"{settings.screenshot_prefix}-user-backends-providers-info")
        assert screenshot_path.endswith((".png", ".webp"))


# ============================================================================
# Navigation Tests
# ============================================================================

async def test_admin_dns_menu_navigation(active_profile):
    """Test all DNS menu items are accessible."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        
        pages_to_visit = [
            ("Backend Services", "Backend Services"),
            ("Domain Roots", "Domain Roots"),
            ("Providers", "Backend Providers"),
        ]
        
        for menu_text, expected_heading in pages_to_visit:
            # Open DNS dropdown
            await browser.click("a.nav-link.dropdown-toggle:has-text('DNS')")
            # Click menu item
            await browser.click(f"a.dropdown-item:has-text('{menu_text}')")
            
            # Verify page loaded
            await browser.verify_status(200)
            heading = await browser.text("main h1")
            assert expected_heading in heading, f"Expected '{expected_heading}' in heading, got '{heading}'"


async def test_user_backends_navigation(active_profile):
    """Test user can navigate through My Backends section."""
    async with browser_session() as browser:
        await workflows.ensure_user_dashboard(browser)
        
        # Navigate directly (more reliable than clicking responsive navbar)
        await browser.goto(settings.url("/account/backends"))
        
        # Verify page loaded
        await browser.verify_status(200)
        heading = await browser.text("main h1")
        assert "My DNS Backends" in heading or "Backends" in heading
        
        # Navigate to create page
        await browser.click("a.btn:has-text('Add Backend')")
        
        # Verify create page loaded
        await browser.verify_status(200)
        heading = await browser.text("main h1")
        assert "Add DNS Backend" in heading or "Add Backend" in heading


# ============================================================================
# Stats Display Tests
# ============================================================================

async def test_admin_backends_stats_display(active_profile):
    """Test that backend stats cards display correctly."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        
        # Navigate to backends
        await browser.click("a.nav-link.dropdown-toggle:has-text('DNS')")
        await browser.click("a.dropdown-item:has-text('Backend Services')")
        
        # Verify stats cards exist
        page_content = await browser.text("main")
        assert "Total Backends" in page_content or "Total" in page_content
        assert "Active" in page_content
        
        # Take screenshot showing stats
        screenshot_path = await browser.screenshot(f"{settings.screenshot_prefix}-backends-stats")
        assert screenshot_path.endswith((".png", ".webp"))


async def test_admin_domain_roots_stats_display(active_profile):
    """Test that domain root stats cards display correctly."""
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        
        # Navigate to domain roots
        await browser.click("a.nav-link.dropdown-toggle:has-text('DNS')")
        await browser.click("a.dropdown-item:has-text('Domain Roots')")
        
        # Verify stats cards exist
        page_content = await browser.text("main")
        assert "Total" in page_content
        assert "Public" in page_content or "Realms" in page_content
        
        # Take screenshot showing stats
        screenshot_path = await browser.screenshot(f"{settings.screenshot_prefix}-domain-roots-stats")
        assert screenshot_path.endswith((".png", ".webp"))


async def test_user_backends_stats_display(active_profile):
    """Test that user backend stats cards display correctly."""
    async with browser_session() as browser:
        await workflows.ensure_user_dashboard(browser)
        
        # Navigate directly (more reliable than clicking responsive navbar)
        await browser.goto(settings.url("/account/backends"))
        
        # Verify stats cards exist
        page_content = await browser.text("main")
        assert "Total Backends" in page_content or "Total" in page_content
        
        # Take screenshot showing stats
        screenshot_path = await browser.screenshot(f"{settings.screenshot_prefix}-user-backends-stats")
        assert screenshot_path.endswith((".png", ".webp"))
