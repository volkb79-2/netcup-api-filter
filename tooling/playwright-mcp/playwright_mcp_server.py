"""Minimal MCP server that exposes Playwright browser controls with multi-context support.

The server implements automation helpers for MCP-compatible clients. Each MCP session
gets its own isolated browser context and page, allowing concurrent access from
multiple clients without interference.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Optional, Sequence

from loguru import logger
from fastmcp import FastMCP
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

SERVER_NAME = os.environ.get("MCP_SERVER_NAME", "playwright-mcp")
DEFAULT_START_URL = os.environ.get("PLAYWRIGHT_START_URL", "https://example.com")
SCREENSHOT_DIR = Path(os.environ.get("PLAYWRIGHT_SCREENSHOT_DIR", "/screenshots"))

mcp = FastMCP(SERVER_NAME)
playwright: Optional[async_playwright] = None
browser: Optional[Browser] = None

# Session storage: session_id -> (context, page)
sessions: Dict[str, tuple[BrowserContext, Page]] = {}


async def ensure_browser() -> Browser:
    """Launch the browser lazily."""
    global playwright, browser
    if browser is None:
        if playwright is None:
            playwright = await async_playwright().start()
        headless = os.environ.get("PLAYWRIGHT_HEADLESS", "false").lower() == "true"
        browser = await playwright.chromium.launch(
            headless=headless, 
            args=["--disable-dev-shm-usage"]
        )
    return browser


async def get_or_create_session(session_id: str) -> tuple[BrowserContext, Page]:
    """Get existing session or create new one with isolated context."""
    if session_id in sessions:
        context, page = sessions[session_id]
        if not page.is_closed():
            return context, page
        # Clean up closed session
        await context.close()
        del sessions[session_id]
    
    # Create new session
    browser = await ensure_browser()
    context = await browser.new_context(ignore_https_errors=True)
    page = await context.new_page()
    await page.goto(DEFAULT_START_URL)
    sessions[session_id] = (context, page)
    logger.info("Created new session %s with page at %s", session_id, DEFAULT_START_URL)
    return context, page


def get_session_id() -> str:
    """Generate or retrieve session ID. In a real implementation, this would come from MCP session context."""
    # For demo: use a thread-local or context variable
    # FastMCP supports session context, but for simplicity, use a global for now
    # In production, use proper session management
    current_task = asyncio.current_task()
    if current_task and hasattr(current_task, '_mcp_session_id'):
        return current_task._mcp_session_id
    
    # Fallback: generate new session per request (not ideal for persistence)
    session_id = str(uuid.uuid4())[:8]
    if current_task:
        current_task._mcp_session_id = session_id
    return session_id


async def get_current_page() -> Page:
    """Get the page for current session."""
    session_id = get_session_id()
    _, page = await get_or_create_session(session_id)
    return page


@mcp.resource("page://current")
async def current_page() -> str:
    page = await get_current_page()
    return f"URL: {page.url}\nTitle: {await page.title()}"


@mcp.tool()
async def goto(url: str) -> dict:
    """Navigate the session's page to the given URL."""
    page = await get_current_page()
    await page.goto(url)
    return {"url": page.url, "title": await page.title()}


@mcp.tool()
async def click(selector: str) -> dict:
    """Click an element matching the CSS selector."""
    page = await get_current_page()
    await page.click(selector, timeout=15000)
    return {"status": "clicked", "selector": selector, "url": page.url}


@mcp.tool()
async def fill(selector: str, value: str, press_enter: bool = False) -> dict:
    """Fill an input identified by selector and optionally press enter."""
    page = await get_current_page()
    await page.fill(selector, value, timeout=15000)
    if press_enter:
        await page.press(selector, "Enter")
    return {"status": "filled", "selector": selector, "value": value}


@mcp.tool()
async def select_option(selector: str, value: str | Sequence[str]) -> dict:
    """Select option(s) for a <select> element, supporting multi-selects."""
    page = await get_current_page()
    selected = await page.select_option(selector, value)
    return {"selector": selector, "value": selected}


@mcp.tool()
async def text(selector: str) -> dict:
    """Return the inner text for the first matching selector."""
    page = await get_current_page()
    content = await page.inner_text(selector, timeout=15000)
    return {"selector": selector, "text": content}


@mcp.tool()
async def get_attribute(selector: str, attribute: str) -> dict:
    """Return a specific attribute from the first matching element."""
    page = await get_current_page()
    handle = await page.query_selector(selector)
    if handle is None:
        raise ValueError(f"Selector {selector} not found")
    value = await handle.get_attribute(attribute)
    return {"selector": selector, "attribute": attribute, "value": value}


@mcp.tool()
async def inner_html(selector: str) -> dict:
    """Capture the inner HTML for debugging complex widgets."""
    page = await get_current_page()
    handle = await page.query_selector(selector)
    if handle is None:
        raise ValueError(f"Selector {selector} not found")
    html = await handle.inner_html()
    return {"selector": selector, "html": html}


@mcp.tool()
async def submit_form(selector: str) -> dict:
    """Submit a form element without clicking its buttons."""
    page = await get_current_page()
    handle = await page.query_selector(selector)
    if handle is None:
        raise ValueError(f"Selector {selector} not found")
    await handle.evaluate(
        "form => (typeof form.requestSubmit === 'function') ? form.requestSubmit() : form.submit()"
    )
    await page.wait_for_load_state()
    return {"selector": selector, "url": page.url}


@mcp.tool()
async def screenshot(name: str = "capture") -> dict:
    """Take a screenshot and return the on-disk path."""
    page = await get_current_page()
    session_id = get_session_id()
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.chmod(0o775)
    path = SCREENSHOT_DIR / f"{session_id}-{name}.png"
    await page.screenshot(path=str(path), full_page=True)
    return {"path": str(path)}


@mcp.tool()
async def reset(start_url: Optional[str] = None) -> dict:
    """Close the existing session context and start fresh."""
    session_id = get_session_id()
    if session_id in sessions:
        context, page = sessions[session_id]
        if not page.is_closed():
            await page.close()
        await context.close()
        del sessions[session_id]
    
    if start_url:
        # Update default for new sessions
        global DEFAULT_START_URL
        DEFAULT_START_URL = start_url
    
    # Create new session
    await get_or_create_session(session_id)
    return {"status": "restarted", "session": session_id}


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
    logger.info("Starting %s on %s:%s with multi-context support", SERVER_NAME, host, port)
    
    # Cleanup sessions on shutdown
    async def cleanup():
        for context, page in sessions.values():
            try:
                if not page.is_closed():
                    await page.close()
                await context.close()
            except Exception as e:
                logger.warning("Error closing session: %s", e)
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()
    
    import atexit
    atexit.register(lambda: asyncio.run(cleanup()))
    
    mcp.run(transport="http", host=host, port=port)
