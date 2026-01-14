"""Helpers for loading config defaults from .env/.env.defaults.

These defaults are used as a last-resort fallback when environment variables
are not set (e.g., during local build-time seeding).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict


@lru_cache(maxsize=1)
def load_defaults() -> Dict[str, str]:
    """Load key/value defaults from .env (preferred) or .env.defaults (fallback).

    Returns empty dict if neither file exists (e.g., in production where all
    config is supplied via environment variables).
    """
    search_paths = []
    
    # Try Path.cwd() but catch OSError if working directory was deleted
    try:
        search_paths.append(Path.cwd() / ".env")
        search_paths.append(Path.cwd() / ".env.defaults")
    except (OSError, FileNotFoundError):
        pass  # Working directory doesn't exist, skip
    
    # Always try relative to this source file
    repo_root = Path(__file__).resolve().parent.parent.parent
    search_paths.append(repo_root / ".env")
    search_paths.append(repo_root / ".env.defaults")

    for env_path in search_paths:
        if env_path.exists():
            return _parse_env_file(env_path)

    # Return empty dict instead of raising - allows running without env files
    # (e.g., in production where all config comes from environment variables)
    return {}


def get_default(key: str, fallback: str | None = None) -> str | None:
    """Return the configured default for a key (or fallback)."""
    return load_defaults().get(key, fallback)


def require_default(key: str) -> str:
    """Return the configured default or raise if missing."""
    value = load_defaults().get(key)
    if value is None:
        raise RuntimeError(f"Required default '{key}' missing from .env/.env.defaults")
    return value


def _parse_env_file(env_path: Path) -> Dict[str, str]:
    defaults: Dict[str, str] = {}
    with env_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip()
            # Strip surrounding quotes (single or double)
            if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
                value = value[1:-1]
            defaults[key.strip()] = value
    return defaults
