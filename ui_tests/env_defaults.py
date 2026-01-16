"""UI test helper to read defaults from .env.defaults.

Why this exists:
- UI tests sometimes run in environments where the `netcup_api_filter` package
  is imported from a deployed bundle (e.g., deploy-local/src) rather than the
  repository `src/` tree.
- In that case, `netcup_api_filter.config_defaults` would resolve its repo-root
  relative to the deployed bundle and miss the real workspace `.env.defaults`.

This module provides a stable, workspace-relative default loader for UI tests.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict


@lru_cache(maxsize=1)
def _load_env_defaults() -> Dict[str, str]:
    repo_root = Path(__file__).resolve().parents[1]
    env_defaults = repo_root / ".env.defaults"
    if not env_defaults.exists():
        return {}

    defaults: Dict[str, str] = {}
    for raw in env_defaults.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
            value = value[1:-1]
        defaults[key.strip()] = value
    return defaults


def get_env_default(key: str) -> str | None:
    return _load_env_defaults().get(key)
