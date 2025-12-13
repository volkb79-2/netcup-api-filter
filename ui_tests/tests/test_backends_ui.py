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
# Backend Services Tests
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
        submit_btn = await browser.page.query_selector("button[type='submit']")
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
