"""Shared configuration for UI regression tests.

Configuration is loaded from deployment_state.json based on DEPLOYMENT_TARGET:
- local: deploy-local/deployment_state.json
- webhosting: deploy-local/screenshots/.deployment_state_webhosting.json

Set DEPLOYMENT_TARGET=local or DEPLOYMENT_TARGET=webhosting to select.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional
from urllib.parse import urljoin

from ui_tests.deployment_state import (
    DeploymentTarget,
    get_deployment_target,
    get_state_file_path,
    load_state,
    state_exists,
    get_base_url as get_default_base_url,
)


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
    deployment_target: str = "local"
    
    @property
    def client_token(self) -> str:
        """Full authentication token in client_id:secret_key format."""
        return f"{self.client_id}:{self.client_secret_key}"


class UiTestConfig:
    """Configuration loaded from deployment_state.json.
    
    Uses DEPLOYMENT_TARGET env var to select which deployment to test:
    - "local" (default): Tests against deploy-local/
    - "webhosting": Tests against production webhosting
    
    All credentials come from the JSON state file, with optional
    environment variable overrides for specific values.
    """

    def __init__(self) -> None:
        # Determine deployment target
        self._deployment_target = get_deployment_target()
        
        # Configuration options with defaults
        headless_str = os.getenv("PLAYWRIGHT_HEADLESS", "true")
        self.playwright_headless: bool = headless_str.lower() in {"true", "1"}
        
        self.screenshot_prefix: str = os.getenv("UI_SCREENSHOT_PREFIX", "ui-regression")

        allow_writes_str = os.getenv("UI_ALLOW_WRITES", "1")
        primary_allow_writes = allow_writes_str not in {"0", "false", "False"}
        
        # Base URL: env override > default for target
        base_url = os.getenv("UI_BASE_URL") or get_default_base_url(self._deployment_target)
        
        # Load state from JSON (REQUIRED - no fallback)
        state_file = get_state_file_path(self._deployment_target)
        if not state_exists(self._deployment_target):
            raise RuntimeError(
                f"Deployment state file not found: {state_file}\n"
                f"DEPLOYMENT_TARGET={self._deployment_target}\n"
                f"\n"
                f"For local: Run ./build-and-deploy-local.sh\n"
                f"For webhosting: Run ./build-and-deploy.sh and ensure state is synced"
            )
        
        state = load_state(self._deployment_target)
        admin = state.admin
        primary_client = state.get_primary_client()
        
        # Allow environment variable overrides for specific credentials
        admin_username = os.getenv("DEPLOYED_ADMIN_USERNAME") or admin.username
        admin_password = os.getenv("DEPLOYED_ADMIN_PASSWORD") or admin.password
        client_id = os.getenv("DEPLOYED_CLIENT_ID") or (primary_client.client_id if primary_client else "")
        client_secret_key = os.getenv("DEPLOYED_CLIENT_SECRET_KEY") or (primary_client.secret_key if primary_client else "")
        
        print(f"[CONFIG] Loaded from {state_file.name} (target={self._deployment_target}, updated={state.last_updated_at or 'unknown'})")
        
        if not all([admin_username, admin_password]):
            raise RuntimeError(
                f"Admin credentials not found in {state_file}\n"
                f"The state file may be corrupted or incomplete."
            )
        
        primary = UiTargetProfile(
            name="primary",
            base_url=base_url,
            admin_username=admin_username,
            admin_password=admin_password,
            admin_new_password=os.getenv("UI_ADMIN_NEW_PASSWORD") or None,
            client_id=client_id,
            client_secret_key=client_secret_key,
            client_domain=os.getenv("UI_CLIENT_DOMAIN", "example.com"),  # Match preseeded clients
            allow_writes=primary_allow_writes,
            deployment_target=self._deployment_target,
        )

        # Optional smoke profile for production testing
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
                deployment_target=self._deployment_target,
            )

        self._profiles: Dict[str, UiTargetProfile] = {primary.name: primary}
        if smoke_profile:
            self._profiles[smoke_profile.name] = smoke_profile

        self._active: UiTargetProfile = primary

    # ---- deployment target info -------------------------------------------------
    @property
    def deployment_target(self) -> DeploymentTarget:
        """Current deployment target (local or webhosting)."""
        return self._deployment_target

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
        """Context manager to temporarily switch active profile.
        
        IMPORTANT: Creates a COPY of the profile to prevent state mutations
        from persisting across test runs in the same Python process.
        """
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

    def refresh_credentials(self) -> None:
        """Reload credentials from deployment_state.json.
        
        Call this at the start of a test to ensure you have the latest
        credentials, especially after another test might have changed passwords.
        
        This reads fresh from the JSON file, bypassing any cached values.
        """
        try:
            state = load_state(self._deployment_target)
        except FileNotFoundError:
            print(f"[CONFIG] Warning: State file not found during refresh, keeping current values")
            return
        
        admin = state.admin
        primary_client = state.get_primary_client()
        
        # Update the active profile with fresh credentials
        if admin.password != self._active.admin_password:
            print(f"[CONFIG] Refreshed admin password (changed: {admin.password_changed_at or 'unknown'})")
            self._active.admin_password = admin.password
        
        if admin.username != self._active.admin_username:
            self._active.admin_username = admin.username
        
        # Update client credentials if changed
        if primary_client:
            if primary_client.client_id != self._active.client_id:
                self._active.client_id = primary_client.client_id
            if primary_client.secret_key != self._active.client_secret_key:
                self._active.client_secret_key = primary_client.secret_key


# Singleton instance - initialized on first import
settings = UiTestConfig()
