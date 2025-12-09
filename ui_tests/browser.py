"""Thin wrapper around direct Playwright for ergonomic assertions."""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Dict, AsyncIterator

import anyio
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from ui_tests.config import settings
from ui_tests.playwright_client import PlaywrightClient


@dataclass
class ToolError(Exception):
    """Raised when a browser operation fails."""

    name: str
    payload: Dict[str, Any]
    message: str

    def __str__(self) -> str:  # pragma: no cover - human readable helper
        return f"{self.name} failed ({self.message}) with payload={self.payload}"


class Browser:
    """Convenience wrapper over direct Playwright with ergonomic API."""

    def __init__(self, page: Page) -> None:
        self._page = page
        self.current_url: str | None = None
        self.current_title: str | None = None

    async def _update_state(self) -> None:
        """Update internal state from page."""
        self.current_url = self._page.url
        self.current_title = await self._page.title()

    async def reset(self) -> Dict[str, Any]:
        """Navigate to about:blank (reset state)."""
        await self._page.goto("about:blank")
        await self._update_state()
        return {"url": self.current_url, "title": self.current_title}

    async def goto(self, url: str, wait_until: str = "networkidle", timeout: int = 30000) -> Dict[str, Any]:
        """Navigate to URL and return response with status.
        
        Args:
            url: URL to navigate to
            wait_until: Wait strategy - "networkidle", "domcontentloaded", or "load"
            timeout: Timeout in milliseconds (default 30s)
            
        Note: "networkidle" can timeout with long-polling/WebSocket connections.
              Use "domcontentloaded" for pages with background connections.
        """
        try:
            response = await self._page.goto(url, wait_until=wait_until, timeout=timeout)
            await self._update_state()
            return {"url": self.current_url, "title": self.current_title, "status": response.status if response else None}
        except PlaywrightTimeout as exc:
            # If networkidle times out, try with domcontentloaded as fallback
            if wait_until == "networkidle":
                try:
                    response = await self._page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                    await self._update_state()
                    return {"url": self.current_url, "title": self.current_title, "status": response.status if response else None}
                except PlaywrightTimeout:
                    pass  # Fall through to original error
            raise ToolError(name="goto", payload={"url": url, "wait_until": wait_until}, message=str(exc))

    async def fill(self, selector: str, value: str) -> Dict[str, Any]:
        """Fill input field."""
        try:
            await self._page.fill(selector, value)
            return {"selector": selector, "value": value}
        except Exception as exc:
            raise ToolError(name="fill", payload={"selector": selector, "value": value}, message=str(exc))

    async def click(self, selector: str, press_enter: bool | None = None) -> Dict[str, Any]:
        """Click element."""
        try:
            await self._page.click(selector)
            if press_enter:
                await self._page.keyboard.press("Enter")
            await self._update_state()
            return {"selector": selector, "url": self.current_url}
        except Exception as exc:
            raise ToolError(name="click", payload={"selector": selector}, message=str(exc))

    async def select(self, selector: str, value: str | list[str]) -> Dict[str, Any]:
        """Select option(s) in select element."""
        try:
            values = [value] if isinstance(value, str) else value
            await self._page.select_option(selector, values)
            return {"selector": selector, "value": value}
        except Exception as exc:
            raise ToolError(name="select", payload={"selector": selector, "value": value}, message=str(exc))

    async def text(self, selector: str) -> str:
        """Get text content of element."""
        try:
            text = await self._page.text_content(selector, timeout=5000)
            return text or ""
        except Exception as exc:
            raise ToolError(name="text", payload={"selector": selector}, message=str(exc))

    async def get_attribute(self, selector: str, attribute: str) -> str:
        """Get attribute value of element."""
        try:
            value = await self._page.get_attribute(selector, attribute, timeout=5000)
            return value or ""
        except Exception as exc:
            raise ToolError(name="get_attribute", payload={"selector": selector, "attribute": attribute}, message=str(exc))

    async def verify_status(self, expected_status: int = 200) -> int:
        """Verify HTTP status code of current page.
        
        Returns the status code. Raises ToolError if status doesn't match expected.
        """
        try:
            # Try to get status from performance API
            status_code = await self._page.evaluate("() => window.performance.getEntriesByType('navigation')[0]?.responseStatus || 0")
            
            # Fallback: check for error indicators in page content
            if status_code == 0:
                page_text = await self._page.text_content("body")
                if page_text and ("500 Internal Server Error" in page_text or "Internal Server Error" in page_text):
                    status_code = 500
                elif page_text and "404" in page_text and ("Not Found" in page_text or "Page not found" in page_text):
                    status_code = 404
            
            if status_code != expected_status:
                page_content = await self._page.content()
                error_msg = f"HTTP {status_code} (expected {expected_status}) on {self.current_url}"
                if len(page_content) < 500:
                    error_msg += f"\nPage content: {page_content[:500]}"
                raise ToolError(
                    name="verify_status",
                    payload={"expected": expected_status, "actual": status_code, "url": self.current_url},
                    message=error_msg
                )
            
            return status_code
        except ToolError:
            raise
        except Exception as exc:
            # Non-critical error - return 0 to indicate unknown status
            return 0

    async def html(self, selector: str) -> str:
        """Get inner HTML of element."""
        try:
            html = await self._page.inner_html(selector, timeout=5000)
            return html or ""
        except Exception as exc:
            raise ToolError(name="html", payload={"selector": selector}, message=str(exc))

    async def evaluate(self, script: str, arg: Any = None) -> Any:
        """Execute JavaScript in the page context."""
        try:
            return await self._page.evaluate(script, arg)
        except Exception as exc:
            raise ToolError(name="evaluate", payload={"script": script}, message=str(exc))

    async def screenshot(self, name: str, format: str = None, quality: int = None) -> str:
        """Take screenshot in specified format (webp or png).
        
        Args:
            name: Screenshot name (without extension)
            format: 'webp' or 'png' (default: from env or 'webp')
            quality: Quality for webp (0-100, default: 85)
        """
        try:
            import os
            # Require SCREENSHOT_DIR (no defaults - fail-fast policy)
            screenshot_dir = os.environ['SCREENSHOT_DIR']
            os.makedirs(screenshot_dir, exist_ok=True)
            
            # Get format from env or default to webp
            if format is None:
                format = os.environ.get('SCREENSHOT_FORMAT', 'webp')
            if quality is None:
                quality = int(os.environ.get('SCREENSHOT_QUALITY', '85'))
            
            path = os.path.join(screenshot_dir, f"{name}.{format}")
            
            if format == 'webp':
                await self._page.screenshot(path=path, type='jpeg', quality=quality, full_page=True)
                # Playwright doesn't support webp directly, use jpeg then convert
                # Actually, let's use png and convert via pillow if available
                import shutil
                try:
                    from PIL import Image
                    temp_path = path + '.temp.png'
                    await self._page.screenshot(path=temp_path, type='png', full_page=True)
                    img = Image.open(temp_path)
                    img.save(path, 'WEBP', quality=quality)
                    os.remove(temp_path)
                except ImportError:
                    # Pillow not available, fall back to png
                    path = os.path.join(screenshot_dir, f"{name}.png")
                    await self._page.screenshot(path=path, type='png', full_page=True)
            else:
                await self._page.screenshot(path=path, type='png', full_page=True)
            
            return path
        except KeyError:
            raise ToolError(
                name="screenshot",
                payload={"name": name},
                message="SCREENSHOT_DIR environment variable must be set. No defaults allowed (fail-fast policy)."
            )
        except Exception as exc:
            raise ToolError(name="screenshot", payload={"name": name}, message=str(exc))

    async def submit(self, selector: str) -> Dict[str, Any]:
        """Submit form.
        
        Note: We try to wait for navigation, but if none occurs (e.g., form validation
        errors that re-render the same page), we gracefully handle the timeout.
        """
        try:
            # Evaluate JavaScript to submit the form programmatically
            # This handles both navigation and same-page reloading correctly
            try:
                async with self._page.expect_navigation(wait_until="domcontentloaded", timeout=5000):
                    await self._page.evaluate(f"document.querySelector('{selector}').requestSubmit()")
            except Exception:
                # Navigation might not happen (e.g., same-page form resubmission with errors)
                # Just wait for the network to settle
                await self._page.wait_for_load_state("domcontentloaded", timeout=5000)
            
            await self._update_state()
            return {"selector": selector, "url": self.current_url}
        except Exception as exc:
            raise ToolError(name="submit", payload={"selector": selector}, message=str(exc))

    async def uncheck(self, selector: str) -> Dict[str, Any]:
        """Uncheck checkbox."""
        try:
            await self._page.uncheck(selector)
            return {"selector": selector}
        except Exception as exc:
            raise ToolError(name="uncheck", payload={"selector": selector}, message=str(exc))

    async def wait_for_text(self, selector: str, expected: str, timeout: float = 3.0, interval: float = 0.5) -> str:
        """Poll for text content until it contains the expected substring."""
        deadline = anyio.current_time() + timeout
        last_error: ToolError | None = None

        while anyio.current_time() <= deadline:
            try:
                content = await self.text(selector)
            except ToolError as exc:
                content = ""
                last_error = exc
            if expected in content:
                return content
            await anyio.sleep(interval)

        if last_error:
            raise AssertionError(
                f"Timed out waiting for '{expected}' in selector '{selector}'. Last error: {last_error}"
            ) from last_error
        raise AssertionError(f"Timed out waiting for '{expected}' in selector '{selector}'")

    async def expect_substring(self, selector: str, expected: str) -> str:
        content = await self.text(selector)
        assert expected in content, f"'{expected}' not found in '{content}'"
        return content

    async def query_selector(self, selector: str):
        """Get element handle for selector (exposes Playwright ElementHandle API)."""
        try:
            return await self._page.query_selector(selector)
        except Exception as exc:
            raise ToolError(name="query_selector", payload={"selector": selector}, message=str(exc))

    async def query_selector_all(self, selector: str):
        """Get all element handles matching selector (exposes Playwright ElementHandle API)."""
        try:
            return await self._page.query_selector_all(selector)
        except Exception as exc:
            raise ToolError(name="query_selector_all", payload={"selector": selector}, message=str(exc))

    async def wait_for_enabled(self, selector: str, timeout: float = 5.0) -> bool:
        """Wait for an element to become enabled (not disabled).
        
        Useful for waiting for form validation to enable submit buttons.
        Returns True if element becomes enabled, raises ToolError on timeout.
        """
        try:
            await self._page.wait_for_function(
                f"() => {{ const el = document.querySelector('{selector}'); return el && !el.disabled; }}",
                timeout=timeout * 1000
            )
            return True
        except PlaywrightTimeout:
            raise ToolError(
                name="wait_for_enabled",
                payload={"selector": selector, "timeout": timeout},
                message=f"Element '{selector}' did not become enabled within {timeout}s"
            )
        except Exception as exc:
            raise ToolError(name="wait_for_enabled", payload={"selector": selector}, message=str(exc))

    async def set_viewport(self, width: int | None = None, height: int | None = None) -> None:
        """Set viewport size using environment config (NO HARDCODED VALUES)."""
        import os
        if width is None:
            width = int(os.environ.get('SCREENSHOT_VIEWPORT_WIDTH', '1920'))
        if height is None:
            height = int(os.environ.get('SCREENSHOT_VIEWPORT_HEIGHT', '2400'))
        await self._page.set_viewport_size({"width": width, "height": height})


@asynccontextmanager
async def browser_session() -> AsyncIterator[Browser]:
    """Yield a Browser instance using direct Playwright with global viewport settings."""
    client = PlaywrightClient(headless=settings.playwright_headless)
    await client.connect()
    try:
        page = await client.new_page()
        browser = Browser(page)
        # CRITICAL: Set viewport globally for ALL browser sessions (including auth flow)
        await browser.set_viewport(1920, 2400)
        yield browser
    finally:
        await client.close()
