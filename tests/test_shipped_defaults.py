"""The shipped runtime catalog (app-defaults.env) vs. .env.defaults and the code that reads it.

The catalog is an ALLOWLIST (config_defaults.RUNTIME_DEFAULT_KEYS, review #5). Failure modes
this pins:
* a build/test-only or credential-like value (the pre-set admin password, SECRET_KEY, test
  fixtures, local mock wiring) reaching a shipped tree;
* a key the RUNTIME reads (require_default / get_default / load_defaults) missing from the
  allowlist, which turns into a 500 in a deployment that has no .env.defaults (never shipped);
* an allowlisted key missing from .env.defaults.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from netcup_api_filter import config_defaults
from netcup_api_filter.config_defaults import (
    RUNTIME_DEFAULT_KEYS,
    SECRET_LOOKING_MARKERS,
    SHIPPED_DEFAULTS_FILENAME,
    SHIPPED_RUNTIME_OVERRIDES,
    is_shipped_key,
    render_shipped_defaults,
    write_shipped_defaults,
)

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src" / "netcup_api_filter"
CATALOG = REPO / ".env.defaults"

# Read by bootstrap.admin.shipped_admin_spec() — at BUILD time only (seeding the tarball /
# golden DB, while .env.defaults is still present). Never needed by a running app.
BUILD_TIME_READS = {"DEFAULT_ADMIN_USERNAME", "DEFAULT_ADMIN_PASSWORD", "DEFAULT_ADMIN_EMAIL"}

# Literal-key reads, the admin int-setting helper, `defaults.get(...)` on load_defaults(), and
# module-level `*_KEY = "..."` constants handed to require_default (bootstrap/init_lock.py).
_READ_PATTERNS = (
    re.compile(r"""(?:get_default|require_default|defaults\.get|_positive_int_setting)\(\s*['"]([A-Z0-9_]+)['"]"""),
    re.compile(r"""^[A-Z_]*_KEY\s*=\s*['"]([A-Z0-9_]+)['"]""", re.MULTILINE),
)


def _shipped_keys() -> set[str]:
    rendered = render_shipped_defaults(CATALOG)
    return {line.split("=", 1)[0] for line in rendered.splitlines() if line and not line.startswith("#")}


def _keys_read_by_runtime_code() -> set[str]:
    keys: set[str] = set()
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for pattern in _READ_PATTERNS:
            keys.update(pattern.findall(text))
    return keys & set(config_defaults._parse_env_file(CATALOG))  # catalog keys only


def test_only_allowlisted_keys_ship():
    assert _shipped_keys() == RUNTIME_DEFAULT_KEYS


@pytest.mark.parametrize("key", [
    "SECRET_KEY", "DEFAULT_ADMIN_PASSWORD", "TELEGRAM_LINK_CALLBACK_SECRET", "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_BOT_USERNAME", "POWERDNS_API_KEY", "POWERDNS_SOA", "MAXMIND_LICENSE_KEY", "IMAP_PASSWORD",
    "ADMIN_2FA_SKIP", "E2E_DEPLOY_DIR", "LOCAL_MAIL_FROM", "DEFAULT_TEST_CLIENT_OPERATIONS",
])
def test_known_non_runtime_keys_never_ship(key):
    assert key not in _shipped_keys()


def test_no_credential_looking_key_ships_even_if_allowlisted():
    shipped = _shipped_keys()
    assert not [k for k in shipped if any(m in k for m in SECRET_LOOKING_MARKERS)]
    assert not is_shipped_key("SOME_API_KEY")  # the marker guard holds independently of the list


def test_secret_key_has_no_published_default():
    assert "SECRET_KEY" not in config_defaults._parse_env_file(CATALOG)


def test_every_runtime_read_key_ships():
    missing = sorted(_keys_read_by_runtime_code() - BUILD_TIME_READS - _shipped_keys())
    assert not missing, f"runtime reads keys the shipped catalog lacks (add to RUNTIME_DEFAULT_KEYS): {missing}"


def test_the_read_scan_sees_the_indirect_readers():
    found = _keys_read_by_runtime_code()
    for key in ("ADMIN_LOGIN_LOCKOUT_THRESHOLD", "NAF_INIT_LOCK_TIMEOUT_SECONDS", "ADMIN_RATE_LIMIT"):
        assert key in found


def test_allowlisted_key_missing_from_the_catalog_fails_the_render(tmp_path):
    partial = tmp_path / "partial.env"
    partial.write_text("ADMIN_RATE_LIMIT=1 per minute\n")
    with pytest.raises(RuntimeError, match="lacks runtime default keys"):
        render_shipped_defaults(partial)


def test_shipped_values_equal_the_catalog_values():
    catalog = config_defaults._parse_env_file(CATALOG)
    rendered = render_shipped_defaults(CATALOG)
    for key in (
        "ADMIN_LOGIN_LOCKOUT_THRESHOLD",
        "ADMIN_LOGIN_LOCKOUT_MINUTES",
        "FLASK_SESSION_LIFETIME",
        "PUBLIC_BASE_URL",
    ):
        assert f"{key}={catalog[key]}" in rendered


def test_shipped_tarball_keeps_one_unverified_proxy_hop_until_probe_b044():
    catalog = config_defaults._parse_env_file(CATALOG)
    rendered = render_shipped_defaults(CATALOG, overrides=SHIPPED_RUNTIME_OVERRIDES)

    assert catalog["TRUSTED_PROXY_HOPS"] == "0"
    assert "# status quo, unverified, see B044\nTRUSTED_PROXY_HOPS=1\n" in rendered


def test_shipped_tree_loads_runtime_defaults_without_env_defaults(tmp_path):
    write_shipped_defaults(CATALOG, tmp_path)
    loaded = config_defaults._parse_env_file(tmp_path / SHIPPED_DEFAULTS_FILENAME)
    assert loaded["ADMIN_LOGIN_LOCKOUT_THRESHOLD"] == config_defaults._parse_env_file(CATALOG)[
        "ADMIN_LOGIN_LOCKOUT_THRESHOLD"]
    assert loaded["TRUSTED_PROXY_HOPS"] == "0"
    assert "DEFAULT_ADMIN_PASSWORD" not in loaded
