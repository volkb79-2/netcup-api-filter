"""Security alert mails are queued for IMMEDIATE sending (delay=0).

``EmailNotifier.send_email_async`` defaults to a 5 s delay before sending, in a daemon thread.
For a security alert that is a hazard: a worker that is recycled or stopped inside that window
loses the alert silently (the e2e suite saw exactly this: "Sent password changed notification"
was logged, the mail never arrived). Failed-login / lockout mails already used ``delay=0``; the
other alerts must too.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from netcup_api_filter import notification_service as ns


class _FakeNotifier:
    def __init__(self):
        self.sent = []

    def send_email_async(self, to_email, subject, body, html_body=None, delay=5):
        self.sent.append({"to": to_email, "subject": subject, "delay": delay})


@pytest.fixture
def notifier(monkeypatch):
    fake = _FakeNotifier()
    monkeypatch.setattr(ns, "_get_notifier", lambda: fake)
    monkeypatch.setattr(ns, "_get_base_url", lambda: "https://naf.test")
    monkeypatch.setattr(ns, "_send_telegram_if_enabled", lambda *a, **k: False)
    return fake


@pytest.fixture
def account():
    return SimpleNamespace(username="alice", email="alice@example.com", user_alias="alias1234abcd")


def _assert_immediate(fake, to):
    assert len(fake.sent) == 1, fake.sent
    assert fake.sent[0]["to"] == to
    assert fake.sent[0]["delay"] == 0


def test_password_changed_is_immediate(notifier, account):
    assert ns.notify_password_changed(account, "203.0.113.5") is True
    _assert_immediate(notifier, "alice@example.com")


def test_token_revoked_is_immediate(notifier, account):
    token = SimpleNamespace(token_name="t1", token_prefix="abcd1234", realm=SimpleNamespace(realm_value="home", domain="example.com"), id=1)
    assert ns.notify_token_revoked(account, token, revoked_by="admin", reason="test") is True
    _assert_immediate(notifier, "alice@example.com")


def test_credential_rotation_is_immediate(notifier, account):
    assert ns.notify_credential_rotation(account, tokens_invalidated=2, reason="test", admin_username="admin") is True
    _assert_immediate(notifier, "alice@example.com")


def test_email_changed_old_is_immediate(notifier, account):
    assert ns.notify_email_changed_old(account, "old@example.com", "new@example.com") is True
    _assert_immediate(notifier, "old@example.com")


def test_email_changed_new_is_immediate(notifier, account):
    assert ns.notify_email_changed_new(account, "old@example.com", "new@example.com") is True
    _assert_immediate(notifier, "new@example.com")
