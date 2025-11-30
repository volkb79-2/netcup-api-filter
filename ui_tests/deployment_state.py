"""Unified deployment state management for UI tests.

This module provides a single source of truth for deployment state that:
1. Is created at build time with initial values
2. Gets updated by tests when state changes (password changes)
3. Is read fresh by each test step (not cached in env vars)

Supports two deployment targets:
- local: deploy-local/deployment_state.json
- webhosting: Remote state synced to screenshots/.deployment_state_webhosting.json

Selection is via DEPLOYMENT_TARGET env var ("local" or "webhosting").
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal, Optional

# Type alias for deployment targets
DeploymentTarget = Literal["local", "webhosting"]

# Well-known state file paths (in REPO_ROOT, not deployed)
# These files contain secrets and must NEVER be deployed to webhosting
WORKSPACE_ROOT = Path("/workspaces/netcup-api-filter")
STATE_FILE_PATHS = {
    "local": WORKSPACE_ROOT / "deployment_state_local.json",
    "webhosting": WORKSPACE_ROOT / "deployment_state_webhosting.json",
}


@dataclass
class ClientCredentials:
    """Client credentials for API access."""
    client_id: str
    secret_key: str
    description: str = ""
    is_primary: bool = False
    
    @property
    def token(self) -> str:
        """Full authentication token in client_id:secret_key format."""
        return f"{self.client_id}:{self.secret_key}"


@dataclass
class AdminCredentials:
    """Admin credentials with change tracking."""
    username: str
    password: str
    password_changed_at: Optional[str] = None


@dataclass
class BuildInfo:
    """Build-time metadata."""
    built_at: str
    git_commit: str = ""
    git_branch: str = ""
    builder: str = ""
    source: str = "build_deployment.py"


@dataclass
class DeploymentState:
    """Complete deployment state including build info and runtime state."""
    build: BuildInfo
    admin: AdminCredentials
    clients: List[ClientCredentials] = field(default_factory=list)
    last_updated_at: str = ""
    updated_by: str = ""
    target: str = "local"  # Which deployment this state is for
    
    def get_primary_client(self) -> Optional[ClientCredentials]:
        """Get the primary client (first one or one marked as primary)."""
        for client in self.clients:
            if client.is_primary:
                return client
        return self.clients[0] if self.clients else None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "target": self.target,
            "build": asdict(self.build),
            "admin": asdict(self.admin),
            "clients": [asdict(c) for c in self.clients],
            "last_updated_at": self.last_updated_at,
            "updated_by": self.updated_by,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "DeploymentState":
        """Create from dictionary (JSON deserialization)."""
        build = BuildInfo(**data.get("build", {}))
        admin = AdminCredentials(**data.get("admin", {}))
        clients = [ClientCredentials(**c) for c in data.get("clients", [])]
        return cls(
            build=build,
            admin=admin,
            clients=clients,
            last_updated_at=data.get("last_updated_at", ""),
            updated_by=data.get("updated_by", ""),
            target=data.get("target", "local"),
        )


def get_deployment_target() -> DeploymentTarget:
    """Get the current deployment target from environment.
    
    Returns:
        "local" or "webhosting"
        
    Raises:
        ValueError: If DEPLOYMENT_TARGET is set to an invalid value
    """
    target = os.getenv("DEPLOYMENT_TARGET", "local").lower()
    
    if target not in ("local", "webhosting"):
        raise ValueError(
            f"Invalid DEPLOYMENT_TARGET: {target}\n"
            f"Must be 'local' or 'webhosting'"
        )
    
    return target  # type: ignore


def get_state_file_path(target: Optional[DeploymentTarget] = None) -> Path:
    """Get the path to the deployment state file.
    
    Args:
        target: Explicit target, or None to use DEPLOYMENT_TARGET env var
        
    Returns:
        Path to the state JSON file
    """
    # Explicit path takes absolute precedence (for testing/debugging)
    explicit_path = os.getenv("DEPLOYMENT_STATE_FILE")
    if explicit_path:
        return Path(explicit_path)
    
    if target is None:
        target = get_deployment_target()
    
    return STATE_FILE_PATHS[target]


def load_state(target: Optional[DeploymentTarget] = None) -> DeploymentState:
    """Load deployment state from JSON file.
    
    This function reads the state FRESH each time it's called,
    ensuring tests always have the latest state (e.g., after password changes).
    
    Args:
        target: Explicit target, or None to use DEPLOYMENT_TARGET env var
    
    Returns:
        DeploymentState with current values
        
    Raises:
        FileNotFoundError: If state file doesn't exist
        json.JSONDecodeError: If state file is invalid JSON
    """
    if target is None:
        target = get_deployment_target()
    
    state_file = get_state_file_path(target)
    
    if not state_file.exists():
        raise FileNotFoundError(
            f"Deployment state file not found: {state_file}\n"
            f"For local: Run build-and-deploy-local.sh\n"
            f"For webhosting: Run build-and-deploy.sh and sync state"
        )
    
    with open(state_file, 'r') as f:
        data = json.load(f)
    
    return DeploymentState.from_dict(data)


def save_state(
    state: DeploymentState, 
    updated_by: str = "unknown",
    target: Optional[DeploymentTarget] = None
) -> None:
    """Save deployment state to JSON file.
    
    Updates the last_updated_at timestamp and updated_by field.
    
    Args:
        state: The state to save
        updated_by: Name of the test/process that updated the state
        target: Explicit target, or None to use DEPLOYMENT_TARGET env var
    """
    if target is None:
        target = get_deployment_target()
    
    state_file = get_state_file_path(target)
    
    # Update metadata
    state.last_updated_at = datetime.now(timezone.utc).isoformat()
    state.updated_by = updated_by
    state.target = target
    
    # Ensure directory exists
    state_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(state_file, 'w') as f:
        json.dump(state.to_dict(), f, indent=2)
    
    print(f"[STATE] Updated {state_file} by {updated_by}")


def update_admin_password(
    new_password: str, 
    updated_by: str = "unknown",
    target: Optional[DeploymentTarget] = None
) -> None:
    """Update the admin password in the state file.
    
    This is called after a password change is confirmed successful.
    
    Args:
        new_password: The new password
        updated_by: Name of the test/process that changed it
        target: Explicit target, or None to use DEPLOYMENT_TARGET env var
    """
    state = load_state(target)
    state.admin.password = new_password
    state.admin.password_changed_at = datetime.now(timezone.utc).isoformat()
    save_state(state, updated_by, target)


def get_admin_credentials(target: Optional[DeploymentTarget] = None) -> tuple[str, str]:
    """Get current admin username and password.
    
    Reads fresh from the state file each time.
    
    Args:
        target: Explicit target, or None to use DEPLOYMENT_TARGET env var
    
    Returns:
        Tuple of (username, password)
    """
    state = load_state(target)
    return state.admin.username, state.admin.password


def get_primary_client(target: Optional[DeploymentTarget] = None) -> ClientCredentials:
    """Get the primary client for testing.
    
    Reads fresh from the state file each time.
    
    Args:
        target: Explicit target, or None to use DEPLOYMENT_TARGET env var
    
    Returns:
        ClientCredentials for the primary test client
        
    Raises:
        ValueError: If no clients are configured
    """
    state = load_state(target)
    client = state.get_primary_client()
    if not client:
        raise ValueError("No clients configured in deployment state")
    return client


def state_exists(target: Optional[DeploymentTarget] = None) -> bool:
    """Check if the state file exists for the given target.
    
    Args:
        target: Explicit target, or None to use DEPLOYMENT_TARGET env var
        
    Returns:
        True if state file exists, False otherwise
    """
    state_file = get_state_file_path(target)
    return state_file.exists()


def get_base_url(target: Optional[DeploymentTarget] = None) -> str:
    """Get the base URL for the deployment target.
    
    Args:
        target: Explicit target, or None to use DEPLOYMENT_TARGET env var
        
    Returns:
        Base URL for the target deployment
    """
    if target is None:
        target = get_deployment_target()
    
    # Check environment override first
    env_url = os.getenv("UI_BASE_URL")
    if env_url:
        return env_url
    
    # Default URLs for each target
    if target == "local":
        return "http://localhost:5100"
    else:  # webhosting
        return "https://naf.vxxu.de"
