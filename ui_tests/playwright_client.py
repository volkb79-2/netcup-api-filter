"""
Playwright Client — in-process or remote-server mode
=====================================================

This client wraps Playwright's Python API directly, providing full browser
automation without MCP server limitations (form submissions, JS evaluation,
storage_state, page.request all work unchanged in both modes).

Connection modes
----------------
1. In-process (default / CI):
   Playwright launches a local Chromium/Firefox/WebKit process.
   Requires browser binaries installed via ``playwright install``.

2. Remote Playwright-as-a-Service (set ``PLAYWRIGHT_SERVER_WS``):
   The client connects to an external ``playwright run-server`` endpoint
   over WebSocket instead of launching a local browser.  The server controls
   headless mode; the client ``headless`` flag is ignored when connecting
   remotely.  Address the service by container name on the shared Docker
   network — never "localhost" — e.g.::

       export PLAYWRIGHT_SERVER_WS=ws://naf-dev-playwright:3000/

   The rest of ``connect()`` (context creation, storage_state, default page)
   runs identically in both modes because ``bt.connect()`` returns a real
   ``Browser`` object with the same API as ``bt.launch()``.

Usage:
    from ui_tests.playwright_client import playwright_session

    async with playwright_session() as page:
        await page.goto(settings.url("/admin/login"))
        await page.fill("#username", settings.admin_username)
        await page.click("button[type='submit']")

Author: netcup-api-filter project
Date: 2025-11-22
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright
from ui_tests.pwmcp_connection import (
    SharedPwmcpSession,
    current_shared_session,
    existing_storage_state,
    fetch_contract,
    load_connection_options,
)

logger = logging.getLogger(__name__)


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
            logger.warning("PLAYWRIGHT_HEADLESS is not set; using the declared default true")
            self.headless = headless_str.lower() == 'true'
        self.timeout = timeout
        self.storage_state_path = storage_state_path
        
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._shared_session: SharedPwmcpSession | None = None
        # Outside a pytest session (no installed shared session) a remote client owns a
        # private SharedPwmcpSession: same contract check, lease headers, bounded connect.
        self._private_session: SharedPwmcpSession | None = None
        self._owns_browser = False
        
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def connect(self):
        """Connect to a browser — either in-process or via a remote server.

        Two modes, selected by the ``PLAYWRIGHT_SERVER_WS`` environment variable:

        * **Remote** (``PLAYWRIGHT_SERVER_WS`` is set):
          Connects to an external Playwright ``run-server`` endpoint over
          WebSocket.  Use the container name as the host on the shared Docker
          network, e.g. ``ws://naf-dev-playwright:3000/``.  Never use
          ``localhost`` here — the server lives in a separate container.
          The server controls headless mode; the client ``self.headless``
          flag is silently ignored in this mode.

        * **In-process** (``PLAYWRIGHT_SERVER_WS`` absent / empty, default):
          Launches a local browser process.  Requires browser binaries
          installed via ``playwright install``.  This is the default for
          local development and CI.

        In both cases the returned ``_browser`` is a standard Playwright
        ``Browser`` object, so ``new_context`` / ``new_page`` / ``page.request``
        work identically downstream.
        """
        try:
            await self._connect()
        except BaseException:
            # Never leak a context (or a private driver) in the shared browser when
            # connect fails half-way, e.g. new_page() after new_context().
            await self._close_partial()
            raise

    async def _connect(self) -> None:
        server_ws = os.environ.get("PLAYWRIGHT_SERVER_WS", "").strip()
        shared_session = current_shared_session()
        if shared_session is not None:
            # The pytest session owns this one driver/browser connection. A
            # client instance owns only its fresh context and page.
            self._shared_session = shared_session
            self._browser = await shared_session.ensure_connected()
            self._owns_browser = False
        elif server_ws:
            # Remote mode outside the pytest session (helpers below): the same contract
            # check, lease headers, per-attempt timeout and bounded 503 retry, all from
            # .env.defaults/environment (no literal defaults here).
            options = load_connection_options()
            contract = fetch_contract(options.ws_url, timeout_seconds=options.contract_timeout_seconds)
            private = SharedPwmcpSession(
                replace(options, browser_type=self.browser_type),
                contract=contract,
                playwright_factory=async_playwright,
            )
            self._private_session = private
            await private.start()
            self._shared_session = private
            self._browser = private.browser
            self._owns_browser = False
        else:
            # In-process mode: launch a local browser (requires installed binaries).
            self._playwright = await async_playwright().start()
            self._owns_browser = True
            if self.browser_type == 'firefox':
                self._browser = await self._playwright.firefox.launch(headless=self.headless)
            elif self.browser_type == 'webkit':
                self._browser = await self._playwright.webkit.launch(headless=self.headless)
            else:
                self._browser = await self._playwright.chromium.launch(headless=self.headless)

        # Create default context
        if self._shared_session is not None:
            self._context = await self._shared_session.new_context(
                storage_state_path=self.storage_state_path,
            )
        else:
            context_kwargs = {}
            storage_state_path = existing_storage_state(self.storage_state_path)
            if storage_state_path:
                context_kwargs["storage_state"] = storage_state_path
            self._context = await self._browser.new_context(**context_kwargs)
        self._context.set_default_timeout(self.timeout)

        # Create default page for convenience
        self._page = await self._context.new_page()

    async def _close_partial(self) -> None:
        try:
            await self.close()
        except Exception as exc:
            logger.warning("cleanup after a failed connect also failed: %s", type(exc).__name__)

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
        
        if self._shared_session is not None:
            context = await self._shared_session.new_context(**kwargs)
        else:
            context = await self._browser.new_context(**kwargs)
        context.set_default_timeout(self.timeout)
        return context
    
    async def close(self):
        """Close all connections and cleanup resources.

        Every step runs even if an earlier one fails: a context left open in the shared
        browser would live for the rest of the session.
        """
        page, self._page = self._page, None
        context, self._context = self._context, None
        browser, self._browser = self._browser, None
        playwright, self._playwright = self._playwright, None
        private, self._private_session = self._private_session, None
        owns_browser = self._owns_browser
        self._shared_session = None
        try:
            if page is not None:
                try:
                    await page.close()
                except Exception as exc:
                    # The context close below closes the page anyway.
                    logger.debug("page close failed: %s", type(exc).__name__)
            if context is not None:
                await context.close()
        finally:
            if private is not None:
                await private.stop()
            elif owns_browser:
                try:
                    if browser is not None:
                        await browser.close()
                finally:
                    if playwright is not None:
                        await playwright.stop()

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
        # await page.goto("https://<your-host>/admin/login")
        # await page.fill("#username", "admin")
        # await page.fill("#password", "admin123")
        # await page.click("button[type='submit']")
        # await page.wait_for_url("**/admin/**")
        
        print("   ✅ Form submission capability available!")
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
