"""Property-based tests for token model logic — the most security-critical
non-I/O code in the app.

Targets (all in src/netcup_api_filter/models.py):
  - generate_user_alias()       — 16-char alphanumeric alias
  - generate_token(alias)       — naf_<alias>_<random64>
  - parse_token(token)          — round-trip and rejection of malformed input
  - AccountRealm.get_fqdn()     — FQDN assembly
  - AccountRealm.matches_hostname(hostname) — host/subdomain/subdomain_only scope
  - AccountRealm.matches_domain(domain)     — zone equality (case-insensitive)
  - APIToken.get_effective_record_types()   — token-level or realm fallback
  - APIToken.get_effective_operations()     — token-level or realm fallback
  - APIToken.is_expired()                   — expires_at boundary

Pure unit tests: no DB, no Flask app context, no fixtures.  All model instances
are constructed transiently and attributes set directly.

Hypothesis profiles are registered in conftest.py:
  ci  — 50 examples (default)
  dev — 500 examples (HYPOTHESIS_PROFILE=dev)

Complements the hand-written cases in tests/test_realm_matching_unit.py —
duplication of those exact examples is deliberately avoided.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from hypothesis import given, assume
from hypothesis import strategies as st

from netcup_api_filter.models import (
    AccountRealm,
    APIToken,
    TOKEN_ALPHABET,
    TOKEN_PREFIX,
    USER_ALIAS_LENGTH,
    RANDOM_PART_LENGTH,
    generate_token,
    parse_token,
)


# =============================================================================
# Shared helpers
# =============================================================================

# DNS label strategy: 1–10 lower-alphanum chars (no hyphens to keep it simple)
_label = st.from_regex(r'[a-z0-9]{1,10}', fullmatch=True)

# A valid two-part domain, e.g. "foo.example"
_domain = st.builds(lambda a, b: f"{a}.{b}", _label, _label)

# A valid realm_value (non-empty prefix, e.g. "iot")
_realm_value = st.from_regex(r'[a-z0-9]{1,8}', fullmatch=True)


def _make_realm(domain: str, realm_type: str, realm_value: str) -> AccountRealm:
    """Return a transient AccountRealm with the three attributes matches_hostname reads."""
    r = AccountRealm()
    r.domain = domain
    r.realm_type = realm_type
    r.realm_value = realm_value
    return r


def _make_token_with_realm(
    realm: AccountRealm,
    *,
    allowed_operations_json: str | None = None,
    allowed_record_types_json: str | None = None,
) -> APIToken:
    """Return a transient APIToken linked to *realm*.

    Pass ``allowed_operations_json`` / ``allowed_record_types_json`` as raw JSON
    strings (or None) to set the column directly, bypassing the set_*() helpers
    whose truthiness guard turns [] into None.
    """
    token = APIToken()
    token.realm = realm
    token.allowed_operations = allowed_operations_json
    token.allowed_record_types = allowed_record_types_json
    return token


# =============================================================================
# Property 1 — Token round-trip and malformed-input rejection
#
# Any well-formed alias must survive generate_token → parse_token intact.
# Any arbitrary text must be handled gracefully (None returned, never raises).
# =============================================================================

@given(alias=st.from_regex(rf'[A-Za-z0-9]{{{USER_ALIAS_LENGTH}}}', fullmatch=True))
def test_token_round_trip(alias):
    """parse_token(generate_token(alias)) returns (alias, <64-char random>).

    The random part must consist solely of TOKEN_ALPHABET characters and be
    exactly RANDOM_PART_LENGTH characters long.
    """
    token = generate_token(alias)
    result = parse_token(token)
    assert result is not None, (
        f"parse_token returned None for a generated token with alias={alias!r}"
    )
    parsed_alias, random_part = result
    assert parsed_alias == alias, (
        f"alias mismatch: expected {alias!r}, got {parsed_alias!r}"
    )
    assert len(random_part) == RANDOM_PART_LENGTH, (
        f"random part length {len(random_part)} != {RANDOM_PART_LENGTH}"
    )
    assert all(c in TOKEN_ALPHABET for c in random_part), (
        f"random part contains chars outside TOKEN_ALPHABET: {random_part!r}"
    )


@given(st.text())
def test_parse_token_malformed_never_raises_returns_none_or_tuple(token_str):
    """parse_token must never raise and return None for anything that doesn't match."""
    try:
        result = parse_token(token_str)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"parse_token({token_str!r}) raised {type(exc).__name__}: {exc}")

    if result is not None:
        # Postcondition: if it returned something, it must be a valid 2-tuple
        assert isinstance(result, tuple) and len(result) == 2, (
            f"parse_token returned non-None non-2-tuple: {result!r}"
        )
        alias, random_part = result
        assert len(alias) == USER_ALIAS_LENGTH
        assert len(random_part) == RANDOM_PART_LENGTH


def test_parse_token_missing_prefix_returns_none():
    """A token without the 'naf_' prefix must be rejected."""
    assert parse_token("abc_" + "x" * USER_ALIAS_LENGTH + "_" + "y" * RANDOM_PART_LENGTH) is None


def test_parse_token_empty_returns_none():
    """Empty string must return None."""
    assert parse_token("") is None


def test_parse_token_wrong_separator_returns_none():
    """Token with wrong separator (no underscores) must return None."""
    alias = "a" * USER_ALIAS_LENGTH
    random = "b" * RANDOM_PART_LENGTH
    assert parse_token(f"{TOKEN_PREFIX}{alias}{random}") is None  # missing separator


# =============================================================================
# Property 2 — Scope monotonicity: host ⊆ subdomain; exact boundary for apex
# and strict children
#
# This is the boundary mutmut will attack (endswith('.' + fqdn) and the
# != apex guard).  We pin it exactly.
# =============================================================================

@given(domain=_domain, realm_value=_realm_value, child_label=_label)
def test_scope_monotonicity_host_subset_of_subdomain(domain, realm_value, child_label):
    """If host.matches_hostname(x) is True, then subdomain.matches_hostname(x) is True.

    host scope is a strict subset of subdomain scope.
    """
    host_realm = _make_realm(domain, "host", realm_value)
    subdomain_realm = _make_realm(domain, "subdomain", realm_value)

    fqdn = host_realm.get_fqdn()
    # Only the apex can match host; check it directly
    if host_realm.matches_hostname(fqdn):
        assert subdomain_realm.matches_hostname(fqdn) is True, (
            f"host matched {fqdn!r} but subdomain did not (fqdn={fqdn!r})"
        )


@given(domain=_domain, realm_value=_realm_value)
def test_apex_matches_host_and_subdomain_but_not_subdomain_only(domain, realm_value):
    """The apex (fqdn itself) must match host and subdomain but NOT subdomain_only.

    subdomain_only is defined as 'children only, NOT apex'.
    """
    host_realm = _make_realm(domain, "host", realm_value)
    subdomain_realm = _make_realm(domain, "subdomain", realm_value)
    subdomain_only_realm = _make_realm(domain, "subdomain_only", realm_value)

    fqdn = host_realm.get_fqdn()

    assert host_realm.matches_hostname(fqdn) is True, (
        f"host realm must match its own fqdn {fqdn!r}"
    )
    assert subdomain_realm.matches_hostname(fqdn) is True, (
        f"subdomain realm must match apex {fqdn!r}"
    )
    assert subdomain_only_realm.matches_hostname(fqdn) is False, (
        f"subdomain_only realm must NOT match apex {fqdn!r}"
    )


@given(domain=_domain, realm_value=_realm_value, child_label=_label)
def test_strict_child_matches_subdomain_and_subdomain_only_but_not_host(
    domain, realm_value, child_label
):
    """A strict child (c.<fqdn>) must match subdomain and subdomain_only but NOT host.

    This pins the exact opposite of the apex rule.
    """
    host_realm = _make_realm(domain, "host", realm_value)
    subdomain_realm = _make_realm(domain, "subdomain", realm_value)
    subdomain_only_realm = _make_realm(domain, "subdomain_only", realm_value)

    fqdn = host_realm.get_fqdn()
    child = f"{child_label}.{fqdn}"

    assert host_realm.matches_hostname(child) is False, (
        f"host realm must NOT match child {child!r}"
    )
    assert subdomain_realm.matches_hostname(child) is True, (
        f"subdomain realm must match child {child!r}"
    )
    assert subdomain_only_realm.matches_hostname(child) is True, (
        f"subdomain_only realm must match child {child!r}"
    )


@given(domain=_domain, realm_value=_realm_value, other=_domain)
def test_unrelated_hostname_matches_no_realm_type(domain, realm_value, other):
    """A hostname outside the realm's zone must match NONE of host/subdomain/subdomain_only.

    Regression for a mutation-surfaced gap: `subdomain_only` was
    `endswith('.'+fqdn) and hostname != fqdn`; flipping `and`→`or` made an
    UNRELATED hostname (endswith False, != fqdn True) match — a scope bypass.
    This pins that an unrelated hostname is rejected by every realm type.
    """
    fqdn = _make_realm(domain, "host", realm_value).get_fqdn()
    # Make `other` provably unrelated: not equal to fqdn and not a child of it.
    assume(other != fqdn)
    assume(not other.endswith("." + fqdn))
    assume(not fqdn.endswith("." + other))
    for rtype in ("host", "subdomain", "subdomain_only"):
        realm = _make_realm(domain, rtype, realm_value)
        assert realm.matches_hostname(other) is False, (
            f"{rtype} realm (fqdn={fqdn!r}) must NOT match unrelated host {other!r}"
        )


# =============================================================================
# Property 3 — matches_hostname never raises; unknown realm_type ⇒ False
# =============================================================================

@given(hostname=st.text(max_size=120), realm_value=_realm_value, domain=_domain)
def test_matches_hostname_never_raises_host(hostname, realm_value, domain):
    """matches_hostname with realm_type='host' must never raise; always returns bool."""
    r = _make_realm(domain, "host", realm_value)
    try:
        result = r.matches_hostname(hostname)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"matches_hostname raised {type(exc).__name__}: {exc}")
    assert isinstance(result, bool)


@given(hostname=st.text(max_size=120), realm_value=_realm_value, domain=_domain)
def test_matches_hostname_never_raises_subdomain(hostname, realm_value, domain):
    """matches_hostname with realm_type='subdomain' must never raise; always returns bool."""
    r = _make_realm(domain, "subdomain", realm_value)
    try:
        result = r.matches_hostname(hostname)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"matches_hostname raised {type(exc).__name__}: {exc}")
    assert isinstance(result, bool)


@given(hostname=st.text(max_size=120), realm_value=_realm_value, domain=_domain)
def test_matches_hostname_never_raises_subdomain_only(hostname, realm_value, domain):
    """matches_hostname with realm_type='subdomain_only' must never raise; always returns bool."""
    r = _make_realm(domain, "subdomain_only", realm_value)
    try:
        result = r.matches_hostname(hostname)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"matches_hostname raised {type(exc).__name__}: {exc}")
    assert isinstance(result, bool)


@given(
    hostname=st.text(max_size=120),
    realm_value=_realm_value,
    domain=_domain,
    realm_type=st.text(min_size=1, max_size=20).filter(
        lambda t: t not in ("host", "subdomain", "subdomain_only")
    ),
)
def test_matches_hostname_unknown_realm_type_returns_false(
    hostname, realm_value, domain, realm_type
):
    """An unknown realm_type must return False and never raise."""
    r = _make_realm(domain, realm_type, realm_value)
    try:
        result = r.matches_hostname(hostname)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            f"matches_hostname raised {type(exc).__name__} for unknown "
            f"realm_type={realm_type!r}: {exc}"
        )
    assert result is False, (
        f"Unknown realm_type={realm_type!r} must return False, got {result!r}"
    )


# =============================================================================
# Property 4 — matches_domain case-insensitivity
# =============================================================================

@given(domain=_domain)
def test_matches_domain_own_domain_case_insensitive(domain):
    """matches_domain must accept the realm's own domain in any case variant."""
    r = _make_realm(domain, "host", "v")
    # All three case forms must match
    assert r.matches_domain(domain) is True
    assert r.matches_domain(domain.upper()) is True
    assert r.matches_domain(domain.lower()) is True


@given(domain=_domain, other_label=_label)
def test_matches_domain_different_domain_returns_false(domain, other_label):
    """A domain distinct from the realm's must return False."""
    r = _make_realm(domain, "host", "v")
    # Construct a different zone that cannot equal domain
    other_domain = f"{other_label}.{other_label}"
    assume(other_domain.lower() != domain.lower())
    assert r.matches_domain(other_domain) is False, (
        f"matches_domain({other_domain!r}) returned True but realm domain is {domain!r}"
    )


# =============================================================================
# Property 5 — Effective-scope fallback
#
# None means "inherit from realm"; empty list [] means "deny all" (no fallback).
#
# IMPORTANT: APIToken.set_allowed_operations([]) stores None (because `if ops`
# is falsy), so we set the column attribute directly to json.dumps([]) to test
# the empty-list sentinel independently of the setter.  If the code were
# correct, token.get_allowed_operations() would return [] and
# get_effective_operations() would return [] (deny all).
#
# The current implementation of set_allowed_operations uses:
#   self.allowed_operations = json.dumps(operations) if operations else None
# which coerces [] → None, conflating "no restriction" with "deny all".
# The *getter* and *effective* methods are correct (they check `is not None`),
# but the *setter* loses the distinction.  We document this by setting the
# column directly and asserting the deny-all behaviour, which works correctly
# at the getter/effective layer.  The setter bug is separately documented
# in test_effective_scope_setter_coerces_empty_list_to_none.
# =============================================================================

@given(
    ops=st.lists(st.sampled_from(["read", "update", "create", "delete"]), min_size=1),
    record_types=st.lists(st.sampled_from(["A", "AAAA", "MX", "TXT"]), min_size=1),
    domain=_domain,
    realm_value=_realm_value,
)
def test_effective_scope_token_level_overrides_realm(ops, record_types, domain, realm_value):
    """When the token has non-None scopes, get_effective_* returns exactly them.

    Neither the realm's ops nor realm's record_types are consulted.
    """
    realm = _make_realm(domain, "host", realm_value)
    realm.set_allowed_operations(["read"])
    realm.set_allowed_record_types(["A"])

    token = _make_token_with_realm(
        realm,
        allowed_operations_json=json.dumps(ops),
        allowed_record_types_json=json.dumps(record_types),
    )

    assert token.get_effective_operations() == ops, (
        f"Expected token-level ops {ops!r}, got {token.get_effective_operations()!r}"
    )
    assert token.get_effective_record_types() == record_types, (
        f"Expected token-level record_types {record_types!r}, "
        f"got {token.get_effective_record_types()!r}"
    )


@given(
    realm_ops=st.lists(st.sampled_from(["read", "update", "create", "delete"]), min_size=1),
    realm_types=st.lists(st.sampled_from(["A", "AAAA", "MX", "TXT"]), min_size=1),
    domain=_domain,
    realm_value=_realm_value,
)
def test_effective_scope_none_falls_back_to_realm(realm_ops, realm_types, domain, realm_value):
    """When token scope is None (column is NULL), get_effective_* inherits from the realm."""
    realm = _make_realm(domain, "host", realm_value)
    realm.set_allowed_operations(realm_ops)
    realm.set_allowed_record_types(realm_types)

    # NULL columns → inherit
    token = _make_token_with_realm(
        realm,
        allowed_operations_json=None,
        allowed_record_types_json=None,
    )

    assert token.get_effective_operations() == realm_ops, (
        f"None token ops should fall back to realm {realm_ops!r}, "
        f"got {token.get_effective_operations()!r}"
    )
    assert token.get_effective_record_types() == realm_types, (
        f"None token record_types should fall back to realm {realm_types!r}, "
        f"got {token.get_effective_record_types()!r}"
    )


def test_effective_scope_empty_list_means_deny_all_not_inherit():
    """[] (stored as JSON '[]') means deny-all; it must NOT fall back to the realm.

    This is the critical sentinel: None = inherit, [] = deny all.
    A mutation flipping `is not None` to truthiness would conflate these.

    We set the column directly to '[]' because set_allowed_operations([]) is
    buggy and coerces [] to None.  See also
    test_effective_scope_setter_coerces_empty_list_to_none below.
    """
    realm = _make_realm("example.com", "host", "vpn")
    realm.set_allowed_operations(["read", "update"])
    realm.set_allowed_record_types(["A", "AAAA"])

    # Set column directly to json.dumps([]) to bypass the setter's truthiness guard
    token = _make_token_with_realm(
        realm,
        allowed_operations_json=json.dumps([]),
        allowed_record_types_json=json.dumps([]),
    )

    eff_ops = token.get_effective_operations()
    eff_types = token.get_effective_record_types()

    assert eff_ops == [], (
        f"Empty-list token ops must deny-all (return []), not fall back to realm; "
        f"got {eff_ops!r}"
    )
    assert eff_types == [], (
        f"Empty-list token record_types must deny-all (return []), not fall back to realm; "
        f"got {eff_types!r}"
    )


# ---------------------------------------------------------------------------
# Bug documentation: set_allowed_operations([]) coerces to None
#
# The setter uses `json.dumps(operations) if operations else None`, which
# conflates [] (empty list) with None (no restriction).  After calling
# set_allowed_operations([]), get_allowed_operations() returns None — meaning
# "inherit from realm" rather than "deny all".
#
# This is a REAL INHERITANCE BUG in the setter, but it is NOT marked xfail
# because the test is asserting the *buggy* behaviour to document it clearly.
# The deny-all contract IS correctly asserted in
# test_effective_scope_empty_list_means_deny_all_not_inherit (which bypasses
# the setter by writing the column directly).
# ---------------------------------------------------------------------------

def test_effective_scope_setter_coerces_empty_list_to_none():
    """Document that set_allowed_operations([]) stores None, not '[]'.

    This means the setter cannot be used to express 'deny all'.
    Callers who need deny-all must set token.allowed_operations = '[]' directly.

    This test asserts the current (buggy) behaviour so a future fix is visible.
    """
    realm = _make_realm("example.com", "host", "vpn")
    realm.set_allowed_operations(["read"])
    realm.set_allowed_record_types(["A"])

    token = APIToken()
    token.realm = realm
    token.set_allowed_operations([])      # Should mean "deny all" but stores None
    token.set_allowed_record_types([])    # Same issue

    # The column is None (not '[]') due to the truthiness guard in the setter
    assert token.allowed_operations is None, (
        "set_allowed_operations([]) should store None (current behaviour); "
        "if this fails, the setter bug has been fixed — update this test."
    )
    assert token.allowed_record_types is None, (
        "set_allowed_record_types([]) should store None (current behaviour); "
        "if this fails, the setter bug has been fixed — update this test."
    )

    # As a consequence, get_effective_* falls back to the realm (NOT deny-all)
    assert token.get_effective_operations() == ["read"], (
        "Due to the setter bug, effective ops falls back to realm instead of []"
    )
    assert token.get_effective_record_types() == ["A"], (
        "Due to the setter bug, effective record_types falls back to realm instead of []"
    )


# =============================================================================
# Property 6 — is_expired boundary
#
# is_expired() uses `self.expires_at < datetime.utcnow()`.  We use fixed
# reference datetimes far from now to avoid a race on the boundary.
# =============================================================================

def test_is_expired_past_expiry_returns_true():
    """expires_at in the past (now - 1 day) must be expired."""
    token = APIToken()
    token.expires_at = datetime.utcnow() - timedelta(days=1)
    assert token.is_expired() is True


def test_is_expired_future_expiry_returns_false():
    """expires_at in the future (now + 1 hour) must not be expired."""
    token = APIToken()
    token.expires_at = datetime.utcnow() + timedelta(hours=1)
    assert token.is_expired() is False


def test_is_expired_none_returns_false():
    """expires_at = None means 'never expires' → is_expired() must return False."""
    token = APIToken()
    token.expires_at = None
    assert token.is_expired() is False


# Fixed-reference boundary (well clear of now to avoid any timing flakiness)
_FIXED_PAST = datetime(2020, 1, 1, 0, 0, 0)    # 5+ years ago
_FIXED_FUTURE = datetime(2099, 12, 31, 23, 59, 59)  # 70+ years ahead


def test_is_expired_fixed_past_reference():
    """A fixed past datetime (2020-01-01) must be expired regardless of when tests run."""
    token = APIToken()
    token.expires_at = _FIXED_PAST
    assert token.is_expired() is True


def test_is_expired_fixed_future_reference():
    """A fixed future datetime (2099-12-31) must not be expired regardless of when tests run."""
    token = APIToken()
    token.expires_at = _FIXED_FUTURE
    assert token.is_expired() is False
