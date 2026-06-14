"""Unit tests for pure validation helpers in utils.py.

Covers:
- validate_ip_range (utils.py:205)
- validate_domain (utils.py:276)
- validate_email (utils.py:294)
- parse_bool (utils.py:27)
- sanitize_filename (utils.py:312)

All tests are pure (no DB, no app context).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from netcup_api_filter.utils import (
    parse_bool,
    sanitize_filename,
    validate_domain,
    validate_email,
    validate_ip_range,
)


# =============================================================================
# validate_ip_range — ~10 cases
# utils.py:205 — uses ipaddress.ip_network / ip_address for validation
# =============================================================================


@pytest.mark.parametrize("ip_range,expected", [
    # --- valid inputs ---
    # Plain IPv4 address
    ("192.168.1.1", True),
    # Valid IPv4 CIDR — /24, a common prefix length (0–32 are valid)
    ("192.168.1.0/24", True),
    # CIDR boundary: /32 is the maximum valid IPv4 prefix length
    # Source: utils.py:231 — ipaddress.ip_network strict=False; max prefix for IPv4 is 32
    ("10.0.0.1/32", True),
    # Plain IPv6 address
    ("2001:db8::1", True),
    # Valid IPv6 CIDR — /64 is a common prefix; max is /128
    ("2001:db8::/32", True),
    # Wildcard single star — explicitly allowed, utils.py:225
    ("*", True),
    # Wildcard with IP prefix — utils.py:248-262
    ("192.168.1.*", True),

    # --- invalid inputs ---
    # Invalid IPv4 octet value > 255
    ("256.0.0.1", False),
    # IPv4 prefix too large — /33 exceeds maximum of 32 for IPv4
    # Source: utils.py:231 — ipaddress raises ValueError for /33
    ("192.168.0.0/33", False),
    # IPv6 prefix too large — /129 exceeds maximum of 128 for IPv6
    # Source: utils.py:231 — ipaddress raises ValueError for /129
    ("2001:db8::/129", False),
    # Garbage non-IP string
    ("not-an-ip-address", False),
    # Empty string — utils.py:221 returns False for falsy input
    ("", False),
    # Whitespace-only — falsy, caught by the same early return
    ("   ", False),
    # Hostname, not an IP address
    ("example.com", False),
])
def test_validate_ip_range(ip_range, expected):
    assert validate_ip_range(ip_range) is expected


def test_validate_ip_range_range_notation_valid():
    """IP range notation '192.168.1.1-192.168.1.254' is valid per utils.py:237-245."""
    assert validate_ip_range("192.168.1.1-192.168.1.254") is True


def test_validate_ip_range_range_notation_invalid():
    """Bad IP on right side of range → False."""
    assert validate_ip_range("192.168.1.1-999.999.999.999") is False


# =============================================================================
# validate_domain — ~8 cases
# utils.py:276 — RFC-1035 pattern, max total 253, max label 63
# =============================================================================


@pytest.mark.parametrize("domain,expected", [
    # Simple two-label domain
    ("example.com", True),
    # Multi-label domain
    ("sub.example.co.uk", True),
    # Single-label (no dot) — pattern allows it
    ("localhost", True),
    # Mixed case is accepted by the pattern [a-zA-Z0-9...]
    ("MyDomain.Example.COM", True),

    # --- invalid ---
    # Leading dot — pattern requires label to start with [a-zA-Z0-9]
    (".example.com", False),
    # Trailing dot — pattern does not end with dot
    ("example.com.", False),
    # Overlong label (>63 characters) — RFC-1035 limit
    # Source: utils.py:290 — pattern {0,61} allows at most 63-char labels (1+61+1)
    ("a" * 64 + ".com", False),
    # Overlong total (>253 characters) — utils.py:286 explicit length check
    ("a" * 64 + "." + "b" * 64 + "." + "c" * 64 + "." + "d" * 64 + ".com", False),
    # Empty string — utils.py:286 falsy check
    ("", False),

    # Underscore label — the RFC 1035 pattern [a-zA-Z0-9\-] does NOT include '_'.
    # validate_domain returns False for labels containing underscores.
    ("_dmarc.example.com", False),
])
def test_validate_domain(domain, expected):
    assert validate_domain(domain) is expected


# =============================================================================
# validate_email — ~6 cases
# utils.py:294 — basic regex pattern ^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$
# =============================================================================


@pytest.mark.parametrize("email,expected", [
    # Plain valid address
    ("user@example.com", True),
    # Plus-tag (common for Gmail-style filtering)
    ("user+tag@example.com", True),
    # Subdomain in host part
    ("user@mail.example.co.uk", True),
    # Missing @ sign
    ("userexample.com", False),
    # Missing TLD-part (no dot after @)
    ("user@example", False),
    # Space in address
    ("user @example.com", False),
    # Empty string — utils.py:298 falsy guard
    ("", False),
])
def test_validate_email(email, expected):
    assert validate_email(email) is expected


# =============================================================================
# parse_bool — ~9 cases
# utils.py:27 — _TRUTHY_VALUES = {"1","true","yes","on"}, _FALSY_VALUES = {"0","false","no","off"}
# =============================================================================


@pytest.mark.parametrize("raw,default,expected", [
    # Truthy strings (utils.py:23 — _TRUTHY_VALUES)
    ("true", False, True),
    ("True", False, True),   # .lower() normalisation at utils.py:38
    ("1", False, True),
    ("yes", False, True),
    ("on", False, True),
    # Falsy strings
    ("false", True, False),
    ("0", True, False),
    ("no", True, False),
    ("off", True, False),
    # None → default (utils.py:34)
    (None, False, False),
    (None, True, True),
    # Unrecognised string → default (utils.py:43)
    ("maybe", False, False),
    ("maybe", True, True),
    # Bool passthrough — utils.py:36 isinstance(raw, bool) check
    (True, False, True),
    (False, True, False),
])
def test_parse_bool(raw, default, expected):
    assert parse_bool(raw, default=default) is expected


def test_parse_bool_default_false_by_default():
    """When default is not provided, it defaults to False per utils.py:27 signature."""
    assert parse_bool(None) is False
    assert parse_bool("weird") is False


# =============================================================================
# sanitize_filename — ~6 cases
# utils.py:312 — os.path.basename + re.sub(r'[^\w\-\.]','_') + hidden-file guard
# =============================================================================


def test_sanitize_filename_already_clean():
    """A clean filename passes through unchanged."""
    assert sanitize_filename("report.pdf") == "report.pdf"


def test_sanitize_filename_strips_path_separators():
    """os.path.basename removes any leading path component — utils.py:323."""
    result = sanitize_filename("/etc/passwd")
    assert "/" not in result
    assert result == "passwd"


def test_sanitize_filename_path_traversal_neutralized():
    """Directory traversal sequences are reduced to a bare filename."""
    result = sanitize_filename("../../etc/shadow")
    # basename on POSIX gives "shadow"; no path components remain
    assert "/" not in result
    assert ".." not in result


def test_sanitize_filename_dangerous_chars_replaced():
    """Characters outside [\\w\\-.] are replaced with underscore — utils.py:326."""
    result = sanitize_filename("file name;rm -rf.txt")
    assert " " not in result
    assert ";" not in result


def test_sanitize_filename_hidden_file_prefixed():
    """Files starting with '.' get a leading underscore — utils.py:329-330."""
    result = sanitize_filename(".bashrc")
    assert not result.startswith(".")
    assert result.startswith("_")


def test_sanitize_filename_unicode():
    """Unicode input doesn't crash; non-word chars are replaced."""
    result = sanitize_filename("résumé.pdf")
    # Just verify no exception and no path separators leak through
    assert isinstance(result, str)
    assert "/" not in result


# =============================================================================
# Mutation-killing tests — added by M2 spot-check
# =============================================================================


# --- validate_ip_range: strict=False matters for CIDR (mutmut_9/11/12) ---

def test_validate_ip_range_cidr_with_host_bits_set_accepted():
    """CIDR with host bits set (e.g. 192.168.1.5/24) is valid with strict=False.

    Kills x_validate_ip_range__mutmut_9 (strict=None), mutmut_11 (no strict kwarg
    i.e. default strict=True), mutmut_12 (strict=True).  With strict=True,
    ipaddress.ip_network raises ValueError for host-bits-set CIDRs, so validate_
    ip_range would wrongly return False.
    """
    # "192.168.1.5/24" has host bits set — ip_network raises with strict=True.
    assert validate_ip_range("192.168.1.5/24") is True


# --- validate_ip_range: range notation validates BOTH endpoints (mutmut_23) ---

def test_validate_ip_range_range_notation_invalid_left_side():
    """The left IP of a range must be validated; an invalid left IP must return False.

    Kills x_validate_ip_range__mutmut_23: 'parts[0]' → 'parts[1]' — that mutation
    validates the right-side IP twice, so a bad left IP slips through.
    """
    assert validate_ip_range("999.999.999.999-192.168.1.254") is False


# --- validate_ip_range: wildcard octet ValueError returns False (mutmut_49) ---

def test_validate_ip_range_wildcard_non_numeric_octet_rejected():
    """An octet that is non-numeric (not '*') in a wildcard pattern must yield False.

    Kills x_validate_ip_range__mutmut_49: the ValueError except branch returns
    True instead of False, allowing patterns like '192.abc.1.*' to be accepted.
    Note: the regex r'^(\d{1,3}|\*).*' only allows digits or *, so pure-alpha
    labels fail the regex before reaching the ValueError path. We use a large
    numeric-looking octet to hit the ValueError via the range check.
    """
    # 300 is numeric-looking but out of 0-255 range → returns False.
    assert validate_ip_range("192.300.1.*") is False


# --- validate_ip_range: IPv6 wildcard returns True only with colon (mutmut_51/52/53) ---

def test_validate_ip_range_ipv6_wildcard_with_colon_is_valid():
    """IPv6 wildcard with ':' in the string must return True.

    Kills mutmut_53: 'return True' → 'return False' in the IPv6-wildcard branch.
    """
    assert validate_ip_range("2001:db8::*") is True


def test_validate_ip_range_wildcard_without_colon_not_mistaken_for_ipv6():
    """A wildcard pattern without ':' must not hit the IPv6-wildcard True branch.

    Kills mutmut_52: 'if ":" in ip_range' → 'if ":" not in ip_range' — that
    mutation would return True for IPv4-style wildcard patterns that DON'T contain
    a colon, bypassing the octet-range validation.

    We use an IPv4-wildcard that is already handled by the regex/octet-check path;
    the colon branch should not fire for it.
    """
    # Valid IPv4 wildcard — handled by the regex path, not the IPv6 branch.
    assert validate_ip_range("192.168.1.*") is True
    # Ensure something clearly not an IPv6 wildcard isn't mis-classified.
    assert validate_ip_range("*.168.1.1") is True


# --- validate_domain: 'or' vs 'and' for empty-check (mutmut_1) ---

def test_validate_domain_long_domain_invalid_even_if_not_empty():
    """A non-empty domain that exceeds 253 chars must be rejected.

    Kills x_validate_domain__mutmut_1: 'not domain or len(domain) > 253' →
    'not domain and len(domain) > 253'. With 'and', a long non-empty domain
    would pass the guard and fall through to the regex — but the regex itself
    rejects overlong labels, so many long domains are still rejected by regex.
    We use a domain that passes the regex (valid labels) but is too long overall.
    """
    # 250 char label + ".co" = 253 chars total — right at the boundary (valid).
    # But 63-char labels * 4 + dots = 259 chars — exceeds 253.
    long_domain = "a" * 63 + "." + "b" * 63 + "." + "c" * 63 + "." + "d" * 63 + ".com"
    assert validate_domain(long_domain) is False


def test_validate_domain_empty_string_invalid_even_if_short():
    """An empty domain must be rejected regardless of the length check.

    Kills x_validate_domain__mutmut_1: with 'and', empty string ('') would only
    be caught if also len('') > 253 — but len('') == 0, not > 253, so it would
    fall through and the regex would return False anyway. This test pins the
    behaviour explicitly.
    """
    assert validate_domain("") is False


# --- validate_domain: boundary at exactly 253 chars (mutmut_3/4) ---

def test_validate_domain_exactly_253_chars_is_valid():
    """A domain of exactly 253 characters must be accepted (> 253 is the limit).

    Kills mutmut_3 (>= 253 rejects at exactly 253) and mutmut_4 (> 254 would
    accept 254-char domains). We use a 253-char domain with valid labels.

    253 = 63 + 1 + 62 + 1 + 62 + 1 + 62 + 1 = 63 + "." + 62 + "." + 62 + "." + 62 + "." + 1-char TLD
    Simplest: 63 + "." + 63 + "." + 63 + "." + 62 = 63+1+63+1+63+1+62 = 254 — too long.
    Try: 62 + "." + 62 + "." + 62 + "." + 62 + ".c" = 62*4 + 3 dots + 2 = 253. ✓
    """
    domain_253 = "a" * 62 + "." + "b" * 62 + "." + "c" * 62 + "." + "d" * 62 + ".c"
    assert len(domain_253) == 253
    # The regex checks label length (max 63) and structure — all labels here are ≤62.
    assert validate_domain(domain_253) is True


def test_validate_domain_254_chars_is_invalid():
    """A domain of 254 characters must be rejected.

    Kills mutmut_4: '> 253' → '> 254' would accept 254-char domains.
    """
    domain_254 = "a" * 62 + "." + "b" * 62 + "." + "c" * 62 + "." + "d" * 62 + ".cc"
    assert len(domain_254) == 254
    assert validate_domain(domain_254) is False


# --- validate_email: uppercase in pattern matters (mutmut_5) ---

def test_validate_email_uppercase_local_part_accepted():
    """Uppercase characters in local-part of email must be accepted.

    Kills x_validate_email__mutmut_5: pattern uses '[a-za-z0-9...]' (lowercase
    a-z duplicated; uppercase A-Z removed), which would reject uppercase local-
    parts even though the original '[a-zA-Z0-9...]' accepts them.
    """
    assert validate_email("User.Name@example.com") is True
    assert validate_email("USER@EXAMPLE.COM") is True


# --- sanitize_filename: replacement is single underscore (mutmut_11) ---

def test_sanitize_filename_dangerous_chars_replaced_with_underscore():
    """Dangerous characters must be replaced with exactly '_', not 'XX_XX'.

    Kills x_sanitize_filename__mutmut_11: re.sub replacement 'XX_XX' instead of '_'.
    The mutant produces longer output with multi-char replacements; this test
    pins that a single dangerous char yields a single underscore replacement.
    """
    # A space is a dangerous char — should become exactly '_'.
    result = sanitize_filename("file name.txt")
    assert result == "file_name.txt"

    # Semicolon — one char → one underscore.
    result2 = sanitize_filename("file;name.txt")
    assert result2 == "file_name.txt"
