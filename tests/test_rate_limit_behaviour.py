"""Behavioural checks for the configured per-blueprint Flask-Limiter budgets."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime

import pytest

from netcup_api_filter.app import create_app
from netcup_api_filter.database import db, get_setting


LIMITS = {
    "admin_rate_limit": "2 per minute",
    "account_rate_limit": "2 per minute",
    "api_rate_limit": "2 per minute",
}


@pytest.fixture
def app(monkeypatch, tmp_path):
    """Seed DB limits before create_app installs blueprint decorators.

    Flask-Limiter is configured with memory:// in app.py. These requests stay in
    one app instance and never claim cross-worker sharing semantics.
    """
    db_path = tmp_path / "rate-limit-sweep.db"
    monkeypatch.setenv("SECRET_KEY", "rate-limit-sweep-secret-key-0123456789")
    monkeypatch.setenv("NETCUP_FILTER_DB_PATH", str(db_path))
    monkeypatch.delenv("NETCUP_FILTER_APP_ROOT", raising=False)
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "0")

    with closing(sqlite3.connect(db_path)) as connection:
        with connection:
            connection.execute(
                "CREATE TABLE settings ("
                "id INTEGER PRIMARY KEY, key VARCHAR(100) NOT NULL UNIQUE, "
                "value TEXT, updated_at DATETIME NOT NULL)"
            )
            connection.executemany(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                [
                    (key, json.dumps(value), datetime(2030, 1, 1).isoformat())
                    for key, value in LIMITS.items()
                ],
            )

    application = create_app()
    application.config["TESTING"] = True
    with application.app_context():
        assert {key: get_setting(key) for key in LIMITS} == LIMITS
        yield application
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


def _request(app, path, ip):
    client = app.test_client()
    return client.get(path, environ_overrides={"REMOTE_ADDR": ip})


def _assert_html_rate_limit(response):
    assert response.status_code == 429
    body = response.get_data(as_text=True)
    assert "429 - Too Many Requests" in body
    assert "You've exceeded the rate limit." in body


def _app_limiter(app):
    registered = app.extensions.get("limiter")
    assert isinstance(registered, set)
    assert len(registered) == 1
    limiter = next(iter(registered))
    assert callable(getattr(limiter, "reset", None))
    return limiter


def test_admin_account_and_api_limits_return_429_after_configured_request_count(app):
    limiter = _app_limiter(app)

    cases = (
        ("/admin/login", "198.51.100.41", 200),
        ("/account/login", "198.51.100.42", 200),
        ("/api/dns/example.com/records", "198.51.100.43", 401),
    )
    for path, client_ip, under_limit_status in cases:
        for _ in range(2):
            response = _request(app, path, client_ip)
            assert response.status_code == under_limit_status, f"unexpected pre-limit status for {path}"

        limited = _request(app, path, client_ip)
        assert limited.status_code == 429
        if path.startswith("/api/"):
            payload = limited.get_json()
            assert payload["error"] == "rate_limited"
            assert payload["message"] == "Too many requests"
        else:
            _assert_html_rate_limit(limited)
        limiter.reset()
        reset_response = _request(app, path, client_ip)
        assert reset_response.status_code == under_limit_status
        limiter.reset()


@pytest.mark.xfail(
    strict=True,
    reason="DEFECT: API 429 responses emit Retry-After: None instead of a numeric delay.",
)
def test_api_rate_limit_returns_numeric_retry_after_header(app):
    """Minimal repro for the API rate-limit header returning the string None."""
    limiter = _app_limiter(app)
    path = "/api/dns/example.com/records"
    client_ip = "198.51.100.49"
    assert _request(app, path, client_ip).status_code == 401
    assert _request(app, path, client_ip).status_code == 401

    limited = _request(app, path, client_ip)
    assert limited.status_code == 429
    retry_after = limited.headers["Retry-After"]
    assert retry_after.isdigit()
    assert int(retry_after) > 0
    payload = limited.get_json()
    assert float(payload["retry_after"]) == float(retry_after)
    limiter.reset()


def test_limits_are_per_client_and_resettable_without_waiting(app):
    limiter = _app_limiter(app)
    # memory:// is process-local. Each reset below checks same-client storage
    # clearing explicitly; it is not a simulation of fixed-window expiry.
    cases = (
        ("/admin/login", 200, False),
        ("/account/login", 200, False),
        ("/api/dns/example.com/records", 401, True),
    )
    for index, (path, under_limit_status, is_api) in enumerate(cases):
        client_a = f"198.51.100.{51 + index * 2}"
        client_b = f"198.51.100.{52 + index * 2}"
        assert _request(app, path, client_a).status_code == under_limit_status
        assert _request(app, path, client_a).status_code == under_limit_status
        assert _request(app, path, client_b).status_code == under_limit_status
        limited_a = _request(app, path, client_a)
        if is_api:
            assert limited_a.status_code == 429
            assert limited_a.get_json()["error"] == "rate_limited"
        else:
            _assert_html_rate_limit(limited_a)
        limiter.reset()
        reset_a = _request(app, path, client_a)
        assert reset_a.status_code == under_limit_status
