"""Edge-path tests for recovery_codes.py that the main unit file does not reach.

Covers: corrupt stored JSON in get_remaining_code_count, store failure
(rollback + False), regenerate failure (None), verify with corrupt JSON, and
normalisation / round-trip properties of hash_recovery_code.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hypothesis import given
from hypothesis import strategies as st

import netcup_api_filter.recovery_codes as rc
from netcup_api_filter.recovery_codes import (
    generate_recovery_codes,
    get_remaining_code_count,
    hash_recovery_code,
    regenerate_recovery_codes,
    store_recovery_codes,
    verify_recovery_code,
)


def test_remaining_count_zero_for_corrupt_json(make_account):
    acct = make_account("rc_corrupt")
    acct.recovery_codes = "{not json"
    assert get_remaining_code_count(acct) == 0


def test_remaining_count_zero_when_unset(make_account):
    assert get_remaining_code_count(make_account("rc_none")) == 0


def test_verify_rejects_corrupt_json_and_keeps_state(make_account):
    acct = make_account("rc_verify_corrupt")
    acct.recovery_codes = "[oops"
    assert verify_recovery_code(acct, "ABCD-2345") is False
    assert acct.recovery_codes == "[oops"


def test_verify_with_no_codes_stored_is_false(make_account):
    assert verify_recovery_code(make_account("rc_empty"), "ABCD-2345") is False


def test_store_failure_returns_false_and_rolls_back(make_account, db, monkeypatch):
    acct = make_account("rc_store_fail")
    rolled_back = []

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(db.session, "commit", boom)
    monkeypatch.setattr(db.session, "rollback", lambda: rolled_back.append(True))
    assert store_recovery_codes(acct, ["ABCD-2345"]) is False
    assert rolled_back == [True]


def test_regenerate_returns_none_when_store_fails(make_account, monkeypatch):
    acct = make_account("rc_regen_fail")
    monkeypatch.setattr(rc, "store_recovery_codes", lambda a, c: False)
    assert regenerate_recovery_codes(acct) is None


def test_last_code_clears_storage_and_timestamp(make_account):
    acct = make_account("rc_last")
    codes = generate_recovery_codes()[:1]
    assert store_recovery_codes(acct, codes)
    assert acct.recovery_codes_generated_at is not None
    assert verify_recovery_code(acct, codes[0]) is True
    assert acct.recovery_codes is None
    assert acct.recovery_codes_generated_at is None
    # consumed code cannot be replayed
    assert verify_recovery_code(acct, codes[0]) is False


def test_stored_value_contains_only_hashes(make_account):
    acct = make_account("rc_hashes")
    codes = generate_recovery_codes()
    store_recovery_codes(acct, codes)
    stored = json.loads(acct.recovery_codes)
    assert stored == [hash_recovery_code(c) for c in codes]
    for c in codes:
        assert c not in acct.recovery_codes


@given(st.text(alphabet=rc.RECOVERY_CODE_ALPHABET, min_size=8, max_size=8))
def test_hash_ignores_case_dash_and_whitespace(chars):
    canonical = hash_recovery_code(chars)
    assert hash_recovery_code(f"{chars[:4]}-{chars[4:]}") == canonical
    assert hash_recovery_code(f"{chars[:4]}-{chars[4:]}".lower()) == canonical
    assert hash_recovery_code(f"  {chars}  ") == canonical


@given(st.text(alphabet=rc.RECOVERY_CODE_ALPHABET, min_size=8, max_size=8),
       st.text(alphabet=rc.RECOVERY_CODE_ALPHABET, min_size=8, max_size=8))
def test_hash_distinguishes_different_codes(a, b):
    assert (hash_recovery_code(a) == hash_recovery_code(b)) == (a == b)
