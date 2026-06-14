"""Property-based tests for DDNS hostname parsing/validation helpers.

Target functions (all in src/netcup_api_filter/api/ddns_protocols.py):
  - validate_hostname_format(hostname) -> bool
  - parse_hostname(hostname) -> (domain, record_name) | (None, None)
  - should_auto_detect_ip(myip) -> bool
  - validate_ip_address(ip_str) -> (is_valid: bool, is_ipv6: bool, normalized: str | None)

Pure unit tests: no Flask app context, no DB, no fixtures.  Import functions
directly.  Hypothesis profiles are registered in conftest.py (ci: 50 examples,
dev: 500 examples); no per-test max_examples unless otherwise noted.

Complements the ~29 hand-written cases in tests/test_ddns_parsing_unit.py by
exploring the full string space rather than developer-chosen examples.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from hypothesis import given, assume
from hypothesis import strategies as st
from hypothesis.strategies import ip_addresses

from netcup_api_filter.api.ddns_protocols import (
    validate_hostname_format,
    parse_hostname,
    should_auto_detect_ip,
    validate_ip_address,
    get_auto_ip_keywords,
)


# =============================================================================
# Shared strategies
# =============================================================================

# A single valid DNS label: starts and ends with alnum, interior may contain
# hyphens; total length 1–63 characters.
_label = st.from_regex(r'[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?', fullmatch=True)

# A syntactically valid hostname: 2–5 labels joined by dots.
_hostname = st.lists(_label, min_size=2, max_size=5).map('.'.join)


# =============================================================================
# Property 1 — Never raises / type contract
# =============================================================================

@given(st.text(max_size=300))
def test_validate_hostname_format_never_raises(s):
    """validate_hostname_format must always return bool, never raise."""
    result = validate_hostname_format(s)
    assert isinstance(result, bool)


@given(st.text(max_size=300))
def test_parse_hostname_never_raises_returns_symmetric_pair(s):
    """parse_hostname must always return a 2-tuple and never raise.

    Both elements must be None or both must be non-None — a mixed partial
    result (domain set but record None, or vice-versa) would indicate a
    logic error in the parser.
    """
    domain, record = parse_hostname(s)
    # Symmetry: exactly one of the two None-states must hold
    assert (domain is None) == (record is None), (
        f"parse_hostname({s!r}) returned mixed partial result: "
        f"domain={domain!r}, record={record!r}"
    )


@given(st.text(max_size=300))
def test_should_auto_detect_ip_never_raises(s):
    """should_auto_detect_ip must always return bool, never raise."""
    result = should_auto_detect_ip(s)
    assert isinstance(result, bool)


@given(st.text(max_size=300))
def test_validate_ip_address_never_raises_returns_documented_shape(s):
    """validate_ip_address must never raise and must return a 3-tuple.

    Contract:
      - element 0: bool  (is_valid)
      - element 1: bool  (is_ipv6)
      - element 2: str | None  (normalized IP, only non-None when is_valid)

    When is_valid is False the other two fields must be their sentinel values
    (False, None) so callers need not guard against unexpected truthy states.
    """
    result = validate_ip_address(s)
    assert isinstance(result, tuple) and len(result) == 3, (
        f"validate_ip_address({s!r}) did not return a 3-tuple: {result!r}"
    )
    is_valid, is_ipv6, normalized = result
    assert isinstance(is_valid, bool)
    assert isinstance(is_ipv6, bool)
    if not is_valid:
        assert is_ipv6 is False, (
            f"is_ipv6 must be False when is_valid is False; got {is_ipv6!r}"
        )
        assert normalized is None, (
            f"normalized must be None when is_valid is False; got {normalized!r}"
        )
    else:
        assert isinstance(normalized, str), (
            f"normalized must be str when is_valid is True; got {normalized!r}"
        )


# =============================================================================
# Property 1b — Specific known-dangerous edge probes (regression guards)
#
# These are not generated; they document the *defined* behaviour for inputs
# that crash naive parsers.  The assertion is just "returns bool / 2-tuple,
# does not raise" — we do NOT prescribe True/False so that future intentional
# behaviour changes only require updating the comment, not the test.
# =============================================================================

_EDGE_INPUTS = [
    "\x00",            # NUL byte
    "\x00foo.bar",     # NUL-prefixed
    "a" * 300,         # overlong (single label, no dot)
    "a" * 63 + "." + "b",  # 63-char label (valid per DNS)
    "a" * 64 + "." + "b",  # 64-char label (exceeds DNS limit)
    ".foo",            # leading dot → empty first label
    "foo.",            # trailing dot → empty last label
    "foo..bar",        # consecutive dots → empty mid label
    "-x.y",           # leading hyphen in first label
    "x-.y",           # trailing hyphen in first label
    "1.2",            # all-numeric two-label (valid chars, but no alpha)
    "localhost",       # single label, no dot
    # 300-char hostname with dots so parse_hostname actually sees labels
    ("a" * 60 + ".") * 4 + "b",
]


@pytest.mark.parametrize("s", _EDGE_INPUTS, ids=[repr(x)[:40] for x in _EDGE_INPUTS])
def test_validate_hostname_format_edge_probe_never_raises(s):
    """validate_hostname_format must not raise on any of these edge inputs.

    Current behaviour (documented, not asserted):
      NUL byte / NUL-prefixed: False (non-alnum start)
      overlong single label:   False (no dot)
      63-char label:           True  (valid)
      64-char label:           False (exceeds 63-char limit)
      leading dot:             False (empty first label)
      trailing dot:            False (empty last label)
      consecutive dots:        False (empty mid label)
      leading hyphen:          False (non-alnum start)
      trailing hyphen:         False (non-alnum end)
      1.2 (all-numeric):       True  (digits are alnum)
      localhost (no dot):      False (no dot)
      300-char dotted:         True  (all labels ≤63 chars, valid chars)
    """
    result = validate_hostname_format(s)
    assert isinstance(result, bool)


@pytest.mark.parametrize("s", _EDGE_INPUTS, ids=[repr(x)[:40] for x in _EDGE_INPUTS])
def test_parse_hostname_edge_probe_never_raises(s):
    """parse_hostname must not raise on any of these edge inputs."""
    domain, record = parse_hostname(s)
    assert (domain is None) == (record is None)


# =============================================================================
# Property 2 — Accepted-set structural invariant
#
# For any hostname that validate_hostname_format accepts, the structural DNS
# rules must hold on every label.
# =============================================================================

@given(_hostname)
def test_accepted_hostname_structural_invariants(hostname):
    """Every hostname accepted by validate_hostname_format satisfies DNS label rules.

    Guards: skip (not assert-fail) if the generated hostname is not accepted —
    we are only verifying the accepted set.
    """
    if not validate_hostname_format(hostname):
        return  # not in the accepted set; nothing to check

    labels = hostname.split('.')
    for label in labels:
        assert label, f"empty label must not be accepted: {hostname!r}"
        assert len(label) <= 63, (
            f"label {label!r} exceeds DNS 63-char limit in {hostname!r}"
        )
        assert label[0].isalnum() and label[-1].isalnum(), (
            f"label {label!r} must start and end with alnum in {hostname!r}"
        )
        assert all(c.isalnum() or c == '-' for c in label), (
            f"label {label!r} contains invalid char(s) in {hostname!r}"
        )


@given(st.text(max_size=300))
def test_arbitrary_accepted_hostname_structural_invariants(hostname):
    """Same structural check, but driven by arbitrary text rather than the _label strategy.

    This catches edge cases where validate_hostname_format uses .strip() before
    splitting, which could cause accepted-set divergence with other callers.
    """
    if not validate_hostname_format(hostname):
        return

    # validate_hostname_format strips; replicate that to get the canonical form
    canonical = hostname.strip()
    labels = canonical.split('.')
    for label in labels:
        assert label, f"empty label must not be accepted: {hostname!r}"
        assert len(label) <= 63, (
            f"label {label!r} exceeds DNS 63-char limit in {hostname!r}"
        )
        assert label[0].isalnum() and label[-1].isalnum(), (
            f"label {label!r} must start and end with alnum in {hostname!r}"
        )
        assert all(c.isalnum() or c == '-' for c in label), (
            f"label {label!r} contains invalid char(s) in {hostname!r}"
        )


# =============================================================================
# Property 3 — validate→parse consistency (key cross-function invariant)
#
# Anything validate_hostname_format accepts, parse_hostname must return a
# non-None (domain, record_name) pair where domain contains a dot.
#
# Security rationale: process_ddns_update() calls validate_hostname_format first
# and then parse_hostname.  If validation accepts a hostname that the parser
# then rejects (returns None, None), the request is logged as "invalid_hostname"
# AFTER passing format validation — a confusing split-brain state that could
# mask real problems.
# =============================================================================

@given(_hostname)
def test_validate_parse_consistency_valid_generated(hostname):
    """Every hostname validate_hostname_format accepts parses to a non-None pair.

    Uses the _label/_hostname strategy so we're testing primarily valid DNS
    hostnames; see test_validate_parse_consistency_arbitrary for the broader check.
    """
    if not validate_hostname_format(hostname):
        return  # guard: only testing the accepted set

    domain, record = parse_hostname(hostname)
    assert domain is not None, (
        f"parse_hostname({hostname!r}) returned None domain after validation passed"
    )
    assert record is not None, (
        f"parse_hostname({hostname!r}) returned None record after validation passed"
    )
    assert '.' in domain, (
        f"parse_hostname({hostname!r}) returned domain without dot: {domain!r}"
    )


@given(st.text(max_size=300))
def test_validate_parse_consistency_arbitrary(hostname):
    """Same validate→parse consistency invariant, driven by arbitrary text.

    This is the most important property: any arbitrary string accepted by
    validate_hostname_format must be parseable by parse_hostname.  Failures
    here reveal a gap between the two functions that could affect production
    request handling.
    """
    if not validate_hostname_format(hostname):
        return  # only testing the accepted set

    domain, record = parse_hostname(hostname)
    assert domain is not None, (
        f"parse_hostname({hostname!r}) returned None domain after validation passed"
    )
    assert record is not None, (
        f"parse_hostname({hostname!r}) returned None record after validation passed"
    )
    assert '.' in domain, (
        f"parse_hostname({hostname!r}) returned domain without dot: {domain!r}"
    )


# =============================================================================
# Property 4 — Idempotence / case normalisation
# =============================================================================

@given(_hostname)
def test_parse_hostname_case_invariant(hostname):
    """parse_hostname normalises to lowercase, so parse(h) == parse(h.upper()).

    Both parse_hostname calls must agree: same domain and same record_name.
    """
    lower_result = parse_hostname(hostname)
    upper_result = parse_hostname(hostname.upper())
    assert lower_result == upper_result, (
        f"parse_hostname({hostname!r}) != parse_hostname({hostname.upper()!r}): "
        f"{lower_result!r} vs {upper_result!r}"
    )


@given(_hostname)
def test_parse_hostname_case_invariant_mixedcase(hostname):
    """Swapcase variant — exercises mixed-case rather than pure upper."""
    swapped = hostname.swapcase()
    assert parse_hostname(hostname) == parse_hostname(swapped), (
        f"case swapcase broke parse_hostname for {hostname!r}"
    )


def test_should_auto_detect_ip_all_keywords_case_insensitive():
    """Every configured keyword (and its upper/title variants) triggers auto-detect.

    Uses the live keyword list from get_auto_ip_keywords() so custom env vars are
    respected.  This is a deterministic test (not @given) because the keyword set
    is finite and known at call time.
    """
    for kw in get_auto_ip_keywords():
        assert should_auto_detect_ip(kw) is True, (
            f"keyword {kw!r} must trigger auto-detect"
        )
        assert should_auto_detect_ip(kw.upper()) is True, (
            f"UPPER keyword {kw.upper()!r} must trigger auto-detect"
        )
        assert should_auto_detect_ip(kw.title()) is True, (
            f"Title keyword {kw.title()!r} must trigger auto-detect"
        )


@given(st.text(min_size=1, max_size=100).filter(
    lambda s: s.strip().lower() not in get_auto_ip_keywords() and s != ''
))
def test_should_auto_detect_ip_non_keyword_non_empty_returns_false(s):
    """Any non-empty string that is not a keyword must NOT trigger auto-detect."""
    # Exclude empty / None cases handled by the unit tests
    assume(s.strip() != '')
    assume(s.strip().lower() not in get_auto_ip_keywords())
    result = should_auto_detect_ip(s)
    assert result is False, (
        f"should_auto_detect_ip({s!r}) returned True for a non-keyword string"
    )


# =============================================================================
# Property 5 — validate_ip_address: valid addresses accepted, shape invariants
# =============================================================================

@given(ip_addresses(v=4).map(str))
def test_validate_ip_address_accepts_valid_ipv4(ip):
    """Any IPv4 address produced by Python's ipaddress module must be accepted."""
    is_valid, is_ipv6, normalized = validate_ip_address(ip)
    assert is_valid is True, f"valid IPv4 {ip!r} was rejected"
    assert is_ipv6 is False, f"IPv4 {ip!r} must not be flagged as IPv6"
    assert normalized is not None, f"normalized must be set for valid IP {ip!r}"


@given(ip_addresses(v=6).map(str))
def test_validate_ip_address_accepts_valid_ipv6(ip):
    """Any IPv6 address produced by Python's ipaddress module must be accepted."""
    is_valid, is_ipv6, normalized = validate_ip_address(ip)
    assert is_valid is True, f"valid IPv6 {ip!r} was rejected"
    assert is_ipv6 is True, f"IPv6 {ip!r} must be flagged as is_ipv6"
    assert normalized is not None, f"normalized must be set for valid IP {ip!r}"


@given(ip_addresses(v=4).map(str))
def test_validate_ip_address_normalized_ipv4_roundtrips(ip):
    """The normalized form of a valid IPv4 address must itself be accepted."""
    is_valid, _is_ipv6, normalized = validate_ip_address(ip)
    assert is_valid  # precondition
    # Round-trip: the normalized string must also pass validation
    is_valid2, is_ipv6_2, normalized2 = validate_ip_address(normalized)
    assert is_valid2, f"normalized IPv4 {normalized!r} failed re-validation"
    assert is_ipv6_2 is False
    assert normalized2 == normalized, (
        f"IPv4 normalization is not idempotent: {normalized!r} -> {normalized2!r}"
    )


@given(ip_addresses(v=6).map(str))
def test_validate_ip_address_normalized_ipv6_roundtrips(ip):
    """The normalized form of a valid IPv6 address must itself be accepted."""
    is_valid, _is_ipv6, normalized = validate_ip_address(ip)
    assert is_valid  # precondition
    is_valid2, is_ipv6_2, normalized2 = validate_ip_address(normalized)
    assert is_valid2, f"normalized IPv6 {normalized!r} failed re-validation"
    assert is_ipv6_2 is True
    assert normalized2 == normalized, (
        f"IPv6 normalization is not idempotent: {normalized!r} -> {normalized2!r}"
    )
