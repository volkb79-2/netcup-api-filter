"""Behavioural checks for the configured per-blueprint Flask-Limiter budgets."""
from __future__ import annotations

import json
import re
import sqlite3
import time
from contextlib import closing
from datetime import datetime
from types import SimpleNamespace

import pytest
from flask import Flask
from limits import parse

from netcup_api_filter.app import _rate_limit_retry_after_seconds, create_app
from netcup_api_filter.database import db, get_setting


LIMITS = {
    "admin_rate_limit": "2 per minute",
    "account_rate_limit": "3 per minute",
    "api_rate_limit": "4 per minute",
}
RETRY_AFTER_SECONDS = parse(LIMITS["api_rate_limit"]).get_expiry()
FROZEN_LIMIT_CLOCK = 1000.1


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


def _freeze_limit_clock(monkeypatch):
    """Freeze both limits' memory storage and the app's reset arithmetic."""
    clock = [FROZEN_LIMIT_CLOCK]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    return clock


def _assert_html_rate_limit(response):
    assert response.status_code == 429
    body = response.get_data(as_text=True)
    assert "429 - Too Many Requests" in body
    assert "You've exceeded the rate limit." in body
    countdown = re.search(
        r'<div class="countdown-value" id="countdown">([0-9]+)</div>',
        body,
    )
    assert countdown is not None, "the HTML countdown must render a numeric delay"
    seconds = int(countdown.group(1))
    assert seconds == RETRY_AFTER_SECONDS
    assert response.headers["Retry-After"] == str(seconds)


def _app_limiter(app):
    registered = app.extensions.get("limiter")
    assert isinstance(registered, set)
    assert len(registered) == 1
    limiter = next(iter(registered))
    assert callable(getattr(limiter, "reset", None))
    return limiter


def test_admin_account_and_api_limits_return_429_after_configured_request_count(app, monkeypatch):
    _freeze_limit_clock(monkeypatch)
    limiter = _app_limiter(app)

    cases = (
        ("/admin/login", "198.51.100.41", 200, 2),
        ("/account/login", "198.51.100.42", 200, 3),
        ("/api/dns/example.com/records", "198.51.100.43", 401, 4),
    )
    for path, client_ip, under_limit_status, allowed_count in cases:
        for _ in range(allowed_count):
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


def test_api_rate_limit_returns_numeric_retry_after_header(app, monkeypatch):
    """Retry-After equals the remaining window after fake time advances."""
    clock = _freeze_limit_clock(monkeypatch)
    limiter = _app_limiter(app)
    path = "/api/dns/example.com/records"
    client_ip = "198.51.100.49"
    for _ in range(4):
        assert _request(app, path, client_ip).status_code == 401
    clock[0] += 20

    limited = _request(app, path, client_ip)
    assert limited.status_code == 429
    retry_after = limited.headers["Retry-After"]
    assert retry_after.isdigit()
    assert int(retry_after) == RETRY_AFTER_SECONDS - 20
    payload = limited.get_json()
    assert float(payload["retry_after"]) == float(retry_after)
    limiter.reset()


def test_retry_after_falls_back_to_the_configured_limit_window():
    """With no request reset metadata, use the limit string's window length."""
    limit_item = parse("1 per hour")
    error = SimpleNamespace(
        retry_after=None,
        limit=SimpleNamespace(limit=limit_item),
    )
    with Flask(__name__).app_context():
        assert _rate_limit_retry_after_seconds(error) == limit_item.get_expiry()


def test_limits_are_per_client_and_resettable_without_waiting(app):
    limiter = _app_limiter(app)
    # memory:// is process-local. Each reset below checks same-client storage
    # clearing explicitly; it is not a simulation of fixed-window expiry.
    cases = (
        ("/admin/login", 200, False, 2),
        ("/account/login", 200, False, 3),
        ("/api/dns/example.com/records", 401, True, 4),
    )
    for index, (path, under_limit_status, is_api, allowed_count) in enumerate(cases):
        client_a = f"198.51.100.{51 + index * 2}"
        client_b = f"198.51.100.{52 + index * 2}"
        for _ in range(allowed_count):
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
