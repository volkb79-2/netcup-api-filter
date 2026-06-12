"""Unit tests for DDNS parsing helpers in ddns_protocols.py.

Covers:
  - parse_hostname (~8 cases)
  - validate_hostname_format (~5 cases)
  - validate_ip_address (~6 cases)
  - should_auto_detect_ip (~6 cases)
  - get_client_ip (~4 cases, requires Flask request context)

No DB is needed: parse_hostname uses a pure heuristic (last two labels = domain),
not managed-domain roots. All DB/app-context fixtures are therefore omitted unless
the implementation changes.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from netcup_api_filter.api.ddns_protocols import (
    get_auto_ip_keywords,
    get_client_ip,
    parse_hostname,
    should_auto_detect_ip,
    validate_hostname_format,
    validate_ip_address,
)


# =============================================================================
# parse_hostname — 8 cases
# =============================================================================
# parse_hostname uses a simple heuristic: the last two dot-separated labels
# are always the domain; everything before that is the record name.
# It does NOT consult managed domain roots, so no DB/app fixture is required.


def test_parse_hostname_simple_subdomain():
    """device.example.com → domain=example.com, record=device"""
    domain, record = parse_hostname("device.example.com")
    assert domain == "example.com"
    assert record == "device"


def test_parse_hostname_multi_label_record():
    """a.b.example.com → domain=example.com, record=a.b (heuristic: last two = domain)"""
    domain, record = parse_hostname("a.b.example.com")
    assert domain == "example.com"
    assert record == "a.b"


def test_parse_hostname_apex():
    """example.com (no subdomain) → domain=example.com, record=@ (apex sentinel)"""
    domain, record = parse_hostname("example.com")
    assert domain == "example.com"
    assert record == "@"


def test_parse_hostname_uppercase_normalized():
    """Uppercase input is normalised to lowercase before splitting."""
    domain, record = parse_hostname("DEVICE.EXAMPLE.COM")
    assert domain == "example.com"
    assert record == "device"


def test_parse_hostname_trailing_dot():
    """Trailing dot creates an empty last label; last-two-parts heuristic produces
    a 'com.' pseudo-domain. This is a known limitation of the simple heuristic —
    validate_hostname_format rejects trailing-dot hostnames before parse_hostname
    is called in production, so this edge case never reaches the DNS update path.
    We document the actual return value rather than guessing.
    """
    domain, record = parse_hostname("example.com.")
    # The parts list is ['example', 'com', ''] → last two are ['com', ''] → 'com.'
    assert domain == "com."
    assert record == "example"


def test_parse_hostname_single_label_rejected():
    """A label without any dot cannot form a valid hostname; expect (None, None)."""
    domain, record = parse_hostname("device")
    assert domain is None
    assert record is None


def test_parse_hostname_empty_string_rejected():
    domain, record = parse_hostname("")
    assert domain is None
    assert record is None


def test_parse_hostname_none_rejected():
    domain, record = parse_hostname(None)
    assert domain is None
    assert record is None


# =============================================================================
# validate_hostname_format — 5 cases
# =============================================================================


def test_validate_hostname_format_valid_fqdn():
    assert validate_hostname_format("device.example.com") is True


def test_validate_hostname_format_invalid_underscore():
    """Underscores are not valid DNS label characters."""
    assert validate_hostname_format("host_1.example.com") is False


def test_validate_hostname_format_overlong_label():
    """DNS labels are limited to 63 characters."""
    long_label = "a" * 64
    assert validate_hostname_format(f"{long_label}.example.com") is False


def test_validate_hostname_format_leading_hyphen():
    """Labels must begin with an alphanumeric character."""
    assert validate_hostname_format("-host.example.com") is False


def test_validate_hostname_format_empty():
    assert validate_hostname_format("") is False


# =============================================================================
# validate_ip_address — 6 cases
# =============================================================================
# Returns (is_valid: bool, is_ipv6: bool, normalized_ip: str | None)


def test_validate_ip_address_valid_v4():
    is_valid, is_ipv6, normalized = validate_ip_address("192.0.2.1")
    assert is_valid is True
    assert is_ipv6 is False
    assert normalized == "192.0.2.1"


def test_validate_ip_address_valid_v6():
    is_valid, is_ipv6, normalized = validate_ip_address("2001:db8::1")
    assert is_valid is True
    assert is_ipv6 is True
    assert normalized == "2001:db8::1"


def test_validate_ip_address_v4_mapped_v6():
    """::ffff:192.0.2.1 is a valid IPv6 address (v4-mapped) and is classified as IPv6."""
    is_valid, is_ipv6, normalized = validate_ip_address("::ffff:192.0.2.1")
    assert is_valid is True
    # ipaddress.ip_address parses this as an IPv6Address
    assert is_ipv6 is True
    assert normalized is not None


def test_validate_ip_address_octet_overflow():
    """256 is out of range for an IPv4 octet."""
    is_valid, is_ipv6, normalized = validate_ip_address("256.0.0.1")
    assert is_valid is False
    assert is_ipv6 is False
    assert normalized is None


def test_validate_ip_address_garbage():
    is_valid, is_ipv6, normalized = validate_ip_address("not-an-ip")
    assert is_valid is False
    assert is_ipv6 is False
    assert normalized is None


def test_validate_ip_address_empty_string():
    is_valid, is_ipv6, normalized = validate_ip_address("")
    assert is_valid is False
    assert is_ipv6 is False
    assert normalized is None


# =============================================================================
# should_auto_detect_ip — 6 cases
# =============================================================================


def test_should_auto_detect_ip_none():
    """None (parameter not provided) → auto-detect."""
    assert should_auto_detect_ip(None) is True


def test_should_auto_detect_ip_empty_string():
    """Empty string → auto-detect."""
    assert should_auto_detect_ip("") is True


def test_should_auto_detect_ip_default_keywords():
    """Each default keyword from get_auto_ip_keywords() triggers auto-detect."""
    for keyword in get_auto_ip_keywords():
        assert should_auto_detect_ip(keyword) is True, f"keyword {keyword!r} should trigger auto-detect"


def test_should_auto_detect_ip_case_insensitive():
    """Keywords are matched case-insensitively."""
    assert should_auto_detect_ip("AUTO") is True
    assert should_auto_detect_ip("Public") is True
    assert should_auto_detect_ip("DETECT") is True


def test_should_auto_detect_ip_explicit_ip():
    """A valid IP address value must NOT trigger auto-detect."""
    assert should_auto_detect_ip("203.0.113.42") is False


def test_should_auto_detect_ip_custom_env_keyword(monkeypatch):
    """Custom DDNS_AUTO_IP_KEYWORDS env var replaces the default keyword set."""
    monkeypatch.setenv("DDNS_AUTO_IP_KEYWORDS", "myip,refresh,dyn")
    # Custom keywords trigger auto-detect
    assert should_auto_detect_ip("myip") is True
    assert should_auto_detect_ip("refresh") is True
    assert should_auto_detect_ip("dyn") is True
    # Default keywords no longer do (they were replaced)
    assert should_auto_detect_ip("auto") is False
    assert should_auto_detect_ip("public") is False


# =============================================================================
# get_client_ip — 4 cases using Flask test request context
#
# Trust contract:
#   get_client_ip() reads X-Forwarded-For and returns the FIRST (leftmost) IP in
#   the comma-separated list. In the standard proxy chain
#       X-Forwarded-For: <client>, <proxy1>, <proxy2>
#   the leftmost IP is the original client as appended by the first trusted proxy.
#   This means the function trusts the entire X-Forwarded-For header as written,
#   including values that a client can forge when there is no hardened reverse
#   proxy stripping/overwriting the header. Deployments behind an untrusted network
#   must ensure the outermost proxy always overwrites (not appends) this header.
# =============================================================================


@pytest.fixture
def app(monkeypatch, tmp_path):
    """Minimal Flask app for request-context tests.

    Mirrors the conftest.py 'app' fixture environment setup so SECRET_KEY and
    DB path are always set. No DB schema or seed data is required for these
    request-context-only tests.
    """
    from netcup_api_filter.app import create_app
    from netcup_api_filter.database import db as _db

    monkeypatch.setenv("SECRET_KEY", "test_secret_key_for_testing_only")
    monkeypatch.setenv("NETCUP_FILTER_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("NETCUP_FILTER_APP_ROOT", raising=False)
    monkeypatch.delenv("SEED_DEMO_ACCOUNTS", raising=False)
    application = create_app()
    application.config["TESTING"] = True
    with application.app_context():
        yield application
        _db.session.remove()
        _db.drop_all()


def test_get_client_ip_no_xff_header(app, monkeypatch):
    """Without X-Forwarded-For, the WSGI remote_addr is returned."""
    with app.test_request_context("/", environ_base={"REMOTE_ADDR": "192.168.1.1"}):
        ip = get_client_ip()
    assert ip == "192.168.1.1"


def test_get_client_ip_single_xff(app):
    """A single X-Forwarded-For value is returned as-is (stripped of whitespace)."""
    with app.test_request_context(
        "/",
        headers={"X-Forwarded-For": "  203.0.113.5  "},
        environ_base={"REMOTE_ADDR": "10.0.0.1"},
    ):
        ip = get_client_ip()
    assert ip == "203.0.113.5"


def test_get_client_ip_multi_hop_xff(app):
    """X-Forwarded-For: client, proxy1, proxy2 — the FIRST (leftmost) element is
    returned. This is the original client IP as recorded by the first trusted proxy.

    Trust contract: the implementation unconditionally trusts element [0] of the
    comma-split list. Spoofing is possible when a client can inject arbitrary
    X-Forwarded-For values before they reach the application.
    """
    with app.test_request_context(
        "/",
        headers={"X-Forwarded-For": "203.0.113.1, 10.0.0.1, 10.0.0.2"},
        environ_base={"REMOTE_ADDR": "10.0.0.2"},
    ):
        ip = get_client_ip()
    # The FIRST element (index 0) is trusted — the original client IP.
    assert ip == "203.0.113.1"  # NOT 10.0.0.1 (proxy1) or 10.0.0.2 (outermost proxy)


def test_get_client_ip_malformed_xff_returned_raw(app):
    """A malformed (non-IP) X-Forwarded-For value is returned as the raw first token.
    The function does not validate IP format — it delegates validation to
    validate_ip_address() in the calling code.
    """
    with app.test_request_context(
        "/",
        headers={"X-Forwarded-For": "not-an-ip"},
        environ_base={"REMOTE_ADDR": "10.0.0.1"},
    ):
        ip = get_client_ip()
    assert ip == "not-an-ip"
