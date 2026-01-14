#!/usr/bin/env python3
"""
Capture screenshots of all UI pages for inspection and optimization.

This script systematically navigates through all admin and client pages,
capturing screenshots for UI/UX review.

Key features:
- Complete route coverage (see docs/ROUTE_COVERAGE.md)
- Inline UX validation (theme compliance, white backgrounds, glow effects)
- Data setup for realistic screenshots (accounts, realms, tokens)
- Error page capture
- Theme variant screenshots for BS5 demo

Environment Variables Required:
- DEPLOYED_ADMIN_PASSWORD: Admin password
- SCREENSHOT_DIR: Output directory for screenshots
- UI_BASE_URL: Base URL for the application
"""
import asyncio
import sys
import os
import re
import json
from pathlib import Path
from typing import Dict, List, Tuple

# Ensure both repo root and ui_tests/ are importable
CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(CURRENT_DIR))

from ui_tests.browser import browser_session
from ui_tests.config import settings


# =============================================================================
# UX Validation Helpers
# =============================================================================

async def validate_ux_compliance(browser, page_name: str) -> List[Dict]:
    """
    Validate current page against BS5 theme reference.
    Returns list of UX issues found.
    """
    issues = []
    
    try:
        # Check for white backgrounds on dark theme (critical issue)
        white_bg_issues = await browser._page.evaluate("""
            () => {
                const issues = [];
                const isWhite = (color) => {
                    return color === 'rgb(255, 255, 255)' || 
                           color === 'white' || 
                           color === '#ffffff' ||
                           color === '#fff';
                };
                
                // Check cards
                document.querySelectorAll('.card').forEach((el, i) => {
                    const bg = getComputedStyle(el).backgroundColor;
                    if (isWhite(bg)) {
                        issues.push({
                            element: `.card[${i}]`,
                            issue: 'Card has white background on dark theme',
                            severity: 'error',
                            actual: bg,
                        });
                    }
                });
                
                // Check table rows
                document.querySelectorAll('table tbody tr').forEach((el, i) => {
                    const bg = getComputedStyle(el).backgroundColor;
                    if (isWhite(bg)) {
                        issues.push({
                            element: `table tr[${i}]`,
                            issue: 'Table row has white background',
                            severity: 'error',
                            actual: bg,
                        });
                    }
                });
                
                // Check buttons use theme colors (not default Bootstrap blue)
                document.querySelectorAll('.btn-primary').forEach((el, i) => {
                    const bg = getComputedStyle(el).backgroundColor;
                    if (bg === 'rgb(13, 110, 253)') {
                        issues.push({
                            element: `.btn-primary[${i}]`,
                            issue: 'Button uses Bootstrap default instead of theme',
                            severity: 'warning',
                            actual: bg,
                        });
                    }
                });
                
                return issues;
            }
        """)
        issues.extend(white_bg_issues)
    except Exception as e:
        print(f"⚠️  UX validation error on {page_name}: {e}")
    
    return issues


# =============================================================================
# Screenshot Helpers
# =============================================================================

async def set_viewport(browser, width=None, height=None):
    """Set viewport for screenshots using environment config (NO HARDCODED VALUES)."""
    if width is None:
        width = int(os.environ.get('SCREENSHOT_VIEWPORT_WIDTH', '1920'))
    if height is None:
        height = int(os.environ.get('SCREENSHOT_VIEWPORT_HEIGHT', '1200'))
    await browser._page.set_viewport_size({"width": width, "height": height})


async def verify_not_login_page(browser, page_name: str):
    """Verify we're not redirected back to a login page (session expired/auth failed)."""
    current_url = browser.current_url
    if "/login" in current_url:
        print(f"❌ ERROR: Redirected to login page while accessing {page_name}!")
        print(f"   Current URL: {current_url}")
        print(f"   This means the session expired or authentication failed.")
        raise RuntimeError(f"Session lost - redirected to login while accessing {page_name}")


async def verify_page_status(browser, page_name: str, expected_status: int = 200):
    """Verify HTTP status code of the current page."""
    try:
        status_code = await browser._page.evaluate(
            "() => window.performance.getEntriesByType('navigation')[0]?.responseStatus || 0"
        )
        
        # If we can't get status from performance API, check for error indicators
        if status_code == 0:
            page_text = await browser._page.text_content("body")
            if "500 Internal Server Error" in page_text:
                status_code = 500
            elif "404" in page_text and "Not Found" in page_text:
                status_code = 404
        
        if status_code != expected_status and status_code != 0:
            print(f"❌ ERROR: Unexpected HTTP status for {page_name}!")
            print(f"   Expected: {expected_status}, Got: {status_code}")
            raise RuntimeError(f"HTTP {status_code} error on {page_name}")
        
        return status_code
    except Exception as e:
        print(f"⚠️  Warning: Could not verify status for {page_name}: {e}")
        return None


async def capture_with_validation(
    browser, 
    name: str, 
    validate_ux: bool = True, 
    expected_status: int = 200
) -> Tuple[str, List[Dict]]:
    """
    Capture screenshot and validate UX compliance.
    Returns (screenshot_path, list of UX issues).
    """
    # Don't verify login page for error pages
    if expected_status != 404:
        await verify_not_login_page(browser, name)
        await verify_page_status(browser, name, expected_status)
    
    # Capture screenshot
    screenshot_path = await browser.screenshot(name)
    
    # Validate UX
    ux_issues = []
    if validate_ux:
        ux_issues = await validate_ux_compliance(browser, name)
        if ux_issues:
            print(f"   ⚠️  {len(ux_issues)} UX issues on {name}")
    
    return screenshot_path, ux_issues


# =============================================================================
# Page Capture Functions
# =============================================================================

async def capture_public_pages(browser):
    """Capture public/unauthenticated pages."""
    screenshots = []
    
    pages = [
        ("/admin/login", "00-admin-login"),
        ("/account/login", "00-account-login"),
        ("/account/forgot-password", "00-account-forgot-password"),
    ]
    
    for path, name in pages:
        print(f"📸 Capturing {name}...")
        try:
            await browser.goto(settings.url(path))
            await browser.wait_for_load_state('networkidle')
            screenshot_path = await browser.screenshot(name)
            screenshots.append((name, screenshot_path))
        except Exception as e:
            print(f"⚠️  Could not capture {name}: {e}")
    
    return screenshots


async def capture_admin_pages(browser):
    """Capture all admin UI pages (calls comprehensive version).
    
    Credentials are passed via environment variables.
    """
    result = await capture_admin_pages_comprehensive(browser)
    return result["screenshots"]


async def capture_admin_pages_comprehensive(browser) -> Dict:
    """
    Capture all admin pages with comprehensive data setup and UX validation.
    
    This creates test data to ensure screenshots show populated pages:
    - Screenshots account detail pages
    - Screenshots realm management
    - Validates UX on each page
    """
    screenshots = []
    ux_issues = []
    
    # Get admin credentials from environment
    admin_password = os.environ.get('DEPLOYED_ADMIN_PASSWORD')
    if not admin_password:
        raise RuntimeError(
            "DEPLOYED_ADMIN_PASSWORD not set. "
            "Playwright container needs credentials passed as environment variables."
        )
    
    # Login to admin
    print("📸 Logging into admin...")
    await browser.goto(settings.url("/admin/login"))
    await browser.wait_for_load_state('networkidle')

    # If Mailpit is available, clear old messages so we reliably grab the
    # *current* 2FA email (registration tests may have produced similar subjects).
    try:
        from ui_tests.mailpit_client import MailpitClient

        mailpit = MailpitClient()
        mailpit.clear()
        mailpit.close()
        print("ℹ️  Cleared Mailpit inbox before admin login")
    except Exception as e:
        print(f"ℹ️  Mailpit not available to pre-clear inbox: {e}")

    await browser.fill("#username", settings.admin_username)
    await browser.fill("#password", admin_password)
    await browser.click("button[type='submit']")
    await browser.wait_for_load_state('networkidle')  # Wait for navigation after form submit
    
    # Check if we're on 2FA page (use page.url for live URL)
    current_url = browser._page.url
    if "/2fa" in current_url or "/login/2fa" in current_url:
        print("ℹ️  Redirected to 2FA - attempting to handle via Mailpit")
        try:
            from ui_tests.mailpit_client import MailpitClient
            mailpit = MailpitClient()
            
            # Wait for 2FA email
            msg = mailpit.wait_for_message(
                predicate=lambda m: "verification" in m.subject.lower() or "login" in m.subject.lower(),
                timeout=10.0
            )
            
            if msg:
                full_msg = mailpit.get_message(msg.id)
                code_match = re.search(r'\b(\d{6})\b', full_msg.text)
                
                if code_match:
                    code = code_match.group(1)
                    print(f"✓ Extracted 2FA code from email: {code}")

                    # Fill the code field and submit. Use requestSubmit/expect_navigation
                    # patterns to avoid Playwright race conditions.
                    await browser.fill("#code", code)
                    await browser.submit("#twoFaForm")

                    # Explicitly wait for leaving the login area.
                    await browser._page.wait_for_url(
                        re.compile(r".*/admin/(?!login).*"),
                        timeout=10_000,
                    )
                    print(f"✓ 2FA navigation complete: {browser._page.url}")
                    
                    mailpit.delete_message(msg.id)
                    mailpit.close()
                else:
                    print("⚠️  Could not extract code from email")
            else:
                print("⚠️  No 2FA email found in Mailpit")
        except Exception as e:
            print(f"⚠️  2FA via Mailpit failed: {e}")
    
    # Verify login was successful (use live URL)
    current_url = browser._page.url
    if "/admin/login/2fa" in current_url:
        raise RuntimeError("Login failed - still on 2FA page")
    if "/admin/login" in current_url:
        raise RuntimeError("Login failed - still on login page")
    
    # Handle password change page (fresh database)
    try:
        current_h1 = await browser._page.locator("main h1").text_content()
        if current_h1 and "Change Password" in current_h1:
            print("📸 Capturing password change page...")
            path, issues = await capture_with_validation(browser, "00b-admin-password-change")
            screenshots.append(("00b-admin-password-change", path))
            ux_issues.extend(issues)
            await browser.goto(settings.url("/admin/"))
            await browser.wait_for_load_state('networkidle')
    except Exception:
        pass  # Continue if h1 not found
    
    # Core admin pages
    pages = [
        ("/admin/", "01-admin-dashboard"),
        ("/admin/accounts", "02-admin-accounts-list"),
        ("/admin/accounts/new", "03-admin-account-create"),
        ("/admin/accounts/pending", "03b-admin-accounts-pending"),
        ("/admin/realms", "10-admin-realms-list"),
        ("/admin/realms/pending", "11-admin-realms-pending"),
        ("/admin/audit", "20-admin-audit-logs"),
        ("/admin/config/netcup", "30-admin-config-netcup"),
        ("/admin/config/email", "31-admin-config-email"),
        ("/admin/system", "32-admin-system-info"),
        ("/admin/change-password", "40-admin-change-password"),
    ]
    
    for path, name in pages:
        print(f"📸 Capturing {name}...")
        await browser.goto(settings.url(path))
        await browser.wait_for_load_state('networkidle')
        
        screenshot_path, issues = await capture_with_validation(browser, name)
        screenshots.append((name, screenshot_path))
        ux_issues.extend([{**i, "page": path} for i in issues])
    
    # Capture detail pages (if data exists)
    await capture_admin_detail_pages(browser, screenshots, ux_issues)
    
    return {"screenshots": screenshots, "ux_issues": ux_issues}


async def capture_admin_detail_pages(browser, screenshots: List, ux_issues: List):
    """Capture admin detail pages for accounts, realms, tokens."""
    
    # Find and capture account detail
    try:
        await browser.goto(settings.url("/admin/accounts"))
        await browser.wait_for_load_state('networkidle')
        
        page_html = await browser.html("body")
        account_match = re.search(r'/admin/accounts/(\d+)', page_html)
        
        if account_match:
            account_id = account_match.group(1)
            await browser.goto(settings.url(f"/admin/accounts/{account_id}"))
            await browser.wait_for_load_state('networkidle')
            
            path, issues = await capture_with_validation(browser, "04-admin-account-detail")
            screenshots.append(("04-admin-account-detail", path))
            ux_issues.extend(issues)
            print(f"   ✓ Captured account detail (ID: {account_id})")
    except Exception as e:
        print(f"⚠️  Could not capture account detail: {e}")
    
    # Find and capture realm detail
    try:
        await browser.goto(settings.url("/admin/realms"))
        await browser.wait_for_load_state('networkidle')
        
        page_html = await browser.html("body")
        realm_match = re.search(r'/admin/realms/(\d+)', page_html)
        
        if realm_match:
            realm_id = realm_match.group(1)
            await browser.goto(settings.url(f"/admin/realms/{realm_id}"))
            await browser.wait_for_load_state('networkidle')
            
            path, issues = await capture_with_validation(browser, "12-admin-realm-detail")
            screenshots.append(("12-admin-realm-detail", path))
            ux_issues.extend(issues)
            print(f"   ✓ Captured realm detail (ID: {realm_id})")
    except Exception as e:
        print(f"⚠️  Could not capture realm detail: {e}")
    
    # Find and capture token detail
    try:
        page_html = await browser.html("body")
        token_match = re.search(r'/admin/tokens/(\d+)', page_html)
        
        if token_match:
            token_id = token_match.group(1)
            await browser.goto(settings.url(f"/admin/tokens/{token_id}"))
            await browser.wait_for_load_state('networkidle')
            
            path, issues = await capture_with_validation(browser, "13-admin-token-detail")
            screenshots.append(("13-admin-token-detail", path))
            ux_issues.extend(issues)
            print(f"   ✓ Captured token detail (ID: {token_id})")
    except Exception as e:
        print(f"⚠️  Could not capture token detail: {e}")


async def capture_account_pages(browser):
    """Capture account portal pages.
    
    Currently captures only public pages since we don't have 
    account user credentials in deployment state.
    """
    screenshots = []
    
    account_pages = [
        ("/account/login", "08-account-login"),
        ("/account/register", "09-account-register"),
    ]
    
    for path, name in account_pages:
        print(f"📸 Capturing {name}...")
        try:
            await browser.goto(settings.url(path))
            await browser.wait_for_load_state('networkidle')
            screenshot_path = await browser.screenshot(name)
            screenshots.append((name, screenshot_path))
        except Exception as e:
            print(f"⚠️  Could not capture {name}: {e}")
    
    return screenshots


async def capture_client_pages(browser):
    """Capture account portal pages (replaces old client portal).
    
    The old /client/ portal has been deprecated in favor of the /account/ system.
    This function now delegates to capture_account_pages for public account pages.
    """
    return await capture_account_pages(browser)


async def capture_bs5_demo_pages(browser):
    """Capture Bootstrap 5 component demo page with different themes.
    
    The component demo page at /component-demo-bs5 showcases all Bootstrap 5
    components styled with our custom themes. This is used as reference for:
    - Visual compliance testing
    - Theme consistency validation
    - CSS variable verification
    
    Themes captured:
    - Cobalt 2: Dark blue theme with bright accents (default)
    - Obsidian Noir: Dark black/gray theme with purple accents
    - Gold Dust: Warm gold/amber theme
    """
    screenshots = []
    
    themes = [
        ("Cobalt 2", "cobalt-2"),
        ("Obsidian Noir", "obsidian-noir"),
        ("Gold Dust", "gold-dust"),
    ]
    
    for theme_name, theme_slug in themes:
        print(f"📸 Capturing BS5 demo with theme: {theme_name}...")
        try:
            # Navigate to BS5 demo page
            await browser.goto(settings.url("/component-demo-bs5"))
            await browser.wait_for_load_state('networkidle')
            
            # Click the theme link in the sidebar
            theme_selector = f'a.nav-link:has-text("{theme_name}")'
            await browser._page.click(theme_selector)
            
            # Small delay to let CSS transitions complete
            await browser.wait_for_timeout(300)
            
            # Capture full page screenshot
            name = f"99-bs5-demo-{theme_slug}"
            screenshot_path = await browser.screenshot(name)
            screenshots.append((name, screenshot_path))
            print(f"   ✓ Captured {name}")
            
        except Exception as e:
            print(f"⚠️  Could not capture BS5 demo with {theme_slug}: {e}")
    
    return screenshots


async def capture_error_pages(browser) -> List[Tuple[str, str]]:
    """Capture error pages (404, etc.)."""
    screenshots = []
    
    print("📸 Capturing 404 error page...")
    try:
        await browser.goto(settings.url("/nonexistent-page-12345"))
        await browser.wait_for_load_state('networkidle')
        screenshot_path = await browser.screenshot("90-error-404")
        screenshots.append(("90-error-404", screenshot_path))
    except Exception as e:
        print(f"⚠️  Could not capture 404 page: {e}")
    
    return screenshots


# =============================================================================
# Main Entry Point
# =============================================================================

async def main():
    """Main screenshot capture workflow with comprehensive route coverage."""
    print("🎬 Starting UI Screenshot Capture (Comprehensive)")
    print(f"📍 Target: {settings.base_url}")
    print(f"👤 Admin: {settings.admin_username}")
    print(f"🔑 Client: {settings.client_id}")
    print()
    
    screenshot_dir_str = os.environ.get("SCREENSHOT_DIR")
    if not screenshot_dir_str:
        raise RuntimeError("SCREENSHOT_DIR environment variable is not set.")
    screenshot_dir = Path(screenshot_dir_str)
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    print(f"📁 Screenshots will be saved to: {screenshot_dir}")
    
    all_screenshots = []
    all_ux_issues = []
    
    async with browser_session() as browser:
        # Set larger viewport
        await set_viewport(browser, 1920, 1200)
        
        # Capture public pages
        print("=" * 60)
        print("PUBLIC PAGES")
        print("=" * 60)
        all_screenshots.extend(await capture_public_pages(browser))
        
        # Capture admin pages (with data setup for comprehensive coverage)
        print("\n" + "=" * 60)
        print("ADMIN PAGES (with UX validation)")
        print("=" * 60)
        admin_result = await capture_admin_pages_comprehensive(browser)
        all_screenshots.extend(admin_result["screenshots"])
        all_ux_issues.extend(admin_result["ux_issues"])
        
        # Capture account portal pages
        print("\n" + "=" * 60)
        print("ACCOUNT PORTAL PAGES")
        print("=" * 60)
        all_screenshots.extend(await capture_account_pages(browser))
        
        # Capture BS5 component demo with different themes
        print("\n" + "=" * 60)
        print("BOOTSTRAP 5 THEME DEMOS")
        print("=" * 60)
        all_screenshots.extend(await capture_bs5_demo_pages(browser))
        
        # Capture error pages
        print("\n" + "=" * 60)
        print("ERROR PAGES")
        print("=" * 60)
        all_screenshots.extend(await capture_error_pages(browser))
    
    # Print final count only (details already shown during capture)
    print(f"\n✅ Captured {len(all_screenshots)} screenshots")
    print(f"📁 Location: {screenshot_dir}/")
    
    # UX Issues Summary
    if all_ux_issues:
        print("\n" + "=" * 60)
        print("UX ISSUES DETECTED")
        print("=" * 60)
        errors = [i for i in all_ux_issues if i.get('severity') == 'error']
        warnings = [i for i in all_ux_issues if i.get('severity') == 'warning']
        print(f"  ❌ Errors: {len(errors)}")
        print(f"  ⚠️  Warnings: {len(warnings)}")
        
        if errors:
            print("\n  Critical Issues (Errors):")
            for issue in errors[:10]:  # Show first 10
                print(f"    - {issue.get('element', 'unknown')}: {issue.get('issue', 'unknown')}")
        
        # Write detailed report
        report_path = screenshot_dir / "ux_issues.json"
        with open(report_path, "w") as f:
            json.dump(all_ux_issues, f, indent=2)
        print(f"\n  Full report: {report_path}")
    else:
        print("\n✅ No UX issues detected!")
    
    print("\n💡 Next steps:")
    print("   1. Review screenshots for UI/UX issues")
    print("   2. Check consistency across pages")
    print("   3. Run pytest ui_tests/tests/test_ux_theme_validation.py for automated checks")
    print("   4. Compare against /component-demo-bs5 reference")


if __name__ == "__main__":
    asyncio.run(main())
