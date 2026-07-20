"""
Portal DNS record-mutation routes must enforce realm hostname scope for every
realm_type (host / subdomain / subdomain_only), and must do so BEFORE any
backend mutation call.

Locks down naf-P02 (see docs/deprecated/FOLLOWUP_REVIEW_2026-07-16.md#P0-2 /
#P0-3): ``dns_record_create`` only checked ``realm_type == 'host'``, so a
subdomain(-only) realm could create at the zone apex or in a sibling subtree.
``dns_record_edit`` / ``dns_record_delete`` resolved ``record_id`` across the
WHOLE zone and mutated after only a realm-level create/update/delete
*operation* check -- with no hostname-scope check on the resolved record at
all, so e.g. a host-scoped realm could edit/delete a sibling's record just by
guessing its id.

Every test asserts backend truth (the fake Netcup backend's mutation call
count and/or its stored records), not just the flashed UI message -- a build
where the flash says "error" but the backend was mutated anyway must fail
these tests.
"""
from __future__ import annotations

import os
import secrets
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from netcup_api_filter.account_auth import SESSION_KEY_SESSION_TOKEN, SESSION_KEY_USER_ID
from netcup_api_filter.database import db as _db, set_setting
from netcup_api_filter.models import AccountSession


# ---------------------------------------------------------------------------
# Local fixtures.
#
# CSRF: account_bp is NOT csrf.exempt()'d (unlike the REST API blueprints), so
# its POST routes need a valid CSRF token. Disabling WTF_CSRF_ENABLED on the
# app is the standard way to test such forms without wiring up the token
# dance; conftest.py is out of scope for this package, so it's done locally by
# overriding the `app` fixture for this module only.
#
# Login: exercising the full password + mandatory-2FA login flow is out of
# scope here (account_auth.py is a forbidden file for this package) and
# orthogonal to what's under test. Authenticate by writing exactly what
# account_auth.create_session() would leave behind -- a DB-backed
# AccountSession row plus the two session keys require_account_auth checks.
# ---------------------------------------------------------------------------

@pytest.fixture
def app(app):
    app.config["WTF_CSRF_ENABLED"] = False
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def _netcup_configured(app):
    """All three routes bail out early with 'Netcup API is not configured'
    unless this is set."""
    set_setting("netcup_config", {
        "customer_id": "cust",
        "api_key": "key",
        "api_password": "pw",
        "api_url": "https://example.invalid/",
        "timeout": 5,
    })


def _login(client, account):
    """Authenticate `client` as `account`, bypassing password + 2FA."""
    token = secrets.token_urlsafe(32)
    _db.session.add(AccountSession(
        account_id=account.id,
        session_token=token,
        ip_address="127.0.0.1",
        user_agent="pytest",
    ))
    _db.session.commit()
    with client.session_transaction() as sess:
        sess[SESSION_KEY_USER_ID] = account.id
        sess[SESSION_KEY_SESSION_TOKEN] = token


@pytest.fixture
def fake_backend(monkeypatch):
    """In-memory stand-in for NetcupClient; tracks mutation calls for
    backend-truth assertions.

    account.py does ``from ..netcup_client import NetcupClient`` INSIDE each
    route function body, so patching the class on its defining module (rather
    than some route-local name) is what takes effect: ``from x import Y``
    re-reads ``x.Y`` at call time, every call.
    """
    state = {"records": {}, "update_calls": []}

    class FakeNetcupClient:
        def __init__(self, customer_id=None, api_key=None, api_password=None,
                     api_url=None, timeout=30):
            pass

        def info_dns_records(self, domain):
            return [dict(r) for r in state["records"].get(domain, [])]

        def update_dns_records(self, domain, dns_records):
            state["update_calls"].append((domain, [dict(r) for r in dns_records]))
            # Mirror real Netcup semantics closely enough for these tests:
            # records flagged deleterecord are dropped, everything else is the
            # new canonical state for the zone.
            state["records"][domain] = [
                dict(r) for r in dns_records if not r.get("deleterecord")
            ]
            return {"status": "success"}

    monkeypatch.setattr("netcup_api_filter.netcup_client.NetcupClient", FakeNetcupClient)
    return state


def _seed(fake_backend, domain, records):
    fake_backend["records"][domain] = [dict(r) for r in records]


# ---------------------------------------------------------------------------
# O1 -- create: every realm_type is scope-checked, not just 'host'.
# ---------------------------------------------------------------------------

class TestCreateScope:
    def test_subdomain_realm_rejects_apex_hostname(self, client, make_account, make_realm, fake_backend):
        """The escalation this package closes: today only realm_type == 'host'
        is checked, so a subdomain realm scoped to sub.example.com could
        create at the zone apex, example.com."""
        account = make_account("create_apex_user")
        realm = make_realm(
            account, domain="example.com", realm_type="subdomain", realm_value="sub",
            operations=("read", "create"), record_types=("A",),
        )
        _seed(fake_backend, "example.com", [])
        _login(client, account)

        resp = client.post(
            f"/account/realms/{realm.id}/dns/create",
            data={"hostname": "", "type": "A", "destination": "1.2.3.4"},
        )

        assert resp.status_code == 302
        assert fake_backend["update_calls"] == []
        assert fake_backend["records"]["example.com"] == []

    def test_subdomain_realm_rejects_sibling_subtree(self, client, make_account, make_realm, fake_backend):
        account = make_account("create_sibling_user")
        realm = make_realm(
            account, domain="example.com", realm_type="subdomain", realm_value="sub",
            operations=("read", "create"), record_types=("A",),
        )
        _seed(fake_backend, "example.com", [])
        _login(client, account)

        resp = client.post(
            f"/account/realms/{realm.id}/dns/create",
            data={"hostname": "other", "type": "A", "destination": "1.2.3.4"},
        )

        assert resp.status_code == 302
        assert fake_backend["update_calls"] == []
        assert fake_backend["records"]["example.com"] == []

    def test_subdomain_realm_accepts_hostname_inside_subtree(self, client, make_account, make_realm, fake_backend):
        account = make_account("create_inside_user")
        realm = make_realm(
            account, domain="example.com", realm_type="subdomain", realm_value="sub",
            operations=("read", "create"), record_types=("A",),
        )
        _seed(fake_backend, "example.com", [])
        _login(client, account)

        resp = client.post(
            f"/account/realms/{realm.id}/dns/create",
            data={"hostname": "device1.sub", "type": "A", "destination": "1.2.3.4"},
        )

        assert resp.status_code == 302
        assert len(fake_backend["update_calls"]) == 1
        stored = fake_backend["records"]["example.com"]
        assert len(stored) == 1
        assert stored[0]["hostname"] == "device1.sub"
        assert stored[0]["destination"] == "1.2.3.4"

    def test_subdomain_only_realm_rejects_apex(self, client, make_account, make_realm, fake_backend):
        """subdomain_only excludes the apex of its own subtree -- another case
        unreachable via the old 'host'-only guard."""
        account = make_account("create_subonly_user")
        realm = make_realm(
            account, domain="example.com", realm_type="subdomain_only", realm_value="sub",
            operations=("read", "create"), record_types=("A",),
        )
        _seed(fake_backend, "example.com", [])
        _login(client, account)

        resp = client.post(
            f"/account/realms/{realm.id}/dns/create",
            data={"hostname": "sub", "type": "A", "destination": "1.2.3.4"},
        )

        assert resp.status_code == 302
        assert fake_backend["update_calls"] == []
        assert fake_backend["records"]["example.com"] == []


# ---------------------------------------------------------------------------
# O2 -- edit/delete: the RESOLVED record's hostname must be validated, not
# just a realm-level operation check.
# ---------------------------------------------------------------------------

class TestEditScope:
    def test_rejects_out_of_scope_record_no_mutation(self, client, make_account, make_realm, fake_backend):
        """Host-scoped realm 'dyn' must not edit a sibling's record ('admin')
        just because it was found by id in the same zone."""
        account = make_account("edit_sibling_user")
        realm = make_realm(
            account, domain="example.com", realm_type="host", realm_value="dyn",
            operations=("read", "update"), record_types=("A",),
        )
        _seed(fake_backend, "example.com", [
            {"id": "99", "hostname": "admin", "type": "A", "destination": "9.9.9.9"},
        ])
        _login(client, account)

        resp = client.post(
            f"/account/realms/{realm.id}/dns/99/edit",
            data={"destination": "6.6.6.6"},
        )

        assert resp.status_code == 302
        assert fake_backend["update_calls"] == []
        assert fake_backend["records"]["example.com"][0]["destination"] == "9.9.9.9"

    def test_edits_in_scope_record(self, client, make_account, make_realm, fake_backend):
        account = make_account("edit_inscope_user")
        realm = make_realm(
            account, domain="example.com", realm_type="host", realm_value="dyn",
            operations=("read", "update"), record_types=("A",),
        )
        _seed(fake_backend, "example.com", [
            {"id": "1", "hostname": "dyn", "type": "A", "destination": "1.1.1.1"},
        ])
        _login(client, account)

        resp = client.post(
            f"/account/realms/{realm.id}/dns/1/edit",
            data={"destination": "2.2.2.2"},
        )

        assert resp.status_code == 302
        assert len(fake_backend["update_calls"]) == 1
        assert fake_backend["records"]["example.com"][0]["destination"] == "2.2.2.2"

    def test_unknown_record_id_is_not_found_not_permission_error(self, client, make_account, make_realm, fake_backend):
        account = make_account("edit_unknown_user")
        realm = make_realm(
            account, domain="example.com", realm_type="host", realm_value="dyn",
            operations=("read", "update"), record_types=("A",),
        )
        _seed(fake_backend, "example.com", [])
        _login(client, account)

        resp = client.post(
            f"/account/realms/{realm.id}/dns/404/edit",
            data={"destination": "2.2.2.2"},
        )

        assert resp.status_code == 302
        assert fake_backend["update_calls"] == []


class TestDeleteScope:
    def test_rejects_out_of_scope_record_no_mutation(self, client, make_account, make_realm, fake_backend):
        """subdomain_only realm 'iot' must not delete a record sitting exactly
        at the subtree apex -- subdomain_only excludes the apex itself."""
        account = make_account("delete_sibling_user")
        realm = make_realm(
            account, domain="example.com", realm_type="subdomain_only", realm_value="iot",
            operations=("read", "delete"), record_types=("A",),
        )
        _seed(fake_backend, "example.com", [
            {"id": "5", "hostname": "iot", "type": "A", "destination": "5.5.5.5"},
        ])
        _login(client, account)

        resp = client.post(f"/account/realms/{realm.id}/dns/5/delete")

        assert resp.status_code == 302
        assert fake_backend["update_calls"] == []
        assert fake_backend["records"]["example.com"] == [
            {"id": "5", "hostname": "iot", "type": "A", "destination": "5.5.5.5"},
        ]

    def test_deletes_in_scope_record(self, client, make_account, make_realm, fake_backend):
        account = make_account("delete_inscope_user")
        realm = make_realm(
            account, domain="example.com", realm_type="subdomain", realm_value="iot",
            operations=("read", "delete"), record_types=("A",),
        )
        _seed(fake_backend, "example.com", [
            {"id": "5", "hostname": "device1.iot", "type": "A", "destination": "5.5.5.5"},
        ])
        _login(client, account)

        resp = client.post(f"/account/realms/{realm.id}/dns/5/delete")

        assert resp.status_code == 302
        assert len(fake_backend["update_calls"]) == 1
        assert fake_backend["records"]["example.com"] == []

    def test_unknown_record_id_is_not_found_not_permission_error(self, client, make_account, make_realm, fake_backend):
        account = make_account("delete_unknown_user")
        realm = make_realm(
            account, domain="example.com", realm_type="host", realm_value="dyn",
            operations=("read", "delete"), record_types=("A",),
        )
        _seed(fake_backend, "example.com", [])
        _login(client, account)

        resp = client.post(f"/account/realms/{realm.id}/dns/404/delete")

        assert resp.status_code == 302
        assert fake_backend["update_calls"] == []


# ---------------------------------------------------------------------------
# O3 -- authorization happens BEFORE any backend mutation call, across all
# three routes, for a variety of denied scenarios.
# ---------------------------------------------------------------------------

class TestZeroMutationOnDenial:
    @pytest.mark.parametrize("realm_type,realm_value,hostname", [
        ("host", "dyn", ""),
        ("subdomain", "sub", "other"),
        ("subdomain_only", "sub", "sub"),
    ])
    def test_create_denied_makes_zero_backend_calls(
        self, client, make_account, make_realm, fake_backend, realm_type, realm_value, hostname
    ):
        account = make_account(f"o3_create_{realm_type}")
        realm = make_realm(
            account, domain="example.com", realm_type=realm_type, realm_value=realm_value,
            operations=("read", "create"), record_types=("A",),
        )
        _seed(fake_backend, "example.com", [])
        _login(client, account)

        client.post(
            f"/account/realms/{realm.id}/dns/create",
            data={"hostname": hostname, "type": "A", "destination": "1.2.3.4"},
        )

        assert fake_backend["update_calls"] == []

    def test_edit_denied_makes_zero_backend_calls(self, client, make_account, make_realm, fake_backend):
        account = make_account("o3_edit_user")
        realm = make_realm(
            account, domain="example.com", realm_type="host", realm_value="dyn",
            operations=("read", "update"), record_types=("A",),
        )
        _seed(fake_backend, "example.com", [
            {"id": "7", "hostname": "other", "type": "A", "destination": "7.7.7.7"},
        ])
        _login(client, account)

        client.post(f"/account/realms/{realm.id}/dns/7/edit", data={"destination": "0.0.0.0"})

        assert fake_backend["update_calls"] == []

    def test_delete_denied_makes_zero_backend_calls(self, client, make_account, make_realm, fake_backend):
        account = make_account("o3_delete_user")
        realm = make_realm(
            account, domain="example.com", realm_type="host", realm_value="dyn",
            operations=("read", "delete"), record_types=("A",),
        )
        _seed(fake_backend, "example.com", [
            {"id": "7", "hostname": "other", "type": "A", "destination": "7.7.7.7"},
        ])
        _login(client, account)

        client.post(f"/account/realms/{realm.id}/dns/7/delete")

        assert fake_backend["update_calls"] == []
