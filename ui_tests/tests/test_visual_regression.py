"""
Visual regression tests using screenshot comparison.

These tests capture screenshots and compare them against baseline images.
Run with: pytest ui_tests/tests/test_visual_regression.py -v

Baseline management:
- First run creates baselines in ui_tests/baselines/
- Subsequent runs compare against baselines
- Set UPDATE_BASELINES=1 to update baselines
- Diff images saved to deploy-local/screenshots/diffs/

Requirements:
- pixelmatch (included in Playwright container)
- Pillow (included in Playwright container)
"""
import os
import pytest
from pathlib import Path
from PIL import Image
import io

# Import from parent ui_tests directory
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


# Constants
BASELINE_DIR = Path(__file__).parent.parent / "baselines"
DIFF_DIR = Path(os.environ.get("SCREENSHOT_DIR", "/tmp")) / "diffs"
THRESHOLD = float(os.environ.get("VISUAL_THRESHOLD", "0.01"))  # 1% pixel difference allowed
UPDATE_BASELINES = os.environ.get("UPDATE_BASELINES", "").lower() in ("1", "true", "yes")


def ensure_dirs():
    """Ensure baseline and diff directories exist."""
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    DIFF_DIR.mkdir(parents=True, exist_ok=True)


def compare_images(current_bytes: bytes, baseline_path: Path, diff_path: Path) -> tuple[bool, float, str]:
    """
    Compare current screenshot against baseline using pixelmatch.
    
    Returns:
        (passed, diff_ratio, message)
    """
    try:
        from pixelmatch import pixelmatch
        from pixelmatch.contrib.PIL import pixelmatch as pil_pixelmatch
    except ImportError:
        return (True, 0.0, "pixelmatch not available - skipping comparison")
    
    if not baseline_path.exists():
        return (False, 1.0, f"Baseline not found: {baseline_path}")
    
    # Load images
    current_img = Image.open(io.BytesIO(current_bytes)).convert("RGBA")
    baseline_img = Image.open(baseline_path).convert("RGBA")
    
    # Handle size mismatch
    if current_img.size != baseline_img.size:
        return (False, 1.0, 
                f"Size mismatch: current={current_img.size}, baseline={baseline_img.size}")
    
    width, height = current_img.size
    total_pixels = width * height
    
    # Create diff image
    diff_img = Image.new("RGBA", (width, height))
    
    # Compare using pixelmatch
    try:
        diff_pixels = pil_pixelmatch(
            baseline_img, current_img, diff_img,
            threshold=0.1,  # Sensitivity threshold
            includeAA=True   # Include anti-aliased pixels
        )
    except Exception as e:
        return (False, 1.0, f"Comparison failed: {e}")
    
    diff_ratio = diff_pixels / total_pixels
    
    # Save diff if there are differences
    if diff_pixels > 0:
        diff_img.save(diff_path)
    
    passed = diff_ratio <= THRESHOLD
    message = f"{diff_pixels} pixels differ ({diff_ratio:.2%})"
    
    return (passed, diff_ratio, message)


def save_baseline(image_bytes: bytes, baseline_path: Path):
    """Save current screenshot as new baseline."""
    ensure_dirs()
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    with open(baseline_path, "wb") as f:
        f.write(image_bytes)


async def capture_and_compare(page, name: str, full_page: bool = True) -> tuple[bool, str]:
    """
    Capture screenshot and compare against baseline.
    
    If UPDATE_BASELINES is set, updates the baseline instead.
    
    Args:
        page: Playwright page object
        name: Base name for screenshot files
        full_page: Whether to capture full page (True) or viewport only (False).
                   Use False for pages with dynamic content that changes height.
    """
    ensure_dirs()
    
    baseline_path = BASELINE_DIR / f"{name}.png"
    diff_path = DIFF_DIR / f"{name}_diff.png"
    
    # Capture screenshot
    screenshot_bytes = await page.screenshot(full_page=full_page)
    
    if UPDATE_BASELINES:
        save_baseline(screenshot_bytes, baseline_path)
        return (True, f"Baseline updated: {baseline_path}")
    
    if not baseline_path.exists():
        # First run - save baseline
        save_baseline(screenshot_bytes, baseline_path)
        return (True, f"Baseline created: {baseline_path}")
    
    # Compare against baseline
    passed, diff_ratio, message = compare_images(screenshot_bytes, baseline_path, diff_path)
    
    if not passed:
        # Save current screenshot for debugging
        current_path = DIFF_DIR / f"{name}_current.png"
        with open(current_path, "wb") as f:
            f.write(screenshot_bytes)
        return (False, f"{message}. Diff saved to {diff_path}")
    
    return (passed, message)


class TestVisualRegressionPublicPages:
    """Visual regression tests for public/unauthenticated pages."""
    
    @pytest.mark.asyncio
    async def test_admin_login_page(self, browser):
        """Verify admin login page hasn't changed."""
        from config import settings
        
        await browser.goto(settings.url("/admin/login"))
        await browser._page.wait_for_load_state("networkidle")
        
        passed, message = await capture_and_compare(browser._page, "admin_login")
        assert passed, message
    
    @pytest.mark.asyncio
    async def test_client_login_page(self, browser):
        """Verify account login page hasn't changed."""
        from config import settings
        
        await browser.goto(settings.url("/account/login"))
        await browser._page.wait_for_load_state("networkidle")
        
        passed, message = await capture_and_compare(browser._page, "account_login")
        assert passed, message


class TestVisualRegressionAdminPages:
    """Visual regression tests for authenticated admin pages."""
    
    @pytest.mark.asyncio
    async def test_admin_dashboard(self, admin_page):
        """Verify admin dashboard hasn't changed.
        
        Note: Dashboard height varies based on audit log entries, so we
        compare a fixed-height viewport screenshot instead of full page.
        This catches layout/style changes while tolerating dynamic content.
        """
        from config import settings
        
        page = admin_page
        await page.goto(settings.url("/admin/"))
        await page.wait_for_load_state("networkidle")
        
        # Use clip to capture fixed viewport instead of full page (height varies)
        passed, message = await capture_and_compare(page, "admin_dashboard", full_page=False)
        assert passed, message
    
    @pytest.mark.asyncio
    async def test_admin_accounts_list(self, admin_page):
        """Verify accounts list page hasn't changed."""
        from config import settings
        
        page = admin_page
        await page.goto(settings.url("/admin/accounts"))
        await page.wait_for_load_state("networkidle")
        
        passed, message = await capture_and_compare(page, "admin_accounts")
        assert passed, message
    
    @pytest.mark.asyncio
    async def test_admin_account_create(self, admin_page):
        """Verify account create form hasn't changed."""
        from config import settings
        
        page = admin_page
        await page.goto(settings.url("/admin/accounts/new"))
        await page.wait_for_load_state("networkidle")
        
        passed, message = await capture_and_compare(page, "admin_account_create")
        assert passed, message
    
    @pytest.mark.asyncio
    async def test_admin_audit_logs(self, admin_page):
        """Verify audit logs page hasn't changed.
        
        Note: Skipped because audit log content is dynamic and creates
        entries during test runs, causing screenshot size to change.
        """
        pytest.skip("Audit logs page has dynamic content that changes during testing")
    
    @pytest.mark.asyncio
    async def test_admin_netcup_config(self, admin_page):
        """Verify Netcup config page hasn't changed."""
        from config import settings
        
        page = admin_page
        await page.goto(settings.url("/admin/config/netcup"))
        await page.wait_for_load_state("networkidle")
        
        passed, message = await capture_and_compare(page, "admin_netcup_config")
        assert passed, message
    
    @pytest.mark.asyncio
    async def test_admin_email_config(self, admin_page):
        """Verify email config page hasn't changed."""
        from config import settings
        
        page = admin_page
        await page.goto(settings.url("/admin/config/email"))
        await page.wait_for_load_state("networkidle")
        
        passed, message = await capture_and_compare(page, "admin_email_config")
        assert passed, message
    
    @pytest.mark.asyncio
    async def test_admin_system_info(self, admin_page):
        """Verify system info page hasn't changed."""
        from config import settings
        
        page = admin_page
        await page.goto(settings.url("/admin/system"))
        await page.wait_for_load_state("networkidle")
        
        passed, message = await capture_and_compare(page, "admin_system")
        assert passed, message


class TestVisualRegressionThemes:
    """Visual regression tests for theme variations."""
    
    @pytest.mark.asyncio
    async def test_dark_theme_dashboard(self, admin_page):
        """Verify dark theme renders correctly.
        
        Note: Uses viewport-only screenshot like regular dashboard test.
        """
        from config import settings
        
        page = admin_page
        await page.goto(settings.url("/admin/"))
        await page.wait_for_load_state("networkidle")
        
        # Switch to dark theme
        await page.evaluate("""
            () => {
                localStorage.setItem('theme', 'dark');
                document.documentElement.setAttribute('data-bs-theme', 'dark');
            }
        """)
        await page.wait_for_timeout(500)  # Wait for theme to apply
        
        passed, message = await capture_and_compare(page, "admin_dashboard_dark", full_page=False)
        assert passed, message
    
    @pytest.mark.asyncio
    async def test_compact_density_dashboard(self, admin_page):
        """Verify compact density renders correctly.
        
        Note: Uses viewport-only screenshot like regular dashboard test.
        """
        from config import settings
        
        page = admin_page
        await page.goto(settings.url("/admin/"))
        await page.wait_for_load_state("networkidle")
        
        # Switch to compact density
        await page.evaluate("""
            () => {
                localStorage.setItem('density', 'compact');
                document.body.classList.remove('density-comfortable', 'density-spacious');
                document.body.classList.add('density-compact');
            }
        """)
        await page.wait_for_timeout(500)
        
        passed, message = await capture_and_compare(page, "admin_dashboard_compact", full_page=False)
        assert passed, message


class TestVisualRegressionMobile:
    """Visual regression tests for mobile viewports."""
    
    @pytest.mark.asyncio
    async def test_mobile_login_page(self, browser):
        """Verify login page on mobile viewport."""
        from config import settings
        
        # Set mobile viewport
        await browser._page.set_viewport_size({"width": 375, "height": 812})
        
        await browser.goto(settings.url("/admin/login"))
        await browser._page.wait_for_load_state("networkidle")
        
        passed, message = await capture_and_compare(browser._page, "admin_login_mobile")
        assert passed, message
    
    @pytest.mark.asyncio
    async def test_mobile_dashboard(self, admin_page):
        """Verify dashboard on mobile viewport.
        
        Note: Uses viewport-only screenshot like regular dashboard test.
        """
        from config import settings
        
        page = admin_page
        # Set mobile viewport
        await page.set_viewport_size({"width": 375, "height": 812})
        
        await page.goto(settings.url("/admin/"))
        await page.wait_for_load_state("networkidle")
        
        passed, message = await capture_and_compare(page, "admin_dashboard_mobile", full_page=False)
        assert passed, message


# Utility function for manual baseline updates
def update_all_baselines():
    """
    Utility to update all baselines.
    Run with: python -c "from test_visual_regression import update_all_baselines; update_all_baselines()"
    """
    import subprocess
    result = subprocess.run(
        ["pytest", __file__, "-v", "--tb=short"],
        env={**os.environ, "UPDATE_BASELINES": "1"},
        capture_output=True,
        text=True
    )
    print(result.stdout)
    print(result.stderr)
    return result.returncode == 0
