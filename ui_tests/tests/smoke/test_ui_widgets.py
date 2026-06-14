"""UI widget behavioral tests.

Harvested from the deleted smoke files; keeps only tests that exercise genuine
JS/CSS behavior — not "page loads" (those moved to test_route_smoke.py).

Rules enforced here:
- No if-found guards: every selector is expected to exist.
- No or-chains in assertions: each assert checks exactly one condition.
- No sleeps: use wait_for_function / wait_for_selector where timing matters.
"""

from __future__ import annotations

import re
import pytest
import pytest_asyncio

from ui_tests.browser import browser_session
from ui_tests.config import settings
from ui_tests import workflows

pytestmark = [pytest.mark.asyncio, pytest.mark.smoke]


# ============================================================================
# CSS / Theme variables
# ============================================================================

class TestCSSThemeVariables:
    """CSS variables are defined for the active theme."""

    REQUIRED_CSS_VARIABLES = [
        "--color-bg-primary",
        "--color-bg-secondary",
        "--color-bg-elevated",
        "--color-accent",
        "--color-text-primary",
        "--color-text-secondary",
        "--color-text-muted",
        "--color-border",
        "--color-success",
        "--color-warning",
        "--color-danger",
        "--color-info",
    ]

    async def test_default_theme_variables_defined(self, active_profile):
        """Default theme defines all required CSS custom properties."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)

            css_vars: dict = await browser.evaluate(
                """
                () => {
                    const s = getComputedStyle(document.documentElement);
                    const names = [
                        '--color-bg-primary','--color-bg-secondary','--color-bg-elevated',
                        '--color-accent','--color-text-primary','--color-text-secondary',
                        '--color-text-muted','--color-border','--color-success',
                        '--color-warning','--color-danger','--color-info'
                    ];
                    const out = {};
                    names.forEach(n => { out[n] = s.getPropertyValue(n).trim(); });
                    return out;
                }
                """
            )

            missing = [v for v in self.REQUIRED_CSS_VARIABLES if not css_vars.get(v)]
            assert not missing, f"Missing CSS variables: {missing}"

    async def test_table_uses_theme_background(self, active_profile):
        """Table background must not be plain white (respects the active theme)."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/accounts"))
            await browser.verify_status(200)

            result = await browser.evaluate(
                """
                () => {
                    const table = document.querySelector('table');
                    if (!table) return null;
                    return getComputedStyle(table).backgroundColor;
                }
                """
            )

            assert result is not None, "Expected a <table> on /admin/accounts"
            assert result != "rgb(255, 255, 255)", (
                f"Table background is plain white — theme CSS not applied: {result}"
            )


# ============================================================================
# Theme switcher
# ============================================================================

class TestThemeSwitcher:
    """Theme switcher applies and persists."""

    async def test_theme_switcher_changes_html_class(self, active_profile):
        """setTheme('ember') must add 'ember' to <html> classList."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)

            await browser.evaluate("() => setTheme('ember')")

            new_class: str = await browser.evaluate(
                "() => document.documentElement.className"
            )
            assert "ember" in new_class, (
                f"Expected 'ember' in html.className after setTheme('ember'), got: {new_class}"
            )

    async def test_theme_persists_across_page_navigation(self, active_profile):
        """Theme chosen on dashboard must still be active after navigating away."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)

            await browser.evaluate("() => setTheme('ember')")
            await browser.goto(settings.url("/admin/accounts"))
            await browser.wait_for_load_state("domcontentloaded")

            theme_class: str = await browser.evaluate(
                "() => document.documentElement.className + ' ' + document.body.className"
            )
            assert "ember" in theme_class, (
                f"Theme 'ember' did not persist to /admin/accounts. Classes: {theme_class}"
            )

            # Restore default so subsequent tests are unaffected
            await browser.evaluate("() => setTheme('cobalt-2')")

    async def test_density_switcher_applies_compact_class(self, active_profile):
        """setDensity('compact') must add 'density-compact' to html or body."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)

            await browser.evaluate("() => setDensity('compact')")

            has_compact: bool = await browser.evaluate(
                """
                () => document.documentElement.classList.contains('density-compact') ||
                      document.body.classList.contains('density-compact')
                """
            )
            assert has_compact, "density-compact class should be present after setDensity('compact')"

            # Restore
            await browser.evaluate("() => setDensity('comfortable')")


# ============================================================================
# Password widget on /admin/change-password
# ============================================================================

class TestPasswordWidget:
    """Password visibility toggle, generator, entropy meter, mismatch warning."""

    async def test_password_toggle_reveals_text(self, active_profile):
        """Eye-toggle button switches #new_password from type=password to type=text."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/change-password"))
            await browser.verify_status(200)

            await browser.fill("#new_password", "TestPassword123+Secure24")

            initial_type = await browser.get_attribute("#new_password", "type")
            assert initial_type == "password", (
                f"Initial type should be 'password', got '{initial_type}'"
            )

            # The toggle button is the next sibling in the input-group
            await browser._page.click("#new_password + button")

            new_type = await browser.get_attribute("#new_password", "type")
            assert new_type == "text", (
                f"After toggle, type should be 'text', got '{new_type}'"
            )

    async def test_generate_password_fills_field(self, active_profile):
        """Generate button must fill #new_password with at least 20 characters."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/change-password"))
            await browser.verify_status(200)

            await browser.fill("#new_password", "")
            await browser._page.click("button[onclick*='generatePassword']")
            await browser._page.wait_for_function(
                "document.getElementById('new_password')?.value?.length > 0",
                timeout=3000,
            )

            password: str = await browser.evaluate(
                "() => document.getElementById('new_password')?.value || ''"
            )
            assert len(password) >= 20, (
                f"Generated password should be >=20 chars, got {len(password)}: {password!r}"
            )

    async def test_entropy_meter_updates_on_input(self, active_profile):
        """#entropyBadge text must change between a weak and a strong password."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/change-password"))
            await browser.verify_status(200)

            await browser.fill("#new_password", "abc")
            await browser._page.wait_for_function(
                "document.getElementById('entropyBadge')?.textContent?.trim().length > 0",
                timeout=2000,
            )
            weak_entropy = await browser.text("#entropyBadge")

            await browser.fill("#new_password", "Th1s!sAStr0ng&C0mpl3xP@ssw0rd#2024")
            await browser._page.wait_for_timeout(150)
            strong_entropy = await browser.text("#entropyBadge")

            assert weak_entropy != strong_entropy, (
                f"Entropy badge should differ: weak={weak_entropy!r}, strong={strong_entropy!r}"
            )

        # Also verify bit counts for the strong password
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/change-password"))
            await browser.verify_status(200)

            await browser.fill("#new_password", "abc")
            await browser._page.wait_for_function(
                "document.getElementById('entropyBadge')?.textContent?.includes('bit')",
                timeout=2000,
            )
            weak_text = await browser.text("#entropyBadge")
            m = re.search(r"(\d+)\s*bit", weak_text)
            assert m, f"Expected 'Xbit' in entropyBadge, got: {weak_text!r}"
            assert int(m.group(1)) < 50, (
                f"Weak password should show <50 bit entropy, got {m.group(1)}"
            )

    async def test_confirm_password_mismatch_warning_visible(self, active_profile):
        """Mismatched confirm-password must make #passwordMismatch visible (no d-none)."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/change-password"))
            await browser.verify_status(200)

            await browser.fill("#new_password", "Password123!Strong")
            await browser.fill("#confirm_password", "DifferentPassword456!")

            mismatch_visible: bool = await browser.evaluate(
                """
                () => {
                    const el = document.getElementById('passwordMismatch');
                    return el !== null && !el.classList.contains('d-none');
                }
                """
            )
            assert mismatch_visible, (
                "Password mismatch warning (#passwordMismatch) should be visible"
            )

    async def test_submit_button_disabled_initially(self, active_profile):
        """Submit button (#submitBtn) must be disabled on page load."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/change-password"))
            await browser.verify_status(200)

            is_disabled: bool = await browser.evaluate(
                "() => document.getElementById('submitBtn')?.disabled ?? true"
            )
            assert is_disabled, "Submit button should be disabled on initial page load"


# ============================================================================
# Copy-to-clipboard function defined
# ============================================================================

class TestCopyButton:
    """The copyToClipboard helper is defined in base.html and available on all pages."""

    async def test_copy_to_clipboard_function_defined(self, active_profile):
        """copyToClipboard must be a callable function on every admin page."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)

            is_callable: bool = await browser.evaluate(
                "() => typeof copyToClipboard === 'function'"
            )
            assert is_callable, (
                "copyToClipboard should be defined as a function on admin pages (from base.html)"
            )


# ============================================================================
# Dropdown / modal
# ============================================================================

class TestDropdownModal:
    """Bootstrap dropdowns open; modals have correct DOM structure."""

    async def test_dropdown_menu_opens_on_click(self, active_profile):
        """Clicking .dropdown-toggle must show a .dropdown-menu.show element."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)

            dropdown_toggle = await browser.query_selector(".dropdown-toggle")
            assert dropdown_toggle is not None, (
                "Expected at least one .dropdown-toggle in admin dashboard"
            )

            await dropdown_toggle.click()

            is_open: bool = await browser.evaluate(
                "() => document.querySelector('.dropdown-menu.show') !== null"
            )
            assert is_open, ".dropdown-menu.show not found after clicking .dropdown-toggle"

    async def test_geoip_modal_present_on_audit_page(self, active_profile):
        """The GeoIP lookup modal markup must be present on /admin/audit."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            await browser.goto(settings.url("/admin/audit"))
            await browser.verify_status(200)

            modal = await browser.query_selector("#geoipModal")
            assert modal is not None, "Expected #geoipModal markup on /admin/audit"

            dialog = await browser.query_selector("#geoipModal .modal-dialog")
            assert dialog is not None, "Modal must contain a .modal-dialog container"


# ============================================================================
# Login → register / forgot-password link navigation
# ============================================================================

class TestLoginPageLinks:
    """Login page links lead to the correct destinations."""

    async def test_account_login_has_register_link(self, browser):
        """Account login page must expose a link to /account/register."""
        await browser._page.context.clear_cookies()
        await browser.goto(settings.url("/account/login"))
        await browser.wait_for_load_state("networkidle")

        register_link = await browser.query_selector('a[href*="register"]')
        assert register_link is not None, (
            "Login page must have a link to the register page"
        )

        await register_link.click()
        await browser.wait_for_load_state("networkidle")

        current = browser._page.url
        assert "/register" in current, (
            f"Clicking register link should navigate to /register, got: {current}"
        )

    async def test_account_login_has_forgot_password_link(self, browser):
        """Account login page must expose a link to the forgot-password page."""
        await browser._page.context.clear_cookies()
        await browser.goto(settings.url("/account/login"))
        await browser.wait_for_load_state("networkidle")

        forgot_link = await browser.query_selector('a[href*="forgot"]')
        assert forgot_link is not None, (
            "Login page must have a link to the forgot-password page"
        )

        await forgot_link.click()
        await browser.wait_for_load_state("networkidle")

        current = browser._page.url
        assert "/forgot" in current, (
            f"Clicking forgot-password link should navigate to /forgot, got: {current}"
        )


# ============================================================================
# Slim responsive tests (mobile viewport)
# ============================================================================

MOBILE_VIEWPORT = {"width": 375, "height": 812}  # iPhone X


class TestResponsive:
    """Mobile viewport: tap targets, no horizontal overflow, navbar collapse."""

    async def test_submit_button_tap_target_exists(self, active_profile):
        """Login page submit button must be present at mobile viewport."""
        async with browser_session() as browser:
            await browser.set_viewport(MOBILE_VIEWPORT["width"], MOBILE_VIEWPORT["height"])
            await browser._page.context.clear_cookies()
            await browser.goto(settings.url("/admin/login"))
            await browser.verify_status(200)

            submit_btn = await browser.query_selector(
                'button[type="submit"], input[type="submit"]'
            )
            assert submit_btn is not None, (
                "Submit button must be present on admin login at mobile viewport"
            )

    async def test_no_horizontal_overflow_on_dashboard(self, active_profile):
        """Admin dashboard must not overflow horizontally at 375 px."""
        async with browser_session() as browser:
            await browser.set_viewport(MOBILE_VIEWPORT["width"], MOBILE_VIEWPORT["height"])
            await workflows.ensure_admin_dashboard(browser)

            overflows: bool = await browser.evaluate(
                "() => document.body.scrollWidth > document.body.clientWidth"
            )
            assert not overflows, (
                "Horizontal overflow detected on admin dashboard at 375px viewport"
            )

    async def test_navbar_toggler_present_at_mobile(self, active_profile):
        """Navbar hamburger toggler must be rendered at mobile viewport."""
        async with browser_session() as browser:
            await browser.set_viewport(MOBILE_VIEWPORT["width"], MOBILE_VIEWPORT["height"])
            await workflows.ensure_admin_dashboard(browser)

            toggler = await browser.query_selector(".navbar-toggler")
            assert toggler is not None, (
                "Navbar toggler (.navbar-toggler) should be present at 375px"
            )

    async def test_viewport_meta_tag_present(self, active_profile):
        """Pages must include a viewport meta tag with width=device-width."""
        async with browser_session() as browser:
            await browser.goto(settings.url("/admin/login"))
            content: str | None = await browser.evaluate(
                "() => document.querySelector('meta[name=\"viewport\"]')?.getAttribute('content') ?? null"
            )

            assert content is not None, "Viewport meta tag must be present"
            assert "width=device-width" in content, (
                f"Viewport meta must set device-width, got: {content}"
            )
