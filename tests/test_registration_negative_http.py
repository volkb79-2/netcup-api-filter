"""Hermetic negative-path tests for registration, admin approval and CSRF.

Moved from ui_tests/tests/features/test_registration_negative.py (S8). Runs the
real Flask stack through the test client with CSRF protection ENABLED (tokens
are scraped from the rendered forms, like a browser would), a tmp SQLite DB and
recording stubs for outbound mail. The originals accepted broad status sets or
"login in url" style disjunctions; these pin the exact redirect/flash and assert
the DB state (no Account / RegistrationRequest created, no approval applied).

The token-boundary class of the original (cross-domain, read-only create/delete,
invalid/missing token) is covered by tests/test_api_security_http.py.
"""
from __future__ import annotations

import pytest

from netcup_api_filter import notification_service
from netcup_api_filter.models import Account, RegistrationRequest
from netcup_api_filter.utils import generate_token

from http_helpers import login_portal, mint_csrf


@pytest.fixture(autouse=True)
def mail_stub(monkeypatch):
    sent = {"verification": [], "admin": []}
    monkeypatch.setattr(
        notification_service, "send_verification_email",
        lambda **kw: sent["verification"].append(kw) or True,
    )
    monkeypatch.setattr(
        notification_service, "notify_admin_pending_account",
        lambda *a, **kw: sent["admin"].append(a) or True,
    )
    return sent


def _csrf(client, path):
    return mint_csrf(client, path)


def _register(client, username, email=None, password=None, confirm=None, csrf=None):
    password = password if password is not None else generate_token(24)
    data = {
        "username": username,
        "email": email or f"{username}@example.com",
        "password": password,
        "confirm_password": confirm if confirm is not None else password,
        "terms": "on",
        "csrf_token": csrf if csrf is not None else _csrf(client, "/account/register"),
    }
    return client.post("/account/register", data=data), password


def _location(resp):
    return resp.headers.get("Location", "")


# ---------------------------------------------------------------------------
# Workflow step skipping
# ---------------------------------------------------------------------------

def test_verify_without_registration_redirects_to_register(client):
    resp = client.get("/account/register/verify")
    assert resp.status_code == 302
    assert _location(resp).endswith("/account/register")


def test_realms_without_registration_redirects_to_register(client):
    resp = client.get("/account/register/realms")
    assert resp.status_code == 302
    assert _location(resp).endswith("/account/register")


def test_realms_before_email_verification_is_blocked(client, db):
    resp, _pw = _register(client, "skipverify")
    assert resp.status_code == 302 and _location(resp).endswith("/account/register/verify")

    skip = client.get("/account/register/realms")
    assert skip.status_code == 302 and _location(skip).endswith("/account/register")
    # POSTing "submit" directly must not finalize either.
    skip_post = client.post(
        "/account/register/realms",
        data={"action": "submit", "csrf_token": _csrf(client, "/account/register/verify")},
    )
    assert skip_post.status_code == 302 and _location(skip_post).endswith("/account/register")
    assert Account.query.filter_by(username="skipverify").first() is None
    assert RegistrationRequest.query.filter_by(username="skipverify").count() == 1


def test_pending_page_is_generic_and_leaks_nothing(client):
    _register(client, "skipverify")  # a registration is in flight in this session
    resp = client.get("/account/register/pending")
    text = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert "pending" in text.lower()
    for needle in ("skipverify", "@example.com", "realm_id=", "token_prefix="):
        assert needle not in text


def test_wrong_verification_code_does_not_advance(client, db):
    _register(client, "wrongcode")
    reg = RegistrationRequest.query.filter_by(username="wrongcode").one()
    reg.verification_code = "123456"
    db.session.commit()
    csrf = _csrf(client, "/account/register/verify")

    resp = client.post("/account/register/verify", data={"code": "000000", "csrf_token": csrf})

    assert resp.status_code == 200  # re-rendered verify form, not a redirect onward
    db.session.expire_all()
    assert RegistrationRequest.query.filter_by(username="wrongcode").one().verification_attempts == 1
    blocked = client.get("/account/register/realms")
    assert blocked.status_code == 302 and _location(blocked).endswith("/account/register")
    assert Account.query.filter_by(username="wrongcode").first() is None


def test_correct_code_does_advance_positive_control(client, db):
    _register(client, "rightcode")
    reg = RegistrationRequest.query.filter_by(username="rightcode").one()
    reg.verification_code = "123456"
    db.session.commit()
    csrf = _csrf(client, "/account/register/verify")

    resp = client.post("/account/register/verify", data={"code": "123456", "csrf_token": csrf})

    assert resp.status_code == 302 and _location(resp).endswith("/account/register/realms")


def test_fresh_session_cannot_reach_realms_step(app):
    _register(app.test_client(), "someoneelse")
    resp = app.test_client().get("/account/register/realms")
    assert resp.status_code == 302 and _location(resp).endswith("/account/register")


def test_realm_request_with_invalid_domain_is_rejected(client, db):
    _register(client, "baddomain")
    reg = RegistrationRequest.query.filter_by(username="baddomain").one()
    reg.verification_code = "123456"
    db.session.commit()
    client.post("/account/register/verify", data={"code": "123456", "csrf_token": _csrf(client, "/account/register/verify")})

    resp = client.post(
        "/account/register/realms",
        data={"action": "add_realm", "full_domain": "nodots", "realm_type": "host",
              "csrf_token": _csrf(client, "/account/register/realms")},
    )

    assert resp.status_code == 200
    assert "Invalid domain format" in resp.get_data(as_text=True)
    db.session.expire_all()
    assert RegistrationRequest.query.filter_by(username="baddomain").one().get_realm_requests() == []


# ---------------------------------------------------------------------------
# Pending accounts cannot log in
# ---------------------------------------------------------------------------

def test_pending_account_cannot_login(app, client, db):
    _resp, password = _register(client, "pending_login")
    reg = RegistrationRequest.query.filter_by(username="pending_login").one()
    code = reg.verification_code
    client.post("/account/register/verify", data={"code": code, "csrf_token": _csrf(client, "/account/register/verify")})
    submit = client.post(
        "/account/register/realms",
        data={"action": "submit", "csrf_token": _csrf(client, "/account/register/realms")},
    )
    assert submit.status_code == 302 and _location(submit).endswith("/account/register/pending")
    account = Account.query.filter_by(username="pending_login").one()
    assert account.is_active == 0  # created, but awaiting admin approval

    fresh = app.test_client()
    login = fresh.post(
        "/account/login",
        data={"username": "pending_login", "password": password,
              "csrf_token": _csrf(fresh, "/account/login")},
    )

    assert login.status_code == 200  # re-rendered form, no redirect onward to 2FA
    assert "pending admin approval" in login.get_data(as_text=True)
    dashboard = fresh.get("/account/dashboard")
    assert dashboard.status_code == 302 and "/account/login" in _location(dashboard)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kwargs, message", [
    ({"username": "ab"}, "Username"),
    ({"username": "validuser", "email": "not-an-email"}, "email"),
    ({"username": "mismatchuser", "confirm": "Different-Pass-123!"}, "Passwords do not match"),
    ({"username": "weakpwduser", "password": "123456", "confirm": "123456"}, "assword"),
], ids=["short-username", "invalid-email", "password-mismatch", "weak-password"])
def test_registration_rejects_invalid_input(client, kwargs, message):
    resp, _pw = _register(client, **kwargs)

    assert resp.status_code == 200  # form re-rendered with an error, no redirect to /verify
    assert message in resp.get_data(as_text=True)
    assert RegistrationRequest.query.count() == 0
    assert Account.query.filter_by(username=kwargs["username"]).first() is None


def test_registration_rejects_duplicate_username(client, make_account):
    make_account("taken_name")
    resp, _pw = _register(client, "taken_name", email="other@example.com")
    assert resp.status_code == 200
    assert RegistrationRequest.query.count() == 0


# ---------------------------------------------------------------------------
# Admin approval is not reachable without an admin session
# ---------------------------------------------------------------------------

def _pending_account(make_account, db, name="awaiting"):
    account = make_account(name, is_active=0)
    account.approved_at = None  # the factory stamps approval; undo it for a pending account
    db.session.commit()
    return account


def test_unauthenticated_cannot_list_pending_accounts(client):
    resp = client.get("/admin/accounts/pending")
    assert resp.status_code == 302 and "/admin/login" in _location(resp)


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_unauthenticated_cannot_approve_or_reject(client, make_account, db, action):
    pending = _pending_account(make_account, db)
    csrf = _csrf(client, "/admin/login")

    resp = client.post(f"/admin/accounts/{pending.id}/{action}", data={"csrf_token": csrf, "reason": "x"})

    assert resp.status_code == 302 and "/admin/login" in _location(resp)
    db.session.expire_all()
    still = Account.query.get(pending.id)
    assert still is not None and still.is_active == 0 and still.approved_at is None


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_regular_user_session_cannot_approve_or_reject(client, make_account, db, action):
    regular = make_account("regular_user")
    pending = _pending_account(make_account, db)
    login_portal(client, regular)
    csrf = _csrf(client, "/account/settings")

    resp = client.post(f"/admin/accounts/{pending.id}/{action}", data={"csrf_token": csrf, "reason": "x"})

    assert resp.status_code == 302 and "/admin/login" in _location(resp)
    db.session.expire_all()
    still = Account.query.get(pending.id)
    assert still is not None and still.is_active == 0 and still.approved_at is None


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------

def test_registration_requires_csrf(client):
    resp, _pw = _register(client, "nocsrf", csrf="")
    assert resp.status_code == 400
    assert RegistrationRequest.query.count() == 0


def test_registration_rejects_forged_csrf(client):
    resp, _pw = _register(client, "forgedcsrf", csrf="forged-token")
    assert resp.status_code == 400
    assert RegistrationRequest.query.count() == 0


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_admin_approval_without_csrf_is_rejected(client, make_account, db, action):
    pending = _pending_account(make_account, db)
    resp = client.post(f"/admin/accounts/{pending.id}/{action}", data={})
    assert resp.status_code == 400
    db.session.expire_all()
    assert Account.query.get(pending.id).is_active == 0
