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
    client_secret_key: str
    client_domain: str
    allow_writes: bool = True
    
    @property
    def client_token(self) -> str:
        """Full authentication token in client_id:secret_key format."""
        return f"{self.client_id}:{self.client_secret_key}"


class UiTestConfig:
    """Environment-driven configuration with optional smoke targets."""

    def __init__(self) -> None:
        # Load deployment state from .env.webhosting if not in environment
        self._load_deployment_state()
        
        self.playwright_headless: bool = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() in {"true", "1"}
        self.screenshot_prefix: str = os.getenv("UI_SCREENSHOT_PREFIX", "ui-regression")

        primary_allow_writes = os.getenv("UI_ALLOW_WRITES", "1") not in {"0", "false", "False"}
        
        # Try to get admin password from deployment state first, fall back to env/default
        deployed_password = os.getenv("DEPLOYED_ADMIN_PASSWORD")
        admin_password = deployed_password if deployed_password else os.getenv("UI_ADMIN_PASSWORD", "admin")
        
        primary = UiTargetProfile(
            name="primary",
            base_url=os.getenv("UI_BASE_URL", "https://naf.vxxu.de"),
            admin_username=os.getenv("UI_ADMIN_USERNAME", "admin"),
            admin_password=admin_password,
            admin_new_password=os.getenv("UI_ADMIN_NEW_PASSWORD") or None,
            client_id=os.getenv("UI_CLIENT_ID", "test_qweqweqwe_vi"),
            client_secret_key=os.getenv("UI_CLIENT_SECRET_KEY", "qweqweqwe_vi_readonly_secret_key_12345"),
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
                client_secret_key=os.getenv("UI_SMOKE_CLIENT_SECRET_KEY", primary.client_secret_key),
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

    def _load_deployment_state(self) -> None:
        """Load deployment state from .env.webhosting and defaults from .env.defaults.
        
        Priority order:
        1. Environment variables (highest priority)
        2. .env.webhosting (updated by tests after deployment)
        3. .env.defaults (single source of truth for initial values)
        """
        import os.path
        
        def load_env_file(file_path: str, prefix: str = "") -> None:
            """Load key=value pairs from file into environment."""
            if not os.path.exists(file_path):
                return
            try:
                with open(file_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            key = key.strip()
                            value = value.strip()
                            # Map DEFAULT_* to DEPLOYED_* for consistency
                            if prefix and key.startswith(prefix):
                                deployed_key = key.replace(prefix, "DEPLOYED_", 1)
                                if deployed_key not in os.environ and value:
                                    os.environ[deployed_key] = value
                            # Only set if not already in environment
                            elif key not in os.environ and value:
                                os.environ[key] = value
            except Exception:
                pass  # Silently ignore errors
        
        # Load .env.defaults first (lowest priority - provides fallback values)
        defaults_paths = [
            '/workspace/.env.defaults',  # Playwright container
            os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env.defaults'),
        ]
        for path in defaults_paths:
            if os.path.exists(path):
                load_env_file(path, prefix="DEFAULT_")
                break
        
        # Then load .env.webhosting (higher priority - updated by tests, should override defaults)
        webhosting_paths = [
            '/screenshots/.env.webhosting',  # Playwright container writable mount
            os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env.webhosting'),
        ]
        for path in webhosting_paths:
            if os.path.exists(path):
                # Load and OVERRIDE any existing values from .env.defaults
                try:
                    with open(path, 'r') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#') and '=' in line:
                                key, value = line.split('=', 1)
                                key = key.strip()
                                value = value.strip()
                                if value:  # Always set non-empty values, overriding defaults
                                    os.environ[key] = value
                except Exception:
                    pass
                break

    @contextmanager
    def use_profile(self, profile: UiTargetProfile) -> Iterator[UiTargetProfile]:
        """Context manager to temporarily switch active profile.
        
        IMPORTANT: Creates a COPY of the profile to prevent state mutations
        from persisting across test runs in the same Python process.
        """
        from copy import deepcopy
        previous = self._active
        # Use a deep copy to prevent mutations from affecting the original
        self._active = deepcopy(profile)
        try:
            yield self._active
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
