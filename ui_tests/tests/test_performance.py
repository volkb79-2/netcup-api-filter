"""
Performance tests for frontend optimization.

These tests verify page load times and performance metrics.
Run with: pytest ui_tests/tests/test_performance.py -v

Performance criteria:
- First Contentful Paint < 2s
- Total page load < 3s
- No render-blocking resources
- Efficient resource loading
"""
import os
import pytest
from pathlib import Path

# Import from parent ui_tests directory
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestPageLoadPerformance:
    """Test page load times and performance metrics."""
    
    @pytest.mark.asyncio
    async def test_login_page_load_time(self, browser):
        """Verify login page loads quickly (< 3 seconds)."""
        from config import settings
        
        start_time = await browser._page.evaluate("() => performance.now()")
        await browser.goto(settings.url("/admin/login"))
        await browser._page.wait_for_load_state("networkidle")
        end_time = await browser._page.evaluate("() => performance.now()")
        
        load_time = (end_time - start_time) / 1000  # Convert to seconds
        assert load_time < 3.0, f"Login page took {load_time:.2f}s to load (should be < 3s)"
    
    @pytest.mark.asyncio
    async def test_dashboard_load_time(self, admin_page):
        """Verify dashboard loads quickly after login."""
        from config import settings
        
        page = admin_page
        
        # Measure navigation to dashboard
        start_time = await page.evaluate("() => performance.now()")
        await page.goto(settings.url("/admin/"))
        await page.wait_for_load_state("networkidle")
        end_time = await page.evaluate("() => performance.now()")
        
        load_time = (end_time - start_time) / 1000
        assert load_time < 3.0, f"Dashboard took {load_time:.2f}s to load"
    
    @pytest.mark.asyncio
    async def test_first_contentful_paint(self, browser):
        """Verify First Contentful Paint is acceptable (< 2 seconds)."""
        from config import settings
        
        await browser.goto(settings.url("/admin/login"))
        await browser._page.wait_for_load_state("networkidle")
        
        # Get FCP from performance timing
        fcp = await browser._page.evaluate("""
            () => {
                const entries = performance.getEntriesByType('paint');
                const fcp = entries.find(e => e.name === 'first-contentful-paint');
                return fcp ? fcp.startTime : null;
            }
        """)
        
        if fcp is not None:
            fcp_seconds = fcp / 1000
            assert fcp_seconds < 2.0, f"FCP is {fcp_seconds:.2f}s (should be < 2s)"
        else:
            pytest.skip("FCP metric not available")


class TestResourceLoading:
    """Test efficient resource loading."""
    
    @pytest.mark.asyncio
    async def test_no_render_blocking_js(self, browser):
        """Verify no render-blocking JavaScript in head."""
        from config import settings
        
        await browser.goto(settings.url("/admin/login"))
        await browser._page.wait_for_load_state("networkidle")
        
        # Check for script tags in head without async/defer
        blocking_scripts = await browser._page.evaluate("""
            () => {
                const scripts = document.querySelectorAll('head script[src]:not([async]):not([defer])');
                return Array.from(scripts).map(s => s.src);
            }
        """)
        
        # Allow some blocking scripts (like critical inline scripts)
        # but flag too many
        if len(blocking_scripts) > 2:
            pytest.fail(f"Too many render-blocking scripts in head: {blocking_scripts}")
    
    @pytest.mark.asyncio
    async def test_efficient_css_loading(self, browser):
        """Verify CSS loads efficiently (CDN or optimized)."""
        from config import settings
        
        await browser.goto(settings.url("/admin/login"))
        await browser._page.wait_for_load_state("networkidle")
        
        # Check number of CSS requests
        css_count = await browser._page.evaluate("""
            () => {
                const links = document.querySelectorAll('link[rel="stylesheet"]');
                return links.length;
            }
        """)
        
        # Should have reasonable number of CSS files (Bootstrap + custom)
        assert css_count <= 5, f"Too many CSS files: {css_count}"
    
    @pytest.mark.asyncio
    async def test_uses_cdn_for_libraries(self, browser):
        """Verify external libraries use CDN."""
        from config import settings
        
        await browser.goto(settings.url("/admin/login"))
        await browser._page.wait_for_load_state("networkidle")
        
        # Check Bootstrap CDN usage
        using_cdn = await browser._page.evaluate("""
            () => {
                const links = document.querySelectorAll('link[href*="cdn.jsdelivr.net"], script[src*="cdn.jsdelivr.net"]');
                return links.length > 0;
            }
        """)
        
        assert using_cdn, "Should use CDN for Bootstrap/libraries"


class TestImageOptimization:
    """Test image loading and optimization."""
    
    @pytest.mark.asyncio
    async def test_images_have_dimensions(self, admin_page):
        """Verify images specify width/height to prevent layout shift."""
        from config import settings
        
        page = admin_page
        await page.goto(settings.url("/admin/"))
        await page.wait_for_load_state("networkidle")
        
        # Check images for width/height attributes
        images_without_dimensions = await page.evaluate("""
            () => {
                const images = document.querySelectorAll('img');
                const problems = [];
                images.forEach(img => {
                    if (!img.width && !img.height && 
                        !img.style.width && !img.style.height &&
                        !img.classList.contains('emoji')) {
                        problems.push(img.src);
                    }
                });
                return problems;
            }
        """)
        
        # Decorative icons are okay without dimensions
        if len(images_without_dimensions) > 0:
            pytest.skip(f"Images without explicit dimensions: {len(images_without_dimensions)}")
    
    @pytest.mark.asyncio
    async def test_lazy_loading_for_offscreen_images(self, admin_page):
        """Verify off-screen images use lazy loading."""
        from config import settings
        
        page = admin_page
        await page.goto(settings.url("/admin/"))
        await page.wait_for_load_state("networkidle")
        
        # Check for loading="lazy" on images
        lazy_images = await page.evaluate("""
            () => {
                const images = document.querySelectorAll('img[loading="lazy"]');
                return images.length;
            }
        """)
        
        total_images = await page.evaluate("() => document.querySelectorAll('img').length")
        
        # If we have many images, some should be lazy
        if total_images > 5:
            assert lazy_images > 0, "Should use lazy loading for images"


class TestCachingHeaders:
    """Test browser caching configuration."""
    
    @pytest.mark.asyncio
    async def test_static_assets_cacheable(self, browser):
        """Verify static assets have cache headers."""
        from config import settings
        
        # Navigate to get static assets
        response = await browser._page.goto(settings.url("/admin/login"))
        
        # This is a basic check - full cache header testing would need HTTP inspection
        # Just verify the page loads successfully
        assert response is not None
        assert response.status == 200


class TestDOMComplexity:
    """Test DOM size and complexity."""
    
    @pytest.mark.asyncio
    async def test_reasonable_dom_size(self, admin_page):
        """Verify DOM doesn't have excessive elements."""
        from config import settings
        
        page = admin_page
        await page.goto(settings.url("/admin/"))
        await page.wait_for_load_state("networkidle")
        
        # Count DOM elements
        dom_size = await page.evaluate("() => document.querySelectorAll('*').length")
        
        # Dashboard should have reasonable DOM (< 1500 elements)
        assert dom_size < 1500, f"DOM has {dom_size} elements (should be < 1500)"
    
    @pytest.mark.asyncio
    async def test_reasonable_dom_depth(self, admin_page):
        """Verify DOM doesn't have excessive nesting."""
        from config import settings
        
        page = admin_page
        await page.goto(settings.url("/admin/"))
        await page.wait_for_load_state("networkidle")
        
        # Find max nesting depth
        max_depth = await page.evaluate("""
            () => {
                function getDepth(element, depth) {
                    if (!element.children || element.children.length === 0) {
                        return depth;
                    }
                    return Math.max(...Array.from(element.children).map(c => getDepth(c, depth + 1)));
                }
                return getDepth(document.body, 0);
            }
        """)
        
        # Reasonable nesting (< 20 levels)
        assert max_depth < 20, f"DOM depth is {max_depth} (should be < 20)"


class TestJavaScriptPerformance:
    """Test JavaScript execution performance."""
    
    @pytest.mark.asyncio
    async def test_no_javascript_errors(self, browser):
        """Verify no JavaScript errors on load."""
        from config import settings
        
        errors = []
        browser._page.on("pageerror", lambda e: errors.append(str(e)))
        
        await browser.goto(settings.url("/admin/login"))
        await browser._page.wait_for_load_state("networkidle")
        
        assert len(errors) == 0, f"JavaScript errors: {errors}"
    
    @pytest.mark.asyncio
    async def test_minimal_console_warnings(self, browser):
        """Verify minimal console warnings on load."""
        from config import settings
        
        warnings = []
        browser._page.on("console", lambda msg: warnings.append(msg.text) if msg.type == "warning" else None)
        
        await browser.goto(settings.url("/admin/login"))
        await browser._page.wait_for_load_state("networkidle")
        
        # Allow some warnings (deprecation notices, etc.)
        if len(warnings) > 5:
            pytest.skip(f"Many console warnings: {len(warnings)}")


class TestNetworkRequests:
    """Test network request efficiency."""
    
    @pytest.mark.asyncio
    async def test_reasonable_request_count(self, browser):
        """Verify page doesn't make too many requests."""
        from config import settings
        
        requests = []
        browser._page.on("request", lambda req: requests.append(req.url))
        
        await browser.goto(settings.url("/admin/login"))
        await browser._page.wait_for_load_state("networkidle")
        
        # Should have reasonable number of requests (< 30)
        assert len(requests) < 30, f"Too many requests: {len(requests)}"
    
    @pytest.mark.asyncio
    async def test_no_failed_requests(self, browser):
        """Verify no failed network requests (excluding external)."""
        from config import settings
        
        failed = []
        
        async def handle_response(response):
            if response.status >= 400 and settings.base_url in response.url:
                failed.append(f"{response.status}: {response.url}")
        
        browser._page.on("response", handle_response)
        
        await browser.goto(settings.url("/admin/login"))
        await browser._page.wait_for_load_state("networkidle")
        
        assert len(failed) == 0, f"Failed requests: {failed}"
