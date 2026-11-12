"""Lockout and recovery-code behaviours with a frozen authentication clock."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pyotp
import pytest
from flask import session

from http_helpers import mint_csrf
from netcup_api_filter import account_auth, notification_service
from netcup_api_filter.account_auth import (
    RECOVERY_CODE_LOCKOUT_MINUTES,
    RECOVERY_CODE_MAX_ATTEMPTS,
    TFA_LOCKOUT_MINUTES,
    TFA_MAX_ATTEMPTS,
)
from netcup_api_filter.api import admin as admin_mod
from netcup_api_filter.models import ActivityLog, Settings
from netcup_api_filter.recovery_codes import (
    RECOVERY_CODE_COUNT,
    generate_recovery_codes,
    get_remaining_code_count,
    store_recovery_codes,
)


IP = "198.51.100.77"
VALID_PASSWORD = "Portal-Lockout-Pass-9!"
EMAIL_CODE = "424242"
BAD_RECOVERY_CODE = "0000-0000"
AUDIT_USER_AGENT = "naf-lockout-audit"


class _FrozenDateTime(datetime):
    now_value = datetime(2032, 4, 5, 12, 0, 0)

    @classmethod
    def utcnow(cls):
        return cls.now_value


@pytest.fixture
def frozen_clock(monkeypatch):
    frozen = datetime(2032, 4, 5, 12, 0, 0)
    monkeypatch.setattr(_FrozenDateTime, "now_value", frozen)
    monkeypatch.setattr(account_auth, "datetime", _FrozenDateTime)
    monkeypatch.setattr(admin_mod, "datetime", _FrozenDateTime)

    real_verify = pyotp.TOTP.verify

    def verify_at_frozen_time(totp, code, for_time=None, valid_window=0):
        check_time = for_time
        if check_time is None:
            check_time = _FrozenDateTime.now_value.replace(tzinfo=UTC)
        return real_verify(totp, code, for_time=check_time, valid_window=valid_window)

    monkeypatch.setattr(pyotp.TOTP, "verify", verify_at_frozen_time)
    return _FrozenDateTime


def _audit_rows(account):
    return [
        (row.status, row.status_reason)
        for row in ActivityLog.query.filter_by(account_id=account.id, action="login")
        .order_by(ActivityLog.id)
    ]


def _arm_portal_2fa(session, account, method, clock, expected_email_code=EMAIL_CODE):
    session[account_auth.SESSION_KEY_2FA_PENDING] = account.id
    session[account_auth.SESSION_KEY_2FA_METHOD] = method
    if method == "email":
        session[account_auth.SESSION_KEY_2FA_CODE] = expected_email_code
        session[account_auth.SESSION_KEY_2FA_EXPIRES] = (
            clock.now_value + timedelta(minutes=5)
        ).isoformat()
    else:
        session.pop(account_auth.SESSION_KEY_2FA_CODE, None)
        session.pop(account_auth.SESSION_KEY_2FA_EXPIRES, None)


def _totp_at_frozen_time(secret, clock):
    frozen_utc = clock.now_value.replace(tzinfo=UTC)
    return pyotp.TOTP(secret).at(frozen_utc)


def _wrong_totp(secret, clock):
    totp = pyotp.TOTP(secret)
    frozen_utc = clock.now_value.replace(tzinfo=UTC)
    valid_codes = {
        totp.at(frozen_utc + timedelta(seconds=offset * totp.interval))
        for offset in (-1, 0, 1)
    }
    for candidate in ("000000", "111111", "222222", "333333", "444444", "555555"):
        if candidate not in valid_codes:
            return candidate
    raise AssertionError("unable to select a TOTP code outside the valid window")


def _post_admin_login(client, username, password, csrf_token):
    return client.post(
        "/admin/login",
        data={"username": username, "password": password, "csrf_token": csrf_token},
        headers={"User-Agent": AUDIT_USER_AGENT},
        environ_overrides={"REMOTE_ADDR": IP},
    )


def _assert_no_audit_secrets(rows, *secrets):
    for row in rows:
        values = (
            row.source_ip,
            row.user_agent,
            row.status_reason,
            row.request_data,
            row.response_summary,
        )
        for value in values:
            for secret in secrets:
                assert secret not in (value or ""), "credential material reached ActivityLog"


@pytest.mark.parametrize("method", ["totp", "email"])
def test_portal_valid_second_factor_is_rejected_until_2fa_lock_expires(
    app, make_account, frozen_clock, monkeypatch, method,
):
    monkeypatch.setattr(notification_service, "notify_2fa_lockout", lambda *args, **kwargs: None)
    secret = pyotp.random_base32() if method == "totp" else None
    account = make_account(
        f"locked-{method}-portal",
        password=VALID_PASSWORD,
        email_2fa_enabled=int(method == "email"),
        totp_enabled=int(method == "totp"),
        totp_secret=secret,
    )
    wrong_code = "999999" if method == "email" else None
    expected_reason = "Invalid TOTP code" if method == "totp" else "Invalid 2FA code"

    with app.test_request_context():
        password_result = account_auth.login_step1(account.username, VALID_PASSWORD, IP)
        assert password_result.success is True
        assert password_result.requires_2fa is True
        assert password_result.tfa_methods == [method]

        for attempt in range(1, TFA_MAX_ATTEMPTS + 1):
            _arm_portal_2fa(session=session, account=account, method=method, clock=frozen_clock)
            attempt_code = wrong_code if method == "email" else _wrong_totp(secret, frozen_clock)
            result = account_auth.verify_2fa(attempt_code, IP)
            assert result.success is False
            if attempt < TFA_MAX_ATTEMPTS:
                assert result.error == f"Invalid code. {TFA_MAX_ATTEMPTS - attempt} attempts remaining."
            else:
                assert result.error == f"Too many failed attempts. Account locked for {TFA_LOCKOUT_MINUTES} minutes."

        assert account_auth.get_2fa_failure_count(account) == TFA_MAX_ATTEMPTS
        assert account_auth.is_2fa_locked(account) is True
        expected_failed_audits = [("denied", expected_reason)] * TFA_MAX_ATTEMPTS
        assert _audit_rows(account) == expected_failed_audits

        # The password is correct and still starts the portal challenge. The
        # valid factor is refused with the lockout message, so the account cannot
        # complete login during the lock window.
        password_during_lock = account_auth.login_step1(account.username, VALID_PASSWORD, IP)
        assert password_during_lock.success is True
        _arm_portal_2fa(session=session, account=account, method=method, clock=frozen_clock)
        valid_code = _totp_at_frozen_time(secret, frozen_clock) if method == "totp" else EMAIL_CODE
        locked_result = account_auth.verify_2fa(valid_code, IP)
        assert locked_result.success is False
        assert locked_result.error == f"Too many failed 2FA attempts. Account locked for {TFA_LOCKOUT_MINUTES} minutes."
        assert account_auth.is_2fa_locked(account) is True
        rows_after_lock = _audit_rows(account)
        assert rows_after_lock[:TFA_MAX_ATTEMPTS] == expected_failed_audits
        assert rows_after_lock[TFA_MAX_ATTEMPTS:] == [("denied", "2FA locked (rate limit)")]

        frozen_clock.now_value += timedelta(minutes=TFA_LOCKOUT_MINUTES, seconds=1)
        password_after_expiry = account_auth.login_step1(account.username, VALID_PASSWORD, IP)
        assert password_after_expiry.success is True
        _arm_portal_2fa(session=session, account=account, method=method, clock=frozen_clock)
        valid_code = _totp_at_frozen_time(secret, frozen_clock) if method == "totp" else EMAIL_CODE
        unlocked_result = account_auth.verify_2fa(valid_code, IP)
        assert unlocked_result.success is True
        assert unlocked_result.account.id == account.id
        assert account_auth.get_2fa_failure_count(account) == 0

    assert _audit_rows(account) == rows_after_lock + [("success", None)]


def test_valid_totp_attempt_rejected_by_active_lock_is_audited(app, make_account, frozen_clock):
    """Minimal repro for the locked-attempt audit gap in account_auth.verify_2fa."""
    secret = pyotp.random_base32()
    account = make_account(
        "locked-totp-audit-user",
        password=VALID_PASSWORD,
        email_2fa_enabled=0,
        totp_enabled=1,
        totp_secret=secret,
    )

    with app.test_request_context(headers={"User-Agent": AUDIT_USER_AGENT}):
        Settings.set(
            f"2fa_failures:{account.id}",
            {"count": TFA_MAX_ATTEMPTS, "last_failure": frozen_clock.now_value.isoformat()},
        )
        session[account_auth.SESSION_KEY_2FA_PENDING] = account.id
        session[account_auth.SESSION_KEY_2FA_METHOD] = "totp"
        code = _totp_at_frozen_time(secret, frozen_clock)
        result = account_auth.verify_2fa(code, IP)
        assert result.success is False
        assert result.error == f"Too many failed 2FA attempts. Account locked for {TFA_LOCKOUT_MINUTES} minutes."

    audit_rows = ActivityLog.query.filter_by(account_id=account.id, action="login").all()
    assert len(audit_rows) == 1
    row = audit_rows[0]
    assert (row.account_id, row.action, row.status, row.status_reason) == (
        account.id,
        "login",
        "denied",
        "2FA locked (rate limit)",
    )
    assert row.source_ip == IP
    assert row.user_agent == AUDIT_USER_AGENT
    _assert_no_audit_secrets(audit_rows, code, VALID_PASSWORD)


def test_valid_recovery_code_is_rejected_during_recovery_lock_and_works_after_expiry(
    app, make_account, frozen_clock,
):
    account = make_account("locked-recovery-user", password=VALID_PASSWORD)
    codes = generate_recovery_codes()
    assert store_recovery_codes(account, codes) is True

    with app.test_request_context():
        session[account_auth.SESSION_KEY_2FA_PENDING] = account.id
        session[account_auth.SESSION_KEY_2FA_METHOD] = "email"

        for attempt in range(1, RECOVERY_CODE_MAX_ATTEMPTS + 1):
            result = account_auth.verify_2fa(BAD_RECOVERY_CODE, IP)
            assert result.success is False
            assert result.error == "Invalid recovery code"
            assert account_auth.get_recovery_code_failure_count(account) == attempt

        assert account_auth.is_recovery_code_locked(account) is True
        locked_result = account_auth.verify_2fa(codes[0], IP)
        assert locked_result.success is False
        assert locked_result.error == (
            f"Too many failed recovery code attempts. Locked for {RECOVERY_CODE_LOCKOUT_MINUTES} minutes."
        )
        assert get_remaining_code_count(account) == RECOVERY_CODE_COUNT

        frozen_clock.now_value += timedelta(minutes=RECOVERY_CODE_LOCKOUT_MINUTES, seconds=1)
        unlocked_result = account_auth.verify_2fa(codes[0], IP)
        assert unlocked_result.success is True
        assert unlocked_result.account.id == account.id
        assert account_auth.get_recovery_code_failure_count(account) == 0
        assert get_remaining_code_count(account) == RECOVERY_CODE_COUNT - 1

    assert _audit_rows(account) == (
        [("denied", "Invalid recovery code")] * RECOVERY_CODE_MAX_ATTEMPTS
        + [("denied", "Recovery code locked (rate limit)"), ("success", "Recovery code used")]
    )


def test_exhausting_recovery_codes_and_reusing_a_consumed_code_fails_with_audit(
    app, make_account,
):
    account = make_account("exhaust-recovery-user", password=VALID_PASSWORD)
    codes = generate_recovery_codes()
    assert len(codes) == RECOVERY_CODE_COUNT
    assert store_recovery_codes(account, codes) is True

    with app.test_request_context():
        for remaining, code in zip(range(RECOVERY_CODE_COUNT - 1, -1, -1), codes):
            session[account_auth.SESSION_KEY_2FA_PENDING] = account.id
            session[account_auth.SESSION_KEY_2FA_METHOD] = "email"
            result = account_auth.verify_2fa(code, IP)
            assert result.success is True
            assert result.account.id == account.id
            assert get_remaining_code_count(account) == remaining

        assert account.recovery_codes is None
        assert get_remaining_code_count(account) == 0

        session[account_auth.SESSION_KEY_2FA_PENDING] = account.id
        session[account_auth.SESSION_KEY_2FA_METHOD] = "email"
        reused_result = account_auth.verify_2fa(codes[0], IP)
        assert reused_result.success is False
        assert reused_result.error == "Invalid recovery code"

        further_result = account_auth.verify_2fa(BAD_RECOVERY_CODE, IP)
        assert further_result.success is False
        assert further_result.error == "Invalid recovery code"

    assert _audit_rows(account) == (
        [("success", "Recovery code used")] * RECOVERY_CODE_COUNT
        + [("denied", "Invalid recovery code"), ("denied", "Invalid recovery code")]
    )


def test_admin_password_lockout_rejects_valid_password_until_frozen_expiry(
    app, make_account, frozen_clock, monkeypatch,
):
    threshold = 2
    lock_minutes = 7
    monkeypatch.setenv("ADMIN_LOGIN_LOCKOUT_THRESHOLD", str(threshold))
    monkeypatch.setenv("ADMIN_LOGIN_LOCKOUT_MINUTES", str(lock_minutes))
    monkeypatch.setattr(admin_mod, "_add_timing_jitter", lambda: None)
    monkeypatch.setattr(admin_mod, "_notify_failed_login_attempt", lambda *args, **kwargs: None)

    admin = make_account(
        "password-lockout-admin",
        is_admin=1,
        password=VALID_PASSWORD,
        email_2fa_enabled=0,
        totp_enabled=0,
        telegram_enabled=0,
    )
    assert admin.verify_password(VALID_PASSWORD) is True

    client = app.test_client()
    csrf_token = mint_csrf(client, "/admin/login")
    for attempt in range(1, threshold + 1):
        response = _post_admin_login(client, admin.username, "wrong-password", csrf_token)
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        if attempt < threshold:
            assert "Invalid credentials" in body
        else:
            assert body.count(f"Too many failed attempts. Account locked for {lock_minutes} minutes.") == 1

    frozen_clock.now_value += timedelta(seconds=1)
    locked_valid_password = _post_admin_login(client, admin.username, VALID_PASSWORD, csrf_token)
    assert locked_valid_password.status_code == 200
    assert locked_valid_password.get_data(as_text=True).count(
        f"Account temporarily locked. Try again in {lock_minutes} minutes."
    ) == 1

    frozen_clock.now_value = datetime(2032, 4, 5, 12, 0, 0) + timedelta(minutes=lock_minutes)
    valid_after_expiry = _post_admin_login(client, admin.username, VALID_PASSWORD, csrf_token)
    assert valid_after_expiry.status_code == 302
    assert valid_after_expiry.headers.get("Location") == "/admin/"

    audit_rows = ActivityLog.query.filter_by(account_id=admin.id, action="login").all()
    assert [(row.status, row.status_reason) for row in audit_rows] == [
        ("denied", "Invalid password"),
        ("denied", "Invalid password"),
        ("denied", "Account locked (login rate limit)"),
        ("success", "Admin login via no_2fa_configured"),
    ]
    assert all(row.source_ip == IP and row.user_agent == AUDIT_USER_AGENT for row in audit_rows)
    _assert_no_audit_secrets(audit_rows, VALID_PASSWORD, "wrong-password")


def test_admin_password_login_outcomes_are_audited(app, make_account, monkeypatch):
    monkeypatch.setattr(admin_mod, "_add_timing_jitter", lambda: None)
    admin = make_account(
        "audit-admin-password-user",
        is_admin=1,
        password=VALID_PASSWORD,
        email_2fa_enabled=0,
        totp_enabled=0,
        telegram_enabled=0,
    )
    portal_account = make_account("audit-portal-at-admin-login")
    unknown_username = "unknown-admin-" + ("x" * 300)
    client = app.test_client()
    csrf_token = mint_csrf(client, "/admin/login")
    wrong_password = "wrong-password"

    wrong = _post_admin_login(client, admin.username, wrong_password, csrf_token)
    assert wrong.status_code == 200
    assert "Invalid credentials" in wrong.get_data(as_text=True)

    non_admin = _post_admin_login(client, portal_account.username, wrong_password, csrf_token)
    assert non_admin.status_code == 200
    assert "Invalid credentials" in non_admin.get_data(as_text=True)

    unknown = _post_admin_login(client, unknown_username, wrong_password, csrf_token)
    assert unknown.status_code == 200
    assert "Invalid credentials" in unknown.get_data(as_text=True)

    success = _post_admin_login(client, admin.username, VALID_PASSWORD, csrf_token)
    assert success.status_code == 302
    assert success.headers.get("Location") == "/admin/"

    audit_rows = ActivityLog.query.filter_by(action="login").order_by(ActivityLog.id).all()
    assert len(audit_rows) == 4
    assert (audit_rows[0].account_id, audit_rows[0].status, audit_rows[0].status_reason) == (
        admin.id,
        "denied",
        "Invalid password",
    )
    assert (audit_rows[1].account_id, audit_rows[1].status, audit_rows[1].status_reason) == (
        None,
        "denied",
        "Invalid credentials",
    )
    assert (audit_rows[2].account_id, audit_rows[2].status, audit_rows[2].status_reason) == (
        None,
        "denied",
        "Invalid credentials",
    )
    assert (audit_rows[3].account_id, audit_rows[3].status, audit_rows[3].status_reason) == (
        admin.id,
        "success",
        "Admin login via no_2fa_configured",
    )
    assert all(row.source_ip == IP and row.user_agent == AUDIT_USER_AGENT for row in audit_rows)
    assert unknown_username not in audit_rows[2].status_reason
    _assert_no_audit_secrets(audit_rows, VALID_PASSWORD, wrong_password)


@pytest.mark.parametrize("method", ["totp", "email"])
def test_admin_two_factor_failure_is_audited(
    app, make_account, frozen_clock, monkeypatch, method,
):
    monkeypatch.setattr(admin_mod, "_add_timing_jitter", lambda: None)
    secret = pyotp.random_base32() if method == "totp" else None
    if method == "email":
        monkeypatch.setattr(notification_service, "send_2fa_email", lambda *args, **kwargs: True)
    admin = make_account(
        f"audit-admin-{method}-user",
        is_admin=1,
        password=VALID_PASSWORD,
        email=f"audit-admin-{method}@example.invalid",
        email_2fa_enabled=int(method == "email"),
        totp_enabled=int(method == "totp"),
        totp_secret=secret,
        telegram_enabled=0,
    )
    client = app.test_client()
    csrf_token = mint_csrf(client, "/admin/login")
    login_response = _post_admin_login(client, admin.username, VALID_PASSWORD, csrf_token)
    assert login_response.status_code == 302
    assert login_response.headers.get("Location") == "/admin/login/2fa"

    csrf_token = mint_csrf(client, f"/admin/login/2fa?method={method}")
    expected_email_code = None
    if method == "email":
        with client.session_transaction() as sess:
            expected_email_code = sess[admin_mod.SESSION_KEY_ADMIN_2FA_CODE]
        wrong_code = "000000" if expected_email_code != "000000" else "111111"
    else:
        wrong_code = _wrong_totp(secret, frozen_clock)

    response = client.post(
        "/admin/login/2fa",
        data={"code": wrong_code, "method": method, "csrf_token": csrf_token},
        headers={"User-Agent": AUDIT_USER_AGENT},
        environ_overrides={"REMOTE_ADDR": IP},
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    if method == "totp":
        assert "Invalid authenticator code." in body
    else:
        assert "Invalid verification code." in body

    audit_rows = ActivityLog.query.filter_by(account_id=admin.id, action="login").all()
    assert len(audit_rows) == 1
    row = audit_rows[0]
    expected_reason = "Invalid TOTP code" if method == "totp" else "Invalid 2FA code"
    assert (row.status, row.status_reason, row.source_ip, row.user_agent) == (
        "denied",
        expected_reason,
        IP,
        AUDIT_USER_AGENT,
    )
    secrets = [VALID_PASSWORD, wrong_code]
    if expected_email_code is not None:
        secrets.append(expected_email_code)
    _assert_no_audit_secrets(audit_rows, *secrets)
