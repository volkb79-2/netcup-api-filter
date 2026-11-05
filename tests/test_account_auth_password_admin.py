"""change_password, admin-driven account lifecycle (create / approve /
reject / disable) and log_login_attempt."""

from __future__ import annotations

import pytest

from netcup_api_filter import account_auth, notification_service, password_reset
from netcup_api_filter.models import Account, AccountRealm, ActivityLog
from netcup_api_filter.utils import generate_token


@pytest.fixture
def notes(monkeypatch):
    calls = {"pw": [], "approved": [], "rejected": [], "invite": []}
    monkeypatch.setattr(notification_service, "notify_password_changed",
                        lambda account, ip=None: calls["pw"].append((account.username, ip)) or True)
    monkeypatch.setattr(notification_service, "notify_account_approved",
                        lambda account, n=0: calls["approved"].append((account.username, n)) or True)
    monkeypatch.setattr(notification_service, "notify_account_rejected",
                        lambda email, username, reason=None: calls["rejected"].append((email, username, reason)) or True)
    monkeypatch.setattr(password_reset, "send_account_invite_email",
                        lambda account, admin_username=None: calls["invite"].append((account.username, admin_username)) or True)
    return calls


# --------------------------------------------------------------------------- change_password

def test_change_password_success_updates_hash_and_notifies(app, make_account, notes):
    old, new = generate_token(24), generate_token(24)
    acct = make_account("chpw000001", password=old)
    old_hash = acct.password_hash
    ok, err = account_auth.change_password(acct, old, new, source_ip="192.0.2.4")
    assert (ok, err) == (True, None)
    assert acct.password_hash != old_hash
    assert acct.verify_password(new)
    assert not acct.verify_password(old)
    assert notes["pw"] == [("chpw000001", "192.0.2.4")]


def test_change_password_wrong_current_leaves_hash(app, make_account, notes):
    old = generate_token(24)
    acct = make_account("chpw000002", password=old)
    before = acct.password_hash
    ok, err = account_auth.change_password(acct, old + "x", generate_token(24))
    assert (ok, err) == (False, "Current password is incorrect")
    assert acct.password_hash == before
    assert notes["pw"] == []


def test_change_password_rejects_weak_new_password(app, make_account, notes):
    old = generate_token(24)
    acct = make_account("chpw000003", password=old)
    ok, err = account_auth.change_password(acct, old, "tooshort")
    assert ok is False and err
    assert acct.verify_password(old)
    assert notes["pw"] == []


def test_change_password_rejects_reuse_of_current(app, make_account, notes):
    old = generate_token(24)
    acct = make_account("chpw000004", password=old)
    ok, err = account_auth.change_password(acct, old, old)
    assert (ok, err) == (False, "New password must be different")
    assert notes["pw"] == []


# --------------------------------------------------------------------------- create_account_by_admin

def test_admin_create_with_invite(app, make_account, notes):
    admin = make_account("adminmaker", is_admin=1)
    acct, warning = account_auth.create_account_by_admin(
        "invitee001", "invitee@example.com", generate_token(24), admin)
    assert warning is None
    assert acct.is_active == 1 and acct.email_verified == 1 and acct.email_2fa_enabled == 1
    assert acct.must_change_password  # invitee must pick their own password
    assert acct.approved_by_id == admin.id
    assert notes["invite"] == [("invitee001", "adminmaker")]


def test_admin_create_invite_email_failure_returns_warning_with_temp_password(
        app, make_account, monkeypatch):
    admin = make_account("adminmaker")
    monkeypatch.setattr(password_reset, "send_account_invite_email", lambda *a, **kw: False)
    pw = generate_token(24)
    acct, warning = account_auth.create_account_by_admin("invitee002", "inv2@example.com", pw, admin)
    assert acct is not None
    assert warning.startswith("WARNING: Invite email failed")
    assert Account.query.filter_by(username="invitee002").first() is not None


def test_admin_create_without_invite_is_immediately_usable(app, make_account, notes):
    admin = make_account("adminmaker")
    pw = generate_token(24)
    acct, warning = account_auth.create_account_by_admin(
        "service001", "svc@example.com", pw, admin, send_invite=False)
    assert warning is None and not acct.must_change_password
    assert acct.verify_password(pw)
    assert notes["invite"] == []


def test_admin_create_generates_valid_password_when_missing(app, make_account, notes):
    admin = make_account("adminmaker")
    acct, warning = account_auth.create_account_by_admin(
        "service002", "svc2@example.com", None, admin, send_invite=False)
    assert acct is not None and warning is None
    assert acct.password_hash and acct.password_hash.startswith("$2")  # bcrypt


@pytest.mark.parametrize("username,email,expect", [
    ("x", "ok@example.com", None),                       # invalid username (validator message)
    ("takenname", "fresh@example.com", "Username already registered"),
    ("freshname1", "taken@example.com", "Email already registered"),
])
def test_admin_create_rejections(app, make_account, notes, username, email, expect):
    admin = make_account("adminmaker")
    make_account("takenname", email="taken@example.com")
    acct, err = account_auth.create_account_by_admin(username, email, generate_token(24), admin)
    assert acct is None and err
    if expect:
        assert err == expect


def test_admin_create_rejects_weak_password(app, make_account, notes):
    admin = make_account("adminmaker")
    acct, err = account_auth.create_account_by_admin("weakadmin1", "w@example.com", "weak", admin)
    assert acct is None and err
    assert Account.query.filter_by(username="weakadmin1").first() is None


# --------------------------------------------------------------------------- approve / reject / disable

def _pending_with_realms(make_account, make_realm, name="pendacct01", n=2):
    acct = make_account(name, is_active=0)
    for i in range(n):
        make_realm(acct, realm_value=f"h{i}", status="pending")
    return acct


def test_approve_unknown_account(app, make_account, notes):
    admin = make_account("adminmaker")
    assert account_auth.approve_account(999, admin) == (False, "Account not found")


def test_approve_already_active(app, make_account, notes):
    admin = make_account("adminmaker")
    acct = make_account("alreadyact")
    assert account_auth.approve_account(acct.id, admin) == (False, "Account already active")
    assert notes["approved"] == []


def test_approve_activates_account_and_pending_realms(app, make_account, make_realm, notes):
    admin = make_account("adminmaker")
    acct = _pending_with_realms(make_account, make_realm)
    assert account_auth.approve_account(acct.id, admin) == (True, None)
    assert acct.is_active == 1 and acct.approved_by_id == admin.id
    statuses = {r.status for r in AccountRealm.query.filter_by(account_id=acct.id)}
    assert statuses == {"approved"}
    assert notes["approved"] == [("pendacct01", 2)]


def test_approve_without_realms_leaves_realms_pending(app, make_account, make_realm, notes):
    admin = make_account("adminmaker")
    acct = _pending_with_realms(make_account, make_realm)
    ok, _ = account_auth.approve_account(acct.id, admin, approve_realms=False)
    assert ok and acct.is_active == 1
    statuses = {r.status for r in AccountRealm.query.filter_by(account_id=acct.id)}
    assert statuses == {"pending"}
    assert notes["approved"] == [("pendacct01", 0)]


def test_reject_unknown_account(app, make_account, notes):
    admin = make_account("adminmaker")
    assert account_auth.reject_account(999, admin) == (False, "Account not found")


def test_reject_refuses_active_account(app, make_account, notes):
    admin = make_account("adminmaker")
    acct = make_account("activeacct")
    assert account_auth.reject_account(acct.id, admin) == (False, "Cannot reject an active account")
    assert Account.query.get(acct.id) is not None
    assert notes["rejected"] == []


def test_reject_deletes_account_and_realms_and_notifies(app, make_account, make_realm, notes):
    admin = make_account("adminmaker")
    acct = _pending_with_realms(make_account, make_realm, "rejectme01")
    acct_id = acct.id
    assert account_auth.reject_account(acct_id, admin, reason="spam") == (True, None)
    assert Account.query.get(acct_id) is None
    assert AccountRealm.query.filter_by(account_id=acct_id).count() == 0
    assert notes["rejected"] == [("rejectme01@example.com", "rejectme01", "spam")]


def test_disable_account_rules(app, make_account, notes):
    admin = make_account("adminmaker", is_admin=1)
    target = make_account("disabled01")
    assert account_auth.disable_account(999, admin) == (False, "Account not found")
    assert account_auth.disable_account(admin.id, admin) == (False, "Cannot disable your own account")
    assert admin.is_active == 1
    assert account_auth.disable_account(target.id, admin) == (True, None)
    assert target.is_active == 0


# --------------------------------------------------------------------------- log_login_attempt

def test_log_login_attempt_links_known_account(app, make_account):
    acct = make_account("logattempt")
    with app.test_request_context(headers={"User-Agent": "UA/2"}):
        account_auth.log_login_attempt("logattempt", "192.0.2.9", True, "because")
    entry = ActivityLog.query.filter_by(action="login").one()
    assert (entry.account_id, entry.source_ip, entry.status, entry.status_reason,
            entry.user_agent) == (acct.id, "192.0.2.9", "success", "because", "UA/2")


def test_log_login_attempt_unknown_user_has_no_account(app):
    with app.test_request_context():
        account_auth.log_login_attempt("noone-here", "192.0.2.9", False)
    entry = ActivityLog.query.filter_by(action="login").one()
    assert (entry.account_id, entry.status, entry.status_reason) == (None, "denied", None)
