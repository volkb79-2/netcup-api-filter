"""Thin wrapper around the MCP Playwright tools for ergonomic assertions."""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Dict, AsyncIterator

import anyio
import mcp
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult

from ui_tests.config import settings


@dataclass
class ToolError(Exception):
    """Raised when the remote MCP tool invocation fails."""

    name: str
    payload: Dict[str, Any]
    message: str

    def __str__(self) -> str:  # pragma: no cover - human readable helper
        return f"{self.name} failed ({self.message}) with payload={self.payload}"


class Browser:
    """Convenience wrapper over the MCP Playwright tools."""

    def __init__(self, session: mcp.ClientSession) -> None:
        self._session = session
        self.current_url: str | None = None
        self.current_title: str | None = None

    async def _call(self, tool_name: str, **arguments: Any) -> Dict[str, Any]:
        payload = arguments or None
        result: CallToolResult = await self._session.call_tool(tool_name, payload)
        if result.isError:
            message = ""
            if result.content:
                for chunk in result.content:
                    if hasattr(chunk, "text"):
                        message = chunk.text or ""
                        break
            raise ToolError(name=tool_name, payload=arguments, message=message or "unknown error")
        return result.structuredContent or {}

    async def reset(self) -> Dict[str, Any]:
        return await self._call("reset")

    async def goto(self, url: str) -> Dict[str, Any]:
        data = await self._call("goto", url=url)
        self.current_url = data.get("url", url)
        self.current_title = data.get("title")
        return data

    async def fill(self, selector: str, value: str) -> Dict[str, Any]:
        return await self._call("fill", selector=selector, value=value)

    async def click(self, selector: str, press_enter: bool | None = None) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {"selector": selector}
        if press_enter:
            kwargs["press_enter"] = True
        data = await self._call("click", **kwargs)
        self.current_url = data.get("url", self.current_url)
        return data

    async def select(self, selector: str, value: str | list[str]) -> Dict[str, Any]:
        return await self._call("select_option", selector=selector, value=value)

    async def text(self, selector: str) -> str:
        data = await self._call("text", selector=selector)
        return data.get("text", "")

    async def get_attribute(self, selector: str, attribute: str) -> str:
        data = await self._call("get_attribute", selector=selector, attribute=attribute)
        return data.get("value", "")

    async def html(self, selector: str) -> str:
        data = await self._call("inner_html", selector=selector)
        return data.get("html", "")

    async def screenshot(self, name: str) -> str:
        data = await self._call("screenshot", name=name)
        return data.get("path", "")

    async def submit(self, selector: str) -> Dict[str, Any]:
        data = await self._call("submit_form", selector=selector)
        self.current_url = data.get("url", self.current_url)
        return data

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
    """Yield a Browser instance wired up to the MCP Playwright transport."""

    async with streamablehttp_client(settings.mcp_url) as (read, write, _):
        async with mcp.ClientSession(read, write) as session:
            await session.initialize()
            browser = Browser(session)
            await browser.reset()
            yield browser
