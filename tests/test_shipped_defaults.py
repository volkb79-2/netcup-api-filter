"""The shipped runtime catalog (app-defaults.env) vs. .env.defaults and the code that reads it.

Two failure modes this pins:
* a build/test-only value (the pre-set admin password, test fixtures, local mock wiring)
  leaking into a shipped tree;
* a key the RUNTIME reads (require_default / get_default) being filtered out, which turns
  into a 500 in a deployment that has no .env.defaults (it is never shipped).
"""
from __future__ import annotations

import re
from pathlib import Path

from netcup_api_filter import config_defaults
from netcup_api_filter.config_defaults import (
    SHIPPED_DEFAULTS_FILENAME,
    is_build_or_test_only,
    render_shipped_defaults,
    write_shipped_defaults,
)

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src" / "netcup_api_filter"
CATALOG = REPO / ".env.defaults"

# Read by bootstrap.admin.shipped_admin_spec() — at BUILD time only (seeding the tarball /
# golden DB, while .env.defaults is still present). Never needed by a running app.
BUILD_TIME_READS = {"DEFAULT_ADMIN_USERNAME", "DEFAULT_ADMIN_PASSWORD", "DEFAULT_ADMIN_EMAIL"}


def _shipped_keys() -> set[str]:
    rendered = render_shipped_defaults(CATALOG)
    return {line.split("=", 1)[0] for line in rendered.splitlines() if line and not line.startswith("#")}


def _keys_read_by_runtime_code() -> set[str]:
    pattern = re.compile(r"""(?:get_default|require_default|defaults\.get)\(\s*['"]([A-Z0-9_]+)['"]""")
    keys: set[str] = set()
    for path in SRC.rglob("*.py"):
        keys.update(pattern.findall(path.read_text(encoding="utf-8")))
    return keys


def test_no_build_or_test_only_key_ships():
    shipped = _shipped_keys()
    leaked = sorted(k for k in shipped if is_build_or_test_only(k))
    assert not leaked
    for key in ("DEFAULT_ADMIN_PASSWORD", "DEFAULT_TEST_CLIENT_OPERATIONS", "TELEGRAM_LINK_CALLBACK_SECRET",
                "ADMIN_2FA_SKIP", "E2E_DEPLOY_DIR", "LOCAL_MAIL_FROM"):
        assert key not in shipped, key


def test_every_runtime_read_key_ships():
    missing = sorted(
        key for key in _keys_read_by_runtime_code() - BUILD_TIME_READS
        if key not in _shipped_keys()
    )
    assert not missing, f"runtime reads keys the shipped catalog lacks: {missing}"


def test_lockout_and_session_defaults_ship_with_their_catalog_values():
    catalog = config_defaults._parse_env_file(CATALOG)
    rendered = render_shipped_defaults(CATALOG)
    for key in ("ADMIN_LOGIN_LOCKOUT_THRESHOLD", "ADMIN_LOGIN_LOCKOUT_MINUTES", "FLASK_SESSION_LIFETIME"):
        assert f"{key}={catalog[key]}" in rendered


def test_shipped_tree_loads_runtime_defaults_without_env_defaults(tmp_path, monkeypatch):
    """A tree with only app-defaults.env (like a deploy tree) resolves runtime keys."""
    write_shipped_defaults(CATALOG, tmp_path)
    assert (tmp_path / SHIPPED_DEFAULTS_FILENAME).is_file()
    monkeypatch.chdir(tmp_path)
    loaded = config_defaults._parse_env_file(tmp_path / SHIPPED_DEFAULTS_FILENAME)
    assert loaded["ADMIN_LOGIN_LOCKOUT_THRESHOLD"] == config_defaults._parse_env_file(CATALOG)[
        "ADMIN_LOGIN_LOCKOUT_THRESHOLD"]
    assert "DEFAULT_ADMIN_PASSWORD" not in loaded
