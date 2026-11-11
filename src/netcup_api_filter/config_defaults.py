"""Helpers for loading config defaults from the defaults catalog.

Sources (per directory: the app/repo root and the cwd), lowest precedence first:

* ``app-defaults.env`` — the SHIPPED runtime catalog that the builds write into the
  Passenger tarball, the local deploy tree and the OCI image: the allowlisted runtime keys of
  ``.env.defaults`` (``RUNTIME_DEFAULT_KEYS``, ``render_shipped_defaults``). ``.env.defaults`` itself is never shipped
  (it holds the documented pre-set admin password and test fixtures).
* ``.env.defaults`` — the version-controlled catalog (repository / build time only).
* ``.env`` — a local developer override layer (gitignored).

Environment variables always win over all of these at the call sites.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

SHIPPED_DEFAULTS_FILENAME = "app-defaults.env"

# ALLOWLIST (review #5): the only keys of .env.defaults that ship in app-defaults.env — exactly
# the keys the RUNNING app resolves through this module (get_default / require_default /
# load_defaults). Everything else (the pre-set admin password, test fixtures, local mock wiring,
# test-tool tuning, values read only from the environment) stays in the repository: a new key does
# NOT ship until it is added here, and tests/test_shipped_defaults.py fails if runtime code reads a
# key that is missing from this set.
RUNTIME_DEFAULT_KEYS = frozenset({
    # rate limits (bootstrap/seeding.seed_settings_from_env, app.py)
    "ADMIN_RATE_LIMIT", "ACCOUNT_RATE_LIMIT", "API_RATE_LIMIT",
    # admin security (api/admin.py)
    "ADMIN_IP_WHITELIST", "ADMIN_SESSION_BIND_IP", "ADMIN_2FA_EMAIL_MIN_INTERVAL_SECONDS",
    "ADMIN_LOGIN_LOCKOUT_THRESHOLD", "ADMIN_LOGIN_LOCKOUT_MINUTES",
    # session cookies (app.py)
    "FLASK_SESSION_COOKIE_SECURE", "FLASK_SESSION_COOKIE_HTTPONLY", "FLASK_SESSION_COOKIE_SAMESITE",
    "FLASK_SESSION_LIFETIME", "FLASK_SESSION_COOKIE_DOMAIN",
    # proxy trust and external URL generation (app.py)
    "TRUSTED_PROXY_HOPS", "PUBLIC_BASE_URL",
    # demo pages switch (bootstrap/seeding.seed_settings_from_env)
    "DEMO_PAGES_ENABLED_LOCAL", "DEMO_PAGES_ENABLED_WEBHOSTING",
    # email references / 2FA mail subject (email_reference.py, notification_service.py)
    "NAF_EMAIL_REF_RANDOM_GROUPS", "NAF_EMAIL_REF_RANDOM_GROUP_SIZE", "NAF_2FA_EMAIL_SUBJECT_TEMPLATE",
    # first-boot initialization lock (bootstrap/init_lock.py)
    "NAF_INIT_LOCK_TIMEOUT_SECONDS",
})

# Never shipped, whatever the allowlist says (defence in depth): credential-like names.
SECRET_LOOKING_MARKERS = ("PASSWORD", "SECRET", "TOKEN", "API_KEY", "LICENSE_KEY", "PRIVATE")

# Preserve the webhosting tarball's pre-WP2 client/protocol hop count until the operator
# measures its front-end chain with probe B044. Repository and app-local defaults remain
# zero; this is an explicit shipped compatibility policy, not a code fallback. X-Forwarded-Host
# remains untrusted under the new policy.
SHIPPED_RUNTIME_OVERRIDES = {
    "TRUSTED_PROXY_HOPS": ("1", "status quo, unverified, see B044"),
}


def is_shipped_key(key: str) -> bool:
    return key in RUNTIME_DEFAULT_KEYS and not any(m in key for m in SECRET_LOOKING_MARKERS)


def render_shipped_defaults(
    source: Path,
    *,
    overrides: dict[str, tuple[str, str]] | None = None,
) -> str:
    """Render runtime defaults, with optional artifact-specific deployment overrides."""
    catalog = _parse_env_file(source)
    overrides = overrides or {}
    missing = sorted(RUNTIME_DEFAULT_KEYS - catalog.keys())
    if missing:
        raise RuntimeError(f"{source} lacks runtime default keys {missing} (config_defaults.RUNTIME_DEFAULT_KEYS)")
    lines = [
        "# GENERATED from .env.defaults by netcup_api_filter.config_defaults.render_shipped_defaults.",
        "# Runtime defaults only; environment variables override every value. Do not edit.",
    ]
    for key, value in catalog.items():
        if is_shipped_key(key):
            override = overrides.get(key)
            if override:
                value, comment = override
                lines.append(f"# {comment}")
            lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def write_shipped_defaults(
    source: Path,
    dest_dir: Path,
    *,
    overrides: dict[str, tuple[str, str]] | None = None,
) -> Path:
    destination = Path(dest_dir) / SHIPPED_DEFAULTS_FILENAME
    destination.write_text(
        render_shipped_defaults(Path(source), overrides=overrides),
        encoding="utf-8",
    )
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
