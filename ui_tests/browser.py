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

    async def goto(self, url: str) -> Dict[str, Any]:
        """Navigate to URL."""
        try:
            await self._page.goto(url, wait_until="networkidle", timeout=30000)
            await self._update_state()
            return {"url": self.current_url, "title": self.current_title}
        except PlaywrightTimeout as exc:
            raise ToolError(name="goto", payload={"url": url}, message=str(exc))

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

    async def html(self, selector: str) -> str:
        """Get inner HTML of element."""
        try:
            html = await self._page.inner_html(selector, timeout=5000)
            return html or ""
        except Exception as exc:
            raise ToolError(name="html", payload={"selector": selector}, message=str(exc))

    async def screenshot(self, name: str) -> str:
        """Take screenshot."""
        try:
            path = f"/screenshots/{name}.png"
            await self._page.screenshot(path=path)
            return path
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


@asynccontextmanager
async def browser_session() -> AsyncIterator[Browser]:
    """Yield a Browser instance using direct Playwright."""
    client = PlaywrightClient(headless=settings.playwright_headless)
    await client.connect()
    try:
        page = await client.new_page()
        browser = Browser(page)
        yield browser
    finally:
        await client.close()
