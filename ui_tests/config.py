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
    """Environment-driven configuration with optional smoke targets.
    
    Configuration priority (highest to lowest):
    1. Explicit environment variables (UI_ADMIN_PASSWORD, etc.)
    2. Deployment state files (.env.local or .env.webhosting)
    3. Default values from .env.defaults
    """

    def __init__(self) -> None:
        # Load deployment state from env file if specified
        self._load_deployment_state()
        
        # Fail-fast: require explicit configuration or use .env.defaults values (loaded above)
        headless_str = os.getenv("PLAYWRIGHT_HEADLESS")
        if not headless_str:
            headless_str = "true"
            print("[CONFIG] WARNING: PLAYWRIGHT_HEADLESS not set, using default: true")
        self.playwright_headless: bool = headless_str.lower() in {"true", "1"}
        
        screenshot_prefix = os.getenv("UI_SCREENSHOT_PREFIX")
        if not screenshot_prefix:
            screenshot_prefix = "ui-regression"
            print("[CONFIG] WARNING: UI_SCREENSHOT_PREFIX not set, using default: ui-regression")
        self.screenshot_prefix: str = screenshot_prefix

        allow_writes_str = os.getenv("UI_ALLOW_WRITES")
        if not allow_writes_str:
            allow_writes_str = "1"
            print("[CONFIG] WARNING: UI_ALLOW_WRITES not set, using default: 1 (writes enabled)")
        primary_allow_writes = allow_writes_str not in {"0", "false", "False"}
        
        # Use DEPLOYED_* variables from environment (NO FILE ACCESS)
        # Playwright container is a pure service - credentials passed via env vars
        base_url = os.getenv("UI_BASE_URL")
        if not base_url:
            raise RuntimeError("base_url not set. Need to be set according to deployment.")
        
        admin_username = os.getenv("DEPLOYED_ADMIN_USERNAME") or os.getenv("UI_ADMIN_USERNAME")
        if not admin_username:
            raise RuntimeError("DEPLOYED_ADMIN_USERNAME and UI_ADMIN_USERNAME not set. Load from .env.defaults or set explicitly.")
        
        admin_password = os.getenv("DEPLOYED_ADMIN_PASSWORD") or os.getenv("UI_ADMIN_PASSWORD")
        if not admin_password:
            raise RuntimeError("DEPLOYED_ADMIN_PASSWORD and UI_ADMIN_PASSWORD not set. Load from .env.defaults or set explicitly.")
        
        client_id = os.getenv("DEPLOYED_CLIENT_ID") or os.getenv("UI_CLIENT_ID")
        if not client_id:
            raise RuntimeError("DEPLOYED_CLIENT_ID and UI_CLIENT_ID not set. Load from .env.defaults or set explicitly.")
        
        client_secret_key = os.getenv("DEPLOYED_CLIENT_SECRET_KEY") or os.getenv("UI_CLIENT_SECRET_KEY")
        if not client_secret_key:
            raise RuntimeError("DEPLOYED_CLIENT_SECRET_KEY and UI_CLIENT_SECRET_KEY not set. Load from .env.defaults or set explicitly.")
        
        primary = UiTargetProfile(
            name="primary",
            base_url=base_url,
            admin_username=admin_username,
            admin_password=admin_password,
            admin_new_password=os.getenv("UI_ADMIN_NEW_PASSWORD") or None,
            client_id=client_id,
            client_secret_key=client_secret_key,
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
        """Load deployment state from environment-specific files.
        
        Priority order (highest to lowest):
        1. Explicit environment variables (set by caller/CI)
        2. Deployment-specific env file (.env.local or .env.webhosting)
        3. .env.defaults (fallback default values)
        
        The deployment file is auto-detected: .env.local if exists, else .env.webhosting.
        Override with DEPLOYMENT_ENV_FILE environment variable.
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
                                # Only set defaults if not already in environment
                                if deployed_key not in os.environ and value:
                                    os.environ[deployed_key] = value
                            # No prefix = deployment-specific file
                            # BUT: respect already-set environment variables (explicit > file)
                            elif not prefix and value:
                                if key not in os.environ:
                                    os.environ[key] = value
                            # With prefix but no match = keep if not set
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
        
        # Load deployment-specific env file (higher priority)
        deployment_env_file = os.getenv("DEPLOYMENT_ENV_FILE")
        
        if deployment_env_file:
            # Explicit file specified via environment variable
            load_env_file(deployment_env_file)
        else:
            # Auto-detect: prefer .env.local (local deployment), fallback to .env.webhosting
            possible_paths = [
                os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env.local'),
                '/screenshots/.env.local',  # Playwright container
                os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env.webhosting'),
                '/screenshots/.env.webhosting',  # Playwright container writable mount
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    load_env_file(path)
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
