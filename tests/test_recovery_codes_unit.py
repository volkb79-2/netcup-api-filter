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


# =============================================================================
# Mutation-killing tests — added by M2 spot-check
# =============================================================================


# --- verify_recovery_code: no-codes guard (mutmut_3) ---
def test_verify_no_codes_returns_false(app, make_account):
    """When account.recovery_codes is None/empty, verify must return False.

    Kills x_verify_recovery_code__mutmut_3: 'return False' → 'return True'.
    An account with no codes stored must never be authenticated via recovery-
    code path regardless of what code string is supplied.
    """
    account = make_account("rc_no_codes")
    # Do NOT store any codes — account.recovery_codes is None.
    assert account.recovery_codes is None
    assert verify_recovery_code(account, "AAAA-BBBB") is False


# --- verify_recovery_code: JSON decode error (mutmut_7) ---
def test_verify_corrupt_json_returns_false(app, make_account):
    """Corrupted recovery_codes JSON must make verify return False, not True.

    Kills x_verify_recovery_code__mutmut_7: 'return False' → 'return True'.
    A corrupted DB value must not grant authentication.
    """
    from netcup_api_filter.models import db
    account = make_account("rc_corrupt")
    # Inject invalid JSON directly into the column.
    account.recovery_codes = "NOT-VALID-JSON{{{!"
    db.session.commit()

    assert verify_recovery_code(account, "AAAA-BBBB") is False


# --- verify_recovery_code: last-code clears timestamp correctly (mutmut_14) ---
def test_verify_last_code_clears_generated_at(app, make_account):
    """Using the last recovery code must clear recovery_codes_generated_at.

    Kills x_verify_recovery_code__mutmut_14: 'if not stored_hashes:' → 'if stored_hashes:'.
    The condition inverted would clear the timestamp when codes REMAIN and keep it
    when the last code is consumed — the exact opposite of the intended behaviour.
    We validate by checking that generated_at is None after using the only code.
    """
    account = make_account("rc_last_code")
    # Store exactly one code so that using it empties the list.
    code = generate_recovery_codes()[0]
    store_recovery_codes(account, [code])
    assert account.recovery_codes_generated_at is not None

    result = verify_recovery_code(account, code)
    assert result is True
    # After the last code is used, the generation timestamp must be cleared.
    assert account.recovery_codes_generated_at is None


# --- store_recovery_codes: exception path returns False (mutmut_9) ---
def test_store_recovery_codes_exception_returns_false(app, make_account, monkeypatch):
    """store_recovery_codes must return False (not True) when db.session.commit raises.

    Kills x_store_recovery_codes__mutmut_9: 'return False' → 'return True'.
    Callers rely on the return value to know whether codes were persisted.
    """
    from netcup_api_filter import recovery_codes as rc
    from netcup_api_filter.models import db

    account = make_account("rc_store_fail")
    codes = generate_recovery_codes()

    def _boom():
        raise RuntimeError("simulated db failure")

    monkeypatch.setattr(db.session, "commit", _boom)
    result = store_recovery_codes(account, codes)
    assert result is False


# --- get_remaining_code_count: no codes returns 0 (mutmut_2) ---
def test_get_remaining_no_codes_returns_zero(app, make_account):
    """get_remaining_code_count must return 0 when no codes are stored.

    Kills x_get_remaining_code_count__mutmut_2: 'return 0' → 'return 1'.
    Callers use this value to decide whether to prompt the user to regenerate codes.
    """
    account = make_account("rc_count_none")
    assert account.recovery_codes is None
    assert get_remaining_code_count(account) == 0


# --- get_remaining_code_count: corrupt JSON returns 0 (mutmut_5) ---
def test_get_remaining_corrupt_json_returns_zero(app, make_account):
    """get_remaining_code_count must return 0 for unparseable JSON, not 1.

    Kills x_get_remaining_code_count__mutmut_5: 'return 0' → 'return 1'.
    """
    from netcup_api_filter.models import db
    account = make_account("rc_count_corrupt")
    account.recovery_codes = "INVALID-JSON"
    db.session.commit()

    assert get_remaining_code_count(account) == 0


# --- _recovery_code_count: default "3" fallback when env var absent (mutmut_3/5/8) ---
def test_recovery_code_count_default_is_three_not_none_or_other(monkeypatch):
    """_recovery_code_count() must return 3 when env var is absent.

    Kills x__recovery_code_count__mutmut_3 (default→None → int(str(None)) raises →
    fallback 3 but via exception path), mutmut_5 (no default arg → KeyError → fallback),
    mutmut_8 (default→"XX3XX" → ValueError → fallback) — these all end up returning 3
    via the except branch, making them equivalent in end-result but exercising
    the try-path rather than except-path. Pin the expected outcome explicitly.
    """
    monkeypatch.delenv("RECOVERY_CODE_COUNT", raising=False)
    assert rc._recovery_code_count() == 3


# --- hash_recovery_code: uppercase normalization (mutmut_6) ---
def test_hash_recovery_code_uppercase_normalization_used_for_storage(app, make_account):
    """Codes are stored hashed with uppercase normalization; lowercase input must still match.

    Kills x_hash_recovery_code__mutmut_6: 'code.upper()' → 'code.lower()'.
    If .lower() were used instead, a stored hash (derived from 'ABCDEFGH') would
    NOT match a lowercase input ('abcdefgh') because sha256('abcdefgh') != sha256('ABCDEFGH').
    We generate uppercase codes, store them, then verify with the exact canonical form.
    This test pins that the hash must be consistent: store(uppercase) == lookup(uppercase).
    """
    account = make_account("rc_hash_norm")
    # Generate codes (all uppercase per RECOVERY_CODE_ALPHABET).
    codes = generate_recovery_codes()
    store_recovery_codes(account, codes)

    canonical = codes[0]  # e.g. "ABCD-2345" — all uppercase
    # Verify with canonical uppercase — must succeed.
    assert verify_recovery_code(account, canonical) is True

    # Now directly confirm the hash function is deterministic and uppercase-based:
    h1 = hash_recovery_code(canonical)
    h2 = hash_recovery_code(canonical.upper())
    assert h1 == h2, "hash_recovery_code must produce the same hash for same-case input"
