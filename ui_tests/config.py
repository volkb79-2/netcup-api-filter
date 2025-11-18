"""Shared configuration for UI regression tests."""
from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Dict, Iterator, List
from urllib.parse import urljoin


@dataclass
class UiTargetProfile:
    """Concrete set of credentials + host for a UI test target."""

    name: str
    base_url: str
    admin_username: str
    admin_password: str
    admin_new_password: str | None
    client_id: str
    client_token: str
    client_domain: str
    allow_writes: bool = True


class UiTestConfig:
    """Environment-driven configuration with optional smoke targets."""

    def __init__(self) -> None:
        self.mcp_url: str = os.getenv("UI_MCP_URL", "http://172.17.0.1:8765/mcp")
        self.screenshot_prefix: str = os.getenv("UI_SCREENSHOT_PREFIX", "ui-regression")

        primary_allow_writes = os.getenv("UI_ALLOW_WRITES", "1") not in {"0", "false", "False"}
        primary = UiTargetProfile(
            name="primary",
            base_url=os.getenv("UI_BASE_URL", "https://naf.vxxu.de"),
            admin_username=os.getenv("UI_ADMIN_USERNAME", "admin"),
            admin_password=os.getenv("UI_ADMIN_PASSWORD", "admin"),
            admin_new_password=os.getenv("UI_ADMIN_NEW_PASSWORD") or None,
            client_id=os.getenv("UI_CLIENT_ID", "test_qweqweqwe_vi"),
            client_token=os.getenv("UI_CLIENT_TOKEN", "qweqweqwe-vi-readonly"),
            client_domain=os.getenv("UI_CLIENT_DOMAIN", "qweqweqwe.vi"),
            allow_writes=primary_allow_writes,
        )

        smoke_base = os.getenv("UI_SMOKE_BASE_URL")
        smoke_profile: UiTargetProfile | None = None
        if smoke_base:
            smoke_allow_writes = os.getenv("UI_SMOKE_ALLOW_WRITES", "0") in {"1", "true", "True"}
            smoke_profile = UiTargetProfile(
                name="smoke",
                base_url=smoke_base,
                admin_username=os.getenv("UI_SMOKE_ADMIN_USERNAME", primary.admin_username),
                admin_password=os.getenv("UI_SMOKE_ADMIN_PASSWORD", primary.admin_password),
                admin_new_password=os.getenv("UI_SMOKE_ADMIN_NEW_PASSWORD")
                or primary.admin_new_password,
                client_id=os.getenv("UI_SMOKE_CLIENT_ID", primary.client_id),
                client_token=os.getenv("UI_SMOKE_CLIENT_TOKEN", primary.client_token),
                client_domain=os.getenv("UI_SMOKE_CLIENT_DOMAIN", primary.client_domain),
                allow_writes=smoke_allow_writes,
            )

        self._profiles: Dict[str, UiTargetProfile] = {primary.name: primary}
        if smoke_profile:
            self._profiles[smoke_profile.name] = smoke_profile

        self._active: UiTargetProfile = primary

    # ---- active profile helpers -------------------------------------------------
    @property
    def base_url(self) -> str:
        return self._active.base_url

    @property
    def admin_username(self) -> str:
        return self._active.admin_username

    @property
    def admin_password(self) -> str:
        return self._active.admin_password

    @admin_password.setter
    def admin_password(self, value: str) -> None:
        self._active.admin_password = value

    @property
    def admin_new_password(self) -> str | None:
        return self._active.admin_new_password

    @property
    def client_id(self) -> str:
        return self._active.client_id

    @property
    def client_token(self) -> str:
        return self._active.client_token

    @property
    def client_domain(self) -> str:
        return self._active.client_domain

    @property
    def allow_writes(self) -> bool:
        return self._active.allow_writes

    # ---- profile orchestration --------------------------------------------------
    def profiles(self) -> List[UiTargetProfile]:
        return list(self._profiles.values())

    @contextmanager
    def use_profile(self, profile: UiTargetProfile) -> Iterator[UiTargetProfile]:
        previous = self._active
        self._active = profile
        try:
            yield profile
        finally:
            self._active = previous

    # ---- utility helpers --------------------------------------------------------
    def url(self, path: str) -> str:
        """Return an absolute URL for the provided path."""
        return urljoin(self.base_url.rstrip("/") + "/", path.lstrip("/"))

    def note_password_change(self) -> None:
        """Update in-memory password after a successful rotation."""
        if self.admin_new_password:
            self.admin_password = self.admin_new_password


settings = UiTestConfig()
