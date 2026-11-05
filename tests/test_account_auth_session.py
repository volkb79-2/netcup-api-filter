"""DB-backed sessions: create_session rotation, logout revocation, the
require_account_auth decorator, and the small session helpers."""

from __future__ import annotations

from datetime import datetime, timedelta

import pyotp
import pytest
from flask import g, session

from netcup_api_filter import account_auth
from netcup_api_filter.account_auth import (
    SESSION_KEY_SESSION_TOKEN,
    SESSION_KEY_USER_ID,
    SESSION_KEY_USERNAME,
    TFA_MAX_ATTEMPTS,
)
from netcup_api_filter.models import AccountSession


def _protected():
    return "secret-page"


def _rows(account):
    return AccountSession.query.filter_by(account_id=account.id).order_by(AccountSession.id).all()


def _login_state(account, db, *, last_active=None):
    """Establish a real logged-in session inside the current request context."""
    account_auth.create_session(account)
    row = _rows(account)[-1]
    if last_active is not None:
        row.last_active = last_active
        db.session.commit()
    return row


# --------------------------------------------------------------------------- create_session

def test_create_session_persists_row_before_token_in_cookie(app, make_account):
    acct = make_account("sess000001")
    with app.test_request_context(environ_base={"REMOTE_ADDR": "192.0.2.55"},
                                  headers={"User-Agent": "UA/1"}):
        account_auth.create_session(acct)
        token = session[SESSION_KEY_SESSION_TOKEN]
        assert session[SESSION_KEY_USER_ID] == acct.id
        assert session[SESSION_KEY_USERNAME] == "sess000001"
        assert session.permanent is True
    (row,) = _rows(acct)
    assert row.session_token == token
    assert (row.ip_address, row.user_agent) == ("192.0.2.55", "UA/1")
    assert row.revoked_at is None


def test_create_session_rotates_previous_session_token(app, make_account):
    acct = make_account("sess000002")
    with app.test_request_context():
        account_auth.create_session(acct)
        first = session[SESSION_KEY_SESSION_TOKEN]
        account_auth.create_session(acct)
        second = session[SESSION_KEY_SESSION_TOKEN]
    assert first != second
    old, new = _rows(acct)
    assert (old.session_token, old.revoked_reason) == (first, "rotated")
    assert old.revoked_at is not None
    assert (new.session_token, new.revoked_at) == (second, None)


def test_create_session_commit_failure_rolls_back_and_sets_no_token(app, make_account, db, monkeypatch):
    acct = make_account("sess000003")
    rolled_back = []

    def failing_commit():
        raise RuntimeError("disk full")

    with app.test_request_context():
        with monkeypatch.context() as m:
            m.setattr(db.session, "commit", failing_commit)
            m.setattr(db.session, "rollback", lambda: rolled_back.append(1))
            with pytest.raises(RuntimeError, match="disk full"):
                account_auth.create_session(acct)
        assert SESSION_KEY_SESSION_TOKEN not in session  # no cookie token without a row
    assert rolled_back == [1]
    db.session.rollback()
    assert _rows(acct) == []


# --------------------------------------------------------------------------- logout

def test_logout_revokes_row_and_clears_session(app, make_account, db):
    acct = make_account("logout0001")
    with app.test_request_context():
        row_id = _login_state(acct, db).id
        account_auth.logout()
        assert dict(session) == {}
    row = AccountSession.query.get(row_id)
    assert row.revoked_reason == "logout" and row.revoked_at is not None


def test_logout_does_not_overwrite_earlier_revocation(app, make_account, db):
    acct = make_account("logout0002")
    with app.test_request_context():
        row = _login_state(acct, db)
        stamp = datetime(2020, 1, 1)
        row.revoked_at, row.revoked_reason = stamp, "admin"
        db.session.commit()
        account_auth.logout()
    refreshed = AccountSession.query.get(row.id)
    assert (refreshed.revoked_at, refreshed.revoked_reason) == (stamp, "admin")


def test_logout_without_session_is_a_noop(app):
    with app.test_request_context():
        account_auth.logout()
        assert dict(session) == {}


def test_logout_swallows_db_error_but_still_clears_cookie(app, make_account, db, monkeypatch):
    acct = make_account("logout0003")
    with app.test_request_context():
        _login_state(acct, db)
        with monkeypatch.context() as m:
            m.setattr(db.session, "commit", lambda: (_ for _ in ()).throw(RuntimeError("x")))
            m.setattr(db.session, "rollback", lambda: None)
            account_auth.logout()
        assert dict(session) == {}
    db.session.rollback()


# --------------------------------------------------------------------------- current account helpers

def test_get_current_account_and_is_authenticated(app, make_account):
    acct = make_account("current001")
    with app.test_request_context():
        assert account_auth.get_current_account() is None
        assert account_auth.is_authenticated() is False
        session[SESSION_KEY_USER_ID] = acct.id
        assert account_auth.get_current_account().id == acct.id
        assert account_auth.is_authenticated() is True


# --------------------------------------------------------------------------- require_account_auth

def test_decorator_redirects_anonymous_to_login(app):
    with app.test_request_context("/account/dashboard"):
        resp = account_auth.require_account_auth(_protected)()
        assert resp.status_code == 302
        assert resp.location.endswith("/account/login")


def test_decorator_unknown_account_id_in_cookie(app):
    with app.test_request_context():
        session[SESSION_KEY_USER_ID] = 424242
        resp = account_auth.require_account_auth(_protected)()
        assert resp.status_code == 302


def test_decorator_allows_valid_session_and_sets_g(app, make_account, db):
    acct = make_account("deco000001")
    with app.test_request_context():
        row = _login_state(acct, db)
        assert account_auth.require_account_auth(_protected)() == "secret-page"
        assert g.account.id == acct.id
        assert g.account_session.id == row.id


def test_decorator_rejects_cookie_without_session_token(app, make_account):
    acct = make_account("deco000002")
    with app.test_request_context():
        session[SESSION_KEY_USER_ID] = acct.id
        resp = account_auth.require_account_auth(_protected)()
        assert resp.status_code == 302
        assert SESSION_KEY_USER_ID not in session  # forced logout


def test_decorator_rejects_token_without_matching_row(app, make_account):
    acct = make_account("deco000003")
    with app.test_request_context():
        session[SESSION_KEY_USER_ID] = acct.id
        session[SESSION_KEY_SESSION_TOKEN] = "forged-token-with-no-row"
        resp = account_auth.require_account_auth(_protected)()
        assert resp.status_code == 302
        assert SESSION_KEY_USER_ID not in session


def test_decorator_rejects_token_belonging_to_other_account(app, make_account, db):
    victim = make_account("deco000004")
    attacker = make_account("deco000005")
    with app.test_request_context():
        victim_row = _login_state(victim, db)
        stolen = victim_row.session_token
        session.clear()
        session[SESSION_KEY_USER_ID] = attacker.id
        session[SESSION_KEY_SESSION_TOKEN] = stolen
        resp = account_auth.require_account_auth(_protected)()
        # attacker is not admitted: redirected, logged out, no g.account leak
        assert resp.status_code == 302
        assert SESSION_KEY_USER_ID not in session
        assert "account" not in g
    # NOTE: the fallback logout() revokes by token alone, so the victim's row is
    # revoked as a side effect (observation, see report); not asserted either way.


def test_decorator_rejects_revoked_session(app, make_account, db):
    acct = make_account("deco000006")
    with app.test_request_context():
        row = _login_state(acct, db)
        row.revoked_at, row.revoked_reason = datetime.utcnow(), "admin"
        db.session.commit()
        resp = account_auth.require_account_auth(_protected)()
        assert resp.status_code == 302
        assert SESSION_KEY_USER_ID not in session


def test_decorator_rejects_deactivated_account_and_revokes_session(app, make_account, db):
    acct = make_account("deco000007")
    with app.test_request_context():
        row = _login_state(acct, db)
        acct.is_active = 0
        db.session.commit()
        resp = account_auth.require_account_auth(_protected)()
        assert resp.status_code == 302
        assert SESSION_KEY_USER_ID not in session
    assert AccountSession.query.get(row.id).revoked_reason == "logout"


def test_decorator_touches_stale_last_active(app, make_account, db):
    acct = make_account("deco000008")
    stale = datetime.utcnow() - timedelta(minutes=10)
    with app.test_request_context():
        row = _login_state(acct, db, last_active=stale)
        account_auth.require_account_auth(_protected)()
    assert AccountSession.query.get(row.id).last_active > stale + timedelta(minutes=9)


def test_decorator_does_not_write_when_last_active_is_recent(app, make_account, db):
    acct = make_account("deco000009")
    recent = datetime.utcnow() - timedelta(seconds=5)
    with app.test_request_context():
        row = _login_state(acct, db, last_active=recent)
        account_auth.require_account_auth(_protected)()
    assert AccountSession.query.get(row.id).last_active == recent  # throttled


def test_decorator_survives_failing_touch(app, make_account, db, monkeypatch):
    acct = make_account("deco000010")
    stale = datetime.utcnow() - timedelta(minutes=10)
    with app.test_request_context():
        _login_state(acct, db, last_active=stale)
        with monkeypatch.context() as m:
            m.setattr(db.session, "commit", lambda: (_ for _ in ()).throw(RuntimeError("busy")))
            m.setattr(db.session, "rollback", lambda: None)
            assert account_auth.require_account_auth(_protected)() == "secret-page"
    db.session.rollback()


# --------------------------------------------------------------------------- full 2FA -> session -> logout

def test_totp_lockout_final_message_and_full_login_logout_cycle(app, make_account, db):
    secret = pyotp.random_base32()
    acct = make_account("cycle00001", totp_enabled=1, totp_secret=secret)
    correct = pyotp.TOTP(secret).now()
    wrong = "111111" if correct != "111111" else "222222"
    with app.test_request_context():
        session[account_auth.SESSION_KEY_2FA_PENDING] = acct.id
        session[account_auth.SESSION_KEY_2FA_METHOD] = "totp"
        last = None
        for _ in range(TFA_MAX_ATTEMPTS):
            last = account_auth.verify_2fa(wrong, "192.0.2.1")
        assert "Too many failed attempts" in last.error

        # lockout cleared (as after window expiry) -> login -> protected -> logout -> protected
        account_auth.reset_2fa_failures(acct)
        assert account_auth.verify_2fa(correct, "192.0.2.1").success
        assert account_auth.require_account_auth(_protected)() == "secret-page"
        account_auth.logout()
        assert account_auth.require_account_auth(_protected)().status_code == 302
    assert _rows(acct)[-1].revoked_reason == "logout"


def test_create_session_with_stale_previous_token_has_nothing_to_rotate(app, make_account, db):
    """Cookie carries a token whose row is gone/already revoked: a fresh row is
    still issued and the already-revoked row keeps its original reason."""
    acct = make_account("sess000004")
    with app.test_request_context():
        session[SESSION_KEY_SESSION_TOKEN] = "token-with-no-row"
        account_auth.create_session(acct)
        fresh = session[SESSION_KEY_SESSION_TOKEN]
        assert fresh != "token-with-no-row"
        # second login: previous row is already revoked by admin -> reason untouched
        first = _rows(acct)[0]
        first.revoked_at, first.revoked_reason = datetime(2020, 1, 1), "admin"
        db.session.commit()
        account_auth.create_session(acct)
    assert _rows(acct)[0].revoked_reason == "admin"
    assert len(_rows(acct)) == 2
