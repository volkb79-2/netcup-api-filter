"""Hermetic tests for the admin bulk-action endpoints (P7.6).

Moved from ui_tests/tests/features/test_bulk_operations.py (S8). The original
only proved the routes "exist" (302/400 without auth) and grepped template
source at a hard-coded absolute path. Here the access-control cases pin the
exact outcome AND assert nothing changed in the DB, the rendered admin pages
are checked for the bulk UI (instead of reading template files), and the actual
bulk behaviour (previously untested) is exercised with an admin session.

The original ``test_bulk_action_valid_actions`` asserted that list literals
contain their own elements, so it could not fail; it is replaced by the
invalid-action cases below.
"""
from __future__ import annotations

import pytest

from netcup_api_filter.models import Account, AccountRealm

from http_helpers import login_admin, login_portal, mint_csrf


def _csrf(client):
    return mint_csrf(client, "/admin/login")


@pytest.fixture
def admin(make_account):
    return make_account("bulk_admin", is_admin=1)


@pytest.fixture
def admin_client(client, admin):
    client.csrf = _csrf(client)  # must be minted BEFORE login (a logged-in /admin/login redirects)
    login_admin(client, admin)
    return client


def _post(client, url, payload):
    return client.post(url, json=payload, headers={"X-CSRFToken": client.csrf})


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url, payload", [
    ("/admin/api/accounts/bulk", {"action": "delete", "account_ids": [1]}),
    ("/admin/api/realms/bulk", {"action": "approve", "realm_ids": [1]}),
])
def test_bulk_endpoints_reject_missing_csrf(client, make_account, url, payload):
    make_account("victim")
    resp = client.post(url, json=payload)
    assert resp.status_code == 400
    assert Account.query.filter_by(username="victim").one().is_active == 1


@pytest.mark.parametrize("url, payload", [
    ("/admin/api/accounts/bulk", {"action": "delete", "account_ids": [1]}),
    ("/admin/api/realms/bulk", {"action": "approve", "realm_ids": [1]}),
])
def test_bulk_endpoints_redirect_unauthenticated_to_admin_login(client, make_account, url, payload):
    make_account("victim")
    resp = client.post(url, json=payload, headers={"X-CSRFToken": _csrf(client)})
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers["Location"]
    assert Account.query.filter_by(username="victim").one().is_active == 1


def test_non_admin_account_cannot_use_bulk_endpoints(client, make_account):
    regular = make_account("regular")
    victim = make_account("victim")
    login_portal(client, regular)  # a portal session is not an admin session
    resp = client.post(
        "/admin/api/accounts/bulk", json={"action": "delete", "account_ids": [victim.id]},
        headers={"X-CSRFToken": _csrf(client)},
    )
    assert resp.status_code == 302 and "/admin/login" in resp.headers["Location"]
    assert Account.query.get(victim.id) is not None


# ---------------------------------------------------------------------------
# Accounts bulk behaviour
# ---------------------------------------------------------------------------

def test_accounts_bulk_disable_then_enable(admin_client, make_account, db):
    a, b = make_account("bulk_a"), make_account("bulk_b")

    resp = _post(admin_client, "/admin/api/accounts/bulk", {"action": "disable", "account_ids": [a.id, b.id]})
    assert resp.status_code == 200
    body = resp.get_json()
    assert (body["action"], body["total"], body["success"], body["failed"]) == ("disable", 2, 2, 0)
    assert {r["action"] for r in body["results"]["success"]} == {"disabled"}
    db.session.expire_all()
    assert Account.query.get(a.id).is_active == 0 and Account.query.get(b.id).is_active == 0

    resp = _post(admin_client, "/admin/api/accounts/bulk", {"action": "enable", "account_ids": [a.id]})
    assert resp.get_json()["success"] == 1
    db.session.expire_all()
    assert Account.query.get(a.id).is_active == 1
    assert Account.query.get(b.id).is_active == 0  # untouched


def test_accounts_bulk_delete_removes_rows(admin_client, make_account, db):
    a, b = make_account("del_a"), make_account("del_b")
    resp = _post(admin_client, "/admin/api/accounts/bulk", {"action": "delete", "account_ids": [a.id]})
    assert resp.status_code == 200 and resp.get_json()["results"]["success"][0]["action"] == "deleted"
    db.session.expire_all()
    assert Account.query.get(a.id) is None
    assert Account.query.get(b.id) is not None


def test_accounts_bulk_never_touches_admin_accounts(admin_client, admin, make_account, db):
    other_admin = make_account("other_admin", is_admin=1)
    resp = _post(admin_client, "/admin/api/accounts/bulk",
                 {"action": "delete", "account_ids": [admin.id, other_admin.id]})
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "No valid accounts found"}
    db.session.expire_all()
    assert Account.query.get(admin.id) is not None and Account.query.get(other_admin.id) is not None


@pytest.mark.parametrize("payload, status, error", [
    ({"action": "explode", "account_ids": [1]}, 400, "Invalid action"),
    ({"account_ids": [1]}, 400, "Invalid action"),
    ({"action": "enable", "account_ids": []}, 400, "No accounts specified"),
    ({"action": "enable", "account_ids": "1"}, 400, "No accounts specified"),
    ({"action": "enable", "account_ids": [987654]}, 404, "No valid accounts found"),
    ({}, 400, "Invalid JSON"),
])
def test_accounts_bulk_validation(admin_client, payload, status, error):
    resp = _post(admin_client, "/admin/api/accounts/bulk", payload)
    assert resp.status_code == status
    assert resp.get_json()["error"] == error


# ---------------------------------------------------------------------------
# Realms bulk behaviour
# ---------------------------------------------------------------------------

def _realms(make_account, make_realm, statuses):
    owner = make_account("realm_owner")
    return [
        make_realm(owner, domain="example.com", realm_type="host", realm_value=f"h{i}", status=status)
        for i, status in enumerate(statuses)
    ]


def test_realms_bulk_approve_only_pending(admin_client, admin, make_account, make_realm, db):
    pending, approved = _realms(make_account, make_realm, ["pending", "approved"])

    resp = _post(admin_client, "/admin/api/realms/bulk",
                 {"action": "approve", "realm_ids": [pending.id, approved.id]})

    body = resp.get_json()
    assert resp.status_code == 200
    assert (body["total"], body["success"], body["failed"]) == (2, 1, 1)
    assert body["results"]["failed"][0]["error"] == "Cannot approve realm in approved status"
    db.session.expire_all()
    realm = AccountRealm.query.get(pending.id)
    assert realm.status == "approved" and realm.approved_by_id == admin.id and realm.approved_at is not None


def test_realms_bulk_reject_records_reason(admin_client, make_account, make_realm, db):
    (pending,) = _realms(make_account, make_realm, ["pending"])
    resp = _post(admin_client, "/admin/api/realms/bulk",
                 {"action": "reject", "realm_ids": [pending.id], "reason": "not allowed"})
    assert resp.get_json()["success"] == 1
    db.session.expire_all()
    realm = AccountRealm.query.get(pending.id)
    assert realm.status == "rejected" and realm.rejection_reason == "not allowed"


def test_realms_bulk_revoke_approved_realm(admin_client, make_account, make_realm, db):
    approved, pending = _realms(make_account, make_realm, ["approved", "pending"])
    resp = _post(admin_client, "/admin/api/realms/bulk",
                 {"action": "revoke", "realm_ids": [approved.id, pending.id]})
    body = resp.get_json()
    assert (body["success"], body["failed"]) == (1, 1)
    db.session.expire_all()
    assert AccountRealm.query.get(approved.id).status == "rejected"
    assert AccountRealm.query.get(approved.id).rejection_reason == "Revoked by admin"
    assert AccountRealm.query.get(pending.id).status == "pending"


@pytest.mark.parametrize("payload, status, error", [
    ({"action": "explode", "realm_ids": [1]}, 400, "Invalid action"),
    ({"action": "approve", "realm_ids": []}, 400, "No realms specified"),
    ({"action": "approve", "realm_ids": [987654]}, 404, "No valid realms found"),
    ({}, 400, "Invalid JSON"),
])
def test_realms_bulk_validation(admin_client, payload, status, error):
    resp = _post(admin_client, "/admin/api/realms/bulk", payload)
    assert resp.status_code == status
    assert resp.get_json()["error"] == error


# ---------------------------------------------------------------------------
# Rendered bulk UI (what the originals grepped template source for)
# ---------------------------------------------------------------------------

def test_accounts_list_renders_bulk_controls(admin_client, make_account):
    make_account("listed_user")
    html = admin_client.get("/admin/accounts").get_data(as_text=True)

    assert 'id="bulkActionsBar"' in html
    assert 'id="selectAll"' in html and "row-checkbox" in html
    for action in ("enable", "disable", "delete"):
        assert f"bulkAction('{action}')" in html
    assert "/admin/api/accounts/bulk" in html and "X-CSRFToken" in html


def test_pending_realms_page_renders_approve_all(admin_client, make_account, make_realm):
    _realms(make_account, make_realm, ["pending"])
    html = admin_client.get("/admin/realms/pending").get_data(as_text=True)

    assert "approveAll()" in html and "Approve All" in html
    assert "/admin/api/realms/bulk" in html
