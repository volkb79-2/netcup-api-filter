"""verify_2fa end to end at function level: email/telegram session codes,
TOTP, recovery codes, lockout counters, session creation and audit rows.

Time is controlled by rewriting stored timestamps (session expiry, Settings
last_failure) -- no sleeping.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pyotp
import pytest
from flask import session

from netcup_api_filter import account_auth, notification_service, recovery_codes
from netcup_api_filter.account_auth import (
    RECOVERY_CODE_MAX_ATTEMPTS,
    SESSION_KEY_2FA_CODE,
    SESSION_KEY_2FA_EXPIRES,
    SESSION_KEY_2FA_METHOD,
    SESSION_KEY_2FA_PENDING,
    SESSION_KEY_USER_ID,
    TFA_MAX_ATTEMPTS,
)
from netcup_api_filter.models import AccountSession, ActivityLog, Settings

IP = "198.51.100.9"
GOOD = "424242"
BAD = "131313"


@pytest.fixture
def lockout_mails(monkeypatch):
    calls = []
    monkeypatch.setattr(
        notification_service, "notify_2fa_lockout",
        lambda account, **kw: calls.append((account.username, kw)),
    )
    return calls


def _arm_code(account, method="email", *, code=GOOD, expires_in=timedelta(minutes=5)):
    session[SESSION_KEY_2FA_PENDING] = account.id
    session[SESSION_KEY_2FA_METHOD] = method
    session[SESSION_KEY_2FA_CODE] = code
    session[SESSION_KEY_2FA_EXPIRES] = (datetime.utcnow() + expires_in).isoformat()


def _events():
    return ActivityLog.query.filter_by(action="login").order_by(ActivityLog.id).all()


# --------------------------------------------------------------------------- preconditions

def test_no_pending_2fa(app):
    with app.test_request_context():
        result = account_auth.verify_2fa(GOOD, IP)
        assert not result.success and result.error == "No pending 2FA verification"
        assert SESSION_KEY_USER_ID not in session


def test_pending_account_deleted_clears_2fa_state(app, make_account, db):
    acct = make_account("vanished1")
    with app.test_request_context():
        _arm_code(acct)
        db.session.delete(acct)
        db.session.commit()
        result = account_auth.verify_2fa(GOOD, IP)
        assert not result.success and result.error == "Account not found"
        assert SESSION_KEY_2FA_PENDING not in session
        assert SESSION_KEY_2FA_CODE not in session


def test_method_without_pending_code(app, make_account):
    acct = make_account("nocode001")
    with app.test_request_context():
        session[SESSION_KEY_2FA_PENDING] = acct.id
        result = account_auth.verify_2fa(GOOD, IP)
        assert not result.success and result.error == "No code pending verification"


# --------------------------------------------------------------------------- email / telegram code

def test_correct_email_code_creates_session_row_and_audit(app, make_account):
    acct = make_account("goodmail01")
    with app.test_request_context(headers={"User-Agent": "pytest-agent"}):
        _arm_code(acct)
        result = account_auth.verify_2fa(GOOD, IP)
        assert result.success and result.account.id == acct.id
        assert session[SESSION_KEY_USER_ID] == acct.id
        token = session[account_auth.SESSION_KEY_SESSION_TOKEN]
        # pending-2FA scaffolding is gone
        for key in (SESSION_KEY_2FA_PENDING, SESSION_KEY_2FA_CODE, SESSION_KEY_2FA_EXPIRES):
            assert key not in session
    row = AccountSession.query.filter_by(account_id=acct.id).one()
    assert row.session_token == token and row.revoked_at is None
    assert row.user_agent == "pytest-agent"
    assert acct.last_login_at is not None
    ev = _events()[-1]
    assert (ev.status, ev.account_id, ev.source_ip) == ("success", acct.id, IP)


def test_telegram_method_uses_session_code_path(app, make_account):
    acct = make_account("goodtg001", telegram_enabled=1, telegram_chat_id="1")
    with app.test_request_context():
        _arm_code(acct, "telegram")
        assert account_auth.verify_2fa(GOOD, IP).success


def test_wrong_code_counts_down_attempts_and_audits(app, make_account):
    acct = make_account("badmail001")
    with app.test_request_context():
        _arm_code(acct)
        first = account_auth.verify_2fa(BAD, IP)
        assert not first.success
        assert f"{TFA_MAX_ATTEMPTS - 1} attempts remaining" in first.error
        assert account_auth.get_2fa_failure_count(acct) == 1
        assert SESSION_KEY_USER_ID not in session
        # pending state survives a failure so the user can retry
        assert session[SESSION_KEY_2FA_PENDING] == acct.id
    assert AccountSession.query.count() == 0
    assert (_events()[-1].status, _events()[-1].status_reason) == ("denied", "Invalid 2FA code")


def test_expired_code_rejected_and_state_cleared(app, make_account):
    acct = make_account("expired001")
    with app.test_request_context():
        _arm_code(acct, expires_in=timedelta(seconds=-1))
        result = account_auth.verify_2fa(GOOD, IP)  # correct code, but too late
        assert not result.success and result.error == "Code has expired"
        assert SESSION_KEY_2FA_PENDING not in session
        assert SESSION_KEY_USER_ID not in session
    assert AccountSession.query.count() == 0


def test_fifth_failure_locks_and_notifies_once(app, make_account, lockout_mails):
    acct = make_account("lockme0001")
    with app.test_request_context():
        _arm_code(acct)
        results = [account_auth.verify_2fa(BAD, IP) for _ in range(TFA_MAX_ATTEMPTS)]
        assert all(not r.success for r in results)
        assert "Too many failed attempts" in results[-1].error
        assert account_auth.is_2fa_locked(acct)
        assert len(lockout_mails) == 1 and lockout_mails[0][0] == "lockme0001"
        assert lockout_mails[0][1]["locked_minutes"] == account_auth.TFA_LOCKOUT_MINUTES

        # while locked even the right code is refused and no session appears
        locked = account_auth.verify_2fa(GOOD, IP)
        assert not locked.success and "Account locked" in locked.error
        assert SESSION_KEY_USER_ID not in session
    assert AccountSession.query.count() == 0
    assert len(lockout_mails) == 1


def test_lockout_expires_after_window(app, make_account, db):
    acct = make_account("unlock0001")
    with app.test_request_context():
        _arm_code(acct)
        for _ in range(TFA_MAX_ATTEMPTS):
            account_auth.verify_2fa(BAD, IP)
        assert account_auth.is_2fa_locked(acct)

        old = (datetime.utcnow() - timedelta(minutes=account_auth.TFA_LOCKOUT_MINUTES + 1)).isoformat()
        Settings.set(f"2fa_failures:{acct.id}", {"count": TFA_MAX_ATTEMPTS, "last_failure": old})
        assert not account_auth.is_2fa_locked(acct)
        assert account_auth.get_2fa_failure_count(acct) == 0
        assert Settings.get(f"2fa_failures:{acct.id}") is None  # stale row removed
        assert account_auth.verify_2fa(GOOD, IP).success


def test_success_resets_failure_counters(app, make_account):
    acct = make_account("resetfail1")
    with app.test_request_context():
        _arm_code(acct)
        account_auth.verify_2fa(BAD, IP)
        account_auth.increment_recovery_code_failures(acct)
        assert account_auth.get_2fa_failure_count(acct) == 1
        assert account_auth.verify_2fa(GOOD, IP).success
        assert account_auth.get_2fa_failure_count(acct) == 0
        assert account_auth.get_recovery_code_failure_count(acct) == 0


def test_lockout_notification_failure_does_not_break_auth(app, make_account, monkeypatch):
    acct = make_account("notifyerr1")

    def boom(*a, **kw):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(notification_service, "notify_2fa_lockout", boom)
    with app.test_request_context():
        for _ in range(TFA_MAX_ATTEMPTS):
            account_auth.increment_2fa_failures(acct)  # must not raise
        assert account_auth.is_2fa_locked(acct)


def test_failure_count_without_last_failure_key_is_kept(app, make_account):
    """A counter row lacking last_failure is treated as fresh, not as expired."""
    acct = make_account("nolastfail")
    with app.test_request_context():
        Settings.set(f"2fa_failures:{acct.id}", {"count": 3})
        assert account_auth.get_2fa_failure_count(acct) == 3
        Settings.set(f"recovery_failures:{acct.id}", {"count": 2})
        assert account_auth.get_recovery_code_failure_count(acct) == 2


# --------------------------------------------------------------------------- TOTP




def _totp_account(make_account, name):
    secret = pyotp.random_base32()
    return make_account(name, totp_enabled=1, totp_secret=secret), secret


def test_valid_totp_logs_in(app, make_account):
    acct, secret = _totp_account(make_account, "totpgood01")
    with app.test_request_context():
        session[SESSION_KEY_2FA_PENDING] = acct.id
        session[SESSION_KEY_2FA_METHOD] = "totp"
        assert account_auth.verify_2fa(pyotp.TOTP(secret).now(), IP).success
        assert session[SESSION_KEY_USER_ID] == acct.id
    assert AccountSession.query.filter_by(account_id=acct.id).count() == 1


def test_totp_method_without_secret(app, make_account):
    acct = make_account("totpnosec1")
    with app.test_request_context():
        session[SESSION_KEY_2FA_PENDING] = acct.id
        session[SESSION_KEY_2FA_METHOD] = "totp"
        result = account_auth.verify_2fa("123456", IP)
        assert not result.success and result.error == "TOTP not configured"


def test_totp_remaining_attempts_message(app, make_account):
    acct, secret = _totp_account(make_account, "totpbad001")
    correct = pyotp.TOTP(secret).now()
    wrong = "111111" if correct != "111111" else "222222"
    with app.test_request_context():
        session[SESSION_KEY_2FA_PENDING] = acct.id
        session[SESSION_KEY_2FA_METHOD] = "totp"
        result = account_auth.verify_2fa(wrong, IP)
        assert f"{TFA_MAX_ATTEMPTS - 1} attempts remaining" in result.error
    assert _events()[-1].status_reason == "Invalid TOTP code"


# --------------------------------------------------------------------------- recovery codes

def _with_recovery(make_account, name, n=3):
    acct = make_account(name)
    codes = recovery_codes.generate_recovery_codes()[:n]
    assert recovery_codes.store_recovery_codes(acct, codes)
    return acct, codes


def test_recovery_code_logs_in_and_is_consumed(app, make_account):
    acct, codes = _with_recovery(make_account, "recover001")
    with app.test_request_context():
        session[SESSION_KEY_2FA_PENDING] = acct.id
        session[SESSION_KEY_2FA_METHOD] = "email"
        result = account_auth.verify_2fa(codes[0], IP)
        assert result.success
        assert session[SESSION_KEY_USER_ID] == acct.id
        assert SESSION_KEY_2FA_PENDING not in session
    assert recovery_codes.get_remaining_code_count(acct) == len(codes) - 1
    assert _events()[-1].status_reason == "Recovery code used"
    assert AccountSession.query.filter_by(account_id=acct.id).count() == 1


def test_recovery_code_is_single_use(app, make_account):
    acct, codes = _with_recovery(make_account, "recover002")
    with app.test_request_context():
        session[SESSION_KEY_2FA_PENDING] = acct.id
        assert account_auth.verify_2fa(codes[0], IP).success
        # new login attempt with the already-used code
        session.clear()
        session[SESSION_KEY_2FA_PENDING] = acct.id
        replay = account_auth.verify_2fa(codes[0], IP)
        assert not replay.success and replay.error == "Invalid recovery code"
        assert SESSION_KEY_USER_ID not in session


def test_recovery_code_clears_both_failure_counters(app, make_account):
    acct, codes = _with_recovery(make_account, "recover003")
    with app.test_request_context():
        session[SESSION_KEY_2FA_PENDING] = acct.id
        account_auth.increment_2fa_failures(acct)
        account_auth.increment_recovery_code_failures(acct)
        assert account_auth.verify_2fa(codes[1], IP).success
        assert account_auth.get_2fa_failure_count(acct) == 0
        assert account_auth.get_recovery_code_failure_count(acct) == 0


def test_recovery_code_lockout_after_repeated_failures(app, make_account):
    acct, codes = _with_recovery(make_account, "recover004")
    wrong = "ABCD-EFGH"
    assert wrong.replace("-", "") not in "".join(codes)
    with app.test_request_context():
        session[SESSION_KEY_2FA_PENDING] = acct.id
        for _ in range(RECOVERY_CODE_MAX_ATTEMPTS):
            r = account_auth.verify_2fa(wrong, IP)
            assert not r.success and r.error == "Invalid recovery code"
        assert account_auth.is_recovery_code_locked(acct)

        # a VALID code is refused while locked; it is not consumed
        locked = account_auth.verify_2fa(codes[0], IP)
        assert not locked.success and "recovery code attempts" in locked.error
        assert SESSION_KEY_USER_ID not in session
    assert recovery_codes.get_remaining_code_count(acct) == len(codes)
    assert _events()[-1].status_reason == "Recovery code locked (rate limit)"


def test_recovery_lockout_expires(app, make_account):
    acct, codes = _with_recovery(make_account, "recover005")
    with app.test_request_context():
        old = (datetime.utcnow()
               - timedelta(minutes=account_auth.RECOVERY_CODE_LOCKOUT_MINUTES + 1)).isoformat()
        Settings.set(f"recovery_failures:{acct.id}",
                     {"count": RECOVERY_CODE_MAX_ATTEMPTS, "last_failure": old})
        assert not account_auth.is_recovery_code_locked(acct)
        session[SESSION_KEY_2FA_PENDING] = acct.id
        assert account_auth.verify_2fa(codes[0], IP).success


def test_recovery_failures_do_not_count_toward_2fa_lockout(app, make_account):
    """Documents the separation of the two counters."""
    acct, _ = _with_recovery(make_account, "recover006")
    with app.test_request_context():
        session[SESSION_KEY_2FA_PENDING] = acct.id
        account_auth.verify_2fa("ABCD-EFGH", IP)
        assert account_auth.get_recovery_code_failure_count(acct) == 1
        assert account_auth.get_2fa_failure_count(acct) == 0


def test_totp_account_can_use_recovery_code(app, make_account):
    acct = make_account("recover007", totp_enabled=1, totp_secret=pyotp.random_base32())
    codes = recovery_codes.generate_recovery_codes()[:2]
    recovery_codes.store_recovery_codes(acct, codes)
    with app.test_request_context():
        session[SESSION_KEY_2FA_PENDING] = acct.id
        session[SESSION_KEY_2FA_METHOD] = "totp"
        assert account_auth.verify_2fa(codes[0], IP).success


def test_account_lock_checked_before_recovery_code(app, make_account):
    acct, codes = _with_recovery(make_account, "recover008")
    with app.test_request_context():
        session[SESSION_KEY_2FA_PENDING] = acct.id
        Settings.set(f"2fa_failures:{acct.id}",
                     {"count": TFA_MAX_ATTEMPTS, "last_failure": datetime.utcnow().isoformat()})
        result = account_auth.verify_2fa(codes[0], IP)
        assert not result.success and "Account locked" in result.error
    assert recovery_codes.get_remaining_code_count(acct) == len(codes)


def test_totp_method_when_pyotp_unavailable_fails_closed(app, make_account, monkeypatch):
    acct = make_account("nopyotp001", totp_enabled=1, totp_secret="JBSWY3DPEHPK3PXP")
    monkeypatch.setitem(__import__("sys").modules, "pyotp", None)  # import raises ImportError
    with app.test_request_context():
        session[SESSION_KEY_2FA_PENDING] = acct.id
        session[SESSION_KEY_2FA_METHOD] = "totp"
        result = account_auth.verify_2fa("123456", IP)
        assert not result.success and result.error == "TOTP not available"
        assert SESSION_KEY_USER_ID not in session
