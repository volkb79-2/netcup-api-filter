"""Hermetic tests for the DDNS quick-update feature (P7.2) and DNS-record UI routes (P7.1).

Moved from ui_tests/tests/roundtrip/test_ddns_quick_update.py (S8). The originals
were mostly "route exists" probes, two tests that re-computed their own expected
values in-test (capability detection, badge colours; neither could fail), and one
round-trip that needed the live Netcup mock + deployment DB. Here:
  * the DDNS-card capability rule is checked against the REAL rendered realm page,
  * route protection is pinned to the exact CSRF/login behaviour,
  * the DynDNS2 round-trip (good -> nochg, zone content, token usage, ActivityLog)
    and the portal "Update to My IP" button run against an in-memory upstream.
/api/myip is covered by tests/test_api_security_http.py.
"""
from __future__ import annotations

import pytest

from netcup_api_filter.api import ddns_protocols as ddns_module
from netcup_api_filter.database import set_setting
from netcup_api_filter.models import ActivityLog, APIToken

from fake_netcup import FakeNetcupBackend, install_fake_netcup
from http_helpers import login_portal, mint_csrf

DOMAIN = "example.com"
PEER_IP = "127.0.0.1"


# ---------------------------------------------------------------------------
# Realm detail page: DDNS card shown exactly when the realm can do DDNS
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("operations, record_types, status, expected", [
    (("read", "update"), ("A", "AAAA"), "approved", True),
    (("read",), ("A", "AAAA"), "approved", False),                 # no update
    (("read", "update"), ("CNAME", "TXT"), "approved", False),     # no A/AAAA
    (("read", "update", "create", "delete"), ("A",), "approved", True),
    (("update",), ("AAAA",), "approved", True),
    (("read", "update"), ("A", "AAAA"), "pending", False),         # not yet approved
])
def test_realm_detail_shows_ddns_card_only_when_capable(
    client, make_account, make_realm, operations, record_types, status, expected
):
    owner = make_account("card_owner")
    realm = make_realm(owner, domain=DOMAIN, realm_type="host", realm_value="vpn",
                       operations=operations, record_types=record_types, status=status)
    login_portal(client, owner)

    resp = client.get(f"/account/realms/{realm.id}")

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert ('id="ddnsForm"' in html) is expected
    assert (f"/account/realms/{realm.id}/ddns" in html) is expected


# ---------------------------------------------------------------------------
# Portal "Update to My IP"
# ---------------------------------------------------------------------------

@pytest.fixture
def portal_backend(monkeypatch):
    backend = FakeNetcupBackend({DOMAIN: [{"id": "7", "hostname": "vpn", "type": "A", "destination": "10.0.0.1"}]})
    monkeypatch.setattr("netcup_api_filter.netcup_client.NetcupClient", lambda **kw: backend)
    return backend


@pytest.fixture
def netcup_configured(app):
    set_setting("netcup_config", {
        "customer_id": "cust", "api_key": "key", "api_password": "pw",
        "api_url": "https://example.invalid/", "timeout": 5,
    })


def test_portal_quick_update_writes_client_ip(client, portal_backend, netcup_configured, make_account, make_realm):
    owner = make_account("quick_owner")
    realm = make_realm(owner, domain=DOMAIN, realm_type="host", realm_value="vpn")
    login_portal(client, owner)
    csrf = mint_csrf(client, f"/account/realms/{realm.id}")

    resp = client.post(f"/account/realms/{realm.id}/ddns", data={"csrf_token": csrf})

    assert resp.status_code == 302 and resp.headers["Location"].endswith(f"/account/realms/{realm.id}")
    rec = portal_backend.find(DOMAIN, "vpn", "A")
    assert rec["destination"] == PEER_IP and rec["id"] == "7"  # updated in place
    log = ActivityLog.query.filter_by(action="ddns_ui").one()
    assert log.status == "success" and log.account_id == owner.id and PEER_IP in log.status_reason


def test_portal_quick_update_refused_for_read_only_realm(
    client, portal_backend, netcup_configured, make_account, make_realm
):
    owner = make_account("quick_ro_owner")
    realm = make_realm(owner, domain=DOMAIN, realm_type="host", realm_value="vpn", operations=("read",))
    login_portal(client, owner)
    csrf = mint_csrf(client, f"/account/realms/{realm.id}")

    resp = client.post(f"/account/realms/{realm.id}/ddns", data={"csrf_token": csrf}, follow_redirects=True)

    assert "does not have update permission" in resp.get_data(as_text=True)
    assert portal_backend.update_calls == []
    assert ActivityLog.query.filter_by(action="ddns_ui").count() == 0


def test_portal_quick_update_refused_for_someone_elses_realm(
    client, portal_backend, netcup_configured, make_account, make_realm
):
    owner = make_account("quick_victim")
    attacker = make_account("quick_attacker")
    realm = make_realm(owner, domain=DOMAIN, realm_type="host", realm_value="vpn")
    login_portal(client, attacker)
    csrf = mint_csrf(client, "/account/settings")

    resp = client.post(f"/account/realms/{realm.id}/ddns", data={"csrf_token": csrf}, follow_redirects=True)

    assert "Access denied" in resp.get_data(as_text=True)
    assert portal_backend.update_calls == []


# ---------------------------------------------------------------------------
# Unauthenticated access to the realm / DNS-record UI routes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "/account/realms/1/dns",
    "/account/realms/1/dns/create",
    "/account/realms/1/dns/123/edit",
    "/account/realms/1",
])
def test_realm_pages_redirect_anonymous_to_login(client, path):
    resp = client.get(path)
    assert resp.status_code == 302
    assert "/account/login" in resp.headers["Location"]


@pytest.mark.parametrize("path", ["/account/realms/1/ddns", "/account/realms/1/dns/123/delete"])
def test_realm_mutations_require_csrf(client, path):
    assert client.post(path).status_code == 400


@pytest.mark.parametrize("path", ["/account/realms/1/ddns", "/account/realms/1/dns/123/delete"])
def test_realm_mutations_redirect_anonymous_with_valid_csrf(client, path):
    csrf = mint_csrf(client, "/account/login")
    resp = client.post(path, data={"csrf_token": csrf})
    assert resp.status_code == 302
    assert "/account/login" in resp.headers["Location"]


# ---------------------------------------------------------------------------
# DynDNS2 round-trip: zone content, idempotence, token usage, audit trail
# ---------------------------------------------------------------------------

def test_dyndns2_roundtrip_mutates_zone_and_records_usage(client, monkeypatch, make_account, make_realm, make_token, db):
    backend = install_fake_netcup(monkeypatch, FakeNetcupBackend({DOMAIN: []}), ddns_module)
    realm = make_realm(make_account("rt_owner"), domain=DOMAIN, realm_type="subdomain", realm_value="")
    token, plain = make_token(realm)
    assert (token.use_count or 0) == 0 and token.last_used_at is None
    test_ip = "198.51.100.42"
    call = lambda: client.get(  # noqa: E731
        "/api/ddns/dyndns2/update", headers={"Authorization": f"Bearer {plain}"},
        query_string={"hostname": DOMAIN, "myip": test_ip},
    )

    first, second = call(), call()

    assert first.status_code == 200 and first.get_data(as_text=True).strip() == f"good {test_ip}"
    assert second.status_code == 200 and second.get_data(as_text=True).strip() == f"nochg {test_ip}"
    assert backend.find(DOMAIN, "@", "A")["destination"] == test_ip
    assert len(backend.update_calls) == 1  # the nochg call wrote nothing
    db.session.expire_all()
    tok = APIToken.query.get(token.id)
    assert tok.use_count == 2 and tok.last_used_at is not None and tok.last_used_ip == PEER_IP
    logs = ActivityLog.query.filter_by(action="ddns_update", status="success").order_by(ActivityLog.id).all()
    assert len(logs) == 2 and all(l.token_id == token.id for l in logs)
