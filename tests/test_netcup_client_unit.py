"""Unit tests for netcup_client.py helper functions.

Covers (pure functions, no network/DB required):
  - extract_dns_records (~5 cases)
  - mutation_failed (~5 cases)
  - mutation_message (~3 cases)

Envelope shapes are verified against the real shapes produced by
ui_tests/mock_netcup_api.py (infoDnsRecords and updateDnsRecords handlers).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from netcup_api_filter.netcup_client import (
    extract_dns_records,
    mutation_failed,
    mutation_message,
)


# =============================================================================
# extract_dns_records — 5 cases
#
# Accepts either:
#   (a) a plain list — returned as-is (NetcupClient.info_dns_records path)
#   (b) a Netcup CCP envelope dict — {"responsedata": {"dnsrecords": [...]}}
#       (mock API / legacy path)
# Any other type raises TypeError.
# =============================================================================

# Minimal record shape matching the mock API (mock_netcup_api.py lines 219-265)
SAMPLE_RECORD = {
    "id": "1",
    "hostname": "@",
    "type": "A",
    "priority": "",
    "destination": "192.0.2.1",
    "deleterecord": False,
    "state": "yes",
}


def test_extract_dns_records_plain_list():
    """A plain list is returned unchanged."""
    records = [SAMPLE_RECORD]
    result = extract_dns_records(records)
    assert result is records


def test_extract_dns_records_netcup_envelope():
    """Well-formed Netcup CCP envelope → inner dnsrecords list extracted."""
    envelope = {
        "serverrequestid": "abc123",
        "status": "success",
        "statuscode": 2000,
        "responsedata": {
            "dnsrecords": [SAMPLE_RECORD],
        },
    }
    result = extract_dns_records(envelope)
    assert result == [SAMPLE_RECORD]


def test_extract_dns_records_missing_responsedata():
    """Dict without 'responsedata' key → empty list (no KeyError)."""
    result = extract_dns_records({"status": "success"})
    assert result == []


def test_extract_dns_records_missing_dnsrecords_key():
    """Dict with 'responsedata' but no 'dnsrecords' → empty list."""
    result = extract_dns_records({"responsedata": {"other_key": "value"}})
    assert result == []


def test_extract_dns_records_non_dict_non_list_raises():
    """Any non-dict, non-list input must raise TypeError (fail loudly, not silently)."""
    with pytest.raises(TypeError, match="Unexpected Netcup response type"):
        extract_dns_records("some string")


def test_extract_dns_records_empty_list():
    """An explicit empty dnsrecords list is returned as an empty list."""
    envelope = {"responsedata": {"dnsrecords": []}}
    result = extract_dns_records(envelope)
    assert result == []


# =============================================================================
# mutation_failed — 5 cases
#
# Returns True only when the result is a dict AND has a truthy 'status' that
# is not 'success'. None/missing-status/non-dict → treated as success (False).
# Matches NetcupClient.update_dns_records() which returns {'status':'success'}.
# =============================================================================


def test_mutation_failed_success_envelope():
    """Standard success envelope → False (not failed)."""
    assert mutation_failed({"status": "success", "statuscode": 2000}) is False


def test_mutation_failed_explicit_error_status():
    """Envelope with a non-success status string → True (failed)."""
    assert mutation_failed({"status": "error", "message": "Invalid session"}) is True


def test_mutation_failed_dict_without_status():
    """Dict missing the 'status' key → treated as success (False)."""
    assert mutation_failed({"responsedata": {}}) is False


def test_mutation_failed_none_input():
    """None result → treated as success (False), not raised."""
    assert mutation_failed(None) is False


def test_mutation_failed_string_input():
    """Non-dict input → treated as success (False)."""
    assert mutation_failed("error") is False


# =============================================================================
# mutation_message — 3 cases
# =============================================================================


def test_mutation_message_present():
    """'message' key present in dict → its value is returned."""
    result = mutation_message({"status": "error", "message": "Domain not found"}, "default msg")
    assert result == "Domain not found"


def test_mutation_message_absent():
    """Dict without 'message' key → default is returned."""
    result = mutation_message({"status": "error"}, "fallback")
    assert result == "fallback"


def test_mutation_message_non_dict_input():
    """Non-dict input (list, None, int) → default is returned."""
    assert mutation_message(None, "fallback") == "fallback"
    assert mutation_message(["error"], "fallback") == "fallback"
    assert mutation_message(42, "fallback") == "fallback"
