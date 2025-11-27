#!/usr/bin/env python3
"""
WebSocket Server for Playwright Browser Automation

Provides a multi-client WebSocket service for browser automation.
Designed for use by both VS Code MCP clients and automated pytest tests.

Features:
- Multi-client WebSocket connections on port 3000
- Session management per client
- Authentication via token
- Full Playwright API access (no MCP limitations)
- Form submission, JavaScript execution, etc.

Protocol:
    All messages are JSON objects with 'type' and 'data' fields.
    
    Request:
        {"type": "command", "id": "unique-id", "command": "navigate", "args": {"url": "..."}}
    
    Response:
        {"type": "response", "id": "unique-id", "success": true, "data": {...}}
        {"type": "error", "id": "unique-id", "error": "message"}

Author: netcup-api-filter project
Date: 2025-11-26
"""

import asyncio
import json
import logging
import os
import secrets
import ssl
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import websockets
from websockets.asyncio.server import ServerConnection
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration from environment
WS_PORT = int(os.getenv('WS_PORT', '3000'))
WS_HOST = os.getenv('WS_HOST', '0.0.0.0')
AUTH_TOKEN = os.getenv('WS_AUTH_TOKEN', '')  # Empty = no auth required
MAX_SESSIONS = int(os.getenv('WS_MAX_SESSIONS', '10'))
SESSION_TIMEOUT = int(os.getenv('WS_SESSION_TIMEOUT', '3600'))  # seconds
PLAYWRIGHT_HEADLESS = os.getenv('PLAYWRIGHT_HEADLESS', 'true').lower() == 'true'
PLAYWRIGHT_BROWSER = os.getenv('PLAYWRIGHT_BROWSER', 'chromium')
SSL_CERT_PATH = os.getenv('SSL_CERT_PATH', '/app/certs/server.crt')
SSL_KEY_PATH = os.getenv('SSL_KEY_PATH', '/app/certs/server.key')
SSL_ENABLED = os.getenv('SSL_ENABLED', 'false').lower() == 'true'


@dataclass
class BrowserSession:
    """Represents a browser session for a client."""
    session_id: str
    context: BrowserContext
    page: Page
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def touch(self):
        """Update last used timestamp."""
        self.last_used = time.time()
    
    def is_expired(self, timeout: int) -> bool:
        """Check if session has expired."""
        return (time.time() - self.last_used) > timeout


class PlaywrightWebSocketServer:
    """
    WebSocket server for Playwright browser automation.
    
    Manages multiple browser sessions and provides a JSON-based
    protocol for browser automation commands.
    """
    
    def __init__(self):
        self.sessions: Dict[str, BrowserSession] = {}
        self.client_sessions: Dict[ServerConnection, str] = {}
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # Command handlers
        self.handlers: Dict[str, Callable] = {
            'navigate': self._handle_navigate,
            'screenshot': self._handle_screenshot,
            'click': self._handle_click,
            'fill': self._handle_fill,
            'type': self._handle_type,
            'press': self._handle_press,
            'evaluate': self._handle_evaluate,
            'get_content': self._handle_get_content,
            'get_url': self._handle_get_url,
            'wait_for_selector': self._handle_wait_for_selector,
            'wait_for_url': self._handle_wait_for_url,
            'wait_for_load_state': self._handle_wait_for_load_state,
            'select_option': self._handle_select_option,
            'check': self._handle_check,
            'uncheck': self._handle_uncheck,
            'hover': self._handle_hover,
            'focus': self._handle_focus,
            'get_attribute': self._handle_get_attribute,
            'get_text': self._handle_get_text,
            'get_inner_html': self._handle_get_inner_html,
            'get_input_value': self._handle_get_input_value,
            'is_visible': self._handle_is_visible,
            'is_enabled': self._handle_is_enabled,
            'is_checked': self._handle_is_checked,
            'query_selector': self._handle_query_selector,
            'query_selector_all': self._handle_query_selector_all,
            'reload': self._handle_reload,
            'go_back': self._handle_go_back,
            'go_forward': self._handle_go_forward,
            'set_viewport_size': self._handle_set_viewport_size,
            'cookies': self._handle_cookies,
            'set_cookies': self._handle_set_cookies,
            'clear_cookies': self._handle_clear_cookies,
            'close_session': self._handle_close_session,
            'health': self._handle_health,
            'login': self._handle_login,  # Convenience method for login flows
        }
    
    async def start(self):
        """Initialize Playwright and start the server."""
        logger.info(f"Initializing Playwright ({PLAYWRIGHT_BROWSER}, headless={PLAYWRIGHT_HEADLESS})")
        
        self._playwright = await async_playwright().start()
        
        if PLAYWRIGHT_BROWSER == 'chromium':
            self._browser = await self._playwright.chromium.launch(headless=PLAYWRIGHT_HEADLESS)
        elif PLAYWRIGHT_BROWSER == 'firefox':
            self._browser = await self._playwright.firefox.launch(headless=PLAYWRIGHT_HEADLESS)
        elif PLAYWRIGHT_BROWSER == 'webkit':
            self._browser = await self._playwright.webkit.launch(headless=PLAYWRIGHT_HEADLESS)
        else:
            raise ValueError(f"Unsupported browser: {PLAYWRIGHT_BROWSER}")
        
        logger.info("Playwright browser initialized")
        
        # Start session cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_expired_sessions())
        
        # Configure SSL if enabled
        ssl_context = None
        if SSL_ENABLED:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(SSL_CERT_PATH, SSL_KEY_PATH)
            logger.info(f"TLS enabled with cert: {SSL_CERT_PATH}")
        
        # Start WebSocket server
        protocol = "wss" if SSL_ENABLED else "ws"
        logger.info(f"Starting WebSocket server on {protocol}://{WS_HOST}:{WS_PORT}")
        
        async with websockets.serve(
            self._handle_connection,
            WS_HOST,
            WS_PORT,
            ssl=ssl_context,
            max_size=10 * 1024 * 1024,  # 10MB max message size
            ping_interval=30,
            ping_timeout=10,
        ):
            logger.info(f"WebSocket server running on {protocol}://{WS_HOST}:{WS_PORT}")
            await asyncio.Future()  # Run forever
    
    async def stop(self):
        """Stop server and cleanup resources."""
        logger.info("Shutting down WebSocket server...")
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Close all sessions
        for session_id in list(self.sessions.keys()):
            await self._close_session(session_id)
        
        if self._browser:
            await self._browser.close()
        
        if self._playwright:
            await self._playwright.stop()
        
        logger.info("WebSocket server stopped")
    
    async def _cleanup_expired_sessions(self):
        """Periodically cleanup expired sessions."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                expired = [
                    sid for sid, session in self.sessions.items()
                    if session.is_expired(SESSION_TIMEOUT)
                ]
                
                for session_id in expired:
                    logger.info(f"Cleaning up expired session: {session_id}")
                    await self._close_session(session_id)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in session cleanup: {e}")
    
    async def _handle_connection(self, websocket: ServerConnection):
        """Handle new WebSocket connection."""
        client_id = str(uuid.uuid4())[:8]
        logger.info(f"New connection from {websocket.remote_address} (client: {client_id})")
        
        # Authentication check
        if AUTH_TOKEN:
            try:
                auth_msg = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                auth_data = json.loads(auth_msg)
                
                if auth_data.get('type') != 'auth' or auth_data.get('token') != AUTH_TOKEN:
                    await websocket.send(json.dumps({
                        'type': 'error',
                        'error': 'Authentication failed'
                    }))
                    await websocket.close(1008, 'Authentication failed')
                    return
                
                await websocket.send(json.dumps({
                    'type': 'auth_success',
                    'message': 'Authenticated successfully'
                }))
                logger.info(f"Client {client_id} authenticated")
                
            except asyncio.TimeoutError:
                await websocket.close(1008, 'Authentication timeout')
                return
            except Exception as e:
                logger.error(f"Auth error: {e}")
                await websocket.close(1008, 'Authentication error')
                return
        
        # Create session for this client
        try:
            session = await self._create_session()
            self.client_sessions[websocket] = session.session_id
            
            await websocket.send(json.dumps({
                'type': 'connected',
                'session_id': session.session_id,
                'message': 'Session created successfully'
            }))
            
            # Handle messages
            async for message in websocket:
                await self._handle_message(websocket, session.session_id, message)
                
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Client {client_id} disconnected")
        except Exception as e:
            logger.error(f"Error handling client {client_id}: {e}")
        finally:
            # Cleanup session on disconnect
            session_id = self.client_sessions.pop(websocket, None)
            if session_id:
                await self._close_session(session_id)
                logger.info(f"Session {session_id} closed for client {client_id}")
    
    async def _create_session(self) -> BrowserSession:
        """Create a new browser session."""
        if len(self.sessions) >= MAX_SESSIONS:
            raise RuntimeError(f"Maximum sessions ({MAX_SESSIONS}) reached")
        
        if not self._browser:
            raise RuntimeError("Browser not initialized")
        
        session_id = f"session_{secrets.token_hex(8)}"
        context = await self._browser.new_context()
        page = await context.new_page()
        
        session = BrowserSession(
            session_id=session_id,
            context=context,
            page=page
        )
        
        self.sessions[session_id] = session
        logger.info(f"Created session: {session_id}")
        
        return session
    
    async def _close_session(self, session_id: str):
        """Close a browser session."""
        session = self.sessions.pop(session_id, None)
        if session:
            try:
                await session.context.close()
            except Exception as e:
                logger.error(f"Error closing session {session_id}: {e}")
    
    def _get_session(self, session_id: str) -> BrowserSession:
        """Get session and update last used timestamp."""
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        session.touch()
        return session
    
    async def _handle_message(self, websocket: ServerConnection, session_id: str, message: str):
        """Handle incoming WebSocket message."""
        try:
            data = json.loads(message)
            msg_id = data.get('id', str(uuid.uuid4())[:8])
            command = data.get('command', '')
            args = data.get('args', {})
            
            logger.debug(f"[{session_id}] Command: {command}, args: {args}")
            
            handler = self.handlers.get(command)
            if not handler:
                await websocket.send(json.dumps({
                    'type': 'error',
                    'id': msg_id,
                    'error': f"Unknown command: {command}"
                }))
                return
            
            # Execute command
            result = await handler(session_id, args)
            
            await websocket.send(json.dumps({
                'type': 'response',
                'id': msg_id,
                'success': True,
                'data': result
            }))
            
        except json.JSONDecodeError as e:
            await websocket.send(json.dumps({
                'type': 'error',
                'error': f"Invalid JSON: {e}"
            }))
        except Exception as e:
            logger.error(f"Command error: {e}")
            await websocket.send(json.dumps({
                'type': 'error',
                'id': data.get('id') if 'data' in dir() else None,
                'error': str(e)
            }))
    
    # ===== Command Handlers =====
    
    async def _handle_navigate(self, session_id: str, args: dict) -> dict:
        """Navigate to a URL."""
        session = self._get_session(session_id)
        url = args.get('url')
        if not url:
            raise ValueError("url is required")
        
        wait_until = args.get('wait_until', 'networkidle')
        timeout = args.get('timeout', 30000)
        
        await session.page.goto(url, wait_until=wait_until, timeout=timeout)
        
        return {
            'url': session.page.url,
            'title': await session.page.title()
        }
    
    async def _handle_screenshot(self, session_id: str, args: dict) -> dict:
        """Take a screenshot."""
        session = self._get_session(session_id)
        
        path = args.get('path')
        if path:
            # Ensure path is within screenshots directory
            screenshot_path = Path("/screenshots") / Path(path).name
        else:
            screenshot_path = Path("/screenshots") / f"screenshot_{int(time.time())}.png"
        
        full_page = args.get('full_page', True)
        
        await session.page.screenshot(path=str(screenshot_path), full_page=full_page)
        
        return {
            'path': str(screenshot_path),
            'url': session.page.url
        }
    
    async def _handle_click(self, session_id: str, args: dict) -> dict:
        """Click an element."""
        session = self._get_session(session_id)
        selector = args.get('selector')
        if not selector:
            raise ValueError("selector is required")
        
        timeout = args.get('timeout', 10000)
        button = args.get('button', 'left')
        click_count = args.get('click_count', 1)
        
        await session.page.click(
            selector,
            timeout=timeout,
            button=button,
            click_count=click_count
        )
        
        return {'clicked': selector, 'url': session.page.url}
    
    async def _handle_fill(self, session_id: str, args: dict) -> dict:
        """Fill an input field."""
        session = self._get_session(session_id)
        selector = args.get('selector')
        value = args.get('value', '')
        if not selector:
            raise ValueError("selector is required")
        
        timeout = args.get('timeout', 10000)
        
        await session.page.fill(selector, value, timeout=timeout)
        
        return {'filled': selector, 'url': session.page.url}
    
    async def _handle_type(self, session_id: str, args: dict) -> dict:
        """Type text character by character."""
        session = self._get_session(session_id)
        selector = args.get('selector')
        text = args.get('text', '')
        if not selector:
            raise ValueError("selector is required")
        
        delay = args.get('delay', 0)
        timeout = args.get('timeout', 10000)
        
        await session.page.locator(selector).press_sequentially(text, delay=delay, timeout=timeout)
        
        return {'typed': selector, 'url': session.page.url}
    
    async def _handle_press(self, session_id: str, args: dict) -> dict:
        """Press a keyboard key."""
        session = self._get_session(session_id)
        key = args.get('key')
        if not key:
            raise ValueError("key is required")
        
        selector = args.get('selector')
        
        if selector:
            await session.page.locator(selector).press(key)
        else:
            await session.page.keyboard.press(key)
        
        return {'pressed': key, 'url': session.page.url}
    
    async def _handle_evaluate(self, session_id: str, args: dict) -> dict:
        """Execute JavaScript."""
        session = self._get_session(session_id)
        script = args.get('script')
        if not script:
            raise ValueError("script is required")
        
        result = await session.page.evaluate(script)
        
        return {'result': result, 'url': session.page.url}
    
    async def _handle_get_content(self, session_id: str, args: dict) -> dict:
        """Get page HTML content."""
        session = self._get_session(session_id)
        
        content = await session.page.content()
        
        return {
            'content': content,
            'url': session.page.url,
            'title': await session.page.title()
        }
    
    async def _handle_get_url(self, session_id: str, args: dict) -> dict:
        """Get current URL."""
        session = self._get_session(session_id)
        
        return {
            'url': session.page.url,
            'title': await session.page.title()
        }
    
    async def _handle_wait_for_selector(self, session_id: str, args: dict) -> dict:
        """Wait for element to appear."""
        session = self._get_session(session_id)
        selector = args.get('selector')
        if not selector:
            raise ValueError("selector is required")
        
        state = args.get('state', 'visible')
        timeout = args.get('timeout', 30000)
        
        await session.page.wait_for_selector(selector, state=state, timeout=timeout)
        
        return {'found': selector, 'url': session.page.url}
    
    async def _handle_wait_for_url(self, session_id: str, args: dict) -> dict:
        """Wait for URL to match pattern."""
        session = self._get_session(session_id)
        url_pattern = args.get('url')
        if not url_pattern:
            raise ValueError("url is required")
        
        timeout = args.get('timeout', 30000)
        
        await session.page.wait_for_url(url_pattern, timeout=timeout)
        
        return {'url': session.page.url}
    
    async def _handle_wait_for_load_state(self, session_id: str, args: dict) -> dict:
        """Wait for page load state."""
        session = self._get_session(session_id)
        state = args.get('state', 'networkidle')
        timeout = args.get('timeout', 30000)
        
        await session.page.wait_for_load_state(state, timeout=timeout)
        
        return {'state': state, 'url': session.page.url}
    
    async def _handle_select_option(self, session_id: str, args: dict) -> dict:
        """Select dropdown option."""
        session = self._get_session(session_id)
        selector = args.get('selector')
        if not selector:
            raise ValueError("selector is required")
        
        value = args.get('value')
        label = args.get('label')
        index = args.get('index')
        
        if value is not None:
            await session.page.select_option(selector, value=value)
        elif label is not None:
            await session.page.select_option(selector, label=label)
        elif index is not None:
            await session.page.select_option(selector, index=index)
        else:
            raise ValueError("value, label, or index is required")
        
        return {'selected': selector, 'url': session.page.url}
    
    async def _handle_check(self, session_id: str, args: dict) -> dict:
        """Check a checkbox."""
        session = self._get_session(session_id)
        selector = args.get('selector')
        if not selector:
            raise ValueError("selector is required")
        
        await session.page.check(selector)
        
        return {'checked': selector, 'url': session.page.url}
    
    async def _handle_uncheck(self, session_id: str, args: dict) -> dict:
        """Uncheck a checkbox."""
        session = self._get_session(session_id)
        selector = args.get('selector')
        if not selector:
            raise ValueError("selector is required")
        
        await session.page.uncheck(selector)
        
        return {'unchecked': selector, 'url': session.page.url}
    
    async def _handle_hover(self, session_id: str, args: dict) -> dict:
        """Hover over element."""
        session = self._get_session(session_id)
        selector = args.get('selector')
        if not selector:
            raise ValueError("selector is required")
        
        await session.page.hover(selector)
        
        return {'hovered': selector, 'url': session.page.url}
    
    async def _handle_focus(self, session_id: str, args: dict) -> dict:
        """Focus on element."""
        session = self._get_session(session_id)
        selector = args.get('selector')
        if not selector:
            raise ValueError("selector is required")
        
        await session.page.focus(selector)
        
        return {'focused': selector, 'url': session.page.url}
    
    async def _handle_get_attribute(self, session_id: str, args: dict) -> dict:
        """Get element attribute."""
        session = self._get_session(session_id)
        selector = args.get('selector')
        name = args.get('name')
        if not selector or not name:
            raise ValueError("selector and name are required")
        
        value = await session.page.get_attribute(selector, name)
        
        return {'selector': selector, 'attribute': name, 'value': value}
    
    async def _handle_get_text(self, session_id: str, args: dict) -> dict:
        """Get element text content."""
        session = self._get_session(session_id)
        selector = args.get('selector')
        if not selector:
            raise ValueError("selector is required")
        
        text = await session.page.text_content(selector)
        
        return {'selector': selector, 'text': text}
    
    async def _handle_get_inner_html(self, session_id: str, args: dict) -> dict:
        """Get element inner HTML."""
        session = self._get_session(session_id)
        selector = args.get('selector')
        if not selector:
            raise ValueError("selector is required")
        
        html = await session.page.inner_html(selector)
        
        return {'selector': selector, 'html': html}
    
    async def _handle_get_input_value(self, session_id: str, args: dict) -> dict:
        """Get input field value."""
        session = self._get_session(session_id)
        selector = args.get('selector')
        if not selector:
            raise ValueError("selector is required")
        
        value = await session.page.input_value(selector)
        
        return {'selector': selector, 'value': value}
    
    async def _handle_is_visible(self, session_id: str, args: dict) -> dict:
        """Check if element is visible."""
        session = self._get_session(session_id)
        selector = args.get('selector')
        if not selector:
            raise ValueError("selector is required")
        
        visible = await session.page.is_visible(selector)
        
        return {'selector': selector, 'visible': visible}
    
    async def _handle_is_enabled(self, session_id: str, args: dict) -> dict:
        """Check if element is enabled."""
        session = self._get_session(session_id)
        selector = args.get('selector')
        if not selector:
            raise ValueError("selector is required")
        
        enabled = await session.page.is_enabled(selector)
        
        return {'selector': selector, 'enabled': enabled}
    
    async def _handle_is_checked(self, session_id: str, args: dict) -> dict:
        """Check if checkbox is checked."""
        session = self._get_session(session_id)
        selector = args.get('selector')
        if not selector:
            raise ValueError("selector is required")
        
        checked = await session.page.is_checked(selector)
        
        return {'selector': selector, 'checked': checked}
    
    async def _handle_query_selector(self, session_id: str, args: dict) -> dict:
        """Query single element."""
        session = self._get_session(session_id)
        selector = args.get('selector')
        if not selector:
            raise ValueError("selector is required")
        
        element = await session.page.query_selector(selector)
        
        return {'selector': selector, 'found': element is not None}
    
    async def _handle_query_selector_all(self, session_id: str, args: dict) -> dict:
        """Query all matching elements."""
        session = self._get_session(session_id)
        selector = args.get('selector')
        if not selector:
            raise ValueError("selector is required")
        
        elements = await session.page.query_selector_all(selector)
        
        return {'selector': selector, 'count': len(elements)}
    
    async def _handle_reload(self, session_id: str, args: dict) -> dict:
        """Reload the page."""
        session = self._get_session(session_id)
        wait_until = args.get('wait_until', 'networkidle')
        
        await session.page.reload(wait_until=wait_until)
        
        return {'url': session.page.url}
    
    async def _handle_go_back(self, session_id: str, args: dict) -> dict:
        """Go back in history."""
        session = self._get_session(session_id)
        
        await session.page.go_back()
        
        return {'url': session.page.url}
    
    async def _handle_go_forward(self, session_id: str, args: dict) -> dict:
        """Go forward in history."""
        session = self._get_session(session_id)
        
        await session.page.go_forward()
        
        return {'url': session.page.url}
    
    async def _handle_set_viewport_size(self, session_id: str, args: dict) -> dict:
        """Set viewport size."""
        session = self._get_session(session_id)
        width = args.get('width', 1280)
        height = args.get('height', 720)
        
        await session.page.set_viewport_size({'width': width, 'height': height})
        
        return {'width': width, 'height': height}
    
    async def _handle_cookies(self, session_id: str, args: dict) -> dict:
        """Get cookies."""
        session = self._get_session(session_id)
        
        cookies = await session.context.cookies()
        
        return {'cookies': cookies}
    
    async def _handle_set_cookies(self, session_id: str, args: dict) -> dict:
        """Set cookies."""
        session = self._get_session(session_id)
        cookies = args.get('cookies', [])
        
        await session.context.add_cookies(cookies)
        
        return {'set': len(cookies)}
    
    async def _handle_clear_cookies(self, session_id: str, args: dict) -> dict:
        """Clear cookies."""
        session = self._get_session(session_id)
        
        await session.context.clear_cookies()
        
        return {'cleared': True}
    
    async def _handle_close_session(self, session_id: str, args: dict) -> dict:
        """Close the current session."""
        await self._close_session(session_id)
        
        return {'closed': session_id}
    
    async def _handle_health(self, session_id: str, args: dict) -> dict:
        """Health check."""
        return {
            'status': 'healthy',
            'sessions': len(self.sessions),
            'max_sessions': MAX_SESSIONS,
            'browser': PLAYWRIGHT_BROWSER,
            'headless': PLAYWRIGHT_HEADLESS
        }
    
    async def _handle_login(self, session_id: str, args: dict) -> dict:
        """
        Convenience method for login flows.
        
        Args:
            url: Login page URL
            username_selector: Username field selector (default: #username)
            password_selector: Password field selector (default: #password)
            submit_selector: Submit button selector (default: button[type='submit'])
            username: Username value
            password: Password value
            success_url_pattern: Optional URL pattern to wait for after login
        """
        session = self._get_session(session_id)
        
        url = args.get('url')
        if not url:
            raise ValueError("url is required")
        
        username = args.get('username')
        password = args.get('password')
        if not username or not password:
            raise ValueError("username and password are required")
        
        username_selector = args.get('username_selector', '#username')
        password_selector = args.get('password_selector', '#password')
        submit_selector = args.get('submit_selector', "button[type='submit']")
        success_url_pattern = args.get('success_url_pattern')
        
        # Navigate to login page
        await session.page.goto(url, wait_until='networkidle')
        
        # Fill credentials
        await session.page.fill(username_selector, username)
        await session.page.fill(password_selector, password)
        
        # Submit form
        await session.page.click(submit_selector)
        
        # Wait for success URL if provided
        if success_url_pattern:
            await session.page.wait_for_url(success_url_pattern, timeout=10000)
        else:
            await session.page.wait_for_load_state('networkidle')
        
        return {
            'logged_in': True,
            'url': session.page.url,
            'title': await session.page.title()
        }


async def main():
    """Main entry point."""
    server = PlaywrightWebSocketServer()
    
    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
