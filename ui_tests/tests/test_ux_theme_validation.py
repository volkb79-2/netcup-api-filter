"""
UX Theme Validation - Automatic detection of theme deviations from BS5 reference.

This module provides comprehensive validation that all application pages
follow the theme styling defined in /component-demo-bs5.

Usage:
    pytest ui_tests/tests/test_ux_theme_validation.py -v
    
Or run standalone:
    python -m ui_tests.tests.test_ux_theme_validation

┌─────────────────────────────────────────────────────────────────┐
│                UX Theme Validation Process                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. REFERENCE EXTRACTION                                         │
│     ┌──────────────────────────────────────────────┐            │
│     │  Navigate to /component-demo-bs5              │            │
│     │  Extract CSS variables via JavaScript:        │            │
│     │    - --bs-primary                             │            │
│     │    - --bs-body-bg                             │            │
│     │    - --bs-modal-bg                            │            │
│     │    - getComputedStyle() on cards, buttons    │            │
│     └──────────────────────────────────────────────┘            │
│                         ↓                                        │
│  2. PAGE VALIDATION                                              │
│     ┌──────────────────────────────────────────────┐            │
│     │  For each admin/public page:                  │            │
│     │    a) Navigate to page                        │            │
│     │    b) Extract computed CSS values             │            │
│     │    c) Compare against reference               │            │
│     │    d) Check for specific anti-patterns:       │            │
│     │       - White backgrounds (rgb(255,255,255)) │            │
│     │       - Bootstrap default blue (#0d6efd)     │            │
│     │       - Missing card shadows                  │            │
│     └──────────────────────────────────────────────┘            │
│                         ↓                                        │
│  3. ISSUE REPORTING                                              │
│     ┌──────────────────────────────────────────────┐            │
│     │  Each issue includes:                         │            │
│     │    - Page URL                                 │            │
│     │    - Element selector                         │            │
│     │    - Issue description                        │            │
│     │    - Expected vs Actual values                │            │
│     │    - Severity (warning/error/critical)        │            │
│     └──────────────────────────────────────────────┘            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  1. Extract Reference from /component-demo-bs5          │
│     - --bs-primary, --bs-body-bg, --bs-modal-bg        │
│     - getComputedStyle() on cards, buttons             │
├─────────────────────────────────────────────────────────┤
│  2. For each admin/public page:                         │
│     - Extract same CSS values via JavaScript            │
│     - Check for anti-patterns:                          │
│       · White backgrounds (rgb(255,255,255))           │
│       · Bootstrap default blue (#0d6efd)               │
│       · Missing card shadows                            │
├─────────────────────────────────────────────────────────┤
│  3. Report issues with:                                 │
│     - Page URL                                          │
│     - Element selector                                  │
│     - Expected vs Actual values                         │
│     - Severity (warning/error)                          │
└─────────────────────────────────────────────────────────┘

**What it detects:**
| Check | Detection Method | Example Issue |
|-------|------------------|---------------|
| White backgrounds | `getComputedStyle().backgroundColor === 'rgb(255,255,255)'` | Modal with white bg on dark theme |
| Bootstrap defaults | Compare button bg to `#0d6efd` | Unstyled button using BS5 default |
| Missing theme vars | Extract `--bs-primary` from `:root` | CSS variable not overridden |
| Card glow effects | Check `boxShadow !== 'none'` | Card missing shadow/glow |
| Navigation consistency | Count nav links across pages | Missing nav on some pages |


"""
import pytest
import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from pathlib import Path

from ui_tests.browser import browser_session, Browser
from ui_tests.config import settings
from ui_tests import workflows


pytestmark = pytest.mark.asyncio


# =============================================================================
# Theme Reference Data (extracted from /component-demo-bs5)
# =============================================================================

@dataclass
class ThemeReference:
    """CSS variable reference values for a theme."""
    name: str
    primary: str
    primary_rgb: str
    body_bg: str
    secondary_bg: str
    elevated_bg: str
    card_border: str
    accent_glow: str
    text_primary: str = "#f8fafc"
    text_secondary: str = "rgba(248, 250, 252, 0.7)"


THEMES = {
    "cobalt-2": ThemeReference(
        name="Cobalt 2",
        primary="#3b7cf5",
        primary_rgb="59, 124, 245",
        body_bg="#070a14",
        secondary_bg="#0c1020",
        elevated_bg="#141c30",
        card_border="rgba(100, 150, 255, 0.38)",
        accent_glow="rgba(59, 124, 245, 0.4)",
    ),
    "obsidian-noir": ThemeReference(
        name="Obsidian Noir",
        primary="#a78bfa",
        primary_rgb="167, 139, 250",
        body_bg="#08080d",
        secondary_bg="#0f0f16",
        elevated_bg="#16161f",
        card_border="rgba(167, 139, 250, 0.42)",
        accent_glow="rgba(167, 139, 250, 0.35)",
    ),
    "gold-dust": ThemeReference(
        name="Gold Dust",
        primary="#fbbf24",
        primary_rgb="251, 191, 36",
        body_bg="#0a0907",
        secondary_bg="#13110d",
        elevated_bg="#1b1814",
        card_border="rgba(251, 191, 36, 0.40)",
        accent_glow="rgba(251, 191, 36, 0.35)",
    ),
}


@dataclass 
class UXIssue:
    """Represents a UX validation issue."""
    page: str
    element: str
    issue: str
    severity: str = "warning"  # warning, error, critical
    expected: Optional[str] = None
    actual: Optional[str] = None


@dataclass
class UXValidationResult:
    """Result of UX validation across pages."""
    pages_checked: int = 0
    issues: List[UXIssue] = field(default_factory=list)
    
    @property
    def has_critical(self) -> bool:
        return any(i.severity == "critical" for i in self.issues)
    
    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)
    
    def add(self, issue: UXIssue):
        self.issues.append(issue)
    
    def summary(self) -> str:
        by_severity = {}
        for issue in self.issues:
            by_severity.setdefault(issue.severity, []).append(issue)
        
        lines = [f"Checked {self.pages_checked} pages, found {len(self.issues)} issues:"]
        for sev in ["critical", "error", "warning"]:
            if sev in by_severity:
                lines.append(f"  {sev.upper()}: {len(by_severity[sev])}")
        return "\n".join(lines)


# =============================================================================
# UX Validation Functions
# =============================================================================

async def extract_reference_from_bs5_demo(browser: Browser) -> Dict[str, str]:
    """
    Navigate to /component-demo-bs5 and extract CSS variable values.
    This establishes the "ground truth" for theme validation.
    """
    await browser.goto(settings.url("/component-demo-bs5"))
    await asyncio.sleep(0.5)
    
    reference = await browser._page.evaluate("""
        () => {
            const style = getComputedStyle(document.documentElement);
            return {
                // Core colors
                primary: style.getPropertyValue('--bs-primary').trim(),
                primaryRgb: style.getPropertyValue('--bs-primary-rgb').trim(),
                
                // Backgrounds
                bodyBg: style.getPropertyValue('--bs-body-bg').trim(),
                secondaryBg: style.getPropertyValue('--bs-secondary-bg').trim(),
                tertiaryBg: style.getPropertyValue('--bs-tertiary-bg').trim(),
                
                // Card styling
                cardBg: style.getPropertyValue('--bs-card-bg').trim(),
                cardBorder: style.getPropertyValue('--bs-card-border-color').trim(),
                
                // Text colors
                bodyColor: style.getPropertyValue('--bs-body-color').trim(),
                
                // Glow effects
                accentGlow: style.getPropertyValue('--accent-glow').trim(),
                
                // Computed styles from elements
                cardActualBg: '',
                buttonPrimaryBg: '',
                tableBg: '',
            };
        }
    """)
    
    # Also get computed styles from actual elements
    element_styles = await browser._page.evaluate("""
        () => {
            const result = {};
            
            // Get card background
            const card = document.querySelector('.card');
            if (card) {
                result.cardActualBg = getComputedStyle(card).backgroundColor;
            }
            
            // Get button primary
            const btn = document.querySelector('.btn-primary');
            if (btn) {
                result.buttonPrimaryBg = getComputedStyle(btn).backgroundColor;
            }
            
            // Get table background
            const table = document.querySelector('table');
            if (table) {
                result.tableBg = getComputedStyle(table).backgroundColor;
            }
            
            return result;
        }
    """)
    
    reference.update(element_styles)
    return reference


async def validate_page_against_reference(
    browser: Browser, 
    page_url: str, 
    reference: Dict[str, str]
) -> List[UXIssue]:
    """
    Validate a page's CSS against the BS5 reference.
    Returns list of issues found.
    """
    issues = []
    page_path = page_url.replace(settings.base_url, "")
    
    # Extract current page CSS values
    page_css = await browser._page.evaluate("""
        () => {
            const style = getComputedStyle(document.documentElement);
            return {
                primary: style.getPropertyValue('--bs-primary').trim(),
                bodyBg: style.getPropertyValue('--bs-body-bg').trim(),
                cardBg: style.getPropertyValue('--bs-card-bg').trim(),
            };
        }
    """)
    
    # Check for CSS variable mismatches
    if reference.get("primary") and page_css["primary"] != reference["primary"]:
        issues.append(UXIssue(
            page=page_path,
            element="html",
            issue="Primary color mismatch",
            severity="warning",
            expected=reference["primary"],
            actual=page_css["primary"],
        ))
    
    # Check for white backgrounds on dark theme elements
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
                        actual: bg,
                    });
                }
            });
            
            // Check table cells
            document.querySelectorAll('table td, table th').forEach((el, i) => {
                const bg = getComputedStyle(el).backgroundColor;
                if (isWhite(bg)) {
                    issues.push({
                        element: `table cell[${i}]`,
                        issue: 'Table cell has white background',
                        actual: bg,
                    });
                }
            });
            
            // Check form controls
            document.querySelectorAll('.form-control, .form-select').forEach((el, i) => {
                const bg = getComputedStyle(el).backgroundColor;
                // Form controls on dark theme should not be pure white
                if (isWhite(bg)) {
                    issues.push({
                        element: `form-control[${i}]`,
                        issue: 'Form control has white background',
                        actual: bg,
                    });
                }
            });
            
            // Check modals
            document.querySelectorAll('.modal-content').forEach((el, i) => {
                const bg = getComputedStyle(el).backgroundColor;
                if (isWhite(bg)) {
                    issues.push({
                        element: `.modal-content[${i}]`,
                        issue: 'Modal has white background',
                        actual: bg,
                    });
                }
            });
            
            return issues;
        }
    """)
    
    for issue_data in white_bg_issues:
        issues.append(UXIssue(
            page=page_path,
            element=issue_data["element"],
            issue=issue_data["issue"],
            severity="error",  # White backgrounds are errors on dark theme
            actual=issue_data.get("actual"),
        ))
    
    # Check button styling
    btn_issues = await browser._page.evaluate("""
        () => {
            const issues = [];
            const BOOTSTRAP_DEFAULT_BLUE = 'rgb(13, 110, 253)';
            
            document.querySelectorAll('.btn-primary').forEach((el, i) => {
                const bg = getComputedStyle(el).backgroundColor;
                if (bg === BOOTSTRAP_DEFAULT_BLUE) {
                    issues.push({
                        element: `.btn-primary[${i}]`,
                        issue: 'Button uses Bootstrap default instead of theme color',
                        actual: bg,
                    });
                }
            });
            
            return issues;
        }
    """)
    
    for issue_data in btn_issues:
        issues.append(UXIssue(
            page=page_path,
            element=issue_data["element"],
            issue=issue_data["issue"],
            severity="warning",
            actual=issue_data.get("actual"),
        ))
    
    # Check for glow effects on cards
    glow_issues = await browser._page.evaluate("""
        () => {
            const issues = [];
            
            // Cards should have box-shadow for glow effect
            document.querySelectorAll('.card').forEach((el, i) => {
                const shadow = getComputedStyle(el).boxShadow;
                if (shadow === 'none' || shadow === '') {
                    issues.push({
                        element: `.card[${i}]`,
                        issue: 'Card missing glow/shadow effect',
                        actual: shadow,
                    });
                }
            });
            
            return issues;
        }
    """)
    
    for issue_data in glow_issues:
        issues.append(UXIssue(
            page=page_path,
            element=issue_data["element"],
            issue=issue_data["issue"],
            severity="warning",
            actual=issue_data.get("actual"),
        ))
    
    return issues


# =============================================================================
# Test Cases
# =============================================================================

class TestThemeDeviation:
    """Tests that detect theme deviations from BS5 reference."""
    
    # Pages that can be tested without test data (forms, static content)
    ADMIN_PAGES = [
        "/admin/",
        "/admin/accounts",
        "/admin/accounts/new",
        "/admin/accounts/pending",
        "/admin/realms",
        "/admin/realms/pending",
        "/admin/audit",
        "/admin/config/netcup",
        "/admin/config/email",
        "/admin/system",
        "/admin/change-password",
    ]
    
    # Pages requiring test data to exist - tested separately with seeded data
    ADMIN_DETAIL_PAGES = [
        # These require seeded accounts/realms/tokens
        # "/admin/accounts/<id>",
        # "/admin/accounts/<id>/realms/new",
        # "/admin/realms/<id>",
        # "/admin/tokens/<id>",
    ]
    
    ACCOUNT_PAGES = [
        "/account/login",
        "/account/register",
        "/account/forgot-password",
    ]
    
    # Account pages requiring authenticated session with seeded data
    ACCOUNT_DETAIL_PAGES = [
        # These require authenticated account session
        # "/account/dashboard",
        # "/account/realms",
        # "/account/realms/request",
        # "/account/tokens",
        # "/account/tokens/new",
        # "/account/tokens/<id>/activity",
        # "/account/settings",
    ]
    
    async def test_extract_bs5_reference(self, active_profile):
        """Verify we can extract reference CSS from BS5 demo page."""
        async with browser_session() as browser:
            reference = await extract_reference_from_bs5_demo(browser)
            
            # Basic sanity checks
            assert reference.get("primary"), "Should extract primary color"
            assert reference.get("bodyBg"), "Should extract body background"
            
            print(f"\nExtracted BS5 Reference:")
            for key, value in reference.items():
                if value:
                    print(f"  {key}: {value}")
    
    async def test_admin_pages_match_bs5_reference(self, active_profile):
        """
        Validate all admin pages match BS5 reference styling.
        
        This is the main automated UX deviation detection test.
        """
        async with browser_session() as browser:
            # First, get reference from BS5 demo
            reference = await extract_reference_from_bs5_demo(browser)
            
            # Login as admin
            await workflows.ensure_admin_dashboard(browser)
            
            # Validate each admin page
            result = UXValidationResult()
            
            for page in self.ADMIN_PAGES:
                await browser.goto(settings.url(page))
                await asyncio.sleep(0.3)
                
                issues = await validate_page_against_reference(
                    browser, 
                    settings.url(page), 
                    reference
                )
                
                for issue in issues:
                    result.add(issue)
                
                result.pages_checked += 1
            
            # Report results
            print(f"\n{result.summary()}")
            
            if result.issues:
                print("\nDetailed Issues:")
                for issue in result.issues:
                    print(f"  [{issue.severity.upper()}] {issue.page}")
                    print(f"    {issue.element}: {issue.issue}")
                    if issue.expected:
                        print(f"    Expected: {issue.expected}")
                    if issue.actual:
                        print(f"    Actual: {issue.actual}")
            
            # Fail on errors (white backgrounds are errors)
            assert not result.has_errors, f"Theme deviation errors found:\n{result.summary()}"
    
    async def test_public_pages_match_bs5_reference(self, active_profile):
        """Validate public pages match BS5 reference styling."""
        async with browser_session() as browser:
            reference = await extract_reference_from_bs5_demo(browser)
            
            result = UXValidationResult()
            
            for page in self.ACCOUNT_PAGES:
                await browser.goto(settings.url(page))
                await asyncio.sleep(0.3)
                
                issues = await validate_page_against_reference(
                    browser,
                    settings.url(page),
                    reference
                )
                
                for issue in issues:
                    result.add(issue)
                
                result.pages_checked += 1
            
            print(f"\n{result.summary()}")
            assert not result.has_errors, f"Theme deviation errors found"
    
    async def test_card_glow_consistency(self, active_profile):
        """Verify all cards have consistent glow effects matching BS5 demo."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            pages_with_issues = []
            
            for page in self.ADMIN_PAGES:
                await browser.goto(settings.url(page))
                await asyncio.sleep(0.3)
                
                # Check card shadows
                card_shadows = await browser._page.evaluate("""
                    () => {
                        return Array.from(document.querySelectorAll('.card'))
                            .map(card => ({
                                shadow: getComputedStyle(card).boxShadow,
                                hasShadow: getComputedStyle(card).boxShadow !== 'none'
                            }));
                    }
                """)
                
                cards_without_shadow = [c for c in card_shadows if not c["hasShadow"]]
                if cards_without_shadow:
                    pages_with_issues.append({
                        "page": page,
                        "cards_missing_shadow": len(cards_without_shadow),
                        "total_cards": len(card_shadows),
                    })
            
            if pages_with_issues:
                print("\nPages with cards missing glow effect:")
                for issue in pages_with_issues:
                    print(f"  {issue['page']}: {issue['cards_missing_shadow']}/{issue['total_cards']} cards")
    
    async def test_navigation_consistency(self, active_profile):
        """Verify navigation elements are consistent across all pages."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            nav_structures = {}
            
            for page in self.ADMIN_PAGES:
                await browser.goto(settings.url(page))
                await asyncio.sleep(0.3)
                
                nav_info = await browser._page.evaluate("""
                    () => {
                        const nav = document.querySelector('nav, .navbar');
                        const links = nav ? Array.from(nav.querySelectorAll('a')).map(a => a.textContent.trim()) : [];
                        return {
                            hasNav: !!nav,
                            linkCount: links.length,
                            links: links,
                        };
                    }
                """)
                
                nav_structures[page] = nav_info
            
            # All pages should have navigation
            pages_without_nav = [p for p, info in nav_structures.items() if not info["hasNav"]]
            assert not pages_without_nav, f"Pages without navigation: {pages_without_nav}"
            
            # Navigation should be consistent
            link_counts = set(info["linkCount"] for info in nav_structures.values())
            if len(link_counts) > 1:
                print("\n⚠️  Navigation link count varies across pages:")
                for page, info in nav_structures.items():
                    print(f"  {page}: {info['linkCount']} links")


class TestResponsiveValidation:
    """Tests for responsive design compliance."""
    
    VIEWPORTS = [
        {"name": "mobile", "width": 375, "height": 667},
        {"name": "tablet", "width": 768, "height": 1024},
        {"name": "desktop", "width": 1920, "height": 1080},
    ]
    
    async def test_admin_dashboard_responsive(self, active_profile):
        """Verify admin dashboard works at different viewport sizes."""
        async with browser_session() as browser:
            await workflows.ensure_admin_dashboard(browser)
            
            for viewport in self.VIEWPORTS:
                await browser._page.set_viewport_size({
                    "width": viewport["width"],
                    "height": viewport["height"],
                })
                
                await browser.goto(settings.url("/admin/"))
                await asyncio.sleep(0.3)
                
                # Check that main content is visible
                is_visible = await browser._page.evaluate("""
                    () => {
                        const main = document.querySelector('main, .container, .content');
                        if (!main) return false;
                        const rect = main.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    }
                """)
                
                assert is_visible, f"Main content not visible at {viewport['name']} ({viewport['width']}x{viewport['height']})"
            
            # Reset to desktop
            await browser._page.set_viewport_size({"width": 1920, "height": 1080})


# =============================================================================
# Standalone Runner
# =============================================================================

if __name__ == "__main__":
    import sys
    
    async def main():
        print("UX Theme Validation - Standalone Mode")
        print("=" * 50)
        
        async with browser_session() as browser:
            # Extract reference
            print("\n1. Extracting BS5 Reference...")
            reference = await extract_reference_from_bs5_demo(browser)
            print(f"   Primary: {reference.get('primary')}")
            print(f"   Body BG: {reference.get('bodyBg')}")
            
            # Login as admin
            print("\n2. Logging in as admin...")
            await workflows.ensure_admin_dashboard(browser)
            
            # Validate pages
            print("\n3. Validating admin pages...")
            pages = TestThemeDeviation.ADMIN_PAGES
            result = UXValidationResult()
            
            for page in pages:
                await browser.goto(settings.url(page))
                await asyncio.sleep(0.3)
                
                issues = await validate_page_against_reference(
                    browser,
                    settings.url(page),
                    reference
                )
                
                for issue in issues:
                    result.add(issue)
                result.pages_checked += 1
                
                status = "✅" if not issues else f"⚠️ {len(issues)} issues"
                print(f"   {page}: {status}")
            
            # Summary
            print(f"\n{result.summary()}")
            
            return 0 if not result.has_errors else 1
    
    sys.exit(asyncio.run(main()))
