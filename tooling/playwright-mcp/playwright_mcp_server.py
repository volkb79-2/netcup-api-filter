"""Minimal MCP server that exposes Playwright browser controls over WebSockets.

The server implements a small subset of automation helpers that are enough for
interactive testing sessions initiated from an MCP-compatible client (e.g. VS
Code Copilot Chat in MCP mode).  The service keeps a single Chromium page open
and provides high-level tools for navigation, form input, clicks, screenshots,
and text extraction.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional, Sequence

from loguru import logger
from fastmcp import FastMCP
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

SERVER_NAME = os.environ.get("MCP_SERVER_NAME", "playwright-mcp")
DEFAULT_START_URL = os.environ.get("PLAYWRIGHT_START_URL", "https://naf.vxxu.de/admin/")
SCREENSHOT_DIR = Path(os.environ.get("PLAYWRIGHT_SCREENSHOT_DIR", "/screenshots"))

mcp = FastMCP(SERVER_NAME)
playwright = None
browser: Optional[Browser] = None
context: Optional[BrowserContext] = None
page: Optional[Page] = None


async def ensure_browser() -> Page:
    """Launch the browser lazily and ensure a single shared page exists."""
    global playwright, browser, context, page

    if page and not page.is_closed():
        return page

    if playwright is None:
        playwright = await async_playwright().start()

    headless = os.environ.get("PLAYWRIGHT_HEADLESS", "false").lower() == "true"
    browser = await playwright.chromium.launch(headless=headless, args=["--disable-dev-shm-usage"])
    context = await browser.new_context(ignore_https_errors=True)
    page = await context.new_page()
    await page.goto(DEFAULT_START_URL)
    logger.info("Browser launched and navigated to %s", DEFAULT_START_URL)
    return page


@mcp.resource("page://current")
async def current_page() -> str:
    browser_page = await ensure_browser()
    return f"URL: {browser_page.url}\nTitle: {await browser_page.title()}"


@mcp.tool()
async def goto(url: str) -> dict:
    """Navigate the shared page to the given URL."""
    browser_page = await ensure_browser()
    await browser_page.goto(url)
    return {"url": browser_page.url, "title": await browser_page.title()}


@mcp.tool()
async def click(selector: str) -> dict:
    """Click an element matching the CSS selector."""
    browser_page = await ensure_browser()
    await browser_page.click(selector, timeout=15000)
    return {"status": "clicked", "selector": selector, "url": browser_page.url}


@mcp.tool()
async def fill(selector: str, value: str, press_enter: bool = False) -> dict:
    """Fill an input identified by selector and optionally press enter."""
    browser_page = await ensure_browser()
    await browser_page.fill(selector, value, timeout=15000)
    if press_enter:
        await browser_page.press(selector, "Enter")
    return {"status": "filled", "selector": selector, "value": value}


@mcp.tool()
async def select_option(selector: str, value: str | Sequence[str]) -> dict:
    """Select option(s) for a <select> element, supporting multi-selects."""

    browser_page = await ensure_browser()
    selected = await browser_page.select_option(selector, value)  # returns list of selected values
    return {"selector": selector, "value": selected}


@mcp.tool()
async def text(selector: str) -> dict:
    """Return the inner text for the first matching selector."""
    browser_page = await ensure_browser()
    content = await browser_page.inner_text(selector, timeout=15000)
    return {"selector": selector, "text": content}


@mcp.tool()
async def get_attribute(selector: str, attribute: str) -> dict:
    """Return a specific attribute from the first matching element."""

    browser_page = await ensure_browser()
    handle = await browser_page.query_selector(selector)
    if handle is None:
        raise ValueError(f"Selector {selector} not found")
    value = await handle.get_attribute(attribute)
    return {"selector": selector, "attribute": attribute, "value": value}


@mcp.tool()
async def inner_html(selector: str) -> dict:
    """Capture the inner HTML for debugging complex widgets."""

    browser_page = await ensure_browser()
    handle = await browser_page.query_selector(selector)
    if handle is None:
        raise ValueError(f"Selector {selector} not found")
    html = await handle.inner_html()
    return {"selector": selector, "html": html}


@mcp.tool()
async def submit_form(selector: str) -> dict:
    """Submit a form element without clicking its buttons."""

    browser_page = await ensure_browser()
    handle = await browser_page.query_selector(selector)
    if handle is None:
        raise ValueError(f"Selector {selector} not found")
    await handle.evaluate(
        "form => (typeof form.requestSubmit === 'function') ? form.requestSubmit() : form.submit()"
    )
    await browser_page.wait_for_load_state()
    return {"selector": selector, "url": browser_page.url}


@mcp.tool()
async def screenshot(name: str = "capture") -> dict:
    """Take a screenshot and return the on-disk path."""
    browser_page = await ensure_browser()
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.chmod(0o775)
    path = SCREENSHOT_DIR / f"{name}.png"
    await browser_page.screenshot(path=str(path), full_page=True)
    return {"path": str(path)}


@mcp.tool()
async def reset(start_url: Optional[str] = None) -> dict:
    """Close the existing browser context and start fresh."""
    global browser, context, page
    if page and not page.is_closed():
        await page.close()
    if context:
        await context.close()
    if browser:
        await browser.close()
    page = None
    context = None
    browser = None

    if start_url:
        os.environ["PLAYWRIGHT_START_URL"] = start_url

    await ensure_browser()
    return {"status": "restarted", "url": page.url if page else None}


if __name__ == "__main__":
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8765"))
    logger.info("Starting %s on %s:%s", SERVER_NAME, host, port)
    mcp.run(transport="http", host=host, port=port)
