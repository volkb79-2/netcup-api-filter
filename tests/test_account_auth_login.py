"""login_step1 and send_2fa_code: credential checks, which 2FA methods are
offered, and what is placed in the session for each method."""

from __future__ import annotations

import pytest
from flask import session

from netcup_api_filter import account_auth, notification_service, telegram_service
from netcup_api_filter.models import ActivityLog
from netcup_api_filter.utils import generate_token

IP = "203.0.113.7"


@pytest.fixture
def password():
    return generate_token(24)


@pytest.fixture
def no_telegram(monkeypatch):
    monkeypatch.delenv("TELEGRAM_NOTIFICATIONS_ENABLED", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)


@pytest.fixture
def telegram_on(monkeypatch):
    monkeypatch.setenv("TELEGRAM_NOTIFICATIONS_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", generate_token(30))


def _login_events():
    return ActivityLog.query.filter_by(action="login").order_by(ActivityLog.id).all()


# --------------------------------------------------------------------------- credentials

def test_unknown_user_fails_and_is_audited_without_account(app, no_telegram):
    with app.test_request_context():
        result = account_auth.login_step1("nobody-here", generate_token(24), IP)
        assert not result.success and not result.requires_2fa
        assert result.error == "Invalid username or password"
        assert account_auth.SESSION_KEY_2FA_PENDING not in session
    events = _login_events()
    assert len(events) == 1
    assert (events[0].status, events[0].account_id, events[0].source_ip) == ("denied", None, IP)


def test_wrong_password_gives_same_message_as_unknown_user(app, make_account, password, no_telegram):
    make_account("pwcheck01", password=password, email_2fa_enabled=1)
    with app.test_request_context():
        wrong = account_auth.login_step1("pwcheck01", password + "x", IP)
        unknown = account_auth.login_step1("ghostuser1", password, IP)
        assert wrong.error == unknown.error  # no username enumeration
        assert not wrong.success
        assert account_auth.SESSION_KEY_2FA_PENDING not in session
    reasons = [e.status_reason for e in _login_events()]
    assert reasons == ["Invalid password", "Invalid credentials"]


def test_inactive_account_is_refused_after_password_check(app, make_account, password, no_telegram):
    make_account("pending01", password=password, is_active=0, email_2fa_enabled=1)
    with app.test_request_context():
        result = account_auth.login_step1("pending01", password, IP)
        assert not result.success and "pending admin approval" in result.error
        assert account_auth.SESSION_KEY_2FA_PENDING not in session
    assert _login_events()[0].status_reason == "Account pending approval"


def test_inactive_account_wrong_password_does_not_leak_state(app, make_account, password, no_telegram):
    make_account("pending02", password=password, is_active=0, email_2fa_enabled=1)
    with app.test_request_context():
        result = account_auth.login_step1("pending02", password + "x", IP)
        assert result.error == "Invalid username or password"


def test_unverified_email_is_refused(app, make_account, password, no_telegram):
    make_account("unverif01", password=password, email_2fa_enabled=1)
    with app.test_request_context():
        # make_account forces email_verified=1; flip it afterwards
        from netcup_api_filter.models import Account, db
        acct = Account.query.filter_by(username="unverif01").first()
        acct.email_verified = 0
        db.session.commit()
        result = account_auth.login_step1("unverif01", password, IP)
        assert not result.success and result.error == "Email not verified"
        assert account_auth.SESSION_KEY_2FA_PENDING not in session


# --------------------------------------------------------------------------- method selection

def test_email_only_account_offers_email(app, make_account, password, no_telegram):
    acct = make_account("email0001", password=password, email_2fa_enabled=1)
    with app.test_request_context():
        result = account_auth.login_step1("email0001", password, IP)
        assert result.success and result.requires_2fa
        assert result.tfa_methods == ["email"]
        assert result.account.id == acct.id
        assert session[account_auth.SESSION_KEY_2FA_PENDING] == acct.id
        # step 1 must NOT create a logged-in session
        assert account_auth.SESSION_KEY_USER_ID not in session


def test_totp_enabled_is_offered_alongside_email(app, make_account, password, no_telegram):
    make_account("totp00001", password=password, email_2fa_enabled=1,
                 totp_enabled=1, totp_secret="JBSWY3DPEHPK3PXP")
    with app.test_request_context():
        result = account_auth.login_step1("totp00001", password, IP)
        assert result.tfa_methods == ["email", "totp"]


def test_telegram_linked_but_sending_disabled_is_not_offered(app, make_account, password, no_telegram):
    make_account("tgoff0001", password=password, email_2fa_enabled=1,
                 telegram_enabled=1, telegram_chat_id="424242")
    with app.test_request_context():
        result = account_auth.login_step1("tgoff0001", password, IP)
        assert result.success
        assert "telegram" not in result.tfa_methods
        assert result.tfa_methods == ["email"]


def test_telegram_offered_only_when_server_can_send(app, make_account, password, telegram_on):
    make_account("tgon00001", password=password, email_2fa_enabled=1,
                 telegram_enabled=1, telegram_chat_id="424242")
    with app.test_request_context():
        assert telegram_service.is_telegram_configured_for_sending()
        result = account_auth.login_step1("tgon00001", password, IP)
        assert result.tfa_methods == ["email", "telegram"]


def test_telegram_not_offered_when_account_has_not_enabled_it(app, make_account, password, telegram_on):
    make_account("tgnone001", password=password, email_2fa_enabled=1)
    with app.test_request_context():
        assert account_auth.login_step1("tgnone001", password, IP).tfa_methods == ["email"]


def test_account_without_any_method_is_refused(app, make_account, password, no_telegram):
    make_account("nomethod1", password=password, email_2fa_enabled=0)
    with app.test_request_context():
        result = account_auth.login_step1("nomethod1", password, IP)
        assert not result.success
        assert result.error == "2FA configuration error"
        assert account_auth.SESSION_KEY_2FA_PENDING not in session


def test_telegram_only_without_server_support_is_refused(app, make_account, password, no_telegram):
    """Only method is a dead Telegram option => treated as no method at all."""
    make_account("tgdead001", password=password, email_2fa_enabled=0,
                 telegram_enabled=1, telegram_chat_id="1")
    with app.test_request_context():
        result = account_auth.login_step1("tgdead001", password, IP)
        assert not result.success and result.error == "2FA configuration error"


# --------------------------------------------------------------------------- send_2fa_code

def test_send_code_unknown_account(app):
    with app.test_request_context():
        ok, err = account_auth.send_2fa_code(99999, "email", IP)
        assert (ok, err) == (False, "Account not found")
        assert account_auth.SESSION_KEY_2FA_CODE not in session


def test_send_code_email_stores_code_and_keeps_reference_stable(app, make_account, monkeypatch):
    acct = make_account("sendmail1")
    mails = []
    monkeypatch.setattr(
        notification_service, "send_2fa_email",
        lambda to, username, code, email_ref=None: mails.append((to, username, code, email_ref)) or True,
    )
    with app.test_request_context():
        assert account_auth.send_2fa_code(acct.id, "email", IP) == (True, None)
        first_ref = session[account_auth.SESSION_KEY_2FA_EMAIL_REF_FULL]
        first_code = session[account_auth.SESSION_KEY_2FA_CODE]
        assert session[account_auth.SESSION_KEY_2FA_METHOD] == "email"
        assert session[account_auth.SESSION_KEY_2FA_EXPIRES]

        assert account_auth.send_2fa_code(acct.id, "email", IP) == (True, None)
        # resend keeps the same reference, mailed code is the session code
        assert session[account_auth.SESSION_KEY_2FA_EMAIL_REF_FULL] == first_ref
        assert len(mails) == 2
        assert mails[0][3] == mails[1][3] == first_ref
        assert mails[1][2] == session[account_auth.SESSION_KEY_2FA_CODE]
        assert mails[1][0] == acct.email
        assert len(first_code) == account_auth.TFA_CODE_LENGTH


def test_send_code_email_failure_reports_error(app, make_account, monkeypatch):
    acct = make_account("sendfail1")
    monkeypatch.setattr(notification_service, "send_2fa_email", lambda *a, **kw: False)
    with app.test_request_context():
        ok, err = account_auth.send_2fa_code(acct.id, "email", IP)
        assert ok is False and err == "Failed to send verification email"


def test_send_code_totp_clears_code_and_email_refs(app, make_account):
    acct = make_account("sendtotp1")
    with app.test_request_context():
        session[account_auth.SESSION_KEY_2FA_EMAIL_REF] = "tok"
        session[account_auth.SESSION_KEY_2FA_EMAIL_REF_FULL] = "NAF-2FA-x"
        assert account_auth.send_2fa_code(acct.id, "totp", IP) == (True, None)
        assert session[account_auth.SESSION_KEY_2FA_METHOD] == "totp"
        assert account_auth.SESSION_KEY_2FA_CODE not in session
        assert account_auth.SESSION_KEY_2FA_EMAIL_REF not in session
        assert account_auth.SESSION_KEY_2FA_EMAIL_REF_FULL not in session


def test_send_code_telegram_requires_chat_id(app, make_account):
    acct = make_account("sendtg001", telegram_enabled=1)
    with app.test_request_context():
        assert account_auth.send_2fa_code(acct.id, "telegram", IP) == (False, "Telegram not configured")


def test_send_code_telegram_success_sends_session_code(app, make_account, monkeypatch):
    acct = make_account("sendtg002", telegram_enabled=1, telegram_chat_id="555")
    sent = []
    monkeypatch.setattr(
        telegram_service, "send_telegram_message",
        lambda chat_id, text: sent.append((chat_id, text)) or True,
    )
    with app.test_request_context():
        assert account_auth.send_2fa_code(acct.id, "telegram", IP) == (True, None)
        code = session[account_auth.SESSION_KEY_2FA_CODE]
    assert sent[0][0] == "555"
    assert code in sent[0][1]


def test_send_code_telegram_failure(app, make_account, monkeypatch):
    acct = make_account("sendtg003", telegram_enabled=1, telegram_chat_id="555")
    monkeypatch.setattr(telegram_service, "send_telegram_message", lambda **kw: False)
    with app.test_request_context():
        ok, err = account_auth.send_2fa_code(acct.id, "telegram", IP)
        assert ok is False and "Telegram" in err


def test_send_code_unknown_method(app, make_account):
    acct = make_account("sendbad01")
    with app.test_request_context():
        ok, err = account_auth.send_2fa_code(acct.id, "carrier-pigeon", IP)
        assert ok is False and "Unknown 2FA method" in err
