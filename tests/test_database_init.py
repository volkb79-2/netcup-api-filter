import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from netcup_api_filter.app import create_app
from netcup_api_filter.database import get_db_path


def _base_monkeypatch(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test_secret_key_for_testing_only")
    monkeypatch.delenv("NETCUP_FILTER_APP_ROOT", raising=False)
    monkeypatch.delenv("SEED_DEMO_ACCOUNTS", raising=False)


def test_in_memory_engine_options_empty(monkeypatch):
    """database.py:141-142: :memory: path → SQLALCHEMY_ENGINE_OPTIONS is {} (StaticPool guard)."""
    _base_monkeypatch(monkeypatch)
    monkeypatch.setenv("NETCUP_FILTER_DB_PATH", ":memory:")
    app = create_app()
    assert app.config["SQLALCHEMY_ENGINE_OPTIONS"] == {}


def test_file_db_engine_options_set(monkeypatch, tmp_path):
    """database.py:143-148: file path → SQLALCHEMY_ENGINE_OPTIONS contains pool_size and pool_pre_ping."""
    _base_monkeypatch(monkeypatch)
    monkeypatch.setenv("NETCUP_FILTER_DB_PATH", str(tmp_path / "test.db"))
    app = create_app()
    opts = app.config["SQLALCHEMY_ENGINE_OPTIONS"]
    assert "pool_size" in opts
    assert "pool_pre_ping" in opts


def test_get_db_path_env_wins(monkeypatch, tmp_path):
    """database.py:114: NETCUP_FILTER_DB_PATH env var takes precedence over the default path."""
    custom = str(tmp_path / "custom.db")
    monkeypatch.setenv("NETCUP_FILTER_DB_PATH", custom)
    assert get_db_path() == custom


def test_get_db_path_default_when_env_absent(monkeypatch):
    """database.py:124-127: without NETCUP_FILTER_DB_PATH, falls back to cwd/netcup_filter.db."""
    monkeypatch.delenv("NETCUP_FILTER_DB_PATH", raising=False)
    result = get_db_path()
    assert result.endswith("netcup_filter.db")
