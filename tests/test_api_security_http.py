"""Hermetic HTTP tests for REST API security (/api/dns/*, /api/ddns/<domain>/<host>, /api/myip).

Moved from ui_tests/tests/security/test_api_security.py and the token-boundary
class of ui_tests/tests/features/test_registration_negative.py (S8). The live
originals depended on a demo token, tolerated 403/500 alternatives and polled
the deployment DB; here the token, realm and Netcup upstream are created per
test, statuses are exact, and denials are checked in ActivityLog directly.
"""
from __future__ import annotations

import json

import pytest

from netcup_api_filter.api import dns_api as dns_api_module
from netcup_api_filter.database import set_setting
from netcup_api_filter.models import ActivityLog

from fake_netcup import FakeNetcupBackend, install_fake_netcup

DOMAIN = "example.com"
SENTINELS = {
    "customer_id": "cust-sentinel-4711",
    "api_key": "apikey-sentinel-ZZ91",
    "api_password": "apipassword-sentinel-QQ73",
}


@pytest.fixture
def backend(monkeypatch):
    zone = {DOMAIN: [
        {"id": "1", "hostname": "vpn", "type": "A", "destination": "10.0.0.1"},
        {"id": "2", "hostname": "txt", "type": "TXT", "destination": "hello"},
    ]}
    return install_fake_netcup(monkeypatch, FakeNetcupBackend(zone), dns_api_module)


def _tokens(make_account, make_realm, make_token, operations, record_types=("A", "AAAA"), name="owner"):
    realm = make_realm(
        make_account(name), domain=DOMAIN, realm_type="subdomain", realm_value="",
        operations=operations, record_types=record_types,
    )
    return make_token(realm)[1]


@pytest.fixture
def rw_token(make_account, make_realm, make_token):
    return _tokens(make_account, make_realm, make_token, ("read", "update", "create", "delete"), name="rw_owner")


@pytest.fixture
def ro_token(make_account, make_realm, make_token):
    return _tokens(make_account, make_realm, make_token, ("read",), name="ro_owner")


def _auth(plain):
    return {"Authorization": f"Bearer {plain}"}


def _logs(**filters):
    return ActivityLog.query.filter_by(**filters).all()


# ---------------------------------------------------------------------------
# Domain scope
# ---------------------------------------------------------------------------

def test_token_cannot_access_other_domain(client, backend, rw_token):
    resp = client.get("/api/dns/unauthorized-domain.example.com/records", headers=_auth(rw_token))

    assert resp.status_code == 403
    body = resp.get_json()
    assert body["error"] == "forbidden" and body["message"]
    rows = _logs(action="api_call", error_code="domain_denied")
    assert len(rows) == 1 and rows[0].status == "denied" and rows[0].operation == "read"


def test_token_can_list_allowed_domain_and_only_sees_allowed_types(client, backend, make_account, make_realm, make_token):
    plain = _tokens(make_account, make_realm, make_token, ("read",), record_types=("A",), name="a_reader")
    resp = client.get(f"/api/dns/{DOMAIN}/records", headers=_auth(plain))

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["domain"] == DOMAIN
    assert [r["type"] for r in body["records"]] == ["A"]  # TXT filtered out
    assert body["total"] == 1
    assert _logs(action="api_call", status="success", operation="read")


# ---------------------------------------------------------------------------
# Operation scope
# ---------------------------------------------------------------------------

def test_readonly_token_cannot_create(client, backend, ro_token):
    resp = client.post(
        f"/api/dns/{DOMAIN}/records", headers=_auth(ro_token),
        json={"hostname": "test-forbidden", "type": "A", "destination": "1.2.3.4"},
    )
    assert resp.status_code == 403
    assert backend.update_calls == []
    rows = _logs(action="api_call", operation="create", status="denied")
    assert len(rows) == 1 and rows[0].error_code == "operation_denied"


def test_readonly_token_cannot_delete(client, backend, ro_token):
    resp = client.delete(f"/api/dns/{DOMAIN}/records/1", headers=_auth(ro_token))

    assert resp.status_code == 403
    assert backend.update_calls == []
    assert backend.find(DOMAIN, "vpn", "A") is not None
    rows = _logs(action="api_call", operation="delete", status="denied")
    assert len(rows) == 1 and rows[0].error_code == "operation_denied"


def test_readonly_token_cannot_delete_unknown_record_id(client, backend, ro_token):
    """Permission is checked before existence: 403, never a 404 oracle."""
    resp = client.delete(f"/api/dns/{DOMAIN}/records/999", headers=_auth(ro_token))
    assert resp.status_code == 403
    assert backend.update_calls == []


def test_readonly_token_cannot_update(client, backend, ro_token):
    resp = client.put(
        f"/api/dns/{DOMAIN}/records/1", headers=_auth(ro_token),
        json={"hostname": "vpn", "type": "A", "destination": "6.6.6.6"},
    )
    assert resp.status_code == 403
    assert backend.find(DOMAIN, "vpn", "A")["destination"] == "10.0.0.1"


# ---------------------------------------------------------------------------
# Token lifecycle / header parsing
# ---------------------------------------------------------------------------

def test_invalid_token_rejected(client, backend):
    resp = client.get(f"/api/dns/{DOMAIN}/records", headers=_auth("invalid-garbage-token-12345"))

    assert resp.status_code == 401
    assert resp.get_json() == {"error": "unauthorized", "message": "Invalid or expired token"}
    row = _logs(action="api_auth")[0]
    assert row.status == "denied"


@pytest.mark.parametrize("header", [
    "Basic abc123",            # wrong scheme
    "Bearer",                  # no token after scheme
    "BearerTokenNoSpace",      # no separator
    "",                        # empty
])
def test_malformed_authorization_header_rejected(client, backend, header):
    resp = client.get(f"/api/dns/{DOMAIN}/records", headers={"Authorization": header})
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "unauthorized"
    assert backend.update_calls == []


def test_missing_auth_rejected(client, backend):
    resp = client.get(f"/api/dns/{DOMAIN}/records")
    assert resp.status_code == 401
    row = _logs(action="api_auth")[0]
    assert row.error_code == "missing_token" and row.status == "denied"


def test_revoked_token_rejected(client, backend, make_account, make_realm, make_token):
    realm = make_realm(make_account("revoked_owner"), domain=DOMAIN, realm_type="subdomain", realm_value="")
    _tok, plain = make_token(realm, is_active=0)
    resp = client.get(f"/api/dns/{DOMAIN}/records", headers=_auth(plain))
    assert resp.status_code == 401


def test_expired_token_rejected(client, backend, make_account, make_realm, make_token):
    from datetime import datetime, timedelta
    realm = make_realm(make_account("expired_owner"), domain=DOMAIN, realm_type="subdomain", realm_value="")
    _tok, plain = make_token(realm, expires_at=datetime.utcnow() - timedelta(days=1))
    resp = client.get(f"/api/dns/{DOMAIN}/records", headers=_auth(plain))
    assert resp.status_code == 401


def test_disabled_account_token_rejected(client, backend, make_account, make_realm, make_token):
    realm = make_realm(make_account("disabled_owner", is_active=0), domain=DOMAIN, realm_type="subdomain", realm_value="")
    _tok, plain = make_token(realm)
    resp = client.get(f"/api/dns/{DOMAIN}/records", headers=_auth(plain))
    assert resp.status_code == 401


def test_ip_whitelist_blocks_other_peer(client, backend, make_account, make_realm, make_token):
    realm = make_realm(
        make_account("ip_owner"), domain=DOMAIN, realm_type="subdomain", realm_value="",
        operations=("read",),
    )
    _tok, plain = make_token(realm, ip_ranges=["203.0.113.0/24"])

    denied = client.get(f"/api/dns/{DOMAIN}/records", headers=_auth(plain))
    allowed = client.get(
        f"/api/dns/{DOMAIN}/records", headers=_auth(plain),
        environ_overrides={"REMOTE_ADDR": "203.0.113.9"},
    )

    assert denied.status_code == 403
    assert _logs(action="api_call", error_code="ip_denied")
    assert allowed.status_code == 200


# ---------------------------------------------------------------------------
# Credential protection
# ---------------------------------------------------------------------------

def _leaks(text: str, *extra: str) -> list[str]:
    lowered = text.lower()
    needles = [*SENTINELS.values(), "apisessionid", "token_hash", "$2b$", *extra]
    return [n for n in needles if n.lower() in lowered]


def test_error_responses_do_not_leak_credentials(client, backend, rw_token):
    set_setting("netcup_config", dict(SENTINELS))
    for resp in (
        client.get(f"/api/dns/{DOMAIN}/records", headers=_auth("invalid-token")),
        client.get(f"/api/dns/{DOMAIN}/records"),
        client.get("/api/dns/unauthorized-domain.example.com/records", headers=_auth(rw_token)),
    ):
        assert resp.status_code in (401, 403)
        assert _leaks(resp.get_data(as_text=True)) == []


def test_success_response_does_not_leak_internal_data(client, backend, rw_token):
    set_setting("netcup_config", dict(SENTINELS))
    resp = client.get(f"/api/dns/{DOMAIN}/records", headers=_auth(rw_token))

    assert resp.status_code == 200
    assert _leaks(resp.get_data(as_text=True), rw_token, rw_token.split("_", 2)[2]) == []
    assert set(resp.get_json()) == {"domain", "records", "total"}


# ---------------------------------------------------------------------------
# Public endpoint /api/myip
# ---------------------------------------------------------------------------

def test_myip_requires_no_auth_and_returns_peer_ip(client):
    resp = client.get("/api/myip")
    assert resp.status_code == 200
    assert resp.get_json()["ip"] == "127.0.0.1"


def test_myip_ignores_forwarded_for_with_zero_trusted_hops(client):
    resp = client.get("/api/myip", headers={"X-Forwarded-For": "203.0.113.50"})
    assert resp.status_code == 200
    assert resp.get_json()["ip"] == "127.0.0.1"


def test_myip_exposes_only_ip_and_echoed_headers(client):
    body = client.get("/api/myip").get_json()
    assert set(body) == {"ip", "headers"}
    assert set(body["headers"]) == {"x-forwarded-for", "x-real-ip"}
    serialized = json.dumps(body).lower()
    for word in ("token", "secret", "password"):
        assert word not in serialized


# ---------------------------------------------------------------------------
# Failed-auth burst
# ---------------------------------------------------------------------------

def test_rapid_failed_auth_is_consistently_401_and_each_logged(client, backend):
    statuses = [
        client.get(f"/api/dns/{DOMAIN}/records", headers=_auth("invalid-token")).status_code
        for _ in range(5)
    ]
    assert statuses == [401] * 5
    assert len(_logs(action="api_auth", status="denied")) == 5


# ---------------------------------------------------------------------------
# /api/ddns/<domain>/<hostname> (documented as POST/PUT)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method", ["post", "put"])
def test_ddns_endpoint_updates_record_for_authorized_token(client, backend, rw_token, method):
    resp = getattr(client, method)(
        f"/api/ddns/{DOMAIN}/home?ip=192.0.2.55", headers=_auth(rw_token),
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "created" and body["destination"] == "192.0.2.55"
    assert body["fqdn"] == f"home.{DOMAIN}"
    assert backend.find(DOMAIN, "home", "A")["destination"] == "192.0.2.55"
    assert _logs(action="api_call", operation="update", status="success")


def test_ddns_endpoint_denies_readonly_token(client, backend, ro_token):
    resp = client.post(f"/api/ddns/{DOMAIN}/home?ip=192.0.2.55", headers=_auth(ro_token))
    assert resp.status_code == 403
    assert backend.update_calls == []


def test_ddns_endpoint_requires_auth(client, backend):
    resp = client.post(f"/api/ddns/{DOMAIN}/home?ip=192.0.2.55")
    assert resp.status_code == 401
    assert backend.update_calls == []
