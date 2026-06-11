"""Unit tests for the DDNS host-scope authorization fix.

These cover the HOSTNAME-scope half of the closed authorization hole: a
host-scoped realm must not be able to write arbitrary in-zone hostnames, and
``token_auth.check_permission`` enforces ``realm.matches_hostname()`` whenever a
``record_name`` is supplied (error_code ``hostname_denied``).

The example.net UI tests cover DOMAIN scope; this file covers HOSTNAME scope and
the FQDN resolution / severity wiring that the fix relies on.

These tests intentionally need only the model + token_auth module -- no DB or
Flask application context. ``AccountRealm`` is a SQLAlchemy declarative model,
but ``matches_hostname()`` / ``get_fqdn()`` are pure-Python and only read plain
instance attributes, so a bare instance is sufficient.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from netcup_api_filter.models import AccountRealm
from netcup_api_filter import token_auth


def _realm(domain: str, realm_type: str, realm_value: str) -> AccountRealm:
    """Build a bare AccountRealm with only the fields matches_hostname() reads.

    No session add / commit -- matches_hostname() and get_fqdn() are pure helpers
    that read self.domain / self.realm_type / self.realm_value only.
    """
    realm = AccountRealm()
    realm.domain = domain
    realm.realm_type = realm_type
    realm.realm_value = realm_value
    return realm


# --- host-scoped realm: the escalation that was possible before the fix --------

def test_host_realm_matches_only_its_exact_hostname():
    realm = _realm("example.com", "host", "dyn")

    # The one host the realm is scoped to.
    assert realm.matches_hostname("dyn.example.com") is True

    # The escalation that USED to be possible: a host-scoped realm writing some
    # other in-zone hostname (e.g. admin.example.com). This MUST be rejected.
    assert realm.matches_hostname("admin.example.com") is False


def test_host_realm_does_not_match_apex_or_children():
    realm = _realm("example.com", "host", "dyn")

    # Apex of the zone is not the scoped host.
    assert realm.matches_hostname("example.com") is False
    # Children of the scoped host are not the scoped host (host == exact match).
    assert realm.matches_hostname("a.dyn.example.com") is False


# --- subdomain (apex + children) realm covering the whole zone ----------------

def test_subdomain_apex_realm_matches_apex_and_children():
    # realm_value='' -> the realm's FQDN is the bare zone (apex).
    realm = _realm("example.com", "subdomain", "")

    # Apex is allowed.
    assert realm.matches_hostname("example.com") is True
    # In-zone child hostnames (e.g. the api-crud demo host) are allowed.
    assert realm.matches_hostname("api-crud-x.example.com") is True


def test_subdomain_apex_realm_does_not_match_other_zone():
    realm = _realm("example.com", "subdomain", "")

    # A different zone entirely (example.net) is out of scope.
    assert realm.matches_hostname("admin.example.net") is False
    assert realm.matches_hostname("example.net") is False


# --- FQDN resolution used by check_permission ---------------------------------

def test_resolve_fqdn_apex_forms():
    # '@' and '' both denote the zone apex.
    assert token_auth._resolve_fqdn("example.com", "@") == "example.com"
    assert token_auth._resolve_fqdn("example.com", "") == "example.com"
    assert token_auth._resolve_fqdn("example.com", None) == "example.com"


def test_resolve_fqdn_relative_name_gets_zone_appended():
    assert token_auth._resolve_fqdn("example.com", "vpn") == "vpn.example.com"


def test_resolve_fqdn_already_qualified_name_is_not_doubled():
    # Callers may pass a full FQDN; the zone must not be appended twice.
    assert token_auth._resolve_fqdn("example.com", "vpn.example.com") == "vpn.example.com"


# --- severity wiring for the new error_code -----------------------------------

def test_hostname_denied_has_a_severity_mapping():
    assert "hostname_denied" in token_auth.ERROR_SEVERITY
