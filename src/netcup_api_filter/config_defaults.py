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
    """Load key/value defaults from `.env.defaults`, then overlay `.env`.

    This matches the project's configuration hierarchy:
    - `.env.defaults` is the catalog + default values (version-controlled)
    - `.env` is a local override layer (not required to contain every key)

    Returns empty dict if neither file exists (e.g., in production where all
    config is supplied via environment variables).
    """

    # Identify candidate directories.
    dirs: list[Path] = []
    repo_root = Path(__file__).resolve().parent.parent.parent
    dirs.append(repo_root)

    # Try Path.cwd() but catch OSError if working directory was deleted.
    try:
        cwd = Path.cwd()
        if cwd.resolve() != repo_root.resolve():
            dirs.append(cwd)
    except (OSError, FileNotFoundError):
        pass

    merged: Dict[str, str] = {}

    # Apply defaults first, then overlay overrides.
    for directory in dirs:
        defaults_path = directory / ".env.defaults"
        if defaults_path.exists():
            merged.update(_parse_env_file(defaults_path))

    for directory in dirs:
        env_path = directory / ".env"
        if env_path.exists():
            merged.update(_parse_env_file(env_path))

    return merged


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
