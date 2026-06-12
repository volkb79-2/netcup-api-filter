"""Unit tests for password entropy and validation helpers in models.py.

Covers:
- calculate_entropy (models.py:127)
- validate_password (models.py:164)

All tests are pure (no DB, no app context).

Boundary derivations:
- PASSWORD_MIN_LENGTH = 20   (models.py:111)
- PASSWORD_MIN_ENTROPY = 100 (models.py:112)
- charset sizes: lower=26, upper=26, digit=10, special=30  (models.py:148-157)
"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from netcup_api_filter.models import (
    PASSWORD_MIN_ENTROPY,  # models.py:112 — default 100 bits
    PASSWORD_MIN_LENGTH,   # models.py:111 — default 20 chars
    calculate_entropy,
    validate_password,
)


# =============================================================================
# calculate_entropy — ~6 cases
# models.py:127 — entropy = len(password) * log2(charset_size)
# charset_size is the sum of sizes of character classes present:
#   lowercase 26, uppercase 26, digits 10, special 30 (models.py:149-157)
# =============================================================================


def test_calculate_entropy_empty_returns_zero():
    """Empty string → 0.0 per models.py:141 early return."""
    assert calculate_entropy("") == 0.0


def test_calculate_entropy_single_class_short():
    """Only lowercase letters — charset_size = 26 (models.py:150).
    entropy = length * log2(26).
    """
    pwd = "abc"
    expected = len(pwd) * math.log2(26)
    assert calculate_entropy(pwd) == pytest.approx(expected)


def test_calculate_entropy_mixed_charset():
    """All four classes present → charset_size = 26+26+10+30 = 92 (models.py:149-157)."""
    # "aA1-" has lower, upper, digit, special
    pwd = "aA1-"
    expected = len(pwd) * math.log2(92)
    assert calculate_entropy(pwd) == pytest.approx(expected)


def test_calculate_entropy_monotonicity_longer_wins():
    """Longer password with same charset ≥ entropy of shorter one."""
    short = "aaaa"
    long_ = "aaaaaaaa"
    assert calculate_entropy(long_) >= calculate_entropy(short)


def test_calculate_entropy_known_value():
    """Spot check: 20 lowercase chars → 20 * log2(26).
    Source: models.py:161 — return len(password) * math.log2(charset_size)
    """
    pwd = "a" * 20
    expected = 20 * math.log2(26)
    assert calculate_entropy(pwd) == pytest.approx(expected)


def test_calculate_entropy_unicode_no_crash():
    """Unicode input must not raise; result is a float."""
    result = calculate_entropy("ünïcödé_pässwörd")
    assert isinstance(result, float)


# =============================================================================
# validate_password — ~8 cases
# models.py:164 — returns (bool, str|None)
#
# Boundary values derived from module-level constants:
#   PASSWORD_MIN_LENGTH  = models.py:111 (default 20)
#   PASSWORD_MIN_ENTROPY = models.py:112 (default 100 bits)
#
# To hit the entropy boundary without hardcoding magic numbers we compute
# the minimum length needed for each charset so tests stay correct even if
# the constants are overridden via environment variables.
# =============================================================================


def _min_length_for_entropy(charset_size: int, min_entropy: float = None) -> int:
    """Return minimum character count to reach PASSWORD_MIN_ENTROPY for the given charset_size.

    Derived from models.py:161 formula: entropy = len * log2(charset_size).
    """
    threshold = min_entropy if min_entropy is not None else PASSWORD_MIN_ENTROPY
    return math.ceil(threshold / math.log2(charset_size))


def test_validate_password_too_short_fails():
    """Length < PASSWORD_MIN_LENGTH (models.py:111) → (False, <non-empty reason>)."""
    # Build a password that would be strong enough if it were long enough,
    # but is under the minimum length of PASSWORD_MIN_LENGTH characters.
    short_pwd = "aA1-" * (PASSWORD_MIN_LENGTH // 4)   # exactly min_length chars
    # Shorten by one to go below the threshold
    short_pwd = short_pwd[:PASSWORD_MIN_LENGTH - 1]
    ok, reason = validate_password(short_pwd)
    assert ok is False
    assert reason is not None
    assert len(reason) > 0


def test_validate_password_long_low_entropy_fails():
    """All-lowercase repetition: length OK but entropy too low.

    Entropy = len * log2(26). We need len such that len*log2(26) < 100 bits,
    but len >= PASSWORD_MIN_LENGTH (20). This requires:
      len < PASSWORD_MIN_ENTROPY / log2(26) ≈ 21.3
    So 20 chars of lowercase has entropy ≈ 94.1 bits < 100.

    Source lines:
      - PASSWORD_MIN_LENGTH = models.py:111
      - PASSWORD_MIN_ENTROPY = models.py:112
      - charset += 26 for lowercase at models.py:150
    """
    # Compute exactly: PASSWORD_MIN_ENTROPY / log2(26) gives the break-even length.
    # At PASSWORD_MIN_LENGTH (20) chars, all-lowercase entropy is ~94.1 bits < 100.
    breakeven = PASSWORD_MIN_ENTROPY / math.log2(26)  # ≈ 21.3
    # We need a length that is >= min_length but < breakeven
    length = PASSWORD_MIN_LENGTH  # 20 by default; 20 < 21.3
    if length >= math.ceil(breakeven):
        pytest.skip(
            f"Config makes all-lowercase {PASSWORD_MIN_LENGTH}-char password strong enough "
            f"(breakeven={breakeven:.1f}); cannot construct this boundary case."
        )
    pwd = "a" * length
    ok, reason = validate_password(pwd)
    assert ok is False
    assert reason is not None
    assert len(reason) > 0


def test_validate_password_just_below_entropy_boundary_fails():
    """One character below the entropy-sufficient length for lowercase-only charset → rejected.

    All-lowercase charset_size = 26 (models.py:150).
    Minimum length to reach PASSWORD_MIN_ENTROPY with only lowercase chars:
      sufficient_len = ceil(PASSWORD_MIN_ENTROPY / log2(26))

    For the default PASSWORD_MIN_ENTROPY=100: sufficient_len = ceil(100/log2(26)) = 22.
    At length 21 (one below): entropy = 21 * log2(26) ≈ 98.9 bits < 100 bits.

    This boundary is meaningful only when sufficient_len > PASSWORD_MIN_LENGTH;
    otherwise the length check would fire first for a different reason. With
    the defaults (min_length=20, sufficient_len≈22) there is exactly a 1-char
    gap where a lowercase password of length 21 passes length but fails entropy.

    Source lines:
      - PASSWORD_MIN_LENGTH = models.py:111 (default 20)
      - PASSWORD_MIN_ENTROPY = models.py:112 (default 100)
      - charset += 26 for lowercase at models.py:150
      - entropy formula at models.py:161
    """
    # charset_size = 26 for lowercase-only (models.py:150)
    charset_size = 26
    sufficient_len = _min_length_for_entropy(charset_size)  # ceil(100/log2(26)) = 22 at defaults
    test_len = sufficient_len - 1  # one below the entropy threshold

    # If this length is below min_length, there's no gap to test; the entropy
    # threshold with mixed charset is below min_length and can't form this case.
    # With the default config (sufficient_len=22, min_length=20) this never fires.
    assert test_len >= PASSWORD_MIN_LENGTH, (
        f"Cannot test the entropy-only boundary: sufficient_len={sufficient_len} is at most "
        f"PASSWORD_MIN_LENGTH={PASSWORD_MIN_LENGTH}+1. The gap between length and entropy "
        f"boundaries does not exist under this configuration."
    )

    pwd = "a" * test_len  # all lowercase, length = test_len
    assert len(pwd) == test_len
    ok, reason = validate_password(pwd)
    assert ok is False
    assert reason is not None


def test_validate_password_at_entropy_boundary_succeeds():
    """Exactly the minimum entropy-sufficient length with all 4 classes → valid.

    charset_size = 92 (models.py:149-157), so threshold length =
    ceil(PASSWORD_MIN_ENTROPY / log2(92)).
    """
    charset_size = 92
    sufficient_len = _min_length_for_entropy(charset_size)
    # Make sure length is also >= PASSWORD_MIN_LENGTH
    length = max(sufficient_len, PASSWORD_MIN_LENGTH)
    template = "aA1-"
    pwd = (template * (length // len(template) + 1))[:length]
    assert len(pwd) == length
    ok, reason = validate_password(pwd)
    assert ok is True
    assert reason is None


def test_validate_password_strong_succeeds():
    """Clearly strong password with all char classes and plenty of length."""
    # "SecurePass-2024:XYZ#abc" is 23 chars with lower+upper+digit+special
    pwd = "SecurePass-2024:XYZ#abc"
    ok, reason = validate_password(pwd)
    assert ok is True
    assert reason is None


def test_validate_password_disallowed_chars_fail():
    """Characters excluded per CHARSET_VALIDATION.md (! ` ' " \\) → rejected.

    Disallowed chars: !, `, ', ", \\ (models.py:116-124 PASSWORD_ALLOWED_CHARS excludes them).
    """
    # Use a password long enough and mixed enough to pass all other checks,
    # but containing a disallowed character.
    base = "SecurePass-2024:XYZ#abc"  # passes length+entropy
    for bad_char in ['!', '`', "'", '"', '\\']:
        pwd = base + bad_char
        ok, reason = validate_password(pwd)
        assert ok is False, f"Expected rejection for password containing '{bad_char}'"
        assert reason is not None
        assert len(reason) > 0


def test_validate_password_whitespace_only_fails():
    """All-space password: fails entropy (charset_size=30 for special-only).
    20 spaces → 20 * log2(30) ≈ 98.0 bits < 100 bits.
    Source: models.py:155-156 — space triggers has_special += 30.
    """
    # Space is in the special set (models.py:146 '-=_+;:,.|/?@#$%^&*()[]{}~<> ')
    # 20-space password: charset=30 (special only), entropy ≈ 98 bits < 100
    pwd = " " * PASSWORD_MIN_LENGTH
    ok, reason = validate_password(pwd)
    # With only spaces, entropy = 20 * log2(30) ≈ 98.0 bits < 100
    # So it should fail on entropy
    entropy = calculate_entropy(pwd)
    if entropy >= PASSWORD_MIN_ENTROPY:
        # If config has lower threshold, it might pass; that's ok—just check return type
        assert isinstance(ok, bool)
    else:
        assert ok is False
        assert reason is not None
        assert len(reason) > 0


def test_validate_password_unicode_input_fails():
    """Unicode characters are not in PASSWORD_ALLOWED_CHARS → disallowed char rejection."""
    pwd = "Ünïcödé-PässWörd-2024"  # length > 20, has upper+lower+special+digit
    ok, reason = validate_password(pwd)
    # Unicode chars are not in PASSWORD_ALLOWED_CHARS (models.py:116-124)
    assert ok is False
    assert reason is not None
    assert len(reason) > 0


def test_validate_password_reason_nonempty_on_failure():
    """Any failing validate_password call must return a non-empty reason string."""
    ok, reason = validate_password("")
    assert ok is False
    assert reason is not None
    assert isinstance(reason, str)
    assert len(reason.strip()) > 0
