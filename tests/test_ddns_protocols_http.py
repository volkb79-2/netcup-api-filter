"""Hermetic HTTP tests for the DynDNS2 / No-IP endpoints (/api/ddns/*/update).

Moved from ui_tests/tests/features/test_ddns_protocols.py (S8). The originals
only issued HTTP requests, so they accepted any of 200/403/502 depending on how
the live demo token and Netcup mock happened to be configured. Here the realm,
token and upstream are all under test control, so every case pins the EXACT
status + protocol body and asserts backend truth (zone contents) and the
ActivityLog row, via the Flask test client with a tmp SQLite DB.
"""
from __future__ import annotations

import pytest

from netcup_api_filter.api import ddns_protocols as ddns_module
from netcup_api_filter.models import ActivityLog, APIToken

from fake_netcup import FakeNetcupBackend, install_fake_netcup

DOMAIN = "example.com"
OUT_OF_SCOPE = "test.unauthorized-domain.example.net"
CLIENT_IP = "127.0.0.1"  # werkzeug test client peer address


@pytest.fixture
def backend(monkeypatch):
    return install_fake_netcup(monkeypatch, FakeNetcupBackend({DOMAIN: []}), ddns_module)


@pytest.fixture
def token(make_account, make_realm, make_token):
    """Bearer token for a whole-zone realm (apex + children) with update on A/AAAA."""
    account = make_account("ddns_owner")
    realm = make_realm(
        account, domain=DOMAIN, realm_type="subdomain", realm_value="",
        operations=("read", "update"), record_types=("A", "AAAA"),
    )
    _tok, plain = make_token(realm)
    return plain


def _auth(plain):
    return {"Authorization": f"Bearer {plain}"}


def _last_log(**filters):
    return ActivityLog.query.filter_by(**filters).order_by(ActivityLog.id.desc()).first()


PROTOCOLS = {
    # protocol -> (url, permission-denied body, bad-hostname (status, body))
    "dyndns2": ("/api/ddns/dyndns2/update", "!yours", (400, "notfqdn")),
    "noip": ("/api/ddns/noip/update", "abuse", (401, "nohost")),
}


# ---------------------------------------------------------------------------
# Success path (both protocols)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("protocol", sorted(PROTOCOLS))
@pytest.mark.parametrize("hostname, record_name", [(DOMAIN, "@"), ("device." + DOMAIN, "device")])
def test_valid_token_ipv4_creates_record(client, backend, token, protocol, hostname, record_name):
    url = PROTOCOLS[protocol][0]
    resp = client.get(url, headers=_auth(token), query_string={"hostname": hostname, "myip": "192.0.2.1"})

    assert resp.status_code == 200
    assert resp.mimetype == "text/plain"
    assert resp.get_data(as_text=True).strip() == "good 192.0.2.1"
    # Channel C: the zone really holds the record.
    rec = backend.find(DOMAIN, record_name, "A")
    assert rec is not None and rec["destination"] == "192.0.2.1"
    log = _last_log(action="ddns_update")
    assert log.status == "success"
    assert log.record_name == record_name and log.record_type == "A" and log.operation == "update"
    assert log.token_id is not None and log.source_ip == CLIENT_IP


@pytest.mark.parametrize("protocol", sorted(PROTOCOLS))
def test_second_identical_update_is_nochg_and_writes_nothing(client, backend, token, protocol):
    url = PROTOCOLS[protocol][0]
    params = {"hostname": "nochg." + DOMAIN, "myip": "198.51.100.20"}
    first = client.get(url, headers=_auth(token), query_string=params)
    assert first.get_data(as_text=True).strip() == "good 198.51.100.20"
    writes_after_first = len(backend.update_calls)

    second = client.get(url, headers=_auth(token), query_string=params)

    assert second.status_code == 200
    assert second.get_data(as_text=True).strip() == "nochg 198.51.100.20"
    assert len(backend.update_calls) == writes_after_first
    assert [r["destination"] for r in backend.records_for(DOMAIN)] == ["198.51.100.20"]


def test_existing_record_is_updated_in_place(client, backend, token):
    backend.update_dns_records(DOMAIN, [{"hostname": "move", "type": "A", "destination": "192.0.2.1"}])
    original_id = backend.find(DOMAIN, "move", "A")["id"]

    resp = client.get(
        PROTOCOLS["dyndns2"][0], headers=_auth(token),
        query_string={"hostname": "move." + DOMAIN, "myip": "192.0.2.99"},
    )

    assert resp.get_data(as_text=True).strip() == "good 192.0.2.99"
    assert len(backend.records_for(DOMAIN)) == 1
    assert backend.find(DOMAIN, "move", "A")["id"] == original_id
    assert backend.find(DOMAIN, "move", "A")["destination"] == "192.0.2.99"


def test_dyndns2_post_form_data(client, backend, token):
    resp = client.post(
        PROTOCOLS["dyndns2"][0], headers=_auth(token),
        data={"hostname": DOMAIN, "myip": "192.0.2.2"},
    )
    assert resp.status_code == 200
    assert resp.get_data(as_text=True).strip() == "good 192.0.2.2"
    assert backend.find(DOMAIN, "@", "A")["destination"] == "192.0.2.2"


def test_success_updates_token_usage(client, backend, token, db):
    prefix = token.split("_", 2)[2][:8]
    before = APIToken.query.filter_by(token_prefix=prefix).one()
    assert (before.use_count or 0) == 0 and before.last_used_at is None

    resp = client.get(
        PROTOCOLS["dyndns2"][0], headers=_auth(token),
        query_string={"hostname": DOMAIN, "myip": "198.51.100.42"},
    )
    assert resp.get_data(as_text=True).strip() == "good 198.51.100.42"

    db.session.expire_all()
    after = APIToken.query.filter_by(token_prefix=prefix).one()
    assert after.use_count == 1
    assert after.last_used_at is not None
    assert _last_log(action="ddns_update", status="success") is not None


# ---------------------------------------------------------------------------
# Auto IP detection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("protocol", sorted(PROTOCOLS))
@pytest.mark.parametrize("myip", ["auto", "public", "detect", "AUTO", ""])
def test_keyword_and_empty_myip_use_client_ip(client, backend, token, protocol, myip):
    resp = client.get(
        PROTOCOLS[protocol][0], headers=_auth(token),
        query_string={"hostname": DOMAIN, "myip": myip},
    )
    assert resp.status_code == 200
    assert resp.get_data(as_text=True).strip() == f"good {CLIENT_IP}"
    assert backend.find(DOMAIN, "@", "A")["destination"] == CLIENT_IP


def test_missing_myip_uses_client_ip(client, backend, token):
    resp = client.get(PROTOCOLS["dyndns2"][0], headers=_auth(token), query_string={"hostname": DOMAIN})
    assert resp.get_data(as_text=True).strip() == f"good {CLIENT_IP}"
    assert backend.find(DOMAIN, "@", "A")["destination"] == CLIENT_IP


def test_forged_leftmost_x_forwarded_for_is_not_the_detected_ip(client, backend, token):
    """ProxyFix(x_for=1) trusts only the rightmost hop; the leftmost is attacker-controlled."""
    resp = client.get(
        PROTOCOLS["dyndns2"][0],
        headers={**_auth(token), "X-Forwarded-For": "203.0.113.1, 198.51.100.1"},
        query_string={"hostname": DOMAIN, "myip": "auto"},
    )
    assert resp.get_data(as_text=True).strip() == "good 198.51.100.1"
    assert backend.find(DOMAIN, "@", "A")["destination"] == "198.51.100.1"
    assert all(r["destination"] != "203.0.113.1" for r in backend.records_for(DOMAIN))


def test_ipv6_creates_aaaa_record(client, backend, token):
    resp = client.get(
        PROTOCOLS["dyndns2"][0], headers=_auth(token),
        query_string={"hostname": DOMAIN, "myip": "2001:db8::1"},
    )
    assert resp.get_data(as_text=True).strip() == "good 2001:db8::1"
    assert backend.find(DOMAIN, "@", "AAAA")["destination"] == "2001:db8::1"
    assert backend.find(DOMAIN, "@", "A") is None


def test_ipv6_denied_when_aaaa_not_allowed(client, backend, make_account, make_realm, make_token):
    realm = make_realm(
        make_account("a_only"), domain=DOMAIN, realm_type="subdomain", realm_value="",
        operations=("read", "update"), record_types=("A",),
    )
    _tok, plain = make_token(realm)

    resp = client.get(
        PROTOCOLS["dyndns2"][0], headers=_auth(plain),
        query_string={"hostname": DOMAIN, "myip": "2001:db8::1"},
    )

    assert resp.status_code == 403
    assert resp.get_data(as_text=True).strip() == "!yours"
    assert backend.records_for(DOMAIN) == []
    assert _last_log(action="ddns_update").error_code == "record_type_denied"


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("protocol", sorted(PROTOCOLS))
def test_missing_token_is_401_and_logged(client, backend, protocol):
    resp = client.get(
        PROTOCOLS[protocol][0], query_string={"hostname": "test." + DOMAIN, "myip": "192.0.2.1"},
    )
    assert resp.status_code == 401
    assert backend.records_for(DOMAIN) == []
    log = _last_log(action="api_auth")
    assert log.status == "denied" and log.error_code == "missing_token"


@pytest.mark.parametrize("protocol", sorted(PROTOCOLS))
def test_invalid_token_is_401_and_logged(client, backend, protocol):
    resp = client.get(
        PROTOCOLS[protocol][0], headers=_auth("invalid-token-12345"),
        query_string={"hostname": "test." + DOMAIN, "myip": "192.0.2.1"},
    )
    assert resp.status_code == 401
    assert backend.records_for(DOMAIN) == []
    assert _last_log(action="api_auth").status == "denied"


def test_query_param_credentials_are_not_an_auth_fallback(client, backend):
    resp = client.get(
        PROTOCOLS["dyndns2"][0],
        query_string={"hostname": "test." + DOMAIN, "myip": "192.0.2.1", "username": "user", "password": "pass"},
    )
    assert resp.status_code == 401
    assert backend.records_for(DOMAIN) == []


def test_query_param_credentials_are_ignored_with_valid_token(client, backend, token):
    resp = client.get(
        PROTOCOLS["dyndns2"][0], headers=_auth(token),
        query_string={"hostname": "test." + DOMAIN, "myip": "192.0.2.1",
                      "username": "ignored-user", "password": "ignored-pass"},
    )
    assert resp.status_code == 200
    assert resp.get_data(as_text=True).strip() == "good 192.0.2.1"
    assert backend.find(DOMAIN, "test", "A")["destination"] == "192.0.2.1"


# ---------------------------------------------------------------------------
# Authorization (protocol-specific denial bodies)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("protocol", sorted(PROTOCOLS))
def test_out_of_realm_domain_is_denied_without_backend_change(client, backend, token, protocol):
    url, denied_body, _ = PROTOCOLS[protocol]
    resp = client.get(url, headers=_auth(token), query_string={"hostname": OUT_OF_SCOPE, "myip": "192.0.2.1"})

    assert resp.status_code == 403
    assert resp.mimetype == "text/plain"
    assert resp.get_data(as_text=True).strip() == denied_body
    assert backend.update_calls == []
    log = _last_log(action="ddns_update")
    assert log.status == "denied" and log.error_code == "domain_denied"


@pytest.mark.parametrize("protocol", sorted(PROTOCOLS))
def test_read_only_token_cannot_update(client, backend, make_account, make_realm, make_token, protocol):
    realm = make_realm(
        make_account("ro_owner"), domain=DOMAIN, realm_type="subdomain", realm_value="",
        operations=("read",), record_types=("A", "AAAA"),
    )
    _tok, plain = make_token(realm)
    url, denied_body, _ = PROTOCOLS[protocol]

    resp = client.get(url, headers=_auth(plain), query_string={"hostname": DOMAIN, "myip": "192.0.2.1"})

    assert resp.status_code == 403
    assert resp.get_data(as_text=True).strip() == denied_body
    assert backend.update_calls == []
    assert _last_log(action="ddns_update").error_code == "operation_denied"


def test_host_scoped_token_cannot_update_sibling_host(client, backend, make_account, make_realm, make_token):
    realm = make_realm(
        make_account("host_owner"), domain=DOMAIN, realm_type="host", realm_value="vpn",
        operations=("read", "update"), record_types=("A",),
    )
    _tok, plain = make_token(realm)
    url = PROTOCOLS["dyndns2"][0]

    denied = client.get(url, headers=_auth(plain), query_string={"hostname": "www." + DOMAIN, "myip": "192.0.2.1"})
    allowed = client.get(url, headers=_auth(plain), query_string={"hostname": "vpn." + DOMAIN, "myip": "192.0.2.1"})

    assert denied.status_code == 403 and denied.get_data(as_text=True).strip() == "!yours"
    assert allowed.status_code == 200
    assert [r["hostname"] for r in backend.records_for(DOMAIN)] == ["vpn"]


# ---------------------------------------------------------------------------
# Input validation (protocol-specific bad-hostname bodies)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("protocol", sorted(PROTOCOLS))
@pytest.mark.parametrize("hostname", ["no-dots", "invalid", "..double-dot.com", "-lead.example.com", "bad_char.example.com"])
def test_malformed_hostname(client, backend, token, protocol, hostname):
    url, _, (status, body) = PROTOCOLS[protocol]
    resp = client.get(url, headers=_auth(token), query_string={"hostname": hostname, "myip": "192.0.2.1"})

    assert resp.status_code == status
    assert resp.get_data(as_text=True).strip() == body
    assert backend.update_calls == []
    assert _last_log(action="ddns_update").error_code == "invalid_hostname"


@pytest.mark.parametrize("protocol", sorted(PROTOCOLS))
@pytest.mark.parametrize("query", [{"myip": "192.0.2.1"}, {"hostname": "", "myip": "192.0.2.1"}])
def test_missing_or_empty_hostname(client, backend, token, protocol, query):
    url, _, (status, body) = PROTOCOLS[protocol]
    resp = client.get(url, headers=_auth(token), query_string=query)

    assert resp.status_code == status
    assert resp.get_data(as_text=True).strip() == body
    assert backend.update_calls == []
    assert _last_log(action="ddns_update").error_code == "missing_parameter"


@pytest.mark.parametrize("protocol", sorted(PROTOCOLS))
def test_invalid_ip_is_dnserr_without_backend_change(client, backend, token, protocol):
    resp = client.get(
        PROTOCOLS[protocol][0], headers=_auth(token),
        query_string={"hostname": "test." + DOMAIN, "myip": "not.an.ip.address"},
    )
    assert resp.status_code == 502
    assert resp.get_data(as_text=True).strip() == "dnserr"
    assert backend.update_calls == []
    assert _last_log(action="ddns_update").error_code == "invalid_ip"


# ---------------------------------------------------------------------------
# Upstream / feature-flag failure modes (previously unreachable from the live lane)
# ---------------------------------------------------------------------------

def test_upstream_write_failure_is_dnserr_and_logged(client, backend, token):
    backend.fail_update = "upstream refused"
    resp = client.get(
        PROTOCOLS["dyndns2"][0], headers=_auth(token),
        query_string={"hostname": DOMAIN, "myip": "192.0.2.1"},
    )
    assert resp.status_code == 502
    assert resp.get_data(as_text=True).strip() == "dnserr"
    log = _last_log(action="ddns_update")
    assert log.status == "error" and "upstream refused" in log.status_reason


def test_upstream_read_failure_is_dnserr(client, backend, token):
    backend.fail_info = "zone unavailable"
    resp = client.get(
        PROTOCOLS["noip"][0], headers=_auth(token),
        query_string={"hostname": DOMAIN, "myip": "192.0.2.1"},
    )
    assert resp.status_code == 502
    assert resp.get_data(as_text=True).strip() == "dnserr"
    assert backend.update_calls == []


def test_netcup_not_configured_is_dnserr(client, monkeypatch, token):
    monkeypatch.setattr(ddns_module, "get_netcup_client", lambda: None)
    resp = client.get(
        PROTOCOLS["dyndns2"][0], headers=_auth(token),
        query_string={"hostname": DOMAIN, "myip": "192.0.2.1"},
    )
    assert resp.status_code == 502
    assert resp.get_data(as_text=True).strip() == "dnserr"
    assert "not configured" in _last_log(action="ddns_update").status_reason


@pytest.mark.parametrize("protocol", sorted(PROTOCOLS))
def test_feature_flag_off_returns_911_and_does_not_write(client, backend, token, monkeypatch, protocol):
    monkeypatch.setenv("DDNS_PROTOCOLS_ENABLED", "false")
    resp = client.get(
        PROTOCOLS[protocol][0], headers=_auth(token),
        query_string={"hostname": DOMAIN, "myip": "192.0.2.1"},
    )
    assert resp.status_code == 500
    assert resp.get_data(as_text=True).strip() == "911"
    assert backend.update_calls == []
