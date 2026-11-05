"""Tests for token_auth.py beyond authenticate/check_permission basics:
require_auth decorator (HTTP behaviour + audit rows), log_activity,
filter_dns_records, validate_dns_records_update, security analytics helpers,
and the permission matrix (realm_type x hostname x operation x record type).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import pytest
from flask import g, jsonify

from netcup_api_filter import token_auth
from netcup_api_filter.models import ActivityLog, APIToken, generate_token
from netcup_api_filter.token_auth import (
    AuthResult,
    authenticate_token,
    check_permission,
    filter_dns_records,
    get_security_stats,
    get_security_timeline,
    log_activity,
    require_auth,
    validate_dns_records_update,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def protected_client(app):
    """Client for a throwaway endpoint wrapped by @require_auth."""
    @require_auth
    def _probe():
        return jsonify({"ok": True, "token": g.auth.token.token_name})

    app.add_url_rule("/__probe_token_auth", "probe_token_auth", _probe)
    return app.test_client()


def _setup(make_account, make_realm, make_token, *, realm_kw=None, token_kw=None,
           username="alice"):
    account = make_account(username)
    realm = make_realm(account, **(realm_kw or {}))
    token, plain = make_token(realm, **(token_kw or {}))
    return account, realm, token, plain


def _auth(plain):
    res = authenticate_token(plain)
    assert res.success, res
    return res


def _rows(**filters):
    return ActivityLog.query.filter_by(**filters).all()


def _corrupt(plain):
    """Same alias and same 8-char prefix, different secret tail."""
    return plain[:-1] + ("A" if plain[-1] != "A" else "B")


# ---------------------------------------------------------------------------
# require_auth: accepted
# ---------------------------------------------------------------------------

def test_require_auth_accepts_valid_token_and_exposes_auth(
        protected_client, make_account, make_realm, make_token):
    _, _, _, plain = _setup(make_account, make_realm, make_token)
    resp = protected_client.get(
        "/__probe_token_auth", headers={"Authorization": f"Bearer {plain}"})
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True, "token": "test-token"}
    # success path writes no denial row
    assert _rows(action="api_auth") == []


# ---------------------------------------------------------------------------
# require_auth: every rejection path -> 401, generic body, audit row
# ---------------------------------------------------------------------------

def test_require_auth_missing_header(protected_client):
    resp = protected_client.get("/__probe_token_auth")
    assert resp.status_code == 401
    assert resp.get_json() == {"error": "unauthorized", "message": "Authorization required"}
    rows = _rows(action="api_auth")
    assert len(rows) == 1
    row = rows[0]
    assert row.error_code == "missing_token"
    assert row.status == "denied"
    assert row.severity == "low"
    assert row.is_attack == 0
    assert row.token_id is None and row.account_id is None


@pytest.mark.parametrize("header", ["Basic abc:def", "Bearer", "naf_x_y"])
def test_require_auth_non_bearer_headers_count_as_missing(protected_client, header):
    resp = protected_client.get("/__probe_token_auth", headers={"Authorization": header})
    assert resp.status_code == 401
    assert [r.error_code for r in _rows(action="api_auth")] == ["missing_token"]


GENERIC = {"error": "unauthorized", "message": "Invalid or expired token"}


def _bad_token(kind, make_account, make_realm, make_token):
    """Return (bearer_plain, expected_error_code, expected_severity, is_attack)."""
    if kind == "malformed":
        return "not-a-token", "invalid_format", "low", 0
    if kind == "wrong_prefix":
        return "xyz_" + "A" * 16 + "_" + "b" * 64, "invalid_format", "low", 0
    if kind == "unknown_alias":
        return generate_token("ZzZzZzZzZzZzZzZz"), "alias_not_found", "medium", 0
    account = make_account("bob", is_active=0 if kind == "inactive_account" else 1)
    realm = make_realm(
        account, status="pending" if kind == "realm_pending" else "approved")
    kw = {}
    if kind == "revoked":
        kw["is_active"] = 0
    if kind == "expired":
        kw["expires_at"] = datetime.utcnow() - timedelta(minutes=1)
    _, plain = make_token(realm, **kw)
    if kind == "unknown_prefix":
        # real alias, random part whose 8-char prefix is not stored
        return f"naf_{account.user_alias}_" + "Q" * 64, "token_prefix_not_found", "high", 1
    if kind == "bad_hash":
        return _corrupt(plain), "token_hash_mismatch", "critical", 1
    return {
        "inactive_account": (plain, "account_disabled", "medium", 0),
        "revoked": (plain, "token_revoked", "high", 1),
        "expired": (plain, "token_expired", "low", 0),
        "realm_pending": (plain, "realm_not_approved", "low", 0),
    }[kind]


@pytest.mark.parametrize("kind", [
    "malformed", "wrong_prefix", "unknown_alias", "unknown_prefix", "bad_hash",
    "inactive_account", "revoked", "expired", "realm_pending",
])
def test_require_auth_rejects_and_audits(
        kind, protected_client, make_account, make_realm, make_token):
    plain, code, severity, attack = _bad_token(kind, make_account, make_realm, make_token)
    resp = protected_client.get(
        "/__probe_token_auth", headers={"Authorization": f"Bearer {plain}"})
    assert resp.status_code == 401
    # body identical for every failure (no oracle)
    assert resp.get_json() == GENERIC
    assert plain not in resp.get_data(as_text=True)

    rows = _rows(action="api_auth")
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "denied"
    assert row.error_code == code
    assert row.severity == severity
    assert row.is_attack == attack
    # the audit row must never contain the full token
    assert plain not in (row.status_reason or "")
    assert plain not in (row.request_data or "")


def test_require_auth_bad_hash_row_is_attributed_to_token_and_account(
        protected_client, make_account, make_realm, make_token):
    account, _, token, plain = _setup(make_account, make_realm, make_token)
    protected_client.get("/__probe_token_auth",
                         headers={"Authorization": f"Bearer {_corrupt(plain)}"})
    row = _rows(action="api_auth")[0]
    assert row.token_id == token.id
    assert row.account_id == account.id


def test_require_auth_does_not_bump_usage_on_failure(
        protected_client, db, make_account, make_realm, make_token):
    _, _, token, plain = _setup(make_account, make_realm, make_token)
    protected_client.get("/__probe_token_auth",
                         headers={"Authorization": f"Bearer {_corrupt(plain)}"})
    db.session.refresh(token)
    assert not token.use_count
    assert token.last_used_at is None


def test_revoked_token_with_wrong_secret_is_hash_mismatch_not_revoked(
        make_account, make_realm, make_token):
    """Hash verification precedes the revoked check: a caller without the
    secret cannot learn that a token is revoked."""
    _, _, _, plain = _setup(make_account, make_realm, make_token, token_kw={"is_active": 0})
    assert authenticate_token(_corrupt(plain)).error_code == "token_hash_mismatch"
    assert authenticate_token(plain).error_code == "token_revoked"


def test_secret_comparison_is_delegated_to_apitoken_verify(
        monkeypatch, make_account, make_realm, make_token):
    """authenticate_token must delegate to APIToken.verify (bcrypt compare)
    and honour its verdict -- no plain equality on the secret."""
    _, _, _, plain = _setup(make_account, make_realm, make_token)
    calls = []

    def fake_verify(self, full):
        calls.append(full)
        return False

    monkeypatch.setattr(APIToken, "verify", fake_verify)
    res = authenticate_token(plain)
    assert calls == [plain]
    assert not res.success and res.error_code == "token_hash_mismatch"


# ---------------------------------------------------------------------------
# log_activity
# ---------------------------------------------------------------------------

def test_log_activity_success_records_row_and_usage(
        app, make_account, make_realm, make_token):
    account, _, token, plain = _setup(make_account, make_realm, make_token)
    auth = _auth(plain)
    with app.test_request_context("/", headers={"User-Agent": "ua-test"},
                                  environ_base={"REMOTE_ADDR": "203.0.113.9"}):
        log_activity(auth, "api_call", operation="read", domain="example.com",
                     record_type="A", record_name="vpn",
                     request_data={"a": 1}, response_summary={"n": 2})
    row = _rows(action="api_call")[0]
    assert row.status == "success"
    assert row.token_id == token.id and row.account_id == account.id
    assert row.realm_type == "host" and row.realm_value == "vpn"
    assert (row.operation, row.record_type, row.record_name) == ("read", "A", "vpn")
    assert row.source_ip == "203.0.113.9"
    assert row.user_agent == "ua-test"
    assert row.severity is None and row.is_attack == 0
    assert row.get_request_data() == {"a": 1}
    assert row.get_response_summary() == {"n": 2}
    assert token.use_count == 1
    assert token.last_used_ip == "203.0.113.9"
    assert token.last_used_at is not None


def test_log_activity_explicit_source_ip_wins_over_request(
        app, make_account, make_realm, make_token):
    _, _, token, plain = _setup(make_account, make_realm, make_token)
    with app.test_request_context("/", environ_base={"REMOTE_ADDR": "203.0.113.9"}):
        log_activity(_auth(plain), "api_call", source_ip="198.51.100.1",
                     user_agent="explicit")
    row = _rows(action="api_call")[0]
    assert row.source_ip == "198.51.100.1"
    assert row.user_agent == "explicit"
    assert token.last_used_ip == "198.51.100.1"


def test_log_activity_no_remote_addr_falls_back_to_unknown(app):
    with app.test_request_context("/", environ_base={"REMOTE_ADDR": ""}):
        log_activity(AuthResult(success=False), "api_auth", status="denied")
    assert _rows(action="api_auth")[0].source_ip == "unknown"


def test_log_activity_denied_without_auth_context_uses_domain(app):
    with app.test_request_context("/", environ_base={"REMOTE_ADDR": "192.0.2.5"}):
        log_activity(AuthResult(success=False, error="nope", error_code="invalid_format",
                                severity="low"),
                     "api_auth", domain="example.com", status="denied")
    row = _rows(action="api_auth")[0]
    assert row.realm_type is None
    assert row.realm_value == "example.com"
    assert row.token_id is None and row.account_id is None
    assert row.error_code == "invalid_format"  # falls back to auth.error_code
    assert row.status_reason == "nope"
    assert row.severity == "low" and row.is_attack == 0


@pytest.mark.parametrize("code,sev,attack", [
    ("token_hash_mismatch", "critical", 1),
    ("ip_denied", "critical", 1),
    ("domain_denied", "high", 1),
    ("hostname_denied", "high", 1),
    ("operation_denied", "medium", 0),
    ("record_type_denied", "low", 0),
    ("totally_unknown_code", "medium", 0),   # default severity for unknown codes
])
def test_log_activity_severity_derived_from_error_code(app, code, sev, attack):
    with app.test_request_context("/", environ_base={"REMOTE_ADDR": "192.0.2.5"}):
        log_activity(AuthResult(success=False), "api_call", status="denied",
                     error_code=code)
    row = _rows(action="api_call")[0]
    assert row.severity == sev
    assert row.is_attack == attack


def test_log_activity_non_success_without_error_keeps_severity_none(app):
    with app.test_request_context("/", environ_base={"REMOTE_ADDR": "192.0.2.5"}):
        log_activity(AuthResult(success=False), "api_call", status="error")
    row = _rows(action="api_call")[0]
    assert row.severity is None and row.is_attack == 0


def test_log_activity_notifies_user_only_when_flagged(app, make_account, caplog):
    account = make_account("carol")
    flagged = AuthResult(success=False, account=account, error_code="token_revoked",
                         severity="high", should_notify_user=True)
    unflagged = AuthResult(success=False, account=account, error_code="token_expired",
                           severity="low", should_notify_user=False)
    with app.test_request_context("/", environ_base={"REMOTE_ADDR": "192.0.2.5"}):
        with caplog.at_level(logging.INFO, logger="netcup_api_filter.token_auth"):
            log_activity(unflagged, "api_auth", status="denied")
            assert "Security notification triggered" not in caplog.text
            log_activity(flagged, "api_auth", status="denied", source_ip="192.0.2.77")
    assert "event=token_revoked" in caplog.text
    assert "ip=192.0.2.77" in caplog.text
    assert "account=carol" in caplog.text


def test_notification_without_account_is_not_sent(app, caplog):
    auth = AuthResult(success=False, error_code="ip_denied", severity="critical",
                      should_notify_user=True)
    with app.test_request_context("/", environ_base={"REMOTE_ADDR": "192.0.2.5"}):
        with caplog.at_level(logging.INFO, logger="netcup_api_filter.token_auth"):
            log_activity(auth, "api_auth", status="denied")
    assert "Security notification triggered" not in caplog.text


def test_trigger_security_notification_unknown_account_label(caplog):
    auth = AuthResult(success=False, error_code="ip_denied", severity="critical")
    with caplog.at_level(logging.INFO, logger="netcup_api_filter.token_auth"):
        token_auth._trigger_security_notification(auth, "192.0.2.1")
    assert "account=unknown" in caplog.text


def test_trigger_security_notification_swallows_errors(monkeypatch, caplog):
    """A failure inside the notifier must never propagate into the request."""
    auth = AuthResult(success=False, error_code="ip_denied", severity="critical")
    real_info = token_auth.logger.info

    def exploding_info(msg, *a, **k):
        if "Security notification" in str(msg):
            raise RuntimeError("log sink down")
        return real_info(msg, *a, **k)

    monkeypatch.setattr(token_auth.logger, "info", exploding_info)
    with caplog.at_level(logging.ERROR, logger="netcup_api_filter.token_auth"):
        token_auth._trigger_security_notification(auth, "192.0.2.1")  # must not raise
    assert "Failed to send security notification" in caplog.text


# ---------------------------------------------------------------------------
# filter_dns_records
# ---------------------------------------------------------------------------

RECORDS = [
    {"hostname": "vpn", "type": "A", "destination": "1.2.3.4"},
    {"hostname": "vpn", "type": "AAAA", "destination": "::1"},
    {"hostname": "vpn", "type": "TXT", "destination": "x"},
    {"hostname": "vpn", "type": "MX", "destination": "m"},
    {"hostname": "vpn", "destination": "no-type"},
]


def test_filter_dns_records_realm_level_types(make_account, make_realm, make_token):
    _, _, _, plain = _setup(make_account, make_realm, make_token)
    out = filter_dns_records(_auth(plain), "example.com", RECORDS)
    assert [r["type"] for r in out] == ["A", "AAAA"]


def test_filter_dns_records_token_narrower_than_realm(make_account, make_realm, make_token):
    _, _, _, plain = _setup(make_account, make_realm, make_token,
                            token_kw={"record_types": ["AAAA"]})
    out = filter_dns_records(_auth(plain), "example.com", RECORDS)
    assert [r["type"] for r in out] == ["AAAA"]


def test_filter_dns_records_returns_empty_on_failed_auth():
    assert filter_dns_records(AuthResult(success=False), "example.com", RECORDS) == []


def test_filter_dns_records_returns_empty_when_token_missing():
    assert filter_dns_records(AuthResult(success=True, token=None), "example.com", RECORDS) == []


def test_filter_dns_records_does_not_mutate_input(make_account, make_realm, make_token):
    _, _, _, plain = _setup(make_account, make_realm, make_token)
    before = [dict(r) for r in RECORDS]
    filter_dns_records(_auth(plain), "example.com", RECORDS)
    assert RECORDS == before


# ---------------------------------------------------------------------------
# validate_dns_records_update
# ---------------------------------------------------------------------------

def _v(plain, records, ip="203.0.113.1", domain="example.com"):
    return validate_dns_records_update(_auth(plain), domain, records, ip)


def test_validate_update_failed_auth_propagates_error():
    auth = AuthResult(success=False, error="Invalid token", error_code="token_hash_mismatch")
    assert validate_dns_records_update(auth, "example.com", [{"hostname": "vpn"}], "1.1.1.1") \
        == (False, "Invalid token", "token_hash_mismatch")


def test_validate_update_empty_list_is_valid(make_account, make_realm, make_token):
    _, _, _, plain = _setup(make_account, make_realm, make_token)
    assert _v(plain, []) == (True, None, None)


@pytest.mark.parametrize("permitted,expect", [
    # token may only 'update': update-by-id allowed, create / delete denied
    (("update",), {"update": True, "create": False, "delete": False}),
    # token may only create+delete: update denied
    (("create", "delete"), {"update": False, "create": True, "delete": True}),
])
def test_validate_update_operation_inference(
        permitted, expect, make_account, make_realm, make_token):
    """Operation is inferred from the record (delete > update > create) and
    checked against the permitted operations."""
    account = make_account("opinfer")
    realm = make_realm(account, realm_value="h", operations=permitted)
    _, plain = make_token(realm)
    records = {
        "update": {"hostname": "h", "type": "A", "id": "5"},
        "create": {"hostname": "h", "type": "A"},
        "delete": {"hostname": "h", "type": "A", "id": "5", "deleterecord": True},
    }
    for operation, record in records.items():
        ok, msg, code = _v(plain, [record])
        if expect[operation]:
            assert (ok, msg, code) == (True, None, None), operation
        else:
            assert ok is False and code == "operation_denied", operation
            assert f"No permission to {operation} record h (A)" in msg
    # deleterecord without an id is still a delete
    ok, _, code = _v(plain, [{"hostname": "h", "type": "A", "deleterecord": True}])
    assert ok is expect["delete"]


def test_validate_update_stops_at_first_denied_record(make_account, make_realm, make_token):
    _, _, _, plain = _setup(make_account, make_realm, make_token)
    ok, msg, code = _v(plain, [
        {"hostname": "vpn", "type": "A", "id": "1"},
        {"hostname": "other", "type": "A", "id": "2"},   # outside host realm
        {"hostname": "vpn", "type": "TXT", "id": "3"},   # would be type-denied
    ])
    assert ok is False
    assert code == "hostname_denied"
    assert "other" in msg


def test_validate_update_record_type_denied(make_account, make_realm, make_token):
    _, _, _, plain = _setup(make_account, make_realm, make_token)
    ok, msg, code = _v(plain, [{"hostname": "vpn", "type": "TXT", "id": "1"}])
    assert (ok, code) == (False, "record_type_denied")
    assert "TXT" in msg


def test_validate_update_ip_denied_then_allowed(make_account, make_realm, make_token):
    _, _, _, plain = _setup(make_account, make_realm, make_token,
                            token_kw={"ip_ranges": ["198.51.100.0/24"]})
    rec = [{"hostname": "vpn", "type": "A", "id": "1"}]
    ok, _, code = _v(plain, rec, ip="203.0.113.1")
    assert (ok, code) == (False, "ip_denied")
    ok, _, code = _v(plain, rec, ip="198.51.100.7")
    assert (ok, code) == (True, None)


def test_validate_update_missing_hostname_means_apex(make_account, make_realm, make_token):
    """A record dict with no 'hostname' key targets the apex: denied for a
    single-host realm, allowed for a whole-zone ('subdomain') realm."""
    _, _, _, plain = _setup(make_account, make_realm, make_token)
    ok, _, code = _v(plain, [{"type": "A", "id": "1"}])
    assert (ok, code) == (False, "hostname_denied")

    account = make_account("zoneowner")
    realm = make_realm(account, realm_type="subdomain", realm_value="", domain="zone.test")
    _, plain2 = make_token(realm)
    ok, _, code = _v(plain2, [{"type": "A", "id": "1"}], domain="zone.test")
    assert (ok, code) == (True, None)


# ---------------------------------------------------------------------------
# check_permission matrix: realm_type x hostname x operation x record type
# ---------------------------------------------------------------------------

# realm domain is example.com in every case
SCOPE_CASES = [
    # (realm_type, realm_value, record_name, hostname-in-scope?)
    ("host", "vpn", "vpn", True),
    ("host", "vpn", "VPN.example.com.", True),
    ("host", "vpn", "", False),
    ("host", "vpn", "@", False),
    ("host", "vpn", "other", False),
    ("host", "vpn", "a.vpn", False),
    ("host", "vpn", "evilvpn", False),
    ("subdomain", "iot", "iot", True),
    ("subdomain", "iot", "dev1.iot", True),
    ("subdomain", "iot", "a.b.iot", True),
    ("subdomain", "iot", "vpn", False),
    ("subdomain", "iot", "notiot", False),
    ("subdomain", "iot", "", False),
    ("subdomain_only", "iot", "iot", False),
    ("subdomain_only", "iot", "dev1.iot", True),
    ("subdomain_only", "iot", "a.b.iot", True),
    ("subdomain_only", "iot", "vpn", False),
    ("subdomain_only", "iot", "notiot", False),
]
OPS = ["read", "update", "create", "delete"]
RTYPES = ["A", "AAAA", "TXT", None]


@pytest.mark.parametrize("realm_type,realm_value", [
    ("host", "vpn"), ("subdomain", "iot"), ("subdomain_only", "iot")])
def test_permission_matrix(realm_type, realm_value, make_account, make_realm, make_token):
    # Realm allows read+update on A/AAAA only (factory defaults). One token per
    # realm type (bcrypt is slow); the full hostname x operation x type grid is
    # checked against it and all mismatches reported together.
    account = make_account("matrix")
    realm = make_realm(account, realm_type=realm_type, realm_value=realm_value)
    _, plain = make_token(realm)
    auth = _auth(plain)
    wrong = []
    checked = 0
    for rt, rv, name, host_ok in SCOPE_CASES:
        if (rt, rv) != (realm_type, realm_value):
            continue
        for operation in OPS:
            for rtype in RTYPES:
                res = check_permission(auth, operation, "example.com",
                                       record_type=rtype, record_name=name)
                if not host_ok:
                    want = (False, "hostname_denied")
                elif operation not in ("read", "update"):
                    want = (False, "operation_denied")
                elif rtype not in (None, "A", "AAAA"):
                    want = (False, "record_type_denied")
                else:
                    want = (True, None)
                got = (res.granted, res.error_code)
                checked += 1
                if got != want:
                    wrong.append((name, operation, rtype, got, want))
    assert checked >= 5 * len(OPS) * len(RTYPES)
    assert not wrong, wrong


def test_permission_check_order(make_account, make_realm, make_token):
    """ip -> domain -> hostname -> operation -> record type."""
    _, _, _, plain = _setup(make_account, make_realm, make_token,
                            token_kw={"ip_ranges": ["198.51.100.0/24"]})
    auth = _auth(plain)
    assert check_permission(auth, "delete", "evil.test", "TXT", "other",
                            client_ip="203.0.113.1").error_code == "ip_denied"
    assert check_permission(auth, "delete", "evil.test", "TXT", "other",
                            client_ip="198.51.100.1").error_code == "domain_denied"
    assert check_permission(auth, "delete", "example.com", "TXT", "other",
                            client_ip="198.51.100.1").error_code == "hostname_denied"
    assert check_permission(auth, "delete", "example.com", "TXT", "vpn",
                            client_ip="198.51.100.1").error_code == "operation_denied"
    assert check_permission(auth, "read", "example.com", "TXT", "vpn",
                            client_ip="198.51.100.1").error_code == "record_type_denied"


def test_permission_empty_record_type_string_skips_type_check(
        make_account, make_realm, make_token):
    """record_type='' (falsy) is treated as 'not specified'. Documents current behaviour."""
    _, _, _, plain = _setup(make_account, make_realm, make_token)
    assert check_permission(_auth(plain), "read", "example.com",
                            record_type="", record_name="vpn").granted is True


def test_permission_token_level_scope_replaces_realm_scope(
        make_account, make_realm, make_token):
    _, _, _, plain = _setup(make_account, make_realm, make_token,
                            token_kw={"operations": ["update"], "record_types": ["A"]})
    auth = _auth(plain)
    assert check_permission(auth, "update", "example.com", "A", "vpn").granted
    assert check_permission(auth, "read", "example.com", "A", "vpn").error_code == "operation_denied"
    assert check_permission(auth, "update", "example.com", "AAAA", "vpn").error_code \
        == "record_type_denied"


def test_permission_denied_result_carries_human_reason(make_account, make_realm, make_token):
    _, _, _, plain = _setup(make_account, make_realm, make_token)
    auth = _auth(plain)
    assert check_permission(auth, "delete", "example.com", "A", "vpn").reason \
        == "Operation 'delete' not permitted"
    assert check_permission(auth, "read", "example.com", "MX", "vpn").reason \
        == "Record type 'MX' not permitted"
    assert check_permission(auth, "read", "example.com", "A", "zzz").reason \
        == "Hostname not in authorized scope"
    assert check_permission(auth, "read", "other.test", "A", "vpn").reason \
        == "Domain not in authorized scope"


# ---------------------------------------------------------------------------
# security analytics
# ---------------------------------------------------------------------------

def _add_log(db, *, code, status="denied", severity=None, attack=0, ago_hours=0,
             ip="192.0.2.1"):
    db.session.add(ActivityLog(
        action="api_auth", source_ip=ip, status=status, error_code=code,
        severity=severity, is_attack=attack,
        created_at=datetime.utcnow() - timedelta(hours=ago_hours)))
    db.session.commit()


def test_get_security_stats_counts_windows_and_attacks(db):
    _add_log(db, code="token_hash_mismatch", severity="critical", attack=1)
    _add_log(db, code="token_hash_mismatch", severity="critical", attack=1)
    _add_log(db, code="alias_not_found", severity="medium")
    _add_log(db, code="token_expired", severity="low")
    _add_log(db, code="token_hash_mismatch", severity="critical", attack=1, ago_hours=48)  # outside window
    _add_log(db, code="ip_denied", status="success", severity="critical", attack=1)        # not denied
    _add_log(db, code=None, severity="low")                                                 # no error code

    stats = get_security_stats(hours=24)
    assert stats["window_hours"] == 24
    assert stats["by_error_code"] == {
        "token_hash_mismatch": 2, "alias_not_found": 1, "token_expired": 1}
    # severity grouping counts denied rows with a severity, error code or not
    assert stats["by_severity"] == {"critical": 2, "medium": 1, "low": 2}
    assert stats["total_denied"] == 4
    # attack events: is_attack==1 within window regardless of status
    assert sorted(e["error_code"] for e in stats["attack_events"]) == [
        "ip_denied", "token_hash_mismatch", "token_hash_mismatch"]
    ev = stats["attack_events"][0]
    assert set(ev) == {"id", "error_code", "severity", "source_ip", "account_id", "created_at"}
    datetime.fromisoformat(ev["created_at"])

    wide = get_security_stats(hours=72)
    assert wide["by_error_code"]["token_hash_mismatch"] == 3


def test_get_security_stats_empty(db):
    assert get_security_stats() == {
        "by_error_code": {}, "by_severity": {}, "attack_events": [],
        "total_denied": 0, "window_hours": 24}


def test_get_security_stats_attack_events_capped_at_50_newest_first(db):
    now = datetime.utcnow()
    for i in range(55):
        db.session.add(ActivityLog(
            action="api_auth", source_ip="192.0.2.1", status="denied",
            error_code="ip_denied", is_attack=1,
            created_at=now - timedelta(seconds=i)))
    db.session.commit()
    events = get_security_stats()["attack_events"]
    assert len(events) == 50
    stamps = [e["created_at"] for e in events]
    assert stamps == sorted(stamps, reverse=True)


def test_get_security_timeline_buckets_by_hour(db):
    now = datetime.utcnow().replace(minute=30, second=0, microsecond=0)
    earlier = now - timedelta(hours=3)
    for when, code in [(now, "ip_denied"), (now, "ip_denied"), (now, "token_expired"),
                       (earlier, "ip_denied")]:
        db.session.add(ActivityLog(action="api_auth", source_ip="192.0.2.1",
                                   status="denied", error_code=code, created_at=when))
    # excluded: success, no error code, outside window
    db.session.add(ActivityLog(action="api_call", source_ip="192.0.2.1", status="success",
                               error_code="ip_denied", created_at=now))
    db.session.add(ActivityLog(action="api_auth", source_ip="192.0.2.1", status="denied",
                               error_code=None, created_at=now))
    db.session.add(ActivityLog(action="api_auth", source_ip="192.0.2.1", status="denied",
                               error_code="ip_denied", created_at=now - timedelta(hours=100)))
    db.session.commit()

    assert get_security_timeline(hours=24) == [
        {"timestamp": earlier.strftime("%Y-%m-%d %H:00:00"), "ip_denied": 1},
        {"timestamp": now.strftime("%Y-%m-%d %H:00:00"), "ip_denied": 2, "token_expired": 1},
    ]


def test_get_security_timeline_empty(db):
    assert get_security_timeline() == []
