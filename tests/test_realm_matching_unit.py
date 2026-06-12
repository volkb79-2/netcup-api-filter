"""Unit tests for AccountRealm.matches_domain and AccountRealm.get_fqdn.

DB-free style: bare AccountRealm instances (no session, no DB), exactly like
test_realm_scope.py. The methods under test read only plain instance attributes.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from netcup_api_filter.models import AccountRealm


def _realm(domain: str, realm_type: str = "host", realm_value: str = "vpn") -> AccountRealm:
    """Build a bare AccountRealm with only the attributes matches_domain / get_fqdn read."""
    r = AccountRealm()
    r.domain = domain
    r.realm_type = realm_type
    r.realm_value = realm_value
    return r


# =============================================================================
# matches_domain — 5 cases
# =============================================================================


def test_matches_domain_exact():
    assert _realm("example.com").matches_domain("example.com") is True


def test_matches_domain_case_insensitive():
    # The DNS zone comparison must be case-insensitive on both sides.
    assert _realm("Example.COM").matches_domain("example.com") is True
    assert _realm("example.com").matches_domain("EXAMPLE.COM") is True


def test_matches_domain_different_zone():
    assert _realm("example.com").matches_domain("example.net") is False


def test_matches_domain_sub_zone_does_not_match_parent():
    # A realm for sub.example.com must NOT match example.com queries.
    r = _realm("sub.example.com")
    assert r.matches_domain("example.com") is False


def test_matches_domain_parent_does_not_match_sub_zone():
    # A realm for example.com must NOT match sub.example.com queries.
    r = _realm("example.com")
    assert r.matches_domain("sub.example.com") is False


# =============================================================================
# get_fqdn — 3 cases
# =============================================================================


def test_get_fqdn_host_realm():
    # realm_value="vpn" → "vpn.example.com"
    assert _realm("example.com", "host", "vpn").get_fqdn() == "vpn.example.com"


def test_get_fqdn_subdomain_realm_with_value():
    # realm_value="iot" → "iot.example.com"
    assert _realm("example.com", "subdomain", "iot").get_fqdn() == "iot.example.com"


def test_get_fqdn_apex_realm_empty_value():
    # realm_value="" → bare zone (apex)
    assert _realm("example.com", "subdomain", "").get_fqdn() == "example.com"
