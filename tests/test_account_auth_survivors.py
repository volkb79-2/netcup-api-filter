"""Pins found by native mutation (R2) on account_auth.py: behaviour the suite asserted nowhere.

Every test names the mutant it kills (line numbers of the pre-change file).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import pyotp
import pytest
from flask import session

from netcup_api_filter import account_auth, email_reference, notification_service, recovery_codes
from netcup_api_filter.account_auth import (
    RECOVERY_CODE_MAX_ATTEMPTS,
    SESSION_KEY_2FA_CODE,
    SESSION_KEY_2FA_EMAIL_REF,
    SESSION_KEY_2FA_EMAIL_REF_FULL,
    SESSION_KEY_2FA_EXPIRES,
    SESSION_KEY_2FA_METHOD,
    SESSION_KEY_2FA_PENDING,
    TFA_MAX_ATTEMPTS,
)
from netcup_api_filter.models import AccountSession, ActivityLog, Settings
from netcup_api_filter.utils import generate_token

IP = "198.51.100.9"
GOOD = "424242"
BAD_RECOVERY_CODE = "0000-0000"  # The generator alphabet excludes 0.


class _Frozen(datetime):
    now_value = datetime(2030, 1, 2, 12, 0, 0)

    @classmethod
    def utcnow(cls):
        return cls.now_value


@pytest.fixture
def frozen(monkeypatch):
    monkeypatch.setattr(account_auth, "datetime", _Frozen)
    return _Frozen.now_value


def _statuses():
    return [row.status for row in ActivityLog.query.filter_by(action="login").order_by(ActivityLog.id)]


def _arm(account, method="email", *, code=GOOD, expires=None):
    session[SESSION_KEY_2FA_PENDING] = account.id
    session[SESSION_KEY_2FA_METHOD] = method
    if code is not None:
        session[SESSION_KEY_2FA_CODE] = code
    if expires is not None:
        session[SESSION_KEY_2FA_EXPIRES] = expires.isoformat()


# --- login_step1 audit rows: failures are recorded as denied (377, 387: False->True) ----------

def test_wrong_password_is_audited_as_denied(app, make_account):
    password = generate_token(24)
    make_account("pwfail0001", password=password)
    with app.test_request_context():
        assert not account_auth.login_step1("pwfail0001", password + "x", IP).success
    assert _statuses() == ["denied"]


def test_inactive_account_is_audited_as_denied(app, make_account):
    password = generate_token(24)
    make_account("inactive01", password=password, is_active=0)
    with app.test_request_context():
        assert not account_auth.login_step1("inactive01", password, IP).success
    assert _statuses() == ["denied"]


# --- 2FA audit rows (539, 560, 572, 591) ------------------------------------------------------

def _with_recovery(make_account, name):
    acct = make_account(name)
    codes = recovery_codes.generate_recovery_codes()[:2]
    assert recovery_codes.store_recovery_codes(acct, codes)
    return acct, codes


def test_recovery_code_login_is_audited_as_success(app, make_account):  # 560 True->False
    acct, codes = _with_recovery(make_account, "recsucc001")
    with app.test_request_context():
        _arm(acct, code=None)
        assert account_auth.verify_2fa(codes[0], IP).success
    assert _statuses() == ["success"]


def test_invalid_recovery_code_is_audited_as_denied(app, make_account):  # 572
    acct, _codes = _with_recovery(make_account, "recbad0001")
    with app.test_request_context():
        _arm(acct, code=None)
        assert not account_auth.verify_2fa(BAD_RECOVERY_CODE, IP).success
    assert _statuses() == ["denied"]


def test_locked_recovery_attempt_is_audited_as_denied(app, make_account, frozen):  # 539
    acct, _codes = _with_recovery(make_account, "reclock001")
    with app.test_request_context():
        Settings.set(f"recovery_failures:{acct.id}",
                     {"count": RECOVERY_CODE_MAX_ATTEMPTS, "last_failure": frozen.isoformat()})
        _arm(acct, code=None)
        assert not account_auth.verify_2fa(BAD_RECOVERY_CODE, IP).success
    assert _statuses() == ["denied"]


def test_invalid_totp_is_audited_as_denied(app, make_account, monkeypatch):  # 591
    class RejectingTOTP:
        def __init__(self, _secret):
            pass

        def verify(self, _code, valid_window=1):
            return False

    secret = pyotp.random_base32()
    acct = make_account("totpdeny01", totp_enabled=1, totp_secret=secret)
    monkeypatch.setattr(pyotp, "TOTP", RejectingTOTP)
    with app.test_request_context():
        _arm(acct, "totp", code=None)
        result = account_auth.verify_2fa("111111", IP)
        assert not result.success and result.error == f"Invalid code. {TFA_MAX_ATTEMPTS - 1} attempts remaining."
    assert _statuses() == ["denied"]


# --- recovery-code shape detection needs BOTH length 9 and a dash (532 And->Or) ---------------

@pytest.mark.parametrize("code", ["42-424", "123456789"])
def test_session_code_that_only_resembles_a_recovery_code_is_checked_as_session_code(
        app, make_account, frozen, code):
    acct = make_account("shape00001")
    with app.test_request_context():
        _arm(acct, code=code, expires=frozen + timedelta(minutes=5))
        assert account_auth.verify_2fa(code, IP).success


# --- pending session code needs BOTH the code and its expiry (613 Or->And) ---------------------

def test_code_without_expiry_is_not_pending(app, make_account):
    acct = make_account("noexp00001")
    with app.test_request_context():
        _arm(acct, code=GOOD)
        result = account_auth.verify_2fa(GOOD, IP)
        assert not result.success and result.error == "No code pending verification"


def test_expiry_without_code_is_not_pending(app, make_account, frozen):
    acct = make_account("nocode0001")
    with app.test_request_context():
        _arm(acct, code=None, expires=frozen + timedelta(minutes=5))
        result = account_auth.verify_2fa(GOOD, IP)
        assert not result.success and result.error == "No code pending verification"


# --- boundaries (618, 1106, 1165, 789: Gt->GtE) ------------------------------------------------

def test_code_is_valid_up_to_and_including_its_expiry_instant(app, make_account, frozen):  # 618
    acct = make_account("expedge001")
    with app.test_request_context():
        _arm(acct, code=GOOD, expires=frozen)
        assert account_auth.verify_2fa(GOOD, IP).success


def test_2fa_lockout_still_counts_at_exactly_the_window_edge(app, make_account, frozen):  # 1106
    acct = make_account("tfaedge001")
    edge = frozen - timedelta(minutes=account_auth.TFA_LOCKOUT_MINUTES)
    with app.test_request_context():
        Settings.set(f"2fa_failures:{acct.id}", {"count": TFA_MAX_ATTEMPTS, "last_failure": edge.isoformat()})
        assert account_auth.get_2fa_failure_count(acct) == TFA_MAX_ATTEMPTS
        assert Settings.get(f"2fa_failures:{acct.id}") is not None


def test_recovery_lockout_still_counts_at_exactly_the_window_edge(app, make_account, frozen):  # 1165
    acct = make_account("recedge001")
    edge = frozen - timedelta(minutes=account_auth.RECOVERY_CODE_LOCKOUT_MINUTES)
    with app.test_request_context():
        Settings.set(f"recovery_failures:{acct.id}",
                     {"count": RECOVERY_CODE_MAX_ATTEMPTS, "last_failure": edge.isoformat()})
        assert account_auth.get_recovery_code_failure_count(acct) == RECOVERY_CODE_MAX_ATTEMPTS


def test_last_active_is_not_touched_at_exactly_the_throttle_edge(app, make_account, db, frozen):  # 789
    acct = make_account("touchedge1")
    with app.test_request_context():
        account_auth.create_session(acct)
        row = AccountSession.query.filter_by(account_id=acct.id).one()
        row.last_active = frozen - timedelta(seconds=60)
        db.session.commit()
        edge = row.last_active
        account_auth.require_account_auth(lambda: "page")()
        db.session.expire_all()
        assert AccountSession.query.get(row.id).last_active == edge


# --- email reference fallback (464 Or->And) ----------------------------------------------------

def test_email_2fa_keeps_the_full_reference_when_it_has_no_token_part(app, make_account, monkeypatch):
    acct = make_account("refback001")
    monkeypatch.setattr(email_reference, "email_ref_token", lambda ref: None)
    monkeypatch.setattr(notification_service, "send_2fa_email", lambda *a, **kw: True)
    with app.test_request_context():
        assert account_auth.send_2fa_code(acct.id, "email", IP) == (True, None)
        assert session[SESSION_KEY_2FA_EMAIL_REF]
        assert session[SESSION_KEY_2FA_EMAIL_REF] == session[SESSION_KEY_2FA_EMAIL_REF_FULL]


# --- rejection log keeps the given reason, falls back only when empty (1066 Or->And) -----------

@pytest.mark.parametrize("reason,expected", [("duplicate signup", "reason: duplicate signup"),
                                              (None, "reason: No reason given")])
def test_rejection_is_logged_with_its_reason(app, make_account, monkeypatch, caplog, reason, expected):
    monkeypatch.setattr(notification_service, "notify_account_rejected", lambda *a, **kw: None)
    admin = make_account("rejadmin01", is_admin=1)
    pending = make_account("rejpend001", is_active=0)
    with caplog.at_level(logging.INFO, logger=account_auth.logger.name):
        assert account_auth.reject_account(pending.id, admin, reason=reason) == (True, None)
    assert expected in caplog.text
