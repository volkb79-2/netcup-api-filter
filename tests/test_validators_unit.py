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
