"""The mock Netcup backend in the golden DB: local/e2e builds get it, release artifacts never do.

Without a configured backend every DNS read of the e2e app is an HTTP 500 (``dns_api`` has no
``netcup_config``), so ``build_deployment.py --local`` seeds ``netcup_config`` pointing at the
Netcup CCP mock (URL from ``MOCK_NETCUP_API_URL``, fail-fast when absent; the mock's public test
credentials from the ``LOCAL_MOCK_NETCUP_*`` defaults). The tarball and the OCI first boot go
through the same ``init_instance`` without it.
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest
from flask import Flask

from netcup_api_filter import database
from netcup_api_filter.api.dns_api import get_netcup_client
from netcup_api_filter.bootstrap import MockNetcup, init_instance, seed_shipped_database, shipped_admin_spec
from netcup_api_filter.config_defaults import is_shipped_key, require_default
from netcup_api_filter.database import get_setting

REPO = Path(__file__).resolve().parents[1]
MOCK_URL = "http://naf-test-mock-netcup-api"
ENDPOINT = f"{MOCK_URL}/run/webservice/servers/endpoint.php"
KEYS = ("customer_id", "api_key", "api_password", "timeout")


def _load_build_deployment():
    spec = importlib.util.spec_from_file_location("build_deployment_under_test", REPO / "build_deployment.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def bare_app(tmp_path):
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_path / 'bare.db'}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    database.db.init_app(app)
    with app.app_context():
        yield app
        database.db.session.remove()
        database.db.drop_all()


def _mock(**overrides) -> MockNetcup:
    values = dict(api_url=ENDPOINT, customer_id="c1", api_key="k1", api_password="p1", timeout=7)
    values.update(overrides)
    return MockNetcup(**values)


# --- the seeder ---------------------------------------------------------------

def test_mock_netcup_is_stored_as_the_admin_ui_shape_and_used_by_the_dns_api(bare_app):
    init_instance(admin=shipped_admin_spec(), mock_netcup=_mock())
    assert get_setting("netcup_config") == {
        "customer_id": "c1", "api_key": "k1", "api_password": "p1", "api_url": ENDPOINT, "timeout": 7,
    }
    client = get_netcup_client()
    assert client is not None, "the DNS API must find a backend (else every read is HTTP 500)"


def test_no_mock_netcup_means_no_backend_config(bare_app):
    init_instance(admin=shipped_admin_spec())
    assert get_setting("netcup_config") is None
    assert get_netcup_client() is None


def test_shipped_database_without_mock_has_no_backend_config(bare_app):
    """seed_shipped_database() is what the tarball builder calls (no mock arguments)."""
    seed_shipped_database()
    assert get_setting("netcup_config") is None
    assert get_setting("email_config") is None


def test_shipped_database_with_mock_gets_backend_config(bare_app):
    seed_shipped_database(mock_netcup=_mock())
    assert get_setting("netcup_config")["api_url"] == ENDPOINT


@pytest.mark.parametrize("field,value", [
    ("api_url", "naf-mock"), ("api_url", ""), ("customer_id", ""), ("api_key", ""),
    ("api_password", ""), ("timeout", 0),
])
def test_invalid_mock_netcup_is_rejected(field, value):
    with pytest.raises(ValueError):
        _mock(**{field: value})


def test_mock_netcup_repr_hides_credentials():
    text = repr(_mock(api_key="very-distinct-key", api_password="very-distinct-pass"))
    assert "very-distinct" not in text and ENDPOINT in text


# --- the defaults are the mock's own credentials ------------------------------

def test_default_credentials_match_the_mock_and_never_ship():
    from ui_tests import mock_netcup_api as mock

    assert require_default("LOCAL_MOCK_NETCUP_CUSTOMER_ID") == mock.MOCK_CUSTOMER_ID
    assert require_default("LOCAL_MOCK_NETCUP_API_KEY") == mock.MOCK_API_KEY
    assert require_default("LOCAL_MOCK_NETCUP_API_PASSWORD") == mock.MOCK_API_PASSWORD
    for key in ("CUSTOMER_ID", "API_KEY", "API_PASSWORD", "TIMEOUT"):
        assert not is_shipped_key(f"LOCAL_MOCK_NETCUP_{key}")


# --- build_deployment.py: local vs. release ------------------------------------

def test_local_build_derives_endpoint_from_mock_url(monkeypatch):
    build = _load_build_deployment()
    monkeypatch.setenv("MOCK_NETCUP_API_URL", MOCK_URL + "/")
    mock = build._local_mock_netcup()
    assert mock.api_url == ENDPOINT
    assert mock.customer_id == require_default("LOCAL_MOCK_NETCUP_CUSTOMER_ID")
    assert mock.timeout == int(require_default("LOCAL_MOCK_NETCUP_TIMEOUT"))


def test_local_build_fails_fast_without_mock_url(monkeypatch, tmp_path):
    build = _load_build_deployment()
    monkeypatch.delenv("MOCK_NETCUP_API_URL", raising=False)
    monkeypatch.chdir(tmp_path)  # no .env.services here
    with pytest.raises(RuntimeError, match="MOCK_NETCUP_API_URL"):
        build._local_mock_netcup()


def _build_db(monkeypatch, tmp_path, *, is_local: bool) -> Path:
    """Run the real ``build_deployment.initialize_database`` on a minimal deploy tree."""
    build = _load_build_deployment()
    tree = tmp_path / ("local" if is_local else "release")
    (tree / "vendor").mkdir(parents=True)
    (tree / "src").symlink_to(REPO / "src")
    for name in ("MOCK_NETCUP_API_URL", "MAILPIT_HOST"):
        monkeypatch.setenv(name, MOCK_URL if name.startswith("MOCK") else "naf-test-mailpit")
    # initialize_database() writes these two process variables; restore them afterwards.
    monkeypatch.setenv("DEPLOYMENT_TARGET", "unset")
    monkeypatch.setenv("NETCUP_FILTER_DB_PATH", "unset")
    monkeypatch.chdir(tmp_path)
    build.initialize_database(tree, is_local=is_local)
    return tree / "netcup_filter.db"


def _setting(db_path: Path, key: str):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    finally:
        conn.close()
    return json.loads(row[0]) if row and row[0] else None


def test_local_golden_db_has_mock_netcup_and_release_db_does_not(monkeypatch, tmp_path):
    local_db = _build_db(monkeypatch, tmp_path, is_local=True)
    config = _setting(local_db, "netcup_config")
    assert config["api_url"] == ENDPOINT
    assert config["customer_id"] == require_default("LOCAL_MOCK_NETCUP_CUSTOMER_ID")
    assert all(config[key] for key in KEYS)

    release_db = _build_db(monkeypatch, tmp_path, is_local=False)
    assert _setting(release_db, "netcup_config") is None
    assert _setting(release_db, "email_config") is None
