"""Helpers for loading config defaults from the defaults catalog.

Sources (per directory: the app/repo root and the cwd), lowest precedence first:

* ``app-defaults.env`` — the SHIPPED runtime catalog that the builds write into the
  Passenger tarball, the local deploy tree and the OCI image: ``.env.defaults`` minus every
  build/test-only key (``render_shipped_defaults``). ``.env.defaults`` itself is never shipped
  (it holds the documented pre-set admin password and test fixtures).
* ``.env.defaults`` — the version-controlled catalog (repository / build time only).
* ``.env`` — a local developer override layer (gitignored).

Environment variables always win over all of these at the call sites.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

SHIPPED_DEFAULTS_FILENAME = "app-defaults.env"

# Keys of .env.defaults that exist for builds and tests only and must never reach a shipped
# tree: the pre-set admin's password, test personas/fixtures, local mock wiring, test-tool
# tuning, and placeholders that are only valid in local tests.
BUILD_AND_TEST_ONLY_PREFIXES = (
    "DEFAULT_ADMIN_", "DEFAULT_TEST_", "DEFAULT_READONLY_TEST_", "LOCAL_", "E2E_", "UI_",
    "PYTEST_", "SCREENSHOT_", "DNS_TEST_", "DNS_PROPAGATION_", "DNS_CHECK_", "IMAP_", "WEBHOSTING_",
)
BUILD_AND_TEST_ONLY_KEYS = frozenset({"ADMIN_2FA_SKIP", "TELEGRAM_LINK_CALLBACK_SECRET"})


def is_build_or_test_only(key: str) -> bool:
    return key in BUILD_AND_TEST_ONLY_KEYS or key.startswith(BUILD_AND_TEST_ONLY_PREFIXES)


def render_shipped_defaults(source: Path) -> str:
    """The shipped runtime catalog: ``source`` (.env.defaults) minus build/test-only keys."""
    lines = [
        "# GENERATED from .env.defaults by netcup_api_filter.config_defaults.render_shipped_defaults.",
        "# Runtime defaults only; environment variables override every value. Do not edit.",
    ]
    for key, value in _parse_env_file(source).items():
        if not is_build_or_test_only(key):
            lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def write_shipped_defaults(source: Path, dest_dir: Path) -> Path:
    destination = Path(dest_dir) / SHIPPED_DEFAULTS_FILENAME
    destination.write_text(render_shipped_defaults(Path(source)), encoding="utf-8")
    return destination


@lru_cache(maxsize=1)
def load_defaults() -> dict[str, str]:
    """Load key/value defaults: `app-defaults.env`, then `.env.defaults`, then overlay `.env`.

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

    merged: dict[str, str] = {}

    # Shipped catalog first, then the repository catalog, then the local overlay.
    for name in (SHIPPED_DEFAULTS_FILENAME, ".env.defaults"):
        for directory in dirs:
            defaults_path = directory / name
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


def _parse_env_file(env_path: Path) -> dict[str, str]:
    defaults: dict[str, str] = {}
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
