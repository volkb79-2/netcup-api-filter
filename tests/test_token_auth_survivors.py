"""Pins found by native mutation (R2) on token_auth.py: behaviour the suite asserted nowhere.

Each test names the mutant it kills (line numbers of the pre-change file).
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from flask import jsonify

from netcup_api_filter import token_auth
from netcup_api_filter.models import ActivityLog, generate_user_alias
from netcup_api_filter.token_auth import (
    AuthResult,
    authenticate_token,
    get_security_stats,
    get_security_timeline,
    require_auth,
)


def test_auth_result_does_not_notify_by_default():  # dataclass default False->True
    assert AuthResult(success=False).should_notify_user is False


def _fresh_alias_token():
    return f"naf_{generate_user_alias()}_{'a' * 64}"


def test_no_security_notification_for_unattributable_or_benign_failures(
        app, make_account, make_realm, make_token):
    """invalid_format / account_disabled / realm_not_approved never alert the user (False->True)."""
    results = [authenticate_token("not-a-token")]

    disabled = make_account("off", is_active=0)
    results.append(authenticate_token(make_token(make_realm(disabled))[1]))

    owner = make_account("pending-owner")
    pending = make_realm(owner, status="pending")
    results.append(authenticate_token(make_token(pending)[1]))

    assert [r.error_code for r in results] == ["invalid_format", "account_disabled", "realm_not_approved"]
    assert [r.should_notify_user for r in results] == [False, False, False]


def test_log_activity_without_error_code_has_no_severity(app):
    """Severity is derived only from an error code (the removed `elif status == 'success'` branch
    assigned None to an already-None variable: dead code, not a behaviour)."""
    with app.test_request_context("/", environ_base={"REMOTE_ADDR": "192.0.2.5"}):
        token_auth.log_activity(AuthResult(success=False), "api_call", status="success")
        token_auth.log_activity(AuthResult(success=False), "api_call", status="denied")
    assert [r.severity for r in ActivityLog.query.all()] == [None, None]


def test_missing_token_row_records_the_real_client_address(app):  # Or->And: always 'unknown'
    @require_auth
    def probe():
        return jsonify({})

    app.add_url_rule("/__survivor_probe", "survivor_probe", probe)
    app.test_client().get("/__survivor_probe", environ_base={"REMOTE_ADDR": "198.51.100.7"})
    (row,) = ActivityLog.query.filter_by(error_code="missing_token").all()
    assert row.source_ip == "198.51.100.7"


class _FrozenDatetime(datetime):
    now_value = datetime(2030, 1, 2, 12, 0, 0)

    @classmethod
    def utcnow(cls):
        return cls.now_value


@pytest.fixture
def frozen_clock(monkeypatch):
    monkeypatch.setattr(token_auth, "datetime", _FrozenDatetime)
    return _FrozenDatetime.now_value


def _row_at(db, when, **kw):
    db.session.add(ActivityLog(action="api_auth", source_ip="192.0.2.1", status="denied",
                               error_code="ip_denied", severity="high", is_attack=1,
                               created_at=when, **kw))
    db.session.commit()


def test_security_stats_window_includes_its_exact_start(db, frozen_clock):  # GtE->Gt x3
    start = frozen_clock - timedelta(hours=24)
    _row_at(db, start)                                   # exactly on the boundary: inside
    _row_at(db, start - timedelta(seconds=1))            # just outside
    stats = get_security_stats(hours=24)
    assert stats["by_error_code"] == {"ip_denied": 1}
    assert stats["by_severity"] == {"high": 1}
    assert len(stats["attack_events"]) == 1


def test_security_timeline_window_includes_its_exact_start(db, frozen_clock):  # GtE->Gt
    start = frozen_clock - timedelta(hours=24)
    _row_at(db, start)
    _row_at(db, start - timedelta(seconds=1))
    timeline = get_security_timeline(hours=24)
    assert [item["ip_denied"] for item in timeline] == [1]
