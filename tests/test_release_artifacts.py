"""What a release tarball contains, checked on the real staging steps of the tarball builder.

``scripts/build_webhosting_tarball.py`` stages the tree (``stage_application_files``), seeds the
database (``seed_database``) and swaps the build-time ``.env.defaults`` for the runtime catalog
(``ship_runtime_defaults``). Only the wheel vendoring and the xz packing are skipped here. The
release is greenfield: a leak of the pre-set admin's password file, a demo account, a persisted
SECRET_KEY or a state file into the artifact is a credential incident, not a cosmetic issue.
"""
from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

from netcup_api_filter.config_defaults import SHIPPED_DEFAULTS_FILENAME, require_default

REPO = Path(__file__).resolve().parents[1]


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_webhosting_tarball", REPO / "scripts/build_webhosting_tarball.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def staging(tmp_path_factory) -> Path:
    builder = _load_builder()
    root = tmp_path_factory.mktemp("release") / "app"
    mp = pytest.MonkeyPatch()
    # seed_database() writes these two process variables; restore them afterwards.
    mp.setenv("DEPLOYMENT_TARGET", "webhosting")
    mp.setenv("NETCUP_FILTER_DB_PATH", str(root / "netcup_filter.db"))
    try:
        builder.stage_application_files(root)
        (root / "vendor").mkdir()
        builder.seed_database(root)
        builder.ship_runtime_defaults(root)
    finally:
        mp.undo()
    return root


def _query(staging: Path, sql: str) -> list[tuple]:
    conn = sqlite3.connect(f"file:{staging / 'netcup_filter.db'}?mode=ro", uri=True)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def test_database_holds_exactly_the_shipped_admin(staging):
    shipped = require_default("DEFAULT_ADMIN_USERNAME")
    assert _query(staging, "SELECT username, is_admin, must_change_password FROM accounts") == [(shipped, 1, 1)]


def test_database_has_no_demo_or_secret_state(staging):
    assert _query(staging, "SELECT key FROM settings WHERE key = 'secret_key'") == []
    for table in ("api_tokens", "account_realms", "account_sessions", "activity_log", "managed_domain_roots", "domain_root_grants", "backend_services"):
        assert _query(staging, f"SELECT COUNT(*) FROM {table}") == [(0,)], table


def test_tree_ships_runtime_catalog_and_no_env_or_state_files(staging):
    names = {p.name for p in staging.rglob("*") if p.is_file()}
    assert SHIPPED_DEFAULTS_FILENAME in names
    forbidden = {".env", ".env.defaults", ".env.webhosting", ".env.workspace", ".env.services"}
    assert not (names & forbidden), names & forbidden
    assert not [n for n in names if n.startswith("deployment_state_")]
    assert (staging / "passenger_wsgi.py").is_file()


def test_shipped_catalog_has_no_admin_password(staging):
    text = (staging / SHIPPED_DEFAULTS_FILENAME).read_text(encoding="utf-8")
    password = require_default("DEFAULT_ADMIN_PASSWORD")
    assert password not in text
    assert "DEFAULT_ADMIN_" not in text
