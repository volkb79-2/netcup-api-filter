"""
Test password change flow including redirect to dashboard.

This test suite addresses a critical gap: we never tested the actual
redirect path from password change to dashboard. Previous tests used
explicit navigation after form submission instead of trusting the redirect.

Critical test case: After password change, the redirect to dashboard
must complete successfully and the dashboard must render without errors.
"""

import secrets
import string

import pytest

from ui_tests.browser import browser_session
from ui_tests.config import settings
from ui_tests.deployment_state import load_state, get_deployment_target, update_admin_password
from ui_tests import workflows


def generate_secure_password(length: int = 24) -> str:
    """Generate a cryptographically secure password.
    
    Default length of 24 characters with mixed charset provides ~140 bits entropy,
    exceeding the 100-bit minimum requirement.
    """
    # Use safe printable ASCII charset matching server validation
    # Excludes: ! (shell history), ` (command substitution), ' " (quoting), \\ (escape)
    alphabet = string.ascii_letters + string.digits + "-=_+;:,.|/?@#$%^&*()[]{}~<>"
    return ''.join(secrets.choice(alphabet) for _ in range(length))


pytestmark = pytest.mark.asyncio


async def test_password_change_redirects_to_dashboard_successfully():
    """Test the complete password change flow including redirect.
    
    This is THE critical test we were missing. It ensures:
    1. Password change form submits successfully
    2. Redirect to dashboard completes without error
    3. Dashboard renders without 500 errors
    4. All dashboard components render correctly
    
    This test does NOT use ensure_admin_dashboard() - it follows
    the actual user flow including the redirect.
    """
    async with browser_session() as browser:
        # This test must start from a logged-out state.
        # `browser_session()` loads persisted storage-state by default; clear cookies
        # so /admin/login isn't auto-redirected to an authenticated page.
        await browser._page.context.clear_cookies()

        # Get current credentials
        try:
            target = get_deployment_target()
            state = load_state(target)
            username = state.admin.username
            current_password = state.admin.password
        except Exception:
            username = "admin"
            current_password = "admin"
        
        # 1. Login with current credentials
        await browser.goto(settings.url("/admin/login"), wait_until="domcontentloaded")
        await browser._page.wait_for_selector("#username", timeout=10_000)
        
        await browser.fill("#username", username)
        await browser.fill("#password", current_password)
        
        # Wait for login submission to complete
        async with browser._page.expect_navigation(wait_until="networkidle", timeout=10000):
            await browser.click("button[type='submit']")

        # If admin 2FA is enabled, we may now be on /admin/login/2fa.
        # Complete the challenge so subsequent navigation is authenticated.
        await workflows.handle_2fa_if_present(browser, timeout=10.0)
        
        # Check if we're redirected to change password (fresh deployment)
        current_url = browser._page.url

        # If we're still on login, the auth flow didn't complete (likely 2FA/email issue).
        if "/admin/login" in current_url:
            body_preview = (await browser.text("body"))[:300]
            raise AssertionError(f"Login did not complete; still at {current_url}. Body preview: {body_preview!r}")
        
        if "/change-password" not in current_url:
            # Already on dashboard - navigate to change password manually
            await browser.goto(settings.url("/admin/change-password"))
            await browser._page.wait_for_load_state('domcontentloaded')
        
        # 2. Verify we're on password change page
        # Prefer main h1, but fall back to any h1 for standalone pages.
        try:
            h1_text = await browser.text("main h1")
        except Exception:
            h1_text = await browser.text("h1")

        if "password" not in h1_text.lower() and "setup" not in h1_text.lower():
            # Sometimes we may have been redirected back to the dashboard; try one more explicit navigation.
            await browser.goto(settings.url("/admin/change-password"))
            await browser._page.wait_for_load_state('domcontentloaded')
            try:
                h1_text = await browser.text("main h1")
            except Exception:
                h1_text = await browser.text("h1")

        assert "password" in h1_text.lower() or "setup" in h1_text.lower(), (
            f"Expected password change page, got: {h1_text} (url={browser._page.url})"
        )
        
        # 3. Fill password form
        new_password = generate_secure_password()
        
        # Check if current password field exists (not present for forced change)
        current_password_field = await browser.query_selector("#current_password")
        if current_password_field:
            await browser.fill("#current_password", current_password)
        
        # Fill new password fields
        await browser.fill("#new_password", new_password)
        
        # Trigger input event to run checkPasswordStrength()
        await browser.evaluate("document.getElementById('new_password').dispatchEvent(new Event('input', { bubbles: true }))")
        
        await browser.fill("#confirm_password", new_password)
        
        # Trigger input event to run checkPasswordMatch() and updateSubmitButton()
        await browser.evaluate("document.getElementById('confirm_password').dispatchEvent(new Event('input', { bubbles: true }))")
        
        # Wait for client-side validation to complete (button should become enabled)
        await browser._page.wait_for_function(
            "document.getElementById('submitBtn') && !document.getElementById('submitBtn').disabled",
            timeout=5000
        )
        
        # Verify submit button is enabled
        try:
            await browser.wait_for_enabled("#submitBtn", timeout=5.0)
        except Exception as e:
            # Debug validation state
            entropy = await browser.text("#entropyBadge")
            hint = await browser.text("#passwordHint")
            print(f"⚠️  Submit button not enabled: entropy={entropy}, hint={hint}")
            raise
        
        # 4. Submit form (THE CRITICAL MOMENT)
        print(f"Submitting password change form...")
        url_before = browser._page.url
        await browser.click("#submitBtn")
        
        # 5. ✅ CRITICAL: Wait for redirect to complete
        # This is what we were missing! We must verify the redirect succeeds
        print(f"Waiting for redirect from {url_before}...")
        
        # Wait for navigation to complete (up to 10 seconds)
        try:
            await browser._page.wait_for_url(
                lambda url: url != url_before and "/change-password" not in url,
                timeout=10000
            )
            current_url = browser._page.url
            print(f"✓ Redirect completed to: {current_url}")
        except Exception as e:
            raise AssertionError(f"Redirect did not complete after 10 seconds, still at: {browser._page.url}") from e
        
        # Wait for dashboard to fully load
        await browser._page.wait_for_load_state('networkidle')
        
        # 6. ✅ Verify dashboard rendered successfully (no 500 error)
        h1_text = await browser.text("h1")
        assert "Dashboard" in h1_text, f"Expected Dashboard, got: {h1_text}"
        
        # 7. ✅ Verify no error messages
        body_text = await browser.text("body")
        # Avoid brittle substring checks (e.g. Bootstrap may contain "fw-500").
        assert "500 Internal Server Error" not in body_text, "Found 500 Internal Server Error"
        assert "Internal Server Error" not in body_text, "Found Internal Server Error"
        assert "UndefinedError" not in body_text, "Found UndefinedError (template issue)"
        assert "jinja2.exceptions" not in body_text, "Found Jinja2 exception"
        
        # 8. ✅ Verify dashboard components rendered
        stats_area = await browser.query_selector(".card, .dashboard-stats, .stat-card")
        assert stats_area is not None, "Dashboard stats area not found"
        
        footer = await browser.query_selector("footer")
        assert footer is not None, "Footer not found"

        # Persist the new password for subsequent tests in the same run.
        update_admin_password(new_password, updated_by="ui_tests/test_password_change_flow")
        
        print(f"✓ Password change redirect test PASSED")


async def test_dashboard_components_render_without_error():
    """Verify all dashboard components render without Jinja errors.
    
    This test checks for template rendering issues that might be hidden
    in production but not caught by navigation tests.
    """
    async with browser_session() as browser:
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
        
        print(f"✓ Dashboard components render test PASSED")


async def test_all_admin_pages_accessible_after_password_change():
    """Verify all admin pages accessible after password change.
    
    This ensures that session persistence works correctly after
    password change and all routes render without errors.
    """
    async with browser_session() as browser:
        from ui_tests import workflows
        
        # Ensure we're logged in with changed password
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
            
            print(f"✓ {page_name} page accessible")
        
        print(f"✓ All admin pages accessible test PASSED")


async def test_password_change_with_email_setup_optional():
    """Test password change with email setup being optional.
    
    Verifies the fix for issue where email was required before SMTP
    was configured, making initial setup impossible.
    """
    async with browser_session() as browser:
        # This test only makes sense on a fresh deployment where the admin is
        # forced through the password-change flow.
        target = get_deployment_target()
        state = load_state(target)
        if state.admin.password_changed_at:
            pytest.skip("Not a fresh deployment (admin password already changed)")

        # Ensure we start logged out (storage-state may otherwise redirect away from /admin/login).
        await browser._page.context.clear_cookies()

        # Login with fresh credentials
        await browser.goto(settings.url("/admin/login"), wait_until="domcontentloaded")
        await browser._page.wait_for_selector("#username", timeout=10_000)
        
        await browser.fill("#username", state.admin.username)
        await browser.fill("#password", state.admin.password)
        
        # Wait for login to resolve (login -> optional 2FA -> change-password/dashboard)
        await browser.click("button[type='submit']")
        await workflows.handle_2fa_if_present(browser, timeout=10.0)
        await browser._page.wait_for_load_state("domcontentloaded")
        
        current_url = browser._page.url
        if "/change-password" in current_url:
            # On password change page - verify email is optional
            email_field = await browser.query_selector("#email")
            
            if email_field:
                # Check that email field does NOT have required attribute
                is_required = await browser.evaluate(
                    "document.getElementById('email').hasAttribute('required')"
                )
                assert not is_required, "Email field should not be required"
                
                # Check for "(Optional)" in label
                label_text = await browser.text("label[for='email']")
                assert "optional" in label_text.lower(), \
                    "Email label should indicate it's optional"
                
                print(f"✓ Email field is optional (can skip for SMTP setup later)")
            
            # Test form submission WITHOUT email
            new_password = generate_secure_password()
            
            await browser.fill("#new_password", new_password)
            await browser.evaluate("document.getElementById('new_password').dispatchEvent(new Event('input'))")
            
            await browser.fill("#confirm_password", new_password)
            await browser.evaluate("document.getElementById('confirm_password').dispatchEvent(new Event('input'))")
            
            # Wait for validation to complete
            await browser._page.wait_for_function(
                "document.getElementById('submitBtn') && !document.getElementById('submitBtn').disabled",
                timeout=5000
            )
            # Wait for form submission and redirect
            async with browser._page.expect_navigation(wait_until="networkidle", timeout=10000):
                await browser.click("#submitBtn")
            
            # Should succeed and redirect to dashboard
            h1 = await browser.text("h1")
            assert "Dashboard" in h1, "Failed to reach dashboard without email"
            
            print(f"✓ Password change without email test PASSED")
        else:
            print(f"ℹ️  Not on fresh deployment, skipping email optional test")
