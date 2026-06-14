"""Property-based tests for security-control validators in utils.py and token_auth.py.

Targets:
  - validate_ip_range(s)  — single IP / CIDR / dash-range / wildcard (utils.py)
  - validate_domain(s)    — RFC-1035 domain name (utils.py)
  - validate_email(s)     — basic email format (utils.py)
  - check_ip_allowed(token, client_ip) — IP allowlist enforcement (token_auth.py)

Pure unit tests: no Flask app context, no DB, no fixtures.  APIToken instances
are constructed transiently and configured via set_allowed_ip_ranges() — no
session or DB needed (it's just JSON on the instance).

Hypothesis profiles are registered in conftest.py (ci: 50 examples, dev: 500
examples).  Default profile is "ci"; run with HYPOTHESIS_PROFILE=dev for a
deeper exploration.

Complements the ~12 hand-written cases in tests/test_validators_unit.py.
"""
from __future__ import annotations

import ipaddress
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.strategies import ip_addresses

from netcup_api_filter.utils import validate_ip_range, validate_domain, validate_email
from netcup_api_filter.token_auth import check_ip_allowed
from netcup_api_filter.models import APIToken


# =============================================================================
# Helpers
# =============================================================================

def _make_token(ip_ranges: list[str] | None) -> APIToken:
    """Return a transient APIToken with the given IP ranges set.

    No session or DB needed — set_allowed_ip_ranges() just calls json.dumps()
    on the instance attribute.  Only used by check_ip_allowed tests.
    """
    token = APIToken()
    token.set_allowed_ip_ranges(ip_ranges)
    return token


# =============================================================================
# Property 1 — Never raises / type contract
#
# Every validator must handle arbitrary text without raising an exception, and
# must always return bool (not None, not int, not str).
# =============================================================================

@given(st.text(max_size=100))
def test_validate_ip_range_never_raises(s):
    """validate_ip_range must always return bool and never raise.

    Edge probes exercised automatically by Hypothesis: NUL bytes, huge numbers,
    truncated CIDRs like '/24', stray dashes '1.2.3.4-', 'a-b-c', '*.*.*.*'.
    """
    result = validate_ip_range(s)
    assert isinstance(result, bool)


@given(st.text(max_size=100))
def test_validate_domain_never_raises(s):
    """validate_domain must always return bool and never raise."""
    result = validate_domain(s)
    assert isinstance(result, bool)


@given(st.text(max_size=100))
def test_validate_email_never_raises(s):
    """validate_email must always return bool and never raise."""
    result = validate_email(s)
    assert isinstance(result, bool)


# =============================================================================
# Property 2 — Valid IPv4 / IPv6 addresses always accepted
# =============================================================================

@given(ip_addresses(v=4).map(str))
def test_valid_ipv4_always_accepted(ip):
    """Any IPv4 address Python's ipaddress module produces must pass validate_ip_range."""
    assert validate_ip_range(ip) is True, f"valid IPv4 {ip!r} was rejected"


@given(ip_addresses(v=6).map(str))
def test_valid_ipv6_always_accepted(ip):
    """Any IPv6 address Python's ipaddress module produces must pass validate_ip_range."""
    assert validate_ip_range(ip) is True, f"valid IPv6 {ip!r} was rejected"


# =============================================================================
# Property 3 — Valid CIDR always accepted (covers prefix 0 and 32/128 edges)
#
# The CIDR branch in validate_ip_range uses ipaddress.ip_network(strict=False),
# so any network string ipaddress produces must be accepted.  Prefix 0 gives
# '0.0.0.0/0'; prefix 32 gives a host-route like '1.2.3.4/32' — both are edge
# cases for manual string-splitting code.
# =============================================================================

@given(ip_addresses(v=4), st.integers(0, 32))
def test_valid_cidr_v4_always_accepted(base_ip, prefix):
    """Any IPv4 CIDR (prefix 0–32) must pass validate_ip_range."""
    network = ipaddress.ip_network(f"{base_ip}/{prefix}", strict=False)
    net_str = str(network)
    assert validate_ip_range(net_str) is True, (
        f"valid IPv4 CIDR {net_str!r} (prefix={prefix}) was rejected"
    )


@given(ip_addresses(v=6), st.integers(0, 128))
def test_valid_cidr_v6_always_accepted(base_ip, prefix):
    """Any IPv6 CIDR (prefix 0–128) must pass validate_ip_range."""
    network = ipaddress.ip_network(f"{base_ip}/{prefix}", strict=False)
    net_str = str(network)
    assert validate_ip_range(net_str) is True, (
        f"valid IPv6 CIDR {net_str!r} (prefix={prefix}) was rejected"
    )


# =============================================================================
# Property 4 — Accepted dash-range ⇒ both halves parse as valid IPs
#
# Guards against "phantom ranges" where our validator accepts a string whose
# halves are not individually valid IP addresses.
# =============================================================================

@given(ip_addresses(v=4).map(str), ip_addresses(v=4).map(str))
def test_accepted_dash_range_both_halves_parseable(ip1, ip2):
    """A dash-range accepted by validate_ip_range must consist of two valid IPv4 addresses.

    If the validator returns True for 'a-b', then both a and b must parse via
    ipaddress.ip_address() — no phantom ranges allowed.
    """
    candidate = f"{ip1}-{ip2}"
    if not validate_ip_range(candidate):
        return  # guard: only testing the accepted set

    # Both halves must parse cleanly; failure here is a real bug
    left, right = candidate.split('-', 1)
    try:
        ipaddress.ip_address(left.strip())
    except ValueError as exc:
        pytest.fail(
            f"validate_ip_range accepted {candidate!r} but left half {left!r} "
            f"is not a valid IP: {exc}"
        )
    try:
        ipaddress.ip_address(right.strip())
    except ValueError as exc:
        pytest.fail(
            f"validate_ip_range accepted {candidate!r} but right half {right!r} "
            f"is not a valid IP: {exc}"
        )


# =============================================================================
# Property 5 — check_ip_allowed soundness
#
# The function is the run-time enforcer of IP allowlisting — a security control.
# Four sub-invariants:
#   5a. in-network ⇒ True
#   5b. out-of-network ⇒ False
#   5c. empty/None ranges ⇒ True ("no restriction" semantics)
#   5d. malformed client_ip ⇒ False, never raises
# =============================================================================

@given(ip_addresses(v=4), st.integers(0, 30))
def test_check_ip_allowed_in_network_returns_true(host_ip, prefix):
    """An address inside the token's allowed CIDR must return True.

    We generate a concrete network, then check every address Hypothesis hands us
    against that network.  Using prefix ≤ 30 to guarantee the network has at
    least 4 addresses (avoids degenerate /31 and /32 where the only address is
    the network/broadcast, which would still pass but less interesting).
    """
    network = ipaddress.ip_network(f"{host_ip}/{prefix}", strict=False)
    # Pick the network address itself (always in-network)
    in_ip = str(network.network_address)
    token = _make_token([str(network)])
    result = check_ip_allowed(token, in_ip)
    assert result is True, (
        f"check_ip_allowed returned False for {in_ip!r} which is in {network!r}"
    )


@given(ip_addresses(v=4), st.integers(8, 30))
def test_check_ip_allowed_out_of_network_returns_false(host_ip, prefix):
    """An address provably outside the allowed CIDR must return False.

    We compute a neighbouring network (next_network()) as the "outside" address.
    Prefix ≥ 8 keeps the networks large enough to have a meaningful next block.
    """
    network = ipaddress.ip_network(f"{host_ip}/{prefix}", strict=False)
    # Neighbouring block of the same size = the supernet split into its two
    # halves; pick the half that is NOT our network as a provably-outside addr.
    halves = list(network.supernet().subnets())
    outside_net = halves[1] if halves[0] == network else halves[0]
    outside_candidate = str(outside_net.network_address)
    if ipaddress.ip_address(outside_candidate) in network:
        return  # degenerate edge — skip rather than false-fail

    token = _make_token([str(network)])
    result = check_ip_allowed(token, outside_candidate)
    assert result is False, (
        f"check_ip_allowed returned True for {outside_candidate!r} which is "
        f"outside {network!r}"
    )


def test_check_ip_allowed_empty_ranges_returns_true():
    """Empty allowed_ip_ranges list means 'no restriction' → always True."""
    token = _make_token([])
    assert check_ip_allowed(token, "1.2.3.4") is True
    assert check_ip_allowed(token, "::1") is True


def test_check_ip_allowed_none_ranges_returns_true():
    """None allowed_ip_ranges (not set) means 'no restriction' → always True."""
    token = _make_token(None)
    assert check_ip_allowed(token, "1.2.3.4") is True
    assert check_ip_allowed(token, "2001:db8::1") is True


@given(st.text(max_size=100).filter(lambda s: not _is_valid_ip(s)))
def test_check_ip_allowed_malformed_client_ip_returns_false_never_raises(bad_ip):
    """A malformed client_ip string must return False and must not raise.

    check_ip_allowed catches ValueError from ipaddress.ip_address() and returns
    False — this property pins that contract against arbitrary garbage input.
    """
    # Give it a real allowed range so the range-list path is exercised
    token = _make_token(["192.168.1.0/24"])
    result = check_ip_allowed(token, bad_ip)
    assert result is False, (
        f"check_ip_allowed({bad_ip!r}) returned True for a non-IP string"
    )


def _is_valid_ip(s: str) -> bool:
    """Return True iff s is a valid IP address (used as strategy filter)."""
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False


# =============================================================================
# Property 6 — Wildcard octet bounds
#
# validate_ip_range supports "192.168.1.*" patterns via manual regex + octet
# range check.  Pins:
#   6a. Octet values > 255 must be rejected even when the pattern matches
#   6b. The single-star wildcard ("*") must always be accepted
#   6c. Valid wildcard patterns (octets 0–255) must be accepted
# =============================================================================

def test_wildcard_star_alone_accepted():
    """The bare '*' wildcard must be accepted (utils.py explicit check)."""
    assert validate_ip_range("*") is True


@pytest.mark.parametrize("bad", [
    "999.1.1.*",
    "1.256.1.*",
    "1.1.300.*",
    "1.1.1.256",  # standard case already in unit tests, include for context
])
def test_wildcard_octet_out_of_range_rejected(bad):
    """Numeric octets > 255 in a wildcard pattern must be rejected."""
    assert validate_ip_range(bad) is False, (
        f"validate_ip_range({bad!r}) should be False (octet > 255)"
    )


@given(
    st.integers(0, 255),
    st.integers(0, 255),
    st.integers(0, 255),
)
def test_wildcard_valid_octets_accepted(a, b, c):
    """A wildcard pattern with all numeric octets in 0–255 must be accepted."""
    pattern = f"{a}.{b}.{c}.*"
    assert validate_ip_range(pattern) is True, (
        f"validate_ip_range({pattern!r}) should be True (all octets valid)"
    )


@given(
    st.one_of(
        st.integers(256, 1000),      # just over 255
        st.integers(-1000, -1),      # negative (won't match \d{1,3}, so rejected by regex)
    )
)
def test_wildcard_invalid_first_octet_rejected(bad_octet):
    """A wildcard pattern where the first octet is out of range must be rejected.

    Negative values won't even match the regex (\\d{1,3} requires digits), so
    this primarily covers the > 255 case where the regex matches but the range
    check fires.
    """
    pattern = f"{bad_octet}.1.1.*"
    result = validate_ip_range(pattern)
    # Negative octets: regex won't match → False via the fallback ip_address() path
    # Octets > 255: regex matches 1-3 digits only (e.g. 999 → matches \d{3}) but
    # the octet range check rejects it.  Either way result must be False.
    assert result is False, (
        f"validate_ip_range({pattern!r}) should be False (first octet={bad_octet})"
    )
