"""Backend tests for Telegram Option A linking.

These tests validate the bot -> app callback contract for finalizing account
linking without requiring any external Telegram services.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import pytest

# Import Flask app and models
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from netcup_api_filter.app import create_app
from netcup_api_filter.database import db
from netcup_api_filter.models import Account
from netcup_api_filter.telegram_service import sha256_hex


@pytest.fixture
def app(monkeypatch, tmp_path):
    """Create test Flask app with a temporary SQLite database file."""
    monkeypatch.setenv("SECRET_KEY", "test_secret_key_for_testing_only")
    monkeypatch.setenv("NETCUP_FILTER_DB_PATH", str(tmp_path / "test.db"))

    app = create_app()
    app.config["TESTING"] = True
    # init_db() sets SQLALCHEMY_DATABASE_URI from NETCUP_FILTER_DB_PATH.

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def _create_account(*, username: str = "testuser") -> Account:
    account = Account(
        username=username,
        user_alias="alias_1234567890abcd",
        email=f"{username}@example.com",
        password_hash="dummy_hash",
        email_2fa_enabled=True,
    )
    db.session.add(account)
    db.session.commit()
    return account


def test_telegram_link_callback_returns_503_when_not_configured(client, monkeypatch):
    monkeypatch.delenv("TELEGRAM_LINK_CALLBACK_SECRET", raising=False)

    resp = client.post("/api/telegram/link", json={"token": "x", "chat_id": "123"})
    assert resp.status_code == 503


def test_telegram_link_callback_rejects_wrong_secret(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_LINK_CALLBACK_SECRET", "expected")

    resp = client.post(
        "/api/telegram/link",
        json={"token": "x", "chat_id": "123"},
        headers={"X-NAF-TELEGRAM-SECRET": "wrong"},
    )
    assert resp.status_code == 401


def test_telegram_link_callback_validates_payload(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_LINK_CALLBACK_SECRET", "expected")

    resp = client.post(
        "/api/telegram/link",
        json={"token": "", "chat_id": "123"},
        headers={"X-NAF-TELEGRAM-SECRET": "expected"},
    )
    assert resp.status_code == 400

    resp = client.post(
        "/api/telegram/link",
        json={"token": "abc", "chat_id": "not-digits"},
        headers={"X-NAF-TELEGRAM-SECRET": "expected"},
    )
    assert resp.status_code == 400


def test_telegram_link_callback_returns_404_for_unknown_token(app, client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_LINK_CALLBACK_SECRET", "expected")

    with app.app_context():
        _create_account()

    resp = client.post(
        "/api/telegram/link",
        json={"token": "unknown", "chat_id": "123"},
        headers={"X-NAF-TELEGRAM-SECRET": "expected"},
    )
    assert resp.status_code == 404


def test_telegram_link_callback_returns_409_when_token_not_pending(app, client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_LINK_CALLBACK_SECRET", "expected")

    raw = "rawtoken"
    with app.app_context():
        account = _create_account()
        account.telegram_link_token_hash = sha256_hex(raw)
        account.telegram_link_token_expires_at = None
        db.session.commit()

    resp = client.post(
        "/api/telegram/link",
        json={"token": raw, "chat_id": "123"},
        headers={"X-NAF-TELEGRAM-SECRET": "expected"},
    )
    assert resp.status_code == 409


def test_telegram_link_callback_returns_410_when_expired(app, client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_LINK_CALLBACK_SECRET", "expected")

    raw = "rawtoken"
    with app.app_context():
        account = _create_account()
        account.telegram_link_token_hash = sha256_hex(raw)
        account.telegram_link_token_expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()

    resp = client.post(
        "/api/telegram/link",
        json={"token": raw, "chat_id": "123"},
        headers={"X-NAF-TELEGRAM-SECRET": "expected"},
    )
    assert resp.status_code == 410


def test_telegram_link_callback_links_account_and_consumes_token(app, client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_LINK_CALLBACK_SECRET", "expected")

    # Avoid any outbound network by stubbing the send function.
    calls: list[tuple[str, str]] = []

    def _fake_send(*, chat_id: str, text: str) -> bool:
        calls.append((chat_id, text))
        return True

    monkeypatch.setattr("netcup_api_filter.api.telegram.send_telegram_message", _fake_send)

    raw = "rawtoken"
    with app.app_context():
        account = _create_account()
        account.telegram_link_token_hash = sha256_hex(raw)
        account.telegram_link_token_expires_at = datetime.utcnow() + timedelta(seconds=60)
        db.session.commit()
        account_id = account.id

    resp = client.post(
        "/api/telegram/link",
        json={"token": raw, "chat_id": "123"},
        headers={"X-NAF-TELEGRAM-SECRET": "expected"},
    )
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "linked"}

    with app.app_context():
        account = Account.query.get(account_id)
        assert account.telegram_enabled == 1
        assert account.telegram_chat_id == "123"
        assert account.telegram_linked_at is not None
        assert account.telegram_link_token_hash is None
        assert account.telegram_link_token_expires_at is None

    assert calls
    assert calls[0][0] == "123"
