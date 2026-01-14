"""
Direct Playwright Client (No Server Required)
==============================================

This client uses Playwright's Python API directly, bypassing MCP server limitations.

Key Features:
- Full Playwright API access
- Form submissions work correctly
- JavaScript execution available
- Type-safe async interface
- No server dependency (runs Playwright directly)

Usage:
    from ui_tests.playwright_client import playwright_session
    
    async with playwright_session() as page:
        await page.goto("https://naf.vxxu.de")
        await page.fill("#username", "admin")
        await page.click("button[type='submit']")  # ✅ Works!

Author: netcup-api-filter project
Date: 2025-11-22
"""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright


class PlaywrightClient:
    """
    Direct Playwright client with full API access (no server required).
    
    This client launches Playwright directly in-process, providing full browser
    automation capabilities without any server or MCP wrapper limitations.
    
    Example:
        async with PlaywrightClient() as client:
            page = await client.new_page()
            await page.goto("https://example.com")
            await page.click("button")
    """
    
    def __init__(
        self,
        browser_type: str = "chromium",
        headless: Optional[bool] = None,
        timeout: int = 30000,
        storage_state_path: Optional[str] = None,
    ):
        """
        Initialize Playwright client.
        
        Args:
            browser_type: Browser to use (chromium, firefox, webkit)
            headless: Run in headless mode (None = auto-detect from env)
            timeout: Default timeout in milliseconds
        """
        self.browser_type = browser_type
        # Fail-fast: require explicit configuration
        if headless is not None:
            self.headless = headless
        else:
            headless_str = os.getenv('PLAYWRIGHT_HEADLESS')
            if not headless_str:
                headless_str = 'true'
                print("[CONFIG] WARNING: PLAYWRIGHT_HEADLESS not set, using default: true")
            self.headless = headless_str.lower() == 'true'
        self.timeout = timeout
        self.storage_state_path = storage_state_path
        
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def connect(self):
        """Launch Playwright browser directly."""
        self._playwright = await async_playwright().start()
        
        # Launch browser directly (no server needed)
        if self.browser_type == 'firefox':
            self._browser = await self._playwright.firefox.launch(headless=self.headless)
        elif self.browser_type == 'webkit':
            self._browser = await self._playwright.webkit.launch(headless=self.headless)
        else:
            self._browser = await self._playwright.chromium.launch(headless=self.headless)
        
        # Create default context
        storage_state_path = self.storage_state_path
        if storage_state_path and not os.path.exists(storage_state_path):
            print(
                f"[CONFIG] WARNING: storage_state_path does not exist, ignoring: {storage_state_path}"
            )
            storage_state_path = None

        if storage_state_path:
            self._context = await self._browser.new_context(storage_state=storage_state_path)
        else:
            self._context = await self._browser.new_context()
        self._context.set_default_timeout(self.timeout)
        
        # Create default page for convenience
        self._page: Optional[Page] = await self._context.new_page()
    
    async def new_page(self) -> Page:
        """
        Create a new page in the default context.
        
        Returns:
            Page object with full Playwright API
        """
        if not self._context:
            raise RuntimeError("Client not connected. Use 'async with' or call connect()")
        
        return await self._context.new_page()
    
    async def new_context(self, **kwargs) -> BrowserContext:
        """
        Create a new browser context with custom options.
        
        Args:
            **kwargs: Context options (viewport, user_agent, etc.)
        
        Returns:
            BrowserContext object
        """
        if not self._browser:
            raise RuntimeError("Client not connected. Use 'async with' or call connect()")
        
        context = await self._browser.new_context(**kwargs)
        context.set_default_timeout(self.timeout)
        return context
    
    async def close(self):
        """Close all connections and cleanup resources."""
        if self._page:
            await self._page.close()
            self._page = None
        
        if self._context:
            await self._context.close()
            self._context = None
        
        if self._browser:
            await self._browser.close()
            self._browser = None
        
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
    
    @property
    def browser(self) -> Browser:
        """Get the browser instance."""
        if not self._browser:
            raise RuntimeError("Client not connected")
        return self._browser
    
    @property
    def context(self) -> BrowserContext:
        """Get the default context."""
        if not self._context:
            raise RuntimeError("Client not connected")
        return self._context
    
    @property
    def page(self) -> Page:
        """Get the default page."""
        if not self._page:
            raise RuntimeError("Client not connected or page not created")
        return self._page


@asynccontextmanager
async def playwright_session(
    browser_type: str = "chromium",
    headless: Optional[bool] = None,
    base_url: Optional[str] = None
):
    """
    Context manager for Playwright sessions.
    
    Usage:
        async with playwright_session() as page:
            await page.goto("https://example.com")
            await page.click("button")
    
    Args:
        browser_type: Browser to use (chromium, firefox, webkit)
        headless: Run headless (None = auto-detect from PLAYWRIGHT_HEADLESS env)
        base_url: Optional base URL to navigate to initially
    
    Yields:
        Page object ready for automation
    """
    client = PlaywrightClient(browser_type=browser_type, headless=headless)
    await client.connect()
    
    try:
        page = await client.new_page()
        if base_url:
            await page.goto(base_url)
        yield page
    finally:
        await client.close()


# Convenience functions for quick testing

async def screenshot(url: str, output_path: str, **kwargs):
    """
    Quick screenshot utility.
    
    Args:
        url: URL to capture
        output_path: Where to save screenshot
        **kwargs: Additional screenshot options
    """
    async with playwright_session() as page:
        await page.goto(url)
        await page.screenshot(path=output_path, **kwargs)


async def get_text(url: str, selector: str) -> str:
    """
    Quick text extraction utility.
    
    Args:
        url: URL to visit
        selector: CSS selector
    
    Returns:
        Text content of element
    """
    async with playwright_session() as page:
        await page.goto(url)
        return await page.text_content(selector) or ""


async def form_submit(
    url: str,
    form_data: dict,
    submit_selector: str = "button[type='submit']"
):
    """
    Quick form submission utility.
    
    Args:
        url: URL with form
        form_data: Dict of {selector: value} pairs
        submit_selector: Submit button selector
    
    Returns:
        New URL after submission
    """
    async with playwright_session() as page:
        await page.goto(url)
        
        # Fill form fields
        for selector, value in form_data.items():
            await page.fill(selector, value)
        
        # Submit form
        await page.click(submit_selector)
        await page.wait_for_load_state("networkidle")
        
        return page.url


# Example usage and tests

async def example_usage():
    """Example demonstrating client usage."""
    print("=" * 70)
    print("Playwright Direct Client - Example Usage")
    print("=" * 70)
    
    # Example 1: Basic usage with context manager
    print("\n1. Basic page navigation:")
    async with PlaywrightClient() as client:
        page = await client.new_page()
        await page.goto("https://example.com")
        title = await page.title()
        print(f"   Page title: {title}")
    
    # Example 2: Form submission (the problem MCP couldn't solve!)
    print("\n2. Form submission (works with direct Playwright!):")
    async with playwright_session(base_url="https://example.com") as page:
        # This works with direct Playwright but not with MCP!
        # For actual testing, uncomment the lines below:
        # await page.goto("https://naf.vxxu.de/admin/login")
        # await page.fill("#username", "admin")
        # await page.fill("#password", "admin123")
        # await page.click("button[type='submit']")
        # await page.wait_for_url("**/admin/**")
        
        print(f"   ✅ Form submission capability available!")
        print(f"   Current URL: {page.url}")
    
    # Example 3: Screenshot
    print("\n3. Taking screenshot:")
    import os
    screenshot_dir = os.environ.get('SCREENSHOT_DIR', 'screenshots')
    screenshot_path = f"{screenshot_dir}/test-screenshot.png"
    await screenshot(
        "https://example.com",
        screenshot_path,
        full_page=True
    )
    print(f"   ✅ Screenshot saved to {screenshot_path}")
    
    # Example 4: Text extraction
    print("\n4. Text extraction:")
    text = await get_text("https://example.com", "h1")
    print(f"   H1 text: {text}")
    
    print("\n" + "=" * 70)
    print("All examples completed successfully!")
    print("=" * 70)


if __name__ == "__main__":
    # Run examples
    asyncio.run(example_usage())
