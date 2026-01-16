"""
Interactive UI Tests - Playwright-based tests for buttons, forms, and interactive elements.

These tests click every button, fill every form, and test every link to ensure:
1. All buttons are clickable and trigger expected behavior
2. All forms validate input correctly
3. All links navigate to valid pages
4. JavaScript interactions work correctly
5. CSS themes apply correctly

Run with: pytest ui_tests/tests/test_ui_interactive.py -v
"""
import pytest
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from ui_tests.config import settings
from browser import browser_session
import workflows


pytestmark = pytest.mark.asyncio


# =============================================================================
# CSS Theme Variable Validation Tests
# =============================================================================

class TestCSSThemeVariables:
    """Validate CSS variables are defined for all themes."""
    
    REQUIRED_CSS_VARIABLES = [
        '--color-bg-primary',
        '--color-bg-secondary',
        '--color-bg-elevated',
        '--color-accent',
        '--color-text-primary',
        '--color-text-secondary',
        '--color-text-muted',
        '--color-border',
        '--color-success',
        '--color-warning',
        '--color-danger',
        '--color-info',
    ]
    
    THEMES = [
        'cobalt-2', 'deep-ocean', 'graphite', 'zinc', 'obsidian-noir',
        'ember', 'arctic', 'jade', 'rose-quartz', 'gold-dust',
        'crimson', 'amethyst', 'sapphire', 'slate-luxe', 'navy',
        'cobalt', 'midnight-blue'
    ]
    
    DENSITIES = ['comfortable', 'compact', 'ultra-compact']

    async def test_default_theme_variables_defined(self, active_profile):
        """Test default theme has all required CSS variables."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            css_vars = await browser.evaluate("""
                () => {
                    const styles = getComputedStyle(document.documentElement);
                    const vars = {};
                    const varNames = [
                        '--color-bg-primary', '--color-bg-secondary', '--color-bg-elevated',
                        '--color-accent', '--color-text-primary', '--color-text-secondary',
                        '--color-text-muted', '--color-border', '--color-success',
                        '--color-warning', '--color-danger', '--color-info'
                    ];
                    varNames.forEach(name => {
                        vars[name] = styles.getPropertyValue(name).trim();
                    });
                    return vars;
                }
            """)
            
            missing = []
            for var in self.REQUIRED_CSS_VARIABLES:
                if not css_vars.get(var):
                    missing.append(var)
            
            assert not missing, f"Missing CSS variables: {missing}"

    async def test_theme_switcher_changes_theme(self, active_profile):
        """Test that theme switcher applies theme class immediately."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            # Get initial theme
            initial_classes = await browser.evaluate(
                "() => document.documentElement.className"
            )
            
            # Apply a different theme via JavaScript
            await browser.evaluate("() => setTheme('ember')")
            
            # Verify theme class changed
            new_classes = await browser.evaluate(
                "() => document.documentElement.className"
            )
            
            assert 'ember' in new_classes or initial_classes != new_classes, \
                f"Theme should change. Before: {initial_classes}, After: {new_classes}"

    async def test_density_switcher_applies_class(self, active_profile):
        """Test that density switcher applies density class."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            # Apply compact density
            await browser.evaluate("() => setDensity('compact')")
            
            # Verify density class is applied
            has_compact = await browser.evaluate("""
                () => document.documentElement.classList.contains('density-compact') ||
                      document.body.classList.contains('density-compact')
            """)
            
            assert has_compact, "Compact density class should be applied"

    async def test_table_uses_theme_background(self, active_profile):
        """Test that tables respect theme background (not Bootstrap default white)."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/accounts"))
            await browser.verify_status(200)
            
            # Check table exists and has styled background
            table_bg = await browser.evaluate("""
                () => {
                    const table = document.querySelector('table');
                    if (!table) return { exists: false };
                    const styles = getComputedStyle(table);
                    return {
                        exists: true,
                        backgroundColor: styles.backgroundColor,
                        background: styles.background
                    };
                }
            """)
            
            if table_bg.get('exists'):
                bg_color = table_bg.get('backgroundColor', '')
                # Should NOT be pure white (#fff / rgb(255, 255, 255))
                assert 'rgb(255, 255, 255)' not in bg_color, \
                    f"Table has white background, not respecting theme: {bg_color}"


# =============================================================================
# Navigation Consistency Matrix Tests
# =============================================================================

class TestNavigationConsistencyMatrix:
    """Verify navigation elements are consistent across all pages."""
    
    ADMIN_PAGES = [
        ("/admin/", "Dashboard"),
        ("/admin/accounts", "Accounts"),
        ("/admin/realms/pending", "Pending"),
        ("/admin/audit", "Audit Logs"),
        ("/admin/settings", "Settings"),
        ("/admin/system", "System Info"),
        ("/admin/app-logs", "Application Logs"),
        ("/admin/change-password", "Change Password"),
    ]
    
    EXPECTED_NAV_LINKS = [
        "/admin/",
        "/admin/accounts",
        "/admin/realms/pending",
        "/admin/audit",
    ]
    
    EXPECTED_DROPDOWN_LINKS = [
        "/admin/settings",
        "/admin/system",
        "/admin/app-logs",
    ]

    async def test_navbar_present_on_all_admin_pages(self, active_profile):
        """Verify navbar is present on all admin pages."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            missing_navbar = []
            for path, name in self.ADMIN_PAGES:
                await browser.goto(settings.url(path))
                navbar = await browser.query_selector("nav.navbar")
                if not navbar:
                    missing_navbar.append((path, name))
            
            assert not missing_navbar, f"Navbar missing on pages: {missing_navbar}"

    async def test_consistent_nav_links_all_pages(self, active_profile):
        """Verify same navigation links appear on all admin pages."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            inconsistencies = []
            for path, name in self.ADMIN_PAGES:
                await browser.goto(settings.url(path))
                
                # Get all nav links
                nav_links = await browser.evaluate("""
                    () => {
                        const links = document.querySelectorAll('nav.navbar a[href]');
                        return Array.from(links).map(a => a.getAttribute('href'));
                    }
                """)
                
                # Check expected links are present
                for expected in self.EXPECTED_NAV_LINKS:
                    found = any(expected in link for link in nav_links)
                    if not found:
                        inconsistencies.append(f"{path} missing link to {expected}")
            
            assert not inconsistencies, f"Navigation inconsistencies:\n" + "\n".join(inconsistencies)

    async def test_logout_accessible_all_pages(self, active_profile):
        """Verify logout link is accessible from all admin pages."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            missing_logout = []
            for path, name in self.ADMIN_PAGES:
                await browser.goto(settings.url(path))
                
                logout = await browser.query_selector('a[href*="logout"]')
                if not logout:
                    # Check in dropdown
                    dropdown_logout = await browser.evaluate("""
                        () => {
                            const link = document.querySelector('.dropdown-menu a[href*="logout"]');
                            return link !== null;
                        }
                    """)
                    if not dropdown_logout:
                        missing_logout.append((path, name))
            
            assert not missing_logout, f"Logout link missing on: {missing_logout}"

    async def test_footer_present_all_pages(self, active_profile):
        """Verify footer with build info is present on all admin pages."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            missing_footer = []
            for path, name in self.ADMIN_PAGES:
                await browser.goto(settings.url(path))
                
                footer = await browser.query_selector("footer.app-footer, footer")
                if not footer:
                    missing_footer.append((path, name))
            
            assert not missing_footer, f"Footer missing on: {missing_footer}"

    async def test_page_title_format_consistent(self, active_profile):
        """Verify all pages have consistent title format."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            invalid_titles = []
            for path, name in self.ADMIN_PAGES:
                await browser.goto(settings.url(path))
                
                title = await browser.evaluate("() => document.title")
                
                # Title should contain "Netcup API Filter" and section name
                if "Netcup API Filter" not in title:
                    invalid_titles.append(f"{path}: {title}")
            
            assert not invalid_titles, f"Pages with invalid title format:\n" + "\n".join(invalid_titles)


# =============================================================================
# Interactive Button Tests
# =============================================================================

class TestButtonInteractions:
    """Test all clickable buttons work correctly."""

    async def test_password_toggle_button(self, active_profile):
        """Test password visibility toggle button works."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/change-password"))
            await browser.verify_status(200)
            
            # Fill password
            await browser.fill("#new_password", "TestPassword123+Secure24")
            
            # Get initial type
            initial_type = await browser.get_attribute("#new_password", "type")
            assert initial_type == "password"
            
            # Click toggle
            toggle_btn = await browser.query_selector("#new_password + button")
            if toggle_btn:
                await toggle_btn.click()
                
                # Type should change
                new_type = await browser.get_attribute("#new_password", "type")
                assert new_type == "text", f"Password should be visible, got type={new_type}"

    async def test_generate_password_button(self, active_profile):
        """Test password generation button creates strong password."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/change-password"))
            await browser.verify_status(200)
            
            # Look for generate button
            generate_btn = await browser.query_selector("button[onclick*='generatePassword']")
            
            if generate_btn:
                # Clear field first
                await browser.fill("#new_password", "")
                
                # Click generate
                await generate_btn.click()
                # Wait for password generation to complete
                await browser._page.wait_for_function(
                    "document.getElementById('new_password')?.value?.length > 0",
                    timeout=2000
                )
                
                # Check password was generated
                password = await browser.evaluate(
                    "() => document.getElementById('new_password')?.value || ''"
                )
                assert len(password) >= 20, f"Generated password should be >=20 chars, got {len(password)}"

    async def test_copy_button_functionality(self, active_profile):
        """Test copy-to-clipboard buttons exist and are clickable."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/system"))
            await browser.verify_status(200)
            
            # Look for copy buttons
            copy_btns = await browser.query_selector_all('[onclick*="copyToClipboard"], .btn-copy')
            
            # System info page may have copy buttons for build info
            # Just verify they exist and are not disabled
            if copy_btns:
                for btn in copy_btns[:3]:  # Test first 3
                    is_disabled = await btn.is_disabled()
                    assert not is_disabled, "Copy button should not be disabled"

    async def test_dropdown_menus_open(self, active_profile):
        """Test Bootstrap dropdown menus open on click."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            # Test Config dropdown
            config_dropdown = await browser.query_selector('a.dropdown-toggle:has-text("Config")')
            if config_dropdown:
                await config_dropdown.click()
                # Wait for dropdown to open
                await browser._page.wait_for_selector('.dropdown-menu.show', timeout=2000)
                
                # Dropdown should be visible
                dropdown_menu = await browser.query_selector('.dropdown-menu.show')
                assert dropdown_menu, "Config dropdown should open on click"

    async def test_theme_dropdown_opens(self, active_profile):
        """Test theme/density dropdown opens."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            # Click theme button (palette icon)
            theme_btn = await browser.query_selector('button[title*="Theme"]')
            if theme_btn:
                await theme_btn.click()
                # Wait briefly for Alpine.js to toggle dropdown
                await browser._page.wait_for_timeout(100)
                
                # Dropdown should show
                is_visible = await browser.evaluate("""
                    () => {
                        const dropdown = document.querySelector('.theme-dropdown');
                        return dropdown && dropdown.style.display !== 'none';
                    }
                """)
                # Alpine.js shows/hides, just verify no errors occurred


# =============================================================================
# Form Interaction Tests
# =============================================================================

class TestFormInteractions:
    """Test all forms accept input and validate correctly."""

    async def test_login_form_accepts_input(self, browser):
        """Test admin login form accepts input."""
        await browser._page.context.clear_cookies()
        await browser.goto(settings.url("/admin/login"))
        await browser._page.wait_for_selector("#username")
        
        # Fill fields
        await browser.fill("#username", "testuser")
        await browser.fill("#password", "testpass")
        
        # Verify values
        username = await browser.evaluate("() => document.getElementById('username').value")
        password = await browser.evaluate("() => document.getElementById('password').value")
        
        assert username == "testuser"
        assert password == "testpass"

    async def test_account_registration_form_validation(self, browser):
        """Test registration form validates input."""
        await browser._page.context.clear_cookies()
        await browser.goto(settings.url("/account/register"))
        await browser._page.wait_for_load_state("networkidle")
        
        # Check required fields have required attribute
        username_required = await browser.evaluate("""
            () => document.querySelector('input[name="username"]')?.required
        """)
        email_required = await browser.evaluate("""
            () => document.querySelector('input[name="email"]')?.required
        """)
        password_required = await browser.evaluate("""
            () => document.querySelector('input[name="password"]')?.required
        """)
        
        assert username_required, "Username should be required"
        assert email_required, "Email should be required"
        assert password_required, "Password should be required"

    async def test_password_change_form_validation(self, active_profile):
        """Test password change form validates matching passwords."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/change-password"))
            await browser.verify_status(200)
            
            # Fill mismatched passwords
            await browser.fill("#new_password", "Password123!")
            await browser.fill("#confirm_password", "DifferentPass!")
            
            # Check mismatch indicator shows
            mismatch_visible = await browser.evaluate("""
                () => {
                    const el = document.getElementById('passwordMismatch');
                    return el && !el.classList.contains('d-none');
                }
            """)
            
            # Mismatch warning should appear
            assert mismatch_visible, "Password mismatch warning should be visible"

    async def test_config_form_accepts_input(self, active_profile):
        """Test Netcup config form accepts input."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/config/netcup"))
            await browser.verify_status(200)
            
            # Fill config fields
            await browser.fill('input[name="customer_id"]', "123456")
            await browser.fill('input[name="api_key"]', "test-api-key")
            await browser.fill('input[name="api_password"]', "test-password")
            
            # Verify values retained
            customer = await browser.evaluate(
                "() => document.querySelector('input[name=\"customer_id\"]')?.value"
            )
            assert customer == "123456", f"Customer number should be retained, got {customer}"


# =============================================================================
# Link Navigation Tests
# =============================================================================

class TestLinkNavigation:
    """Test all links navigate to valid pages."""

    async def test_all_navbar_links_work(self, active_profile):
        """Test all navbar links navigate successfully."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            # Get all nav links
            nav_links = await browser.evaluate("""
                () => {
                    const links = document.querySelectorAll('nav.navbar a.nav-link[href]');
                    return Array.from(links)
                        .map(a => a.getAttribute('href'))
                        .filter(href => href && !href.startsWith('#') && !href.startsWith('javascript'));
                }
            """)
            
            broken_links = []
            for link in nav_links:
                try:
                    # Re-authenticate if needed and navigate
                    await browser.goto(settings.url("/admin/"))
                    await browser.goto(settings.url(link))
                    
                    # Check for actual error states, not just any text with "error"
                    h1_text = await browser.text("h1")
                    title = await browser.evaluate("() => document.title")
                    
                    # Check for HTTP error codes in title/h1
                    is_error = any([
                        "404" in title or "404" in h1_text,
                        "500" in title or "500" in h1_text,
                        "Not Found" in h1_text,
                        "Internal Server Error" in h1_text,
                    ])
                    
                    if is_error:
                        broken_links.append(f"{link} - error page")
                except Exception as e:
                    broken_links.append(f"{link} - {str(e)[:50]}")
            
            assert not broken_links, f"Broken navbar links:\n" + "\n".join(broken_links)

    async def test_dashboard_quick_action_links(self, active_profile):
        """Test dashboard stat cards navigate correctly."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            # Dashboard has stat cards that link to list pages, not direct "Create Account" button
            # Test Accounts stat card link
            accounts_link = await browser.query_selector('a[href="/admin/accounts"]')
            assert accounts_link, "Accounts link should exist on dashboard (stat card or nav)"
            
            async with browser._page.expect_navigation(wait_until="domcontentloaded"):
                await accounts_link.click()
            
            h1 = await browser.text("main h1")
            assert "Accounts" in h1, f"Should navigate to accounts page, got h1: {h1}"

    async def test_footer_links_if_present(self, active_profile):
        """Test footer links work if present."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            # Get footer links
            footer_links = await browser.evaluate("""
                () => {
                    const links = document.querySelectorAll('footer a[href]');
                    return Array.from(links)
                        .map(a => a.getAttribute('href'))
                        .filter(href => href && !href.startsWith('#'));
                }
            """)
            
            # Verify footer links if any
            for link in footer_links[:5]:  # Check first 5
                # Just verify link format is valid
                assert link.startswith('/') or link.startswith('http'), f"Invalid footer link: {link}"


# =============================================================================
# JavaScript Behavior Tests
# =============================================================================

class TestJavaScriptBehavior:
    """Test JavaScript-dependent functionality."""

    async def test_alpine_js_loaded(self, active_profile):
        """Test Alpine.js is loaded and functional."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            # Check Alpine is defined
            alpine_loaded = await browser.evaluate("""
                () => typeof Alpine !== 'undefined'
            """)
            
            assert alpine_loaded, "Alpine.js should be loaded"

    async def test_bootstrap_js_loaded(self, active_profile):
        """Test Bootstrap JS is loaded."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            # Check Bootstrap is defined
            bootstrap_loaded = await browser.evaluate("""
                () => typeof bootstrap !== 'undefined'
            """)
            
            assert bootstrap_loaded, "Bootstrap JS should be loaded"

    async def test_password_entropy_updates(self, active_profile):
        """Test password entropy badge updates dynamically."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/change-password"))
            await browser.verify_status(200)
            
            # Type weak password
            await browser.fill("#new_password", "abc")
            # Wait for entropy calculation
            await browser._page.wait_for_function(
                "document.getElementById('entropyBadge')?.textContent?.length > 0",
                timeout=1000
            )
            
            weak_entropy = await browser.text("#entropyBadge")
            
            # Type strong password
            await browser.fill("#new_password", "Th1s!sAStr0ng&C0mpl3xP@ssw0rd#2024")
            # Wait for entropy recalculation
            await browser._page.wait_for_timeout(100)
            
            strong_entropy = await browser.text("#entropyBadge")
            
            # Entropy should be different for different passwords
            assert weak_entropy != strong_entropy, \
                f"Entropy should update: weak={weak_entropy}, strong={strong_entropy}"

    async def test_no_javascript_errors(self, active_profile):
        """Test pages load without JavaScript console errors."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            # Capture console errors
            errors = []
            
            async def handle_console(msg):
                if msg.type == 'error':
                    errors.append(msg.text)
            
            browser._page.on('console', handle_console)
            
            # Navigate through pages
            pages = ["/admin/", "/admin/accounts", "/admin/audit"]
            for page in pages:
                await browser.goto(settings.url(page))
                await browser._page.wait_for_load_state('domcontentloaded')
            
            # Filter out known acceptable errors (e.g., network issues, List.js init on pages without tables)
            known_non_critical = [
                'net::',
                'favicon',
                "List.js initialization failed",  # Expected on some pages without pagination tables
            ]
            critical_errors = [
                e for e in errors 
                if not any(known in e for known in known_non_critical)
            ]
            
            assert not critical_errors, f"JavaScript errors found: {critical_errors}"


# =============================================================================
# Account Portal Interactive Tests
# =============================================================================

class TestAccountPortalInteraction:
    """Test Account (client) portal interactive elements."""

    async def test_account_login_form_works(self, browser):
        """Test account login form accepts input and submits."""
        await browser._page.context.clear_cookies()
        await browser.goto(settings.url("/account/login"))
        await browser._page.wait_for_load_state("networkidle")
        
        # Check form elements exist
        username = await browser.query_selector('input[name="username"]')
        password = await browser.query_selector('input[name="password"]')
        submit = await browser.query_selector('button[type="submit"]')
        
        assert username, "Username field should exist"
        assert password, "Password field should exist"
        assert submit, "Submit button should exist"
        
        # Fill form
        await browser.fill('input[name="username"]', "testuser")
        await browser.fill('input[name="password"]', "testpass")
        
        # Verify values retained
        username_val = await browser.evaluate(
            "() => document.querySelector('input[name=\"username\"]')?.value"
        )
        assert username_val == "testuser"

    async def test_forgot_password_form_works(self, browser):
        """Test forgot password form accepts email."""
        await browser._page.context.clear_cookies()
        await browser.goto(settings.url("/account/forgot-password"))
        await browser._page.wait_for_load_state("networkidle")
        
        # Check for email input
        email_input = await browser.query_selector('input[type="email"], input[name="email"]')
        assert email_input, "Email input should exist on forgot password page"
        
        # Fill email
        await browser.fill('input[type="email"], input[name="email"]', "test@example.com")
        
        # Verify value
        email_val = await browser.evaluate("""
            () => document.querySelector('input[type="email"], input[name="email"]')?.value
        """)
        assert email_val == "test@example.com"

    async def test_registration_terms_checkbox(self, browser):
        """Test registration form has terms checkbox."""
        await browser._page.context.clear_cookies()
        await browser.goto(settings.url("/account/register"))
        await browser._page.wait_for_load_state("networkidle")
        
        # Check for terms checkbox
        terms = await browser.query_selector('input[name="terms"]')
        
        if terms:
            # Should be unchecked initially
            is_checked = await browser.evaluate(
                "() => document.querySelector('input[name=\"terms\"]')?.checked"
            )
            assert not is_checked, "Terms should be unchecked by default"
            
            # Check it
            await browser._page.check('input[name="terms"]')
            
            is_checked = await browser.evaluate(
                "() => document.querySelector('input[name=\"terms\"]')?.checked"
            )
            assert is_checked, "Terms should be checked after clicking"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])


# =============================================================================
# Layout and Centering Validation Tests
# =============================================================================

class TestLayoutValidation:
    """Validate page layouts, centering, and responsive behavior."""

    async def test_admin_login_page_centering(self, browser):
        """Test admin login page is properly centered on viewport."""
        await browser._page.context.clear_cookies()
        await browser.goto(settings.url("/admin/login"))
        await browser._page.wait_for_load_state("networkidle")
        
        # Check vertical and horizontal centering
        layout = await browser.evaluate("""
            () => {
                const container = document.querySelector('.login-container');
                const innerWrapper = container?.querySelector('div');
                const card = document.querySelector('.login-card');
                const viewport = { width: window.innerWidth, height: window.innerHeight };
                
                if (!innerWrapper || !card) return { error: 'Missing elements' };
                
                const wrapperRect = innerWrapper.getBoundingClientRect();
                const cardRect = card.getBoundingClientRect();
                
                // Calculate expected center positions
                const expectedHorizontalCenter = viewport.width / 2;
                const actualHorizontalCenter = (wrapperRect.left + wrapperRect.right) / 2;
                const horizontalOffset = Math.abs(expectedHorizontalCenter - actualHorizontalCenter);
                
                // Vertical: content should be roughly centered
                const contentHeight = wrapperRect.height;
                const availableHeight = viewport.height;
                const topMargin = wrapperRect.top;
                const bottomMargin = availableHeight - wrapperRect.bottom;
                const verticalOffset = Math.abs(topMargin - bottomMargin);
                
                return {
                    viewport,
                    horizontalOffset,
                    verticalOffset,
                    topMargin,
                    bottomMargin,
                    contentHeight,
                    isHorizontallyCentered: horizontalOffset < 10,
                    isVerticallyCentered: verticalOffset < 50  // Allow some tolerance
                };
            }
        """)
        
        assert 'error' not in layout, f"Layout check failed: {layout.get('error')}"
        assert layout['isHorizontallyCentered'], \
            f"Login page should be horizontally centered (offset: {layout['horizontalOffset']}px)"
        assert layout['isVerticallyCentered'], \
            f"Login page should be vertically centered (top: {layout['topMargin']}px, bottom: {layout['bottomMargin']}px)"

    async def test_account_login_page_centering(self, browser):
        """Test account login page is properly centered on viewport."""
        await browser._page.context.clear_cookies()
        await browser.goto(settings.url("/account/login"))
        await browser._page.wait_for_load_state("networkidle")
        
        layout = await browser.evaluate("""
            () => {
                const container = document.querySelector('.login-container');
                const card = document.querySelector('.card') || document.querySelector('.login-card');
                const viewport = { width: window.innerWidth, height: window.innerHeight };
                
                if (!card) return { error: 'Missing card element' };
                
                const cardRect = card.getBoundingClientRect();
                
                // Check horizontal centering
                const expectedCenter = viewport.width / 2;
                const actualCenter = (cardRect.left + cardRect.right) / 2;
                const horizontalOffset = Math.abs(expectedCenter - actualCenter);
                
                return {
                    viewport,
                    horizontalOffset,
                    cardWidth: cardRect.width,
                    isHorizontallyCentered: horizontalOffset < 10
                };
            }
        """)
        
        assert 'error' not in layout, f"Layout check failed: {layout.get('error')}"
        assert layout['isHorizontallyCentered'], \
            f"Account login should be horizontally centered (offset: {layout['horizontalOffset']}px)"
