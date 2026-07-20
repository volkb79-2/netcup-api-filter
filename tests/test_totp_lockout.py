"""Backend-truth tests for TOTP 2FA lockout (naf-P07).

Before this fix, the TOTP branch of account_auth.verify_2fa() returned
"Invalid code" on a bad code WITHOUT calling increment_2fa_failures(), so
is_2fa_locked() never flipped True and a TOTP code could be brute-forced
indefinitely (the email/telegram branch already counted failures correctly).

These tests drive verify_2fa() directly (not HTTP) and assert on the
lockout state produced by the real counters (Settings-backed), matching
the shape already used for the email branch in test_2fa_security_functional.py.
"""

from __future__ import annotations

import pytest

pyotp = pytest.importorskip("pyotp")

from netcup_api_filter import account_auth
from netcup_api_filter.account_auth import (
    SESSION_KEY_2FA_METHOD,
    SESSION_KEY_2FA_PENDING,
    TFA_LOCKOUT_MINUTES,
    TFA_MAX_ATTEMPTS,
)


def _wrong_code(secret: str) -> str:
    """A 6-digit numeric code guaranteed to differ from the current TOTP value.

    Using a fixed "000000" risks a ~1-in-a-million accidental match against the
    real current code; deriving the wrong code from the actual current value
    keeps the test fully deterministic.
    """
    correct = pyotp.TOTP(secret).now()
    return "111111" if correct != "111111" else "222222"


def _make_totp_account(make_account, username="totpuser"):
    secret = pyotp.random_base32()
    account = make_account(
        username,
        totp_secret=secret,
        totp_enabled=1,
    )
    return account, secret


def test_totp_wrong_code_locks_account_after_max_attempts(app, make_account):
    """O1: TFA_MAX_ATTEMPTS wrong TOTP codes must lock the account, exactly
    like the email/telegram branch does."""
    account, secret = _make_totp_account(make_account)
    wrong_code = _wrong_code(secret)

    with app.test_request_context():
        from flask import session

        session[SESSION_KEY_2FA_PENDING] = account.id
        session[SESSION_KEY_2FA_METHOD] = "totp"

        assert not account_auth.is_2fa_locked(account)

        result = None
        for _ in range(TFA_MAX_ATTEMPTS):
            result = account_auth.verify_2fa(wrong_code, "127.0.0.1")
            assert result.success is False

        # After TFA_MAX_ATTEMPTS wrong codes, the account must be locked —
        # this is the core regression check: before the fix, the counter
        # never moved and this stayed False forever.
        assert account_auth.is_2fa_locked(account)
        assert account_auth.get_2fa_failure_count(account) == TFA_MAX_ATTEMPTS

        # The final result's error must name the lockout, same shape as the
        # email branch ("Too many failed attempts. Account locked for N minutes.")
        assert "too many failed attempts" in result.error.lower()
        assert f"{TFA_LOCKOUT_MINUTES} minutes" in result.error

        # Once locked, verify_2fa's up-front is_2fa_locked() check must reject
        # further attempts (even with a would-be-correct code) without ever
        # touching the TOTP branch.
        locked_result = account_auth.verify_2fa(wrong_code, "127.0.0.1")
        assert locked_result.success is False
        assert "locked" in locked_result.error.lower()


def test_totp_partial_failures_report_attempts_remaining(app, make_account):
    """Failures before the lockout threshold must report attempts remaining,
    matching the email branch's two-message shape."""
    account, secret = _make_totp_account(make_account)
    wrong_code = _wrong_code(secret)

    with app.test_request_context():
        from flask import session

        session[SESSION_KEY_2FA_PENDING] = account.id
        session[SESSION_KEY_2FA_METHOD] = "totp"

        result = account_auth.verify_2fa(wrong_code, "127.0.0.1")

        assert result.success is False
        assert account_auth.get_2fa_failure_count(account) == 1
        assert not account_auth.is_2fa_locked(account)
        assert "attempts remaining" in result.error.lower()
        assert f"{TFA_MAX_ATTEMPTS - 1} attempts remaining" in result.error


def test_totp_correct_code_after_partial_failures_resets_counter(app, make_account):
    """Parity assertion: a correct TOTP code after a partial failure streak
    resets the failure counter (the success path already did this before the
    fix — this pins that it still works once the failure branch increments)."""
    account, secret = _make_totp_account(make_account)
    wrong_code = _wrong_code(secret)

    with app.test_request_context():
        from flask import session

        session[SESSION_KEY_2FA_PENDING] = account.id
        session[SESSION_KEY_2FA_METHOD] = "totp"

        # Partial failure streak (fewer than TFA_MAX_ATTEMPTS).
        for _ in range(TFA_MAX_ATTEMPTS - 2):
            result = account_auth.verify_2fa(wrong_code, "127.0.0.1")
            assert result.success is False

        assert account_auth.get_2fa_failure_count(account) == TFA_MAX_ATTEMPTS - 2
        assert not account_auth.is_2fa_locked(account)

        # Re-arm the pending 2FA session (verify_2fa doesn't clear it on
        # failure, but be explicit that this is the same challenge).
        session[SESSION_KEY_2FA_PENDING] = account.id
        session[SESSION_KEY_2FA_METHOD] = "totp"

        correct_code = pyotp.TOTP(secret).now()
        success_result = account_auth.verify_2fa(correct_code, "127.0.0.1")

        assert success_result.success is True
        assert success_result.account is not None
        assert success_result.account.id == account.id

        # Success resets counters for all methods (account_auth.py's
        # reset_2fa_failures call after the method dispatch).
        assert account_auth.get_2fa_failure_count(account) == 0
        assert not account_auth.is_2fa_locked(account)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
