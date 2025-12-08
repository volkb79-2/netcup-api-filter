#!/usr/bin/env python3
"""
MCP Server for Playwright Browser Automation

Provides Model Context Protocol (MCP) interface to Playwright for AI agent exploration.
Uses official MCP SDK for proper protocol implementation.

Note: This is for exploration only. Use direct Playwright API for production testing.
"""

import os
import asyncio
import logging
from typing import Optional
from pathlib import Path

from mcp.server import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from playwright.async_api import async_playwright, Browser, Page

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration from environment
MCP_PORT = int(os.getenv('MCP_PORT', '8765'))
MCP_SERVER_NAME = os.getenv('MCP_SERVER_NAME', 'playwright')
PLAYWRIGHT_HEADLESS = os.getenv('PLAYWRIGHT_HEADLESS', 'true').lower() == 'true'
PLAYWRIGHT_BROWSER = os.getenv('PLAYWRIGHT_BROWSER', 'chromium')

# Configure transport security to allow container hostname access
# This is required for VS Code MCP clients connecting via Docker network
transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=[
        "localhost",
        f"localhost:{MCP_PORT}",
        "playwright",
        f"playwright:{MCP_PORT}",
        "127.0.0.1",
        f"127.0.0.1:{MCP_PORT}",
        "0.0.0.0",
        f"0.0.0.0:{MCP_PORT}",
    ],
    allowed_origins=[
        "http://localhost",
        f"http://localhost:{MCP_PORT}",
        "http://playwright",
        f"http://playwright:{MCP_PORT}",
        "vscode-file://vscode-app",
    ],
)

# Initialize MCP server using official SDK with transport security
mcp = FastMCP(
    MCP_SERVER_NAME,
    host="0.0.0.0",
    port=MCP_PORT,
    transport_security=transport_security,
)

# Global browser state
_browser: Optional[Browser] = None
_page: Optional[Page] = None
_playwright = None


async def ensure_browser():
    """Ensure browser is initialized"""
    global _browser, _page, _playwright
    
    if _browser is None or not _browser.is_connected():
        logger.info(f"Initializing {PLAYWRIGHT_BROWSER} browser (headless={PLAYWRIGHT_HEADLESS})")
        _playwright = await async_playwright().start()
        
        if PLAYWRIGHT_BROWSER == 'chromium':
            _browser = await _playwright.chromium.launch(headless=PLAYWRIGHT_HEADLESS)
        elif PLAYWRIGHT_BROWSER == 'firefox':
            _browser = await _playwright.firefox.launch(headless=PLAYWRIGHT_HEADLESS)
        elif PLAYWRIGHT_BROWSER == 'webkit':
            _browser = await _playwright.webkit.launch(headless=PLAYWRIGHT_HEADLESS)
        else:
            raise ValueError(f"Unsupported browser: {PLAYWRIGHT_BROWSER}")
        
        _page = await _browser.new_page()
        logger.info("Browser initialized successfully")
    
    return _browser, _page


@mcp.tool()
async def navigate(url: str) -> dict:
    """
    Navigate to a URL in the browser.
    
    Args:
        url: The URL to navigate to
        
    Returns:
        Dict with success status, current URL, and page title
    """
    try:
        _, page = await ensure_browser()
        await page.goto(url, wait_until="networkidle", timeout=30000)
        
        return {
            "success": True,
            "url": page.url,
            "title": await page.title()
        }
    except Exception as e:
        logger.error(f"Navigation error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@mcp.tool()
async def screenshot(path: Optional[str] = None, full_page: bool = True) -> dict:
    """
    Take a screenshot of the current page.
    
    Args:
        path: Optional filename for screenshot (saved to /screenshots/)
        full_page: Whether to capture the full page (default: True)
        
    Returns:
        Dict with success status and screenshot path
    """
    try:
        _, page = await ensure_browser()
        
        if path is None:
            import time
            path = f"mcp-screenshot-{int(time.time())}.png"
        
        # Ensure path is within screenshots directory
        screenshot_path = Path("/screenshots") / Path(path).name
        
        await page.screenshot(path=str(screenshot_path), full_page=full_page)
        
        return {
            "success": True,
            "path": str(screenshot_path),
            "url": page.url
        }
    except Exception as e:
        logger.error(f"Screenshot error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@mcp.tool()
async def get_content() -> dict:
    """
    Get the HTML content of the current page.
    
    Returns:
        Dict with success status, HTML content, and current URL
    """
    try:
        _, page = await ensure_browser()
        content = await page.content()
        
        return {
            "success": True,
            "content": content,
            "url": page.url,
            "title": await page.title()
        }
    except Exception as e:
        logger.error(f"Get content error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@mcp.tool()
async def click(selector: str) -> dict:
    """
    Click an element on the page.
    
    Args:
        selector: CSS selector for the element to click
        
    Returns:
        Dict with success status
    """
    try:
        _, page = await ensure_browser()
        await page.click(selector, timeout=10000)
        
        return {
            "success": True,
            "selector": selector,
            "url": page.url
        }
    except Exception as e:
        logger.error(f"Click error: {e}")
        return {
            "success": False,
            "error": str(e),
            "selector": selector
        }


@mcp.tool()
async def fill(selector: str, value: str) -> dict:
    """
    Fill an input field with text.
    
    Args:
        selector: CSS selector for the input element
        value: Text to fill into the input
        
    Returns:
        Dict with success status
    """
    try:
        _, page = await ensure_browser()
        await page.fill(selector, value, timeout=10000)
        
        return {
            "success": True,
            "selector": selector,
            "url": page.url
        }
    except Exception as e:
        logger.error(f"Fill error: {e}")
        return {
            "success": False,
            "error": str(e),
            "selector": selector
        }


@mcp.tool()
async def evaluate(script: str) -> dict:
    """
    Execute JavaScript in the browser context.
    
    Args:
        script: JavaScript code to execute
        
    Returns:
        Dict with success status and result of evaluation
    """
    try:
        _, page = await ensure_browser()
        result = await page.evaluate(script)
        
        return {
            "success": True,
            "result": result,
            "url": page.url
        }
    except Exception as e:
        logger.error(f"Evaluate error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@mcp.tool()
async def get_url() -> dict:
    """
    Get the current page URL.
    
    Returns:
        Dict with current URL and page title
    """
    try:
        _, page = await ensure_browser()
        return {
            "success": True,
            "url": page.url,
            "title": await page.title()
        }
    except Exception as e:
        logger.error(f"Get URL error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Starting MCP server on 0.0.0.0:{MCP_PORT}")
    logger.info(f"Server name: {MCP_SERVER_NAME}")
    logger.info(f"Browser: {PLAYWRIGHT_BROWSER} (headless={PLAYWRIGHT_HEADLESS})")
    logger.info(f"Allowed hosts: {transport_security.allowed_hosts}")
    
    # Get the Starlette app from FastMCP for streamable HTTP transport
    app = mcp.streamable_http_app()
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=MCP_PORT,
        log_level="info"
    )
