"""Shared configuration for UI regression tests."""
from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urljoin


@dataclass
class UiTestConfig:
    """Environment-driven configuration for UI regression coverage."""

    base_url: str = os.getenv("UI_BASE_URL", "https://naf.vxxu.de")
    mcp_url: str = os.getenv("UI_MCP_URL", "http://172.17.0.1:8765/mcp")
    admin_username: str = os.getenv("UI_ADMIN_USERNAME", "admin")
    admin_password: str = os.getenv("UI_ADMIN_PASSWORD", "admin")
    admin_new_password: str | None = os.getenv("UI_ADMIN_NEW_PASSWORD") or None

    client_id: str = os.getenv("UI_CLIENT_ID", "test_qweqweqwe_vi")
    client_token: str = os.getenv("UI_CLIENT_TOKEN", "qweqweqwe-vi-readonly")
    client_domain: str = os.getenv("UI_CLIENT_DOMAIN", "qweqweqwe.vi")

    screenshot_prefix: str = os.getenv("UI_SCREENSHOT_PREFIX", "ui-regression")

    def url(self, path: str) -> str:
        """Return an absolute URL for the provided path."""
        return urljoin(self.base_url.rstrip("/") + "/", path.lstrip("/"))

    def note_password_change(self) -> None:
        """Update in-memory password after a successful rotation."""
        if self.admin_new_password:
            self.admin_password = self.admin_new_password


settings = UiTestConfig()
