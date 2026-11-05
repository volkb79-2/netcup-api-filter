"""Registration-flow and helper tests for account_auth (generate_code,
register_account, verify_registration, resend_verification,
finalize_registration_with_realms).

Outbound notifications are replaced by recording stubs; everything else
(DB rows, bcrypt hashing, validators) is real.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from netcup_api_filter import account_auth, notification_service
from netcup_api_filter.models import Account, AccountRealm, RegistrationRequest
from netcup_api_filter.utils import generate_token


@pytest.fixture
def sent(monkeypatch):
    """Record verification / admin-notification mails instead of sending."""
    calls = {"verification": [], "admin": []}
    monkeypatch.setattr(
        notification_service, "send_verification_email",
        lambda **kw: calls["verification"].append(kw) or True,
    )
    monkeypatch.setattr(
        notification_service, "notify_admin_pending_account",
        lambda *a, **kw: calls["admin"].append(a) or True,
    )
    return calls


def _register(username="reguser01", email="reguser01@example.com"):
    password = generate_token(24)
    return account_auth.register_account(username, email, password), password


# --------------------------------------------------------------------------- helpers

def test_generate_code_is_numeric_with_requested_length():
    for length in (1, 6, 12):
        code = account_auth.generate_code(length)
        assert len(code) == length
        assert code.isdigit()


def test_generate_unique_user_alias_skips_taken_alias(app, make_account, monkeypatch):
    taken = make_account("aliasowner")
    aliases = iter([taken.user_alias, "fresh_alias_value"])
    monkeypatch.setattr(account_auth, "generate_user_alias", lambda: next(aliases))
    assert account_auth._generate_unique_user_alias() == "fresh_alias_value"


def test_generate_unique_user_alias_gives_up_after_ten_collisions(app, make_account, monkeypatch):
    taken = make_account("aliasowner")
    monkeypatch.setattr(account_auth, "generate_user_alias", lambda: taken.user_alias)
    with pytest.raises(RuntimeError, match="unique user_alias"):
        account_auth._generate_unique_user_alias()


# --------------------------------------------------------------------------- register

def test_register_success_creates_request_and_sends_code(app, sent):
    result, password = _register()
    assert result.success and result.request_id
    req = RegistrationRequest.query.get(result.request_id)
    assert req.username == "reguser01"
    assert req.password_hash != password  # never stored plaintext
    assert len(req.verification_code) == account_auth.VERIFICATION_CODE_LENGTH
    assert req.verification_expires_at > datetime.utcnow()
    # no Account yet: needs verification + admin approval
    assert Account.query.filter_by(username="reguser01").first() is None
    assert len(sent["verification"]) == 1
    assert sent["verification"][0]["email"] == "reguser01@example.com"


@pytest.mark.parametrize("username", ["", "a"])
def test_register_rejects_invalid_username(app, sent, username):
    result = account_auth.register_account(username, "x@example.com", generate_token(24))
    assert not result.success and result.field == "username"
    assert RegistrationRequest.query.count() == 0


def test_register_rejects_existing_account_username(app, sent, make_account):
    make_account("takenuser")
    result = account_auth.register_account("takenuser", "other@example.com", generate_token(24))
    assert (result.success, result.field) == (False, "username")
    assert "already registered" in result.error


def test_register_rejects_pending_username(app, sent):
    first, _ = _register("pendinguser", "p1@example.com")
    assert first.success
    second = account_auth.register_account("pendinguser", "p2@example.com", generate_token(24))
    assert (second.success, second.field) == (False, "username")
    assert "pending" in second.error
    assert RegistrationRequest.query.count() == 1


@pytest.mark.parametrize("email", ["", "nodomain", "no-at.example.com", "nodot@localhost"])
def test_register_rejects_malformed_email(app, sent, email):
    result = account_auth.register_account("mailbad01", email, generate_token(24))
    assert (result.success, result.field) == (False, "email")


def test_register_rejects_email_of_existing_account(app, sent, make_account):
    make_account("owner", email="shared@example.com")
    result = account_auth.register_account("newname01", "shared@example.com", generate_token(24))
    assert (result.success, result.field) == (False, "email")
    assert "already registered" in result.error


def test_register_rejects_email_with_pending_request(app, sent):
    first, _ = _register("firstreg", "dup@example.com")
    assert first.success
    result = account_auth.register_account("secondreg", "dup@example.com", generate_token(24))
    assert (result.success, result.field) == (False, "email")
    assert "pending" in result.error


def test_register_rejects_weak_password(app, sent):
    result = account_auth.register_account("weakpw001", "weak@example.com", "short")
    assert (result.success, result.field) == (False, "password")
    assert RegistrationRequest.query.count() == 0
    assert sent["verification"] == []


# --------------------------------------------------------------------------- verify

def test_verify_registration_unknown_id(app):
    result = account_auth.verify_registration(99999, "123456")
    assert not result.success and "not found" in result.error


def test_verify_registration_correct_code_extends_expiry(app, sent):
    result, _ = _register()
    req = RegistrationRequest.query.get(result.request_id)
    verified = account_auth.verify_registration(req.id, req.verification_code)
    assert verified.success and verified.request_id == req.id
    db_req = RegistrationRequest.query.get(req.id)
    # expiry bumped from 30 minutes to ~24h for the realm-request step
    assert db_req.verification_expires_at > datetime.utcnow() + timedelta(hours=23)


def test_verify_registration_wrong_code_counts_attempts(app, sent):
    result, _ = _register()
    req = RegistrationRequest.query.get(result.request_id)
    wrong = "000000" if req.verification_code != "000000" else "111111"
    first = account_auth.verify_registration(req.id, wrong)
    assert not first.success and "4 attempts remaining" in first.error
    assert RegistrationRequest.query.get(req.id).verification_attempts == 1


def test_verify_registration_locks_after_five_failures(app, sent):
    result, _ = _register()
    req = RegistrationRequest.query.get(result.request_id)
    right = req.verification_code
    wrong = "000000" if right != "000000" else "111111"
    for _ in range(5):
        assert not account_auth.verify_registration(req.id, wrong).success
    # even the CORRECT code is now refused
    locked = account_auth.verify_registration(req.id, right)
    assert not locked.success and "Too many" in locked.error


def test_verify_registration_expired_request_is_deleted(app, sent, db):
    result, _ = _register()
    req = RegistrationRequest.query.get(result.request_id)
    req.verification_expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.session.commit()
    outcome = account_auth.verify_registration(req.id, req.verification_code)
    assert not outcome.success and "expired" in outcome.error
    assert RegistrationRequest.query.get(req.id) is None


# --------------------------------------------------------------------------- resend

def test_resend_verification_unknown_id(app):
    assert not account_auth.resend_verification(4242).success


def test_resend_verification_resets_attempts_and_expiry(app, sent, db):
    result, _ = _register()
    req = RegistrationRequest.query.get(result.request_id)
    req.verification_attempts = 4
    req.verification_expires_at = datetime.utcnow() - timedelta(minutes=5)
    db.session.commit()
    sent["verification"].clear()

    outcome = account_auth.resend_verification(req.id)
    assert outcome.success
    refreshed = RegistrationRequest.query.get(req.id)
    assert refreshed.verification_attempts == 0
    assert refreshed.verification_expires_at > datetime.utcnow()
    assert len(sent["verification"]) == 1
    assert sent["verification"][0]["code"] == refreshed.verification_code


# --------------------------------------------------------------------------- finalize

def test_finalize_unknown_request(app):
    assert not account_auth.finalize_registration_with_realms(31337).success


def test_finalize_creates_inactive_account_with_pending_realms(app, sent, db):
    result, password = _register("finaluser", "final@example.com")
    req = RegistrationRequest.query.get(result.request_id)
    req.add_realm_request("host", "example.com", "vpn", ["A"], ["read"])
    db.session.commit()
    req_id, req_hash = req.id, req.password_hash

    outcome = account_auth.finalize_registration_with_realms(req_id)
    assert outcome.success

    account = Account.query.filter_by(username="finaluser").first()
    assert account.is_active == 0          # waits for admin approval
    assert account.email_2fa_enabled == 1  # email 2FA mandatory
    assert account.email_verified == 1
    assert account.password_hash == req_hash
    assert account.verify_password(password)
    realms = AccountRealm.query.filter_by(account_id=account.id).all()
    assert len(realms) == 1
    assert (realms[0].status, realms[0].realm_value, realms[0].domain) == ("pending", "vpn", "example.com")
    assert RegistrationRequest.query.get(req_id) is None
    assert sent["admin"] == [("finaluser", "final@example.com", 1)]
