"""Backend tests for Telegram-based 2FA delivery.

These tests validate that the Telegram 2FA code path calls the Telegram sender
and reports success/failure correctly, without performing real HTTP requests.
"""

from __future__ import annotations

import os

import pytest

import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from netcup_api_filter.app import create_app
from netcup_api_filter.database import db
from netcup_api_filter.models import Account
from netcup_api_filter import account_auth


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("SECRET_KEY", "test_secret_key_for_testing_only")
    monkeypatch.setenv("NETCUP_FILTER_DB_PATH", str(tmp_path / "test.db"))

    app = create_app()
    app.config["TESTING"] = True

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _create_account(*, username: str = "testuser") -> Account:
    account = Account(
        username=username,
        user_alias="alias_1234567890abcd",
        email=f"{username}@example.com",
        password_hash="dummy_hash",
        email_2fa_enabled=True,
        telegram_enabled=1,
        telegram_chat_id="123",
        is_active=1,
        email_verified=1,
    )
    db.session.add(account)
    db.session.commit()
    return account


def test_send_2fa_code_via_telegram_calls_sender_and_succeeds(app, monkeypatch):
    calls: list[tuple[str, str]] = []

    def _fake_send(*, chat_id: str, text: str) -> bool:
        calls.append((chat_id, text))
        return True

    monkeypatch.setattr("netcup_api_filter.telegram_service.send_telegram_message", _fake_send)

    with app.app_context():
        account = _create_account()

        with app.test_request_context():
            ok, err = account_auth.send_2fa_code(account.id, "telegram", "127.0.0.1")
            assert ok is True
            assert err is None

    assert calls
    assert calls[0][0] == "123"
    assert "login code" in calls[0][1].lower()


def test_send_2fa_code_via_telegram_fails_when_not_linked(app):
    with app.app_context():
        account = Account(
            username="testuser",
            user_alias="alias_1234567890abcd",
            email="testuser@example.com",
            password_hash="dummy_hash",
            email_2fa_enabled=True,
            telegram_enabled=1,
            telegram_chat_id=None,
            is_active=1,
            email_verified=1,
        )
        db.session.add(account)
        db.session.commit()

        with app.test_request_context():
            ok, err = account_auth.send_2fa_code(account.id, "telegram", "127.0.0.1")
            assert ok is False
            assert err == "Telegram not configured"
