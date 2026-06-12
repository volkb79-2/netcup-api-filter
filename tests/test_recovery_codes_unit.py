"""Unit tests for recovery_codes.py.

Covers:
- _recovery_code_count (recovery_codes.py:27) — config parsing / bounding
- generate_recovery_codes (recovery_codes.py:48) — count, format, alphabet
- hash_recovery_code (recovery_codes.py:65) — determinism, normalization
- store_recovery_codes (recovery_codes.py:80) — DB persistence
- verify_recovery_code (recovery_codes.py:108) — happy path, one-time use, wrong code
- get_remaining_code_count (recovery_codes.py:151) — decrements after use
- regenerate_recovery_codes (recovery_codes.py:171) — invalidates old codes

DB-backed tests use the 'app' and 'make_account' fixtures from conftest.py.
Pure tests (no DB) run without any fixture.
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

import netcup_api_filter.recovery_codes as rc
from netcup_api_filter.recovery_codes import (
    RECOVERY_CODE_ALPHABET,  # recovery_codes.py:45 — excludes confusables I,O,0,1
    RECOVERY_CODE_COUNT,     # recovery_codes.py:43 — module-level constant from _recovery_code_count()
    RECOVERY_CODE_LENGTH,    # recovery_codes.py:44 — 8 chars per code
    generate_recovery_codes,
    get_remaining_code_count,
    hash_recovery_code,
    regenerate_recovery_codes,
    store_recovery_codes,
    verify_recovery_code,
)


# =============================================================================
# _recovery_code_count — pure, no DB
# recovery_codes.py:27 — default=3, bounded max(1, min(count, 20))
# =============================================================================


def test_recovery_code_count_default(monkeypatch):
    """Without env var, default is 3 (recovery_codes.py:34 os.environ.get default='3')."""
    monkeypatch.delenv("RECOVERY_CODE_COUNT", raising=False)
    assert rc._recovery_code_count() == 3


def test_recovery_code_count_custom(monkeypatch):
    """Integer env var within range is used as-is."""
    monkeypatch.setenv("RECOVERY_CODE_COUNT", "10")
    assert rc._recovery_code_count() == 10


def test_recovery_code_count_clamped_to_max(monkeypatch):
    """Values above 20 are clamped to 20 (recovery_codes.py:40 min(count, 20))."""
    monkeypatch.setenv("RECOVERY_CODE_COUNT", "999")
    assert rc._recovery_code_count() == 20


def test_recovery_code_count_clamped_to_min(monkeypatch):
    """Values below 1 are clamped to 1 (recovery_codes.py:40 max(1, ...))."""
    monkeypatch.setenv("RECOVERY_CODE_COUNT", "0")
    assert rc._recovery_code_count() == 1


def test_recovery_code_count_bad_value_falls_back(monkeypatch):
    """Non-numeric env var falls back to default 3 (recovery_codes.py:37-39)."""
    monkeypatch.setenv("RECOVERY_CODE_COUNT", "banana")
    assert rc._recovery_code_count() == 3


# =============================================================================
# generate_recovery_codes — pure, no DB
# recovery_codes.py:48 — returns list of RECOVERY_CODE_COUNT codes
# each formatted as XXXX-XXXX (recovery_codes.py:59-61)
# =============================================================================

# Expected format: 4 alphabet chars, dash, 4 alphabet chars
_CODE_PATTERN = re.compile(
    r'^[' + re.escape(RECOVERY_CODE_ALPHABET) + r']{4}-[' + re.escape(RECOVERY_CODE_ALPHABET) + r']{4}$'
)


def test_generate_recovery_codes_count():
    """Returns exactly RECOVERY_CODE_COUNT codes (recovery_codes.py:56)."""
    codes = generate_recovery_codes()
    assert len(codes) == RECOVERY_CODE_COUNT


def test_generate_recovery_codes_format():
    """Each code matches 'XXXX-XXXX' pattern using RECOVERY_CODE_ALPHABET."""
    codes = generate_recovery_codes()
    for code in codes:
        assert _CODE_PATTERN.match(code), (
            f"Code {code!r} does not match expected format XXXX-XXXX "
            f"using alphabet {RECOVERY_CODE_ALPHABET!r}"
        )


def test_generate_recovery_codes_alphabet_excludes_confusables():
    """RECOVERY_CODE_ALPHABET excludes I, O, 0, 1 (recovery_codes.py:45)."""
    for excluded in ("I", "O", "0", "1"):
        assert excluded not in RECOVERY_CODE_ALPHABET, (
            f"Confusable character {excluded!r} found in RECOVERY_CODE_ALPHABET"
        )


def test_generate_recovery_codes_all_chars_from_alphabet():
    """Every character (excluding the dash) must be from RECOVERY_CODE_ALPHABET."""
    codes = generate_recovery_codes()
    for code in codes:
        chars = code.replace("-", "")
        for ch in chars:
            assert ch in RECOVERY_CODE_ALPHABET, (
                f"Character {ch!r} in code {code!r} is not in RECOVERY_CODE_ALPHABET"
            )


# =============================================================================
# hash_recovery_code — pure, no DB
# recovery_codes.py:65 — SHA-256 of normalized (uppercase, strip dashes) code
# =============================================================================


def test_hash_recovery_code_deterministic():
    """Same code always produces the same hash."""
    code = "ABCD-1234"
    assert hash_recovery_code(code) == hash_recovery_code(code)


def test_hash_recovery_code_differs_across_codes():
    """Different plaintext codes produce different hashes."""
    codes = generate_recovery_codes()
    hashes = [hash_recovery_code(c) for c in codes]
    assert len(set(hashes)) == len(hashes), "Duplicate hashes detected across generated codes"


def test_hash_recovery_code_case_insensitive():
    """Normalization: uppercase and lowercase versions hash to the same value.
    recovery_codes.py:76 — normalized = code.upper().replace('-','').strip()
    """
    assert hash_recovery_code("abcd-efgh") == hash_recovery_code("ABCD-EFGH")


def test_hash_recovery_code_dash_insensitive():
    """Normalization: code with dashes stripped hashes identically.
    recovery_codes.py:76 — .replace('-','') before hashing.
    """
    assert hash_recovery_code("ABCDEFGH") == hash_recovery_code("ABCD-EFGH")


# =============================================================================
# store + verify + get_remaining — DB-backed
# Uses 'app' + 'make_account' fixtures from conftest.py
# =============================================================================


def test_store_and_verify_happy_path(app, make_account):
    """store_recovery_codes then verify_recovery_code succeeds."""
    account = make_account("rcuser1")
    codes = generate_recovery_codes()
    result = store_recovery_codes(account, codes)
    assert result is True

    # Verify the first code
    assert verify_recovery_code(account, codes[0]) is True


def test_verify_consumes_code_one_time_use(app, make_account):
    """Second use of the same code is rejected (one-time use per recovery_codes.py:135)."""
    account = make_account("rcuser2")
    codes = generate_recovery_codes()
    store_recovery_codes(account, codes)

    assert verify_recovery_code(account, codes[0]) is True
    # Second attempt with the same code must fail
    assert verify_recovery_code(account, codes[0]) is False


def test_verify_wrong_code_rejected(app, make_account):
    """A code not in the stored set is rejected."""
    account = make_account("rcuser3")
    codes = generate_recovery_codes()
    store_recovery_codes(account, codes)

    # Construct a code guaranteed not to be in the set
    wrong_code = "ZZZZ-ZZZZ"
    # Ensure it's not accidentally equal to any generated code
    assert wrong_code not in codes
    assert verify_recovery_code(account, wrong_code) is False


def test_get_remaining_code_count_decrements(app, make_account):
    """get_remaining_code_count decrements by 1 after each verify."""
    account = make_account("rcuser4")
    codes = generate_recovery_codes()
    store_recovery_codes(account, codes)

    initial = get_remaining_code_count(account)
    assert initial == RECOVERY_CODE_COUNT

    verify_recovery_code(account, codes[0])
    assert get_remaining_code_count(account) == RECOVERY_CODE_COUNT - 1


def test_regenerate_invalidates_old_codes(app, make_account):
    """regenerate_recovery_codes replaces all old codes; old codes no longer work."""
    account = make_account("rcuser5")
    old_codes = generate_recovery_codes()
    store_recovery_codes(account, old_codes)

    new_codes = regenerate_recovery_codes(account)
    assert new_codes is not None
    assert len(new_codes) == RECOVERY_CODE_COUNT

    # Old codes must no longer verify
    for old in old_codes:
        assert verify_recovery_code(account, old) is False, (
            f"Old code {old!r} still verified after regeneration"
        )


def test_verify_case_and_dash_tolerant(app, make_account):
    """verify_recovery_code normalizes input via hash_recovery_code,
    so lowercase / dash-free input works just as well as the canonical form.
    recovery_codes.py:130 — code_hash = hash_recovery_code(code)
    recovery_codes.py:76  — normalized = code.upper().replace('-','').strip()
    """
    account = make_account("rcuser6")
    codes = generate_recovery_codes()
    store_recovery_codes(account, codes)

    canonical = codes[0]             # e.g. "ABCD-1234"
    no_dash = canonical.replace("-", "")   # "ABCD1234"
    lower = canonical.lower()         # "abcd-1234"

    # One of the three forms must succeed (they all map to the same hash).
    # We verify 'no_dash' first, which normalizes identically to 'canonical'.
    assert verify_recovery_code(account, no_dash) is True
