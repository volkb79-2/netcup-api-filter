"""Unit tests for token_auth.py — authenticate_token, check_ip_allowed,
check_permission, _resolve_fqdn.

Uses the T02 factories (make_account, make_realm, make_token) from conftest.py,
which require a Flask app context (in-memory SQLite). DB-free cases use bare
instances as in test_realm_scope.py.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from netcup_api_filter import token_auth
from netcup_api_filter.models import (
    AccountRealm,
    APIToken,
    generate_token,
    generate_user_alias,
    hash_token,
)
from netcup_api_filter.token_auth import (
    AuthResult,
    PermissionResult,
    _resolve_fqdn,
    authenticate_token,
    check_ip_allowed,
    check_permission,
    extract_bearer_token,
)


# =============================================================================
# extract_bearer_token — 5 cases, no DB needed
# =============================================================================


def test_extract_bearer_token_none_header():
    assert extract_bearer_token(None) is None


def test_extract_bearer_token_empty_string():
    assert extract_bearer_token("") is None


def test_extract_bearer_token_no_space():
    # Header with no space → not "scheme token" format.
    assert extract_bearer_token("Bearertoken") is None


def test_extract_bearer_token_wrong_scheme():
    assert extract_bearer_token("Basic dXNlcjpwYXNz") is None


def test_extract_bearer_token_valid():
    token = "naf_Ab3xYz9KmNpQrStU_" + "a" * 64
    assert extract_bearer_token(f"Bearer {token}") == token


# =============================================================================
# _resolve_fqdn — 6 cases, no DB needed
# =============================================================================


def test_resolve_fqdn_empty_string_gives_apex():
    assert _resolve_fqdn("example.com", "") == "example.com"


def test_resolve_fqdn_at_sign_gives_apex():
    assert _resolve_fqdn("example.com", "@") == "example.com"


def test_resolve_fqdn_none_gives_apex():
    assert _resolve_fqdn("example.com", None) == "example.com"


def test_resolve_fqdn_simple_prefix_appended():
    assert _resolve_fqdn("example.com", "vpn") == "vpn.example.com"


def test_resolve_fqdn_already_fqdn_not_doubled():
    # Caller passes a full FQDN — must not append zone a second time.
    assert _resolve_fqdn("example.com", "vpn.example.com") == "vpn.example.com"


def test_resolve_fqdn_trailing_dot_stripped_and_case_lowered():
    # Trailing dots and mixed case must be normalised.
    assert _resolve_fqdn("Example.COM.", "VPN") == "vpn.example.com"


# =============================================================================
# authenticate_token — invalid-format group (no DB needed)
# =============================================================================


def test_auth_token_no_prefix_invalid_format():
    result = authenticate_token("Ab3xYz9KmNpQrStU_" + "a" * 64)
    assert result.success is False
    assert result.error_code == "invalid_format"


def test_auth_token_too_short_invalid_format():
    result = authenticate_token("naf_shorttoken")
    assert result.success is False
    assert result.error_code == "invalid_format"


def test_auth_token_empty_string_invalid_format():
    result = authenticate_token("")
    assert result.success is False
    assert result.error_code == "invalid_format"


def test_auth_token_none_like_invalid_format():
    # parse_token returns None for None; passing it as str triggers invalid_format.
    result = authenticate_token("None")
    assert result.success is False
    assert result.error_code == "invalid_format"


# =============================================================================
# authenticate_token — DB-backed cases
# =============================================================================


def test_auth_token_alias_not_found(app, make_account, make_realm, make_token):
    """Valid format, but user_alias doesn't exist in DB."""
    # Generate a fresh alias that's definitely not in the DB.
    fake_alias = generate_user_alias()
    fake_random = "a" * 64
    fake_token = f"naf_{fake_alias}_{fake_random}"
    result = authenticate_token(fake_token)
    assert result.success is False
    assert result.error_code == "alias_not_found"
    assert result.severity == "medium"
    assert result.should_notify_user is False


def test_auth_token_account_disabled(app, make_account, make_realm, make_token):
    """Account exists but is_active=0 — must return account_disabled before token lookup."""
    account = make_account("disabled_user", is_active=0)
    realm = make_realm(account)
    _token, plain = make_token(realm)

    result = authenticate_token(plain)
    assert result.success is False
    assert result.error_code == "account_disabled"
    assert result.account is account
    assert result.severity == "medium"


def test_auth_token_prefix_not_found(app, make_account, make_realm, make_token):
    """Alias exists, prefix doesn't match any stored token."""
    account = make_account("probe_target")
    realm = make_realm(account)
    # Create one real token so the account has tokens, but we'll use a different random part.
    _token, _plain = make_token(realm, name="real-token")

    # Build a token with the real alias but a different random part.
    fake_random = "z" * 64  # prefix will be "zzzzzzzz"
    fake_token = f"naf_{account.user_alias}_{fake_random}"
    result = authenticate_token(fake_token)
    assert result.success is False
    assert result.error_code == "token_prefix_not_found"
    assert result.account is account
    assert result.severity == "high"
    assert result.should_notify_user is True


def test_auth_token_hash_mismatch(app, make_account, make_realm, make_token):
    """Alias+prefix found, but the full token is wrong — brute-force indicator."""
    account = make_account("brute_target")
    realm = make_realm(account)
    stored_token, plain = make_token(realm, name="real-token")

    # Swap in a different random part that shares the same prefix.
    # The prefix is the first 8 chars of the random part.
    prefix_start = len("naf_") + len(account.user_alias) + 1  # skip "naf_<alias>_"
    prefix = plain[prefix_start:prefix_start + 8]
    # Construct a token whose prefix matches but whose full value does not.
    wrong_suffix = "W" * 56
    wrong_token = f"naf_{account.user_alias}_{prefix}{wrong_suffix}"

    result = authenticate_token(wrong_token)
    assert result.success is False
    assert result.error_code == "token_hash_mismatch"
    assert result.severity == "critical"
    assert result.should_notify_user is True
    # Attribution fields must be set even on failure.
    assert result.account is account
    assert result.token is stored_token


def test_auth_token_revoked(app, make_account, make_realm, make_token):
    """Token is_active=0 — revoked."""
    account = make_account("revoked_user")
    realm = make_realm(account)
    _token, plain = make_token(realm, name="revoked-tok", is_active=0)

    result = authenticate_token(plain)
    assert result.success is False
    assert result.error_code == "token_revoked"
    assert result.severity == "high"
    assert result.should_notify_user is True


def test_auth_token_expired(app, make_account, make_realm, make_token):
    """Token expires_at in the past."""
    account = make_account("expired_user")
    realm = make_realm(account)
    past = datetime.utcnow() - timedelta(days=1)
    _token, plain = make_token(realm, name="expired-tok", expires_at=past)

    result = authenticate_token(plain)
    assert result.success is False
    assert result.error_code == "token_expired"
    assert result.severity == "low"
    assert result.should_notify_user is False


def test_auth_token_realm_pending(app, make_account, make_realm, make_token):
    """Realm status is 'pending' — not yet approved."""
    account = make_account("pending_user")
    realm = make_realm(account, status="pending")
    _token, plain = make_token(realm, name="pending-tok")

    result = authenticate_token(plain)
    assert result.success is False
    assert result.error_code == "realm_not_approved"
    assert result.severity == "low"


def test_auth_token_realm_rejected(app, make_account, make_realm, make_token):
    """Realm status is 'rejected'."""
    account = make_account("rejected_user")
    realm = make_realm(account, status="rejected")
    _token, plain = make_token(realm, name="rejected-tok")

    result = authenticate_token(plain)
    assert result.success is False
    assert result.error_code == "realm_not_approved"


def test_auth_token_success(app, make_account, make_realm, make_token):
    """Happy path — all checks pass."""
    account = make_account("happy_user")
    realm = make_realm(account)
    stored_token, plain = make_token(realm, name="ok-token")

    result = authenticate_token(plain)
    assert result.success is True
    assert result.error_code is None
    assert result.account is account
    assert result.realm is realm
    assert result.token is stored_token


# =============================================================================
# check_ip_allowed — 8 parametrized cases
# =============================================================================


def _bare_token_with_ranges(ranges: list[str] | None) -> APIToken:
    """Create a bare APIToken instance without DB for IP-only tests."""
    tok = APIToken()
    tok.token_name = "test"
    tok.allowed_ip_ranges = None
    if ranges is not None:
        tok.set_allowed_ip_ranges(ranges)
    return tok


@pytest.mark.parametrize("ranges,client_ip,expected", [
    # No restriction → always allowed.
    (None, "1.2.3.4", True),
    ([], "1.2.3.4", True),
    # Exact IPv4 match.
    (["203.0.113.5"], "203.0.113.5", True),
    # Exact IPv4 mismatch.
    (["203.0.113.5"], "203.0.113.6", False),
    # IPv4 CIDR — client inside range.
    (["203.0.113.0/24"], "203.0.113.42", True),
    # IPv4 CIDR — client outside range.
    (["203.0.113.0/24"], "203.0.114.1", False),
    # IPv6 exact match.
    (["2001:db8::1"], "2001:db8::1", True),
    # IPv6 CIDR.
    (["2001:db8::/32"], "2001:db8::ffff", True),
])
def test_check_ip_allowed_parametrized(ranges, client_ip, expected):
    tok = _bare_token_with_ranges(ranges)
    assert check_ip_allowed(tok, client_ip) is expected


def test_check_ip_allowed_invalid_client_ip():
    """Invalid client IP string → denied (False), not an exception."""
    tok = _bare_token_with_ranges(["203.0.113.0/24"])
    assert check_ip_allowed(tok, "not-an-ip") is False


def test_check_ip_allowed_invalid_whitelist_entry_skipped():
    """A malformed whitelist entry is skipped; a valid entry still matches."""
    tok = _bare_token_with_ranges(["bad-entry!!!", "203.0.113.5"])
    # The valid entry should still allow the matching IP.
    assert check_ip_allowed(tok, "203.0.113.5") is True


def test_check_ip_allowed_only_bad_whitelist_entry_denies():
    """If whitelist contains only a bad entry, no match → denied."""
    tok = _bare_token_with_ranges(["bad-entry!!!"])
    assert check_ip_allowed(tok, "203.0.113.5") is False


# =============================================================================
# check_permission — uses DB fixtures + bare AuthResult construction
# =============================================================================


def _failed_auth(error_code: str = "token_expired") -> AuthResult:
    return AuthResult(
        success=False,
        error="Token has expired",
        error_code=error_code,
        severity="low",
    )


def test_check_permission_propagates_auth_failure():
    """check_permission on a failed auth returns the auth error_code."""
    auth = _failed_auth("token_expired")
    result = check_permission(auth, "read", "example.com")
    assert result.granted is False
    assert result.error_code == "token_expired"


def test_check_permission_ip_denied(app, make_account, make_realm, make_token):
    """IP not in whitelist → ip_denied."""
    account = make_account("ip_test_user")
    realm = make_realm(account)
    _tok, plain = make_token(realm, ip_ranges=["10.0.0.1"])
    auth = authenticate_token(plain)
    assert auth.success is True

    result = check_permission(auth, "read", "example.com", client_ip="1.2.3.4")
    assert result.granted is False
    assert result.error_code == "ip_denied"


def test_check_permission_domain_denied(app, make_account, make_realm, make_token):
    """Domain doesn't match realm zone → domain_denied."""
    account = make_account("domain_test_user")
    realm = make_realm(account, domain="example.com")
    _tok, plain = make_token(realm)
    auth = authenticate_token(plain)
    assert auth.success is True

    result = check_permission(auth, "read", "other.org")
    assert result.granted is False
    assert result.error_code == "domain_denied"


# --- hostname-scope cases (parametrized) ---
#
# Realm semantics (AGENTS.md):
#   host          — exact FQDN only (realm_value.domain)
#   subdomain     — realm's FQDN apex + all children
#   subdomain_only — children only, NOT the realm's apex
#
# All cases use domain="example.com".
# Realm realm_value sets the FQDN: "" → example.com, "vpn" → vpn.example.com.
# record_name is passed to check_permission; it is resolved via _resolve_fqdn
# before the hostname check.

@pytest.mark.parametrize("realm_type,realm_value,record_name,should_grant", [
    # host: allows only the exact host (vpn.example.com).
    ("host", "vpn", "vpn", True),
    ("host", "vpn", "other", False),
    # host: zone apex (example.com) != realm FQDN (vpn.example.com) → denied.
    ("host", "vpn", "@", False),

    # subdomain with realm_value="vpn": apex=vpn.example.com, children=*.vpn.example.com.
    # record_name="vpn" resolves to vpn.example.com (the apex) → allowed.
    ("subdomain", "vpn", "vpn", True),
    # child of vpn.example.com is allowed.
    ("subdomain", "vpn", "child.vpn", True),
    # zone apex example.com is NOT vpn.example.com and not a child → denied.
    ("subdomain", "vpn", "@", False),

    # subdomain with realm_value="": apex=example.com.
    # record_name="@" resolves to example.com (the zone apex = realm apex) → allowed.
    ("subdomain", "", "@", True),
    # a child of example.com is allowed by subdomain.
    ("subdomain", "", "vpn", True),

    # subdomain_only with realm_value="vpn": children of vpn.example.com only.
    # "child.vpn" → child.vpn.example.com → allowed.
    ("subdomain_only", "vpn", "child.vpn", True),
    # "vpn" → vpn.example.com (the realm apex itself) → denied for subdomain_only.
    ("subdomain_only", "vpn", "vpn", False),
])
def test_check_permission_hostname_scope(
    app, make_account, make_realm, make_token,
    realm_type, realm_value, record_name, should_grant
):
    # Build a unique username from the parameter values to avoid DB collisions.
    safe_name = f"{realm_type}_{realm_value or 'apex'}_{record_name.replace('@','at')}"
    account = make_account(f"scope_{safe_name}_user")
    realm = make_realm(
        account,
        domain="example.com",
        realm_type=realm_type,
        realm_value=realm_value,
        operations=("read", "update"),
        record_types=("A",),
    )
    _tok, plain = make_token(realm)
    auth = authenticate_token(plain)
    assert auth.success is True

    result = check_permission(
        auth, "read", "example.com", record_type="A", record_name=record_name
    )
    if should_grant:
        assert result.granted is True, (
            f"Expected granted=True for {realm_type}/{realm_value!r} + record_name={record_name!r}, "
            f"got: {result}"
        )
    else:
        assert result.granted is False
        assert result.error_code == "hostname_denied"


def test_check_permission_operation_denied(app, make_account, make_realm, make_token):
    """Operation not in realm/token allowed set → operation_denied."""
    account = make_account("op_denied_user")
    realm = make_realm(account, operations=("read",))
    _tok, plain = make_token(realm)
    auth = authenticate_token(plain)
    assert auth.success is True

    result = check_permission(auth, "delete", "example.com", record_name="vpn")
    assert result.granted is False
    assert result.error_code == "operation_denied"


def test_check_permission_record_type_denied(app, make_account, make_realm, make_token):
    """Record type not allowed → record_type_denied."""
    account = make_account("rt_denied_user")
    realm = make_realm(account, record_types=("A",))
    _tok, plain = make_token(realm)
    auth = authenticate_token(plain)
    assert auth.success is True

    result = check_permission(
        auth, "read", "example.com", record_type="MX", record_name="vpn"
    )
    assert result.granted is False
    assert result.error_code == "record_type_denied"


def test_check_permission_token_scope_narrower_than_realm(
    app, make_account, make_realm, make_token
):
    """Token-level scope overrides realm scope (token wins when stricter)."""
    account = make_account("narrow_token_user")
    # Realm allows read+update+delete; token restricts to read only.
    realm = make_realm(account, operations=("read", "update", "delete"), record_types=("A", "AAAA", "TXT"))
    _tok, plain = make_token(realm, operations=("read",), record_types=("A",))
    auth = authenticate_token(plain)
    assert auth.success is True

    # Read A record — allowed by token.
    ok = check_permission(auth, "read", "example.com", record_type="A", record_name="vpn")
    assert ok.granted is True

    # Update not allowed by token even though realm allows it.
    denied = check_permission(auth, "update", "example.com", record_type="A", record_name="vpn")
    assert denied.granted is False
    assert denied.error_code == "operation_denied"

    # TXT not allowed by token even though realm allows it.
    denied2 = check_permission(auth, "read", "example.com", record_type="TXT", record_name="vpn")
    assert denied2.granted is False
    assert denied2.error_code == "record_type_denied"


def test_check_permission_token_scope_unset_uses_realm(
    app, make_account, make_realm, make_token
):
    """Token with no scope override inherits realm scope."""
    account = make_account("inherit_scope_user")
    realm = make_realm(account, operations=("read", "update"), record_types=("A", "AAAA"))
    # make_token with operations=None → no token-level override.
    _tok, plain = make_token(realm, operations=None, record_types=None)
    auth = authenticate_token(plain)
    assert auth.success is True

    ok = check_permission(auth, "update", "example.com", record_type="AAAA", record_name="vpn")
    assert ok.granted is True


def test_check_permission_zone_read_no_record_name(app, make_account, make_realm, make_token):
    """Zone-level read (record_name=None) skips hostname check."""
    account = make_account("zone_read_user")
    # host-scoped realm; without record_name the hostname check is skipped.
    realm = make_realm(account, realm_type="host", realm_value="vpn", operations=("read",))
    _tok, plain = make_token(realm)
    auth = authenticate_token(plain)
    assert auth.success is True

    result = check_permission(auth, "read", "example.com", record_name=None)
    assert result.granted is True


def test_check_permission_success(app, make_account, make_realm, make_token):
    """Full happy path — all checks pass."""
    account = make_account("perm_ok_user")
    realm = make_realm(account, realm_type="host", realm_value="vpn",
                       operations=("read", "update"), record_types=("A",))
    _tok, plain = make_token(realm)
    auth = authenticate_token(plain)
    assert auth.success is True

    result = check_permission(
        auth, "update", "example.com", record_type="A", record_name="vpn"
    )
    assert result.granted is True
    assert result.error_code is None
