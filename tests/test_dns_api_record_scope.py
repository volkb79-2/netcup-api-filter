"""Route-level tests for record-scoped authorization on delete_record and
update_record in dns_api.py (naf-P01).

Before this fix, `delete_record` called `check_permission(auth, 'delete',
domain, client_ip=client_ip)` with no `record_name`/`record_type`, which
`check_permission` treats as "skip the hostname check" (see token_auth.py:
the hostname check only runs when `record_name is not None`). On a shared
`ManagedDomainRoot`, this let a host-scoped token delete/repoint ANY record
in the zone, not just its own.

Oracles (see handoffs/naf-P01-dns-api-record-scope.md):
  O1 - DELETE by record id must be authorized against the record's OWN
       stored hostname. A cross-hostname delete is denied (403,
       hostname_denied) and the backend still holds the record; deleting
       your own record id succeeds and removes it.
  O2 - PUT by record id must be authorized against the hostname of the
       record ACTUALLY stored under that id, not the request body's
       hostname. Supplying an in-scope hostname in the body does not grant
       access to an out-of-scope record id.
  O3 - An unknown record id yields 404 (not 403, and no backend mutation),
       distinguishing "not yours" (403) from "not there" (404). No
       ActivityLog row with status='success' is written for it.

All tests assert BACKEND TRUTH (state of the in-memory fake Netcup store
after the call), not just HTTP status codes.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from netcup_api_filter.api import dns_api as dns_api_module
from netcup_api_filter.models import ActivityLog


# =============================================================================
# Fake Netcup backend
# =============================================================================


class FakeNetcupClient:
    """In-memory stand-in for NetcupClient, good enough to assert backend
    truth without touching the real Netcup API.

    Mirrors the two calls dns_api.py makes:
      - info_dns_records(domain) -> list[dict]
      - update_dns_records(domain, dns_records) -> {'status': 'success'}
        (applies create/update/delete-by-`deleterecord` semantics in place)
    """

    def __init__(self, zones):
        # {domain: [record_dict, ...]}
        self._zones = {domain: [dict(r) for r in recs] for domain, recs in zones.items()}

    def records_for(self, domain):
        """Current backend truth for a domain (list of record dicts)."""
        return self._zones.get(domain, [])

    def info_dns_records(self, domain):
        return [dict(r) for r in self._zones.get(domain, [])]

    def update_dns_records(self, domain, dns_records):
        zone = self._zones.setdefault(domain, [])
        for incoming in dns_records:
            rid = str(incoming.get('id'))
            if incoming.get('deleterecord'):
                self._zones[domain] = [r for r in zone if str(r.get('id')) != rid]
                zone = self._zones[domain]
                continue
            for i, existing in enumerate(zone):
                if str(existing.get('id')) == rid:
                    zone[i] = {**existing, **incoming}
                    break
            else:
                zone.append(dict(incoming))
        return {'status': 'success'}


@pytest.fixture
def zone_records():
    """A shared zone with two records under different hostnames."""
    return {
        "example.com": [
            {"id": "101", "hostname": "vpn", "type": "A", "destination": "10.0.0.1"},
            {"id": "202", "hostname": "www", "type": "A", "destination": "10.0.0.2"},
        ]
    }


def _install_fake_client(monkeypatch, zones):
    fake = FakeNetcupClient(zones)
    monkeypatch.setattr(dns_api_module, "get_netcup_client", lambda: fake)
    return fake


def _auth_header(plain_token):
    return {"Authorization": f"Bearer {plain_token}"}


def _record_ids(fake, domain="example.com"):
    # Netcup ids arrive as strings from the (fake) backend, but the route
    # rebuilds the mutation payload with the URL's int record_id, so the
    # stored 'id' can come back as either str or int after a merge. Normalise
    # to str for comparisons — backend truth is about which record survives,
    # not the id's Python type.
    return {str(r["id"]) for r in fake.records_for(domain)}


def _record_by_id(fake, record_id, domain="example.com"):
    for r in fake.records_for(domain):
        if str(r["id"]) == str(record_id):
            return r
    return None


def _last_log(db):
    return ActivityLog.query.order_by(ActivityLog.id.desc()).first()


# =============================================================================
# O1 - delete_record must authorize against the record's OWN hostname
# =============================================================================


def test_delete_cross_hostname_denied_and_backend_unchanged(
    app, client, db, monkeypatch, make_account, make_realm, make_token, zone_records
):
    """Host-scoped token (vpn.example.com) tries to delete record 202, which
    is stored under hostname 'www'. Must be denied with hostname_denied, and
    the record must still be present in the backend afterwards.
    """
    fake = _install_fake_client(monkeypatch, zone_records)

    account = make_account("del_cross_user")
    realm = make_realm(
        account, domain="example.com", realm_type="host", realm_value="vpn",
        operations=("read", "delete"), record_types=("A",),
    )
    _tok, plain = make_token(realm)

    resp = client.delete("/api/dns/example.com/records/202", headers=_auth_header(plain))

    assert resp.status_code == 403
    body = resp.get_json()
    assert body["error"] == "forbidden"

    # Backend truth: record 202 is still there, untouched.
    assert "202" in _record_ids(fake)
    assert _record_by_id(fake, "202")["hostname"] == "www"

    # The permission failure must be attributed to hostname scope, not a
    # generic/other denial.
    log = _last_log(db)
    assert log.status == "denied"
    assert log.error_code == "hostname_denied"


def test_delete_own_record_succeeds_and_backend_removes_it(
    app, client, db, monkeypatch, make_account, make_realm, make_token, zone_records
):
    """The SAME host-scoped token deleting its OWN record id (101, hostname
    'vpn') must succeed and the record must be gone from the backend.
    """
    fake = _install_fake_client(monkeypatch, zone_records)

    account = make_account("del_own_user")
    realm = make_realm(
        account, domain="example.com", realm_type="host", realm_value="vpn",
        operations=("read", "delete"), record_types=("A",),
    )
    _tok, plain = make_token(realm)

    resp = client.delete("/api/dns/example.com/records/101", headers=_auth_header(plain))

    assert resp.status_code == 200
    assert resp.get_json()["status"] == "deleted"

    # Backend truth: record 101 is gone; the other zone record is untouched.
    assert "101" not in _record_ids(fake)
    assert "202" in _record_ids(fake)


# =============================================================================
# O2 - update_record must authorize against the STORED hostname, not the
# request body's hostname
# =============================================================================


def test_update_cross_hostname_denied_even_with_in_scope_body_hostname(
    app, client, db, monkeypatch, make_account, make_realm, make_token, zone_records
):
    """Host-scoped token (vpn.example.com) PUTs record id 202 (stored under
    'www') but supplies its OWN in-scope hostname ('vpn') in the request
    body. The authorization decision must follow the record actually
    addressed by the id (www), not the body, so this must be denied and the
    stored record must be unchanged.
    """
    fake = _install_fake_client(monkeypatch, zone_records)

    account = make_account("upd_cross_user")
    realm = make_realm(
        account, domain="example.com", realm_type="host", realm_value="vpn",
        operations=("read", "update"), record_types=("A",),
    )
    _tok, plain = make_token(realm)

    resp = client.put(
        "/api/dns/example.com/records/202",
        headers=_auth_header(plain),
        json={"type": "A", "hostname": "vpn", "destination": "6.6.6.6"},
    )

    assert resp.status_code == 403
    body = resp.get_json()
    assert body["error"] == "forbidden"

    # Backend truth: record 202 is unchanged (not repointed to 6.6.6.6, and
    # its hostname was not silently accepted as 'vpn').
    stored = _record_by_id(fake, "202")
    assert stored is not None
    assert stored["hostname"] == "www"
    assert stored["destination"] == "10.0.0.2"

    log = _last_log(db)
    assert log.status == "denied"
    assert log.error_code == "hostname_denied"


def test_update_own_record_in_place_succeeds(
    app, client, db, monkeypatch, make_account, make_realm, make_token, zone_records
):
    """Sanity/regression: updating a record you actually own (same hostname)
    must still work and be reflected in the backend.
    """
    fake = _install_fake_client(monkeypatch, zone_records)

    account = make_account("upd_own_user")
    realm = make_realm(
        account, domain="example.com", realm_type="host", realm_value="vpn",
        operations=("read", "update"), record_types=("A",),
    )
    _tok, plain = make_token(realm)

    resp = client.put(
        "/api/dns/example.com/records/101",
        headers=_auth_header(plain),
        json={"type": "A", "hostname": "vpn", "destination": "9.9.9.9"},
    )

    assert resp.status_code == 200
    assert resp.get_json()["status"] == "updated"

    stored = _record_by_id(fake, "101")
    assert stored is not None
    assert stored["destination"] == "9.9.9.9"


def test_update_cannot_move_own_record_out_of_scope(
    app, client, db, monkeypatch, make_account, make_realm, make_token, zone_records
):
    """A host-scoped token owns record 101 ('vpn'), but tries to retarget it
    to hostname 'www' (outside its scope) via the request body. The target
    hostname must ALSO pass check_permission, so this must be denied and the
    record must remain at its original hostname/destination.
    """
    fake = _install_fake_client(monkeypatch, zone_records)

    account = make_account("upd_move_out_user")
    realm = make_realm(
        account, domain="example.com", realm_type="host", realm_value="vpn",
        operations=("read", "update"), record_types=("A",),
    )
    _tok, plain = make_token(realm)

    resp = client.put(
        "/api/dns/example.com/records/101",
        headers=_auth_header(plain),
        json={"type": "A", "hostname": "www", "destination": "6.6.6.6"},
    )

    assert resp.status_code == 403

    stored = _record_by_id(fake, "101")
    assert stored is not None
    assert stored["hostname"] == "vpn"
    assert stored["destination"] == "10.0.0.1"


# =============================================================================
# O3 - unknown record id yields 404, not a backend mutation, and no
# ActivityLog row with status='success'
# =============================================================================


def test_delete_unknown_record_id_yields_404_not_403(
    app, client, db, monkeypatch, make_account, make_realm, make_token, zone_records
):
    fake = _install_fake_client(monkeypatch, zone_records)

    account = make_account("del_missing_user")
    realm = make_realm(
        account, domain="example.com", realm_type="host", realm_value="vpn",
        operations=("read", "delete"), record_types=("A",),
    )
    _tok, plain = make_token(realm)

    before_ids = _record_ids(fake)

    resp = client.delete("/api/dns/example.com/records/9999", headers=_auth_header(plain))

    assert resp.status_code == 404
    body = resp.get_json()
    assert body["error"] == "not_found"

    # No backend mutation happened.
    assert _record_ids(fake) == before_ids

    # No log row for this call reports success.
    success_logs = ActivityLog.query.filter_by(status="success").all()
    assert success_logs == []


def test_update_unknown_record_id_yields_404_not_403(
    app, client, db, monkeypatch, make_account, make_realm, make_token, zone_records
):
    fake = _install_fake_client(monkeypatch, zone_records)

    account = make_account("upd_missing_user")
    realm = make_realm(
        account, domain="example.com", realm_type="host", realm_value="vpn",
        operations=("read", "update"), record_types=("A",),
    )
    _tok, plain = make_token(realm)

    before = [dict(r) for r in fake.records_for("example.com")]

    resp = client.put(
        "/api/dns/example.com/records/9999",
        headers=_auth_header(plain),
        json={"type": "A", "hostname": "vpn", "destination": "1.2.3.4"},
    )

    assert resp.status_code == 404
    body = resp.get_json()
    assert body["error"] == "not_found"

    # No backend mutation happened — zone contents identical to before.
    assert fake.records_for("example.com") == before

    success_logs = ActivityLog.query.filter_by(status="success").all()
    assert success_logs == []
