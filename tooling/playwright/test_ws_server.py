#!/usr/bin/env python3
"""
Tests for Playwright WebSocket Server

These tests verify the WebSocket server functionality for the standalone
Playwright service container.

Run with:
    pytest tooling/playwright/test_ws_server.py -v

Author: netcup-api-filter project
Date: 2025-11-26
"""

import asyncio
import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Mark all tests in this module as async by default
# except for TestBrowserSession which has synchronous tests
pytestmark = pytest.mark.asyncio


class TestWebSocketServerCommands:
    """Test WebSocket server command handlers."""
    
    @pytest.fixture
    def mock_page(self):
        """Create a mock Playwright page."""
        page = AsyncMock()
        page.url = "https://example.com"
        page.title = AsyncMock(return_value="Example Page")
        page.content = AsyncMock(return_value="<html></html>")
        page.goto = AsyncMock()
        page.click = AsyncMock()
        page.fill = AsyncMock()
        page.screenshot = AsyncMock()
        page.evaluate = AsyncMock(return_value="result")
        page.wait_for_selector = AsyncMock()
        page.wait_for_url = AsyncMock()
        page.wait_for_load_state = AsyncMock()
        page.text_content = AsyncMock(return_value="Hello World")
        page.inner_html = AsyncMock(return_value="<p>Hello</p>")
        page.input_value = AsyncMock(return_value="input value")
        page.get_attribute = AsyncMock(return_value="attr value")
        page.is_visible = AsyncMock(return_value=True)
        page.is_enabled = AsyncMock(return_value=True)
        page.is_checked = AsyncMock(return_value=False)
        page.query_selector = AsyncMock(return_value=MagicMock())
        page.query_selector_all = AsyncMock(return_value=[MagicMock(), MagicMock()])
        page.reload = AsyncMock()
        page.go_back = AsyncMock()
        page.go_forward = AsyncMock()
        page.set_viewport_size = AsyncMock()
        page.select_option = AsyncMock()
        page.check = AsyncMock()
        page.uncheck = AsyncMock()
        page.hover = AsyncMock()
        page.focus = AsyncMock()
        page.keyboard = AsyncMock()
        page.keyboard.press = AsyncMock()
        page.locator = MagicMock()
        page.locator.return_value.press_sequentially = AsyncMock()
        page.locator.return_value.press = AsyncMock()
        return page
    
    @pytest.fixture
    def mock_context(self, mock_page):
        """Create a mock browser context."""
        context = AsyncMock()
        context.new_page = AsyncMock(return_value=mock_page)
        context.close = AsyncMock()
        context.cookies = AsyncMock(return_value=[{"name": "test", "value": "cookie"}])
        context.add_cookies = AsyncMock()
        context.clear_cookies = AsyncMock()
        return context
    
    @pytest.fixture
    def mock_browser(self, mock_context):
        """Create a mock browser."""
        browser = AsyncMock()
        browser.new_context = AsyncMock(return_value=mock_context)
        browser.close = AsyncMock()
        browser.is_connected = MagicMock(return_value=True)
        return browser
    
    @pytest.fixture
    async def server(self, mock_browser):
        """Create a PlaywrightWebSocketServer with mocked browser."""
        from ws_server import PlaywrightWebSocketServer
        
        server = PlaywrightWebSocketServer()
        server._browser = mock_browser
        
        # Create a test session
        from ws_server import BrowserSession
        session = BrowserSession(
            session_id="test_session",
            context=mock_browser.new_context.return_value,
            page=mock_browser.new_context.return_value.new_page.return_value
        )
        server.sessions["test_session"] = session
        
        return server
    
    async def test_handle_navigate(self, server, mock_page):
        """Test navigate command."""
        result = await server._handle_navigate("test_session", {"url": "https://test.com"})
        
        mock_page.goto.assert_called_once()
        assert result["url"] == "https://example.com"
        assert result["title"] == "Example Page"
    
    async def test_handle_click(self, server, mock_page):
        """Test click command."""
        result = await server._handle_click("test_session", {"selector": "#button"})
        
        mock_page.click.assert_called_once_with(
            "#button",
            timeout=10000,
            button='left',
            click_count=1
        )
        assert result["clicked"] == "#button"
    
    async def test_handle_fill(self, server, mock_page):
        """Test fill command."""
        result = await server._handle_fill("test_session", {
            "selector": "#input",
            "value": "test value"
        })
        
        mock_page.fill.assert_called_once_with("#input", "test value", timeout=10000)
        assert result["filled"] == "#input"
    
    async def test_handle_screenshot(self, server, mock_page):
        """Test screenshot command."""
        result = await server._handle_screenshot("test_session", {"path": "test.png"})
        
        mock_page.screenshot.assert_called_once()
        assert "path" in result
        assert result["url"] == "https://example.com"
    
    async def test_handle_evaluate(self, server, mock_page):
        """Test evaluate command."""
        result = await server._handle_evaluate("test_session", {"script": "document.title"})
        
        mock_page.evaluate.assert_called_once_with("document.title")
        assert result["result"] == "result"
    
    async def test_handle_get_content(self, server, mock_page):
        """Test get_content command."""
        result = await server._handle_get_content("test_session", {})
        
        mock_page.content.assert_called_once()
        assert result["content"] == "<html></html>"
    
    async def test_handle_get_url(self, server, mock_page):
        """Test get_url command."""
        result = await server._handle_get_url("test_session", {})
        
        assert result["url"] == "https://example.com"
        assert result["title"] == "Example Page"
    
    async def test_handle_wait_for_selector(self, server, mock_page):
        """Test wait_for_selector command."""
        result = await server._handle_wait_for_selector("test_session", {
            "selector": ".element"
        })
        
        mock_page.wait_for_selector.assert_called_once()
        assert result["found"] == ".element"
    
    async def test_handle_get_text(self, server, mock_page):
        """Test get_text command."""
        result = await server._handle_get_text("test_session", {"selector": "h1"})
        
        mock_page.text_content.assert_called_once_with("h1")
        assert result["text"] == "Hello World"
    
    async def test_handle_is_visible(self, server, mock_page):
        """Test is_visible command."""
        result = await server._handle_is_visible("test_session", {"selector": "#element"})
        
        mock_page.is_visible.assert_called_once_with("#element")
        assert result["visible"] is True
    
    async def test_handle_cookies(self, server):
        """Test cookies command."""
        result = await server._handle_cookies("test_session", {})
        
        assert "cookies" in result
        assert len(result["cookies"]) == 1
    
    async def test_handle_health(self, server):
        """Test health command."""
        result = await server._handle_health("test_session", {})
        
        assert result["status"] == "healthy"
        assert "sessions" in result
        assert "max_sessions" in result
    
    async def test_handle_login(self, server, mock_page):
        """Test login convenience command."""
        result = await server._handle_login("test_session", {
            "url": "https://example.com/login",
            "username": "admin",
            "password": "secret"
        })
        
        # Verify navigation
        mock_page.goto.assert_called_once()
        
        # Verify form fill
        assert mock_page.fill.call_count == 2  # username + password
        
        # Verify click
        mock_page.click.assert_called_once()
        
        assert result["logged_in"] is True
    
    async def test_handle_missing_selector(self, server):
        """Test error handling for missing required selector."""
        with pytest.raises(ValueError, match="selector is required"):
            await server._handle_click("test_session", {})
    
    async def test_handle_missing_url(self, server):
        """Test error handling for missing required URL."""
        with pytest.raises(ValueError, match="url is required"):
            await server._handle_navigate("test_session", {})
    
    async def test_session_not_found(self, server):
        """Test error handling for missing session."""
        with pytest.raises(ValueError, match="Session not found"):
            await server._handle_navigate("invalid_session", {"url": "https://test.com"})


class TestWebSocketClientCommands:
    """Test WebSocket client command methods."""
    
    @pytest.fixture
    def mock_ws(self):
        """Create a mock WebSocket connection."""
        ws = AsyncMock()
        ws.send = AsyncMock()
        ws.recv = AsyncMock()
        ws.close = AsyncMock()
        return ws
    
    @pytest.fixture
    async def client(self, mock_ws):
        """Create a WebSocket client with mocked connection."""
        from ws_client import PlaywrightWSClient
        
        client = PlaywrightWSClient("ws://localhost:3000")
        client._ws = mock_ws
        client._session_id = "test_session"
        
        # Mock the pending responses
        async def mock_send_command(command, args=None):
            # Return appropriate mock data based on command
            mock_responses = {
                'navigate': {'url': 'https://example.com', 'title': 'Example'},
                'screenshot': {'path': '/screenshots/test.png', 'url': 'https://example.com'},
                'click': {'clicked': args.get('selector') if args else '#button'},
                'fill': {'filled': args.get('selector') if args else '#input'},
                'get_url': {'url': 'https://example.com', 'title': 'Example'},
                'get_content': {'content': '<html></html>', 'url': 'https://example.com'},
                'get_text': {'text': 'Hello World', 'selector': args.get('selector') if args else 'h1'},
                'is_visible': {'visible': True, 'selector': '#element'},
                'is_enabled': {'enabled': True, 'selector': '#element'},
                'is_checked': {'checked': False, 'selector': '#checkbox'},
                'query_selector': {'found': True, 'selector': '#element'},
                'query_selector_all': {'count': 3, 'selector': '.items'},
                'cookies': {'cookies': [{'name': 'test', 'value': 'cookie'}]},
                'health': {'status': 'healthy', 'sessions': 1, 'max_sessions': 10},
                'login': {'logged_in': True, 'url': 'https://example.com/dashboard'},
            }
            return mock_responses.get(command, {})
        
        client._send_command = mock_send_command
        
        return client
    
    async def test_navigate(self, client):
        """Test navigate method."""
        result = await client.navigate("https://example.com")
        
        assert result['url'] == 'https://example.com'
        assert result['title'] == 'Example'
    
    async def test_screenshot(self, client):
        """Test screenshot method."""
        result = await client.screenshot("test.png")
        
        assert result['path'] == '/screenshots/test.png'
    
    async def test_click(self, client):
        """Test click method."""
        result = await client.click("#button")
        
        assert result['clicked'] == '#button'
    
    async def test_fill(self, client):
        """Test fill method."""
        result = await client.fill("#input", "test value")
        
        assert result['filled'] == '#input'
    
    async def test_get_url(self, client):
        """Test get_url method."""
        result = await client.get_url()
        
        assert result['url'] == 'https://example.com'
    
    async def test_get_text(self, client):
        """Test get_text method."""
        result = await client.get_text("h1")
        
        assert result['text'] == 'Hello World'
    
    async def test_is_visible(self, client):
        """Test is_visible method."""
        result = await client.is_visible("#element")
        
        assert result is True
    
    async def test_query_selector_all(self, client):
        """Test query_selector_all method."""
        result = await client.query_selector_all(".items")
        
        assert result == 3
    
    async def test_cookies(self, client):
        """Test cookies method."""
        result = await client.cookies()
        
        assert len(result) == 1
        assert result[0]['name'] == 'test'
    
    async def test_health(self, client):
        """Test health method."""
        result = await client.health()
        
        assert result['status'] == 'healthy'
    
    async def test_login(self, client):
        """Test login convenience method."""
        result = await client.login(
            url="https://example.com/login",
            username="admin",
            password="secret"
        )
        
        assert result['logged_in'] is True


class TestBrowserSession:
    """Test BrowserSession dataclass."""
    
    async def test_session_touch(self):
        """Test session touch updates last_used."""
        from ws_server import BrowserSession
        import time
        
        session = BrowserSession(
            session_id="test",
            context=MagicMock(),
            page=MagicMock()
        )
        
        initial_time = session.last_used
        await asyncio.sleep(0.01)
        session.touch()
        
        assert session.last_used > initial_time
    
    async def test_session_expired(self):
        """Test session expiration check."""
        from ws_server import BrowserSession
        import time
        
        session = BrowserSession(
            session_id="test",
            context=MagicMock(),
            page=MagicMock()
        )
        
        # Not expired with long timeout
        assert session.is_expired(3600) is False
        
        # Simulate old session
        session.last_used = time.time() - 100
        assert session.is_expired(60) is True


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
