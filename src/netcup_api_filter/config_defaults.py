"""Helpers for loading config defaults from .env.defaults."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict


@lru_cache(maxsize=1)
def load_defaults() -> Dict[str, str]:
    """Load key/value defaults from .env.defaults with graceful fallback.
    
    Returns empty dict if .env.defaults not found (e.g., in production with env vars).
    """
    search_paths = [
        Path.cwd() / ".env.defaults",
        Path(__file__).resolve().parent.parent.parent / ".env.defaults",
    ]

    for env_path in search_paths:
        if env_path.exists():
            return _parse_env_file(env_path)

    # Return empty dict instead of raising - allows running without .env.defaults
    # (e.g., in production where all config comes from environment variables)
    return {}


def get_default(key: str, fallback: str | None = None) -> str | None:
    """Return the configured default for a key (or fallback)."""
    return load_defaults().get(key, fallback)


def require_default(key: str) -> str:
    """Return the configured default or raise if missing."""
    value = load_defaults().get(key)
    if value is None:
        raise RuntimeError(f"Required default '{key}' missing from .env.defaults")
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
            defaults[key.strip()] = value.strip()
    return defaults
