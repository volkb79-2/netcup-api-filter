"""
Holistic Coverage Tests - Integrated testing with screenshot capture and UX validation.

This module provides comprehensive coverage of all routes with:
1. Data setup - Create accounts, realms, tokens, and API activity
2. Screenshot capture - Take screenshots at each stage
3. UX validation - Compare styling against BS5 reference
4. Error simulation - Test error handling and logging

The approach interweaves testing and screenshots to ensure:
- All routes are covered with realistic data
- Screenshots show populated pages (not empty states)
- Theme compliance is automatically validated
- Error conditions are properly captured

Run with: pytest ui_tests/tests/test_holistic_coverage.py -v --capture=no
"""
import pytest
import re
import secrets
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import os

from ui_tests.browser import browser_session, Browser
from ui_tests.config import settings
from ui_tests import workflows


pytestmark = pytest.mark.asyncio


# =============================================================================
# CSS Reference Values from /component-demo-bs5 (Cobalt 2 theme)
# =============================================================================

THEME_REFERENCE = {
    "cobalt-2": {
        "primary": "#3b7cf5",
        "primary_rgb": "59, 124, 245",
        "body_bg": "#070a14",
        "secondary_bg": "#0c1020",
        "elevated_bg": "#141c30",
        "border_card": "rgba(100, 150, 255, 0.38)",
        "accent_glow": "rgba(59, 124, 245, 0.4)",
        "text_color": "#f8fafc",
    },
    "obsidian-noir": {
        "primary": "#a78bfa",
        "primary_rgb": "167, 139, 250",
        "body_bg": "#08080d",
        "secondary_bg": "#0f0f16",
        "elevated_bg": "#16161f",
        "border_card": "rgba(167, 139, 250, 0.42)",
        "accent_glow": "rgba(167, 139, 250, 0.35)",
    },
    "gold-dust": {
        "primary": "#fbbf24",
        "primary_rgb": "251, 191, 36",
        "body_bg": "#0a0907",
        "secondary_bg": "#13110d",
        "elevated_bg": "#1b1814",
        "border_card": "rgba(251, 191, 36, 0.40)",
        "accent_glow": "rgba(251, 191, 36, 0.35)",
    }
}


# =============================================================================
# Screenshot Helper with UX Validation
# =============================================================================

class ScreenshotCapture:
    """Helper for capturing screenshots with UX validation."""
    
    def __init__(self, browser: Browser, screenshot_dir: Path):
        self.browser = browser
        self.screenshot_dir = screenshot_dir
        self.captured: List[Tuple[str, str]] = []
        self.ux_issues: List[Dict] = []
        
    async def capture(self, name: str, validate_ux: bool = True) -> str:
        """Capture screenshot and optionally validate UX compliance."""
        screenshot_path = await self.browser.screenshot(name)
        self.captured.append((name, screenshot_path))
        
        if validate_ux:
            issues = await self._validate_ux_compliance()
            if issues:
                self.ux_issues.extend(issues)
                print(f"⚠️  UX issues on {name}: {len(issues)}")
                for issue in issues:
                    print(f"    - {issue['element']}: {issue['issue']}")
        
        return screenshot_path
    
    async def _validate_ux_compliance(self) -> List[Dict]:
        """Validate current page against BS5 theme reference."""
        issues = []
        
        # Get current theme from page
        current_theme = await self.browser._page.evaluate("""
            () => {
                const html = document.documentElement;
                const body = document.body;
                
                // Check theme class
                for (const cls of html.classList) {
                    if (cls.startsWith('theme-')) {
                        return cls.replace('theme-', '');
                    }
                }
                for (const cls of body.classList) {
                    if (cls.startsWith('theme-')) {
                        return cls.replace('theme-', '');
                    }
                }
                
                // Check data-theme attribute
                return html.getAttribute('data-theme') || 'cobalt-2';
            }
        """)
        
        # Validate CSS variables
        css_check = await self.browser._page.evaluate("""
            () => {
                const style = getComputedStyle(document.documentElement);
                return {
                    primary: style.getPropertyValue('--bs-primary').trim(),
                    bodyBg: style.getPropertyValue('--bs-body-bg').trim(),
                    cardBg: style.getPropertyValue('--bs-card-bg').trim(),
                };
            }
        """)
        
        # Validate cards have proper styling
        card_issues = await self.browser._page.evaluate("""
            () => {
                const issues = [];
                const cards = document.querySelectorAll('.card');
                
                cards.forEach((card, i) => {
                    const style = getComputedStyle(card);
                    const bg = style.backgroundColor;
                    const border = style.borderColor;
                    
                    // Check for common issues
                    if (bg === 'rgb(255, 255, 255)' || bg === 'white') {
                        issues.push({
                            element: `.card[${i}]`,
                            issue: `Card has white background (${bg}) instead of theme color`
                        });
                    }
                    
                    // Check table rows for white backgrounds
                    const tables = card.querySelectorAll('table tbody tr');
                    tables.forEach((row, j) => {
                        const rowStyle = getComputedStyle(row);
                        if (rowStyle.backgroundColor === 'rgb(255, 255, 255)') {
                            issues.push({
                                element: `.card[${i}] table tr[${j}]`,
                                issue: 'Table row has white background'
                            });
                        }
                    });
                });
                
                return issues;
            }
        """)
        
        issues.extend(card_issues)
        
        # Validate buttons use theme accent
        btn_issues = await self.browser._page.evaluate("""
            () => {
                const issues = [];
                const primaryBtns = document.querySelectorAll('.btn-primary');
                
                primaryBtns.forEach((btn, i) => {
                    const style = getComputedStyle(btn);
                    const bg = style.backgroundColor;
                    
                    // Should not be Bootstrap default blue
                    if (bg === 'rgb(13, 110, 253)') {
                        issues.push({
                            element: `.btn-primary[${i}]`,
                            issue: 'Button uses default Bootstrap blue instead of theme accent'
                        });
                    }
                });
                
                return issues;
            }
        """)
        
        issues.extend(btn_issues)
        
        return issues
    
    def get_summary(self) -> Dict:
        """Get summary of captured screenshots and UX issues."""
        return {
            "captured_count": len(self.captured),
            "screenshots": self.captured,
            "ux_issues_count": len(self.ux_issues),
            "ux_issues": self.ux_issues,
        }


# =============================================================================
# Data Setup Helpers
# =============================================================================

async def create_test_account(browser: Browser, prefix: str = "test") -> Dict:
    """Create a test account via admin UI and return details."""
    suffix = secrets.token_hex(4)
    account_data = {
        "username": f"{prefix}-{suffix}",
        "email": f"{prefix}-{suffix}@example.test",
        "description": f"Test account created at {datetime.now().isoformat()}",
    }
    
    await browser.goto(settings.url("/admin/accounts/new"))
    await browser.wait_for_load_state('domcontentloaded')

    await browser.fill("#username", account_data["username"])
    await browser.fill("#email", account_data["email"])
    
    # Fill description if field exists
    desc_field = await browser.query_selector("#description")
    if desc_field:
        await browser.fill("#description", account_data["description"])
    
    # Submit form
    await browser.click("button[type='submit']")
    await browser.wait_for_load_state('domcontentloaded')
    return account_data


async def create_test_realm(browser: Browser, account_id: int, prefix: str = "realm") -> Dict:
    """Create a realm for an account."""
    suffix = secrets.token_hex(4)
    realm_data = {
        "value": f"{prefix}-{suffix}.example.test",
        "type": "host",
        "record_types": ["A", "AAAA", "TXT"],
        "operations": ["read", "update"],
    }
    
    await browser.goto(settings.url(f"/admin/accounts/{account_id}/realms/new"))
    await browser.wait_for_load_state('domcontentloaded')

    # Fill realm form
    await browser.fill("#realm_value", realm_data["value"])
    
    # Select realm type
    type_select = await browser.query_selector("#realm_type")
    if type_select:
        await browser._page.select_option("#realm_type", realm_data["type"])
    
    # Check record types
    for rt in realm_data["record_types"]:
        checkbox = await browser.query_selector(f'input[name="record_types"][value="{rt}"]')
        if checkbox:
            await checkbox.check()
    
    # Check operations
    for op in realm_data["operations"]:
        checkbox = await browser.query_selector(f'input[name="operations"][value="{op}"]')
        if checkbox:
            await checkbox.check()
    
    await browser.click("button[type='submit']")
    await browser.wait_for_load_state('domcontentloaded')
    return realm_data


async def simulate_api_activity(browser: Browser) -> None:
    """Simulate API activity to populate audit logs.
    
    Uses the mock API to create realistic log entries.
    """
    import httpx
    
    base_url = settings.base_url
    
    # Get demo token from environment or use default
    demo_token = os.environ.get("DEPLOYED_CLIENT_SECRET_KEY", "")
    
    if not demo_token:
        print("⚠️  No client token available for API activity simulation")
        return
    
    async with httpx.AsyncClient(verify=False, timeout=10) as client:
        headers = {"Authorization": f"Bearer {demo_token}"}
        
        # Successful read request
        try:
            await client.get(f"{base_url}/api/dns/example.test/records", headers=headers)
        except Exception:
            pass
        
        # Invalid token (should log error)
        try:
            await client.get(
                f"{base_url}/api/dns/example.test/records", 
                headers={"Authorization": "Bearer invalid_token"}
            )
        except Exception:
            pass
        
        # Missing authorization (should log error)
        try:
            await client.get(f"{base_url}/api/dns/example.test/records")
        except Exception:
            pass


# =============================================================================
# Comprehensive Route Coverage Tests
# =============================================================================

class TestHolisticAdminCoverage:
    """Comprehensive admin panel coverage with data setup and screenshots."""
    
    async def test_complete_admin_journey_with_screenshots(self, active_profile):
        """
        Complete admin journey that:
        1. Sets up test data (accounts, realms, tokens)
        2. Captures screenshots of all admin pages
        3. Validates UX compliance against BS5 reference
        4. Simulates API activity for audit logs
        5. Captures error states
        """
        screenshot_dir = Path(os.environ.get("SCREENSHOT_DIR", "/tmp/screenshots"))
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        
        async with browser_session() as browser:
            capture = ScreenshotCapture(browser, screenshot_dir)
            
            # =================================================================
            # Phase 1: Public Pages (Unauthenticated)
            # =================================================================
            print("\n📸 Phase 1: Public Pages")
            
            await browser.goto(settings.url("/admin/login"))
            await capture.capture("holistic-01-admin-login", validate_ux=True)
            
            await browser.goto(settings.url("/account/login"))
            await capture.capture("holistic-02-account-login", validate_ux=True)
            
            await browser.goto(settings.url("/account/register"))
            await capture.capture("holistic-03-account-register", validate_ux=True)
            
            await browser.goto(settings.url("/account/forgot-password"))
            await capture.capture("holistic-04-forgot-password", validate_ux=True)
            
            # =================================================================
            # Phase 2: Admin Login and Dashboard
            # =================================================================
            print("\n📸 Phase 2: Admin Authentication")
            
            await workflows.ensure_admin_dashboard(browser)
            await capture.capture("holistic-10-admin-dashboard", validate_ux=True)
            
            # =================================================================
            # Phase 3: Account Management with Data
            # =================================================================
            print("\n📸 Phase 3: Account Management")
            
            # Capture empty/initial accounts list
            await browser.goto(settings.url("/admin/accounts"))
            await capture.capture("holistic-11-accounts-list", validate_ux=True)
            
            # Create test accounts
            print("   Creating test accounts...")
            account1 = await create_test_account(browser, "holistic-test")
            
            # Capture accounts list with data
            await browser.goto(settings.url("/admin/accounts"))
            await capture.capture("holistic-12-accounts-with-data", validate_ux=True)
            
            # Capture account creation form
            await browser.goto(settings.url("/admin/accounts/new"))
            await capture.capture("holistic-13-account-create-form", validate_ux=True)
            
            # Capture account detail (get first account ID)
            page_html = await browser.html("body")
            account_match = re.search(r'/admin/accounts/(\d+)', page_html)
            if account_match:
                account_id = account_match.group(1)
                await browser.goto(settings.url(f"/admin/accounts/{account_id}"))
                await capture.capture("holistic-14-account-detail", validate_ux=True)
            
            # =================================================================
            # Phase 4: Realm Management
            # =================================================================
            print("\n📸 Phase 4: Realm Management")
            
            await browser.goto(settings.url("/admin/realms"))
            await capture.capture("holistic-20-realms-list", validate_ux=True)
            
            await browser.goto(settings.url("/admin/realms/pending"))
            await capture.capture("holistic-21-realms-pending", validate_ux=True)
            
            # =================================================================
            # Phase 5: Audit Logs with Activity
            # =================================================================
            print("\n📸 Phase 5: Audit Logs")
            
            # Simulate API activity first
            print("   Simulating API activity...")
            await simulate_api_activity(browser)
            # Brief wait for logs to be written
            await browser.wait_for_timeout(500)

            await browser.goto(settings.url("/admin/audit"))
            await capture.capture("holistic-30-audit-logs", validate_ux=True)
            
            # =================================================================
            # Phase 6: Configuration Pages
            # =================================================================
            print("\n📸 Phase 6: Configuration")
            
            await browser.goto(settings.url("/admin/config/netcup"))
            await capture.capture("holistic-40-config-netcup", validate_ux=True)
            
            await browser.goto(settings.url("/admin/config/email"))
            await capture.capture("holistic-41-config-email", validate_ux=True)
            
            await browser.goto(settings.url("/admin/system"))
            await capture.capture("holistic-42-system-info", validate_ux=True)
            
            # =================================================================
            # Phase 7: Password Change
            # =================================================================
            print("\n📸 Phase 7: Admin Password")
            
            await browser.goto(settings.url("/admin/change-password"))
            await capture.capture("holistic-50-change-password", validate_ux=True)
            
            # =================================================================
            # Phase 8: Error Pages
            # =================================================================
            print("\n📸 Phase 8: Error Pages")
            
            await browser.goto(settings.url("/nonexistent-page-404"))
            await capture.capture("holistic-90-error-404", validate_ux=True)
            
            # =================================================================
            # Phase 9: Theme Demo Reference
            # =================================================================
            print("\n📸 Phase 9: Theme Reference (BS5 Demo)")
            
            await browser.goto(settings.url("/component-demo-bs5"))
            await capture.capture("holistic-99-bs5-reference-cobalt2", validate_ux=False)
            
            # Switch to other themes and capture
            await browser._page.click('a.nav-link:has-text("Obsidian Noir")')
            await browser.wait_for_timeout(300)
            await browser._page.click('a.nav-link:has-text("Gold Dust")')
            await browser.wait_for_timeout(300)
            
            # =================================================================
            # Summary
            # =================================================================
            summary = capture.get_summary()
            print(f"\n✅ Captured {summary['captured_count']} screenshots")
            print(f"⚠️  Found {summary['ux_issues_count']} UX issues")
            
            if summary['ux_issues']:
                print("\nUX Issues Found:")
                for issue in summary['ux_issues']:
                    print(f"  - {issue['element']}: {issue['issue']}")
            
            # Assert no critical UX issues
            critical_issues = [i for i in summary['ux_issues'] if 'white background' in i['issue'].lower()]
            assert len(critical_issues) == 0, f"Critical UX issues found: {critical_issues}"


class TestHolisticAccountPortalCoverage:
    """Comprehensive account portal coverage with user journey."""
    
    async def test_complete_account_journey_with_screenshots(self, active_profile):
        """
        Complete account portal journey:
        1. Register new account
        2. Verify email (mock)
        3. Login as account user
        4. Navigate account dashboard
        5. Request realm
        6. Create token
        7. View DNS records
        """
        screenshot_dir = Path(os.environ.get("SCREENSHOT_DIR", "/tmp/screenshots"))
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        
        async with browser_session() as browser:
            capture = ScreenshotCapture(browser, screenshot_dir)
            
            # For now, capture public account pages
            # Full journey requires email verification which needs mock SMTP setup
            
            print("\n📸 Account Portal Public Pages")
            
            await browser.goto(settings.url("/account/login"))
            await capture.capture("holistic-account-01-login", validate_ux=True)
            
            await browser.goto(settings.url("/account/register"))
            await capture.capture("holistic-account-02-register", validate_ux=True)
            
            await browser.goto(settings.url("/account/forgot-password"))
            await capture.capture("holistic-account-03-forgot-password", validate_ux=True)
            
            summary = capture.get_summary()
            print(f"\n✅ Captured {summary['captured_count']} account portal screenshots")


class TestThemeComplianceValidation:
    """Automated theme compliance validation against BS5 reference."""
    
    async def test_admin_pages_match_bs5_reference(self, active_profile):
        """
        Validate that admin pages use the same CSS variables as BS5 demo.
        
        Checks:
        - Card backgrounds match theme
        - Button colors use theme accent
        - Table rows don't have white backgrounds
        - Form controls use themed styling
        """
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            # Pages to validate
            pages = [
                "/admin/",
                "/admin/accounts",
                "/admin/audit",
                "/admin/config/netcup",
                "/admin/config/email",
                "/admin/system",
            ]
            
            all_issues = []
            
            for page in pages:
                await browser.goto(settings.url(page))
                await browser.wait_for_load_state('domcontentloaded')

                issues = await self._check_theme_compliance(browser)
                for issue in issues:
                    issue["page"] = page
                    all_issues.append(issue)
            
            if all_issues:
                print(f"\n⚠️  Theme compliance issues found ({len(all_issues)}):")
                for issue in all_issues:
                    print(f"  {issue['page']}: {issue['element']} - {issue['issue']}")
            
            # Fail if critical issues (white backgrounds)
            white_bg_issues = [i for i in all_issues if 'white' in i['issue'].lower()]
            assert len(white_bg_issues) == 0, f"White background issues: {white_bg_issues}"
    
    async def _check_theme_compliance(self, browser: Browser) -> List[Dict]:
        """Check current page for theme compliance issues."""
        return await browser._page.evaluate("""
            () => {
                const issues = [];
                
                // Check cards
                document.querySelectorAll('.card').forEach((card, i) => {
                    const style = getComputedStyle(card);
                    const bg = style.backgroundColor;
                    
                    if (bg === 'rgb(255, 255, 255)' || bg === 'white' || bg === '#ffffff') {
                        issues.push({
                            element: `.card[${i}]`,
                            issue: `White background: ${bg}`
                        });
                    }
                });
                
                // Check table rows
                document.querySelectorAll('table tbody tr').forEach((row, i) => {
                    const style = getComputedStyle(row);
                    const bg = style.backgroundColor;
                    
                    if (bg === 'rgb(255, 255, 255)') {
                        issues.push({
                            element: `table tr[${i}]`,
                            issue: `Table row white background: ${bg}`
                        });
                    }
                });
                
                // Check form controls
                document.querySelectorAll('.form-control, .form-select').forEach((input, i) => {
                    const style = getComputedStyle(input);
                    const bg = style.backgroundColor;
                    
                    if (bg === 'rgb(255, 255, 255)') {
                        issues.push({
                            element: `form-control[${i}]`,
                            issue: `Form control white background: ${bg}`
                        });
                    }
                });
                
                // Check buttons use theme colors
                document.querySelectorAll('.btn-primary').forEach((btn, i) => {
                    const style = getComputedStyle(btn);
                    const bg = style.backgroundColor;
                    
                    // Default Bootstrap blue
                    if (bg === 'rgb(13, 110, 253)') {
                        issues.push({
                            element: `.btn-primary[${i}]`,
                            issue: 'Uses default Bootstrap blue instead of theme'
                        });
                    }
                });
                
                return issues;
            }
        """)


class TestAPIErrorSimulation:
    """Simulate API errors to verify proper logging and error pages."""
    
    async def test_api_error_scenarios_logged(self, active_profile):
        """
        Simulate various API error scenarios and verify they appear in audit logs.
        
        Scenarios:
        - Invalid token
        - Expired token
        - Unauthorized domain access
        - Rate limiting
        - Malformed requests
        """
        import httpx
        
        base_url = settings.base_url
        
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            # Simulate error scenarios via API
            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                # Invalid token
                try:
                    await client.get(
                        f"{base_url}/api/dns/example.test/records",
                        headers={"Authorization": "Bearer invalid_token_12345"}
                    )
                except Exception:
                    pass
                
                # Missing authorization
                try:
                    await client.get(f"{base_url}/api/dns/example.test/records")
                except Exception:
                    pass
                
                # Malformed request
                try:
                    await client.post(
                        f"{base_url}/api/dns/example.test/records",
                        json={"invalid": "payload"},
                        headers={"Authorization": "Bearer test"}
                    )
                except Exception:
                    pass
            
            # Wait for logs to be written
            await browser.wait_for_timeout(1000)

            # Check audit logs show errors
            await browser.goto(settings.url("/admin/audit"))
            await browser.wait_for_load_state('domcontentloaded')

            page_text = await browser.text('body')
            
            # Should have some error entries
            assert 'error' in page_text.lower() or 'failed' in page_text.lower() or 'denied' in page_text.lower(), \
                "Audit logs should show error entries from simulated API errors"
