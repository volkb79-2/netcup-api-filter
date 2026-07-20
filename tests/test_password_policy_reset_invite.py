"""Backend-truth tests for naf-P09: reset/invite paths must honor the real
password policy (models.validate_password), not the old hardcoded
`len(new_password) < 12` check.

Covers:
- api/account.py `/reset-password/<token>` POST  (route: account.reset_password)
- api/account.py `/invite/<token>` POST           (route: account.accept_invite)
- password_reset.py `complete_password_reset()`   (defense-in-depth gate)

All assertions are on backend state (account.password_hash, direct function
return values) rather than HTTP status codes, per the handoff.

Tokens are minted via the real `generate_reset_token()` flow (not
hand-crafted), so the tests exercise the same code path a real reset/invite
email would produce.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from netcup_api_filter.models import validate_password
from netcup_api_filter.password_reset import (
    complete_password_reset,
    generate_reset_token,
)

# CSRF: account_bp is NOT csrf.exempt()'d (unlike the REST API blueprints),
# so its POST routes need a valid CSRF token. Disabling WTF_CSRF_ENABLED is
# the established pattern for testing these forms without wiring up the
# token dance (see tests/test_portal_record_scope.py for precedent);
# conftest.py itself is out of scope for this package, so it's overridden
# locally here.


@pytest.fixture
def app(app):
    app.config["WTF_CSRF_ENABLED"] = False
    return app


@pytest.fixture
def client(app):
    return app.test_client()

# A password that satisfies the OLD (removed) `len(new_password) < 12` check
# but is low-entropy enough to fail the real policy (min 20 chars / 100 bits
# entropy). This is exactly the gap naf-P09 closes.
WEAK_12_CHAR_PASSWORD = "aaaaaaaaaaaa"  # 12 chars, lowercase-only

# A password that satisfies the real policy (length + entropy + charset).
STRONG_PASSWORD = "SecurePass-2024:XYZ#abc"  # 23 chars, all 4 classes

assert len(WEAK_12_CHAR_PASSWORD) >= 12, "sanity: must pass the old len<12 gate"
_weak_ok, _weak_reason = validate_password(WEAK_12_CHAR_PASSWORD)
assert _weak_ok is False, "sanity: WEAK_12_CHAR_PASSWORD must fail the real policy"
_strong_ok, _strong_reason = validate_password(STRONG_PASSWORD)
assert _strong_ok is True, "sanity: STRONG_PASSWORD must pass the real policy"


def _mint_reset_token(account):
    """Mint a real 'reset' token with no IP binding (keeps the HTTP test
    independent of the test client's REMOTE_ADDR)."""
    raw_token, _expiry = generate_reset_token(
        account, source_ip=None, token_type="reset"
    )
    return raw_token


def _mint_invite_token(account):
    """Mint a real 'invite' token (invites never use IP binding)."""
    raw_token, _expiry = generate_reset_token(
        account, source_ip=None, token_type="invite"
    )
    return raw_token


# =============================================================================
# O1 — /reset-password/<token> POST honors the real policy
# =============================================================================


def test_reset_password_post_rejects_weak_12char_password(client, db, make_account):
    account = make_account(username="resetuser", password=STRONG_PASSWORD)
    original_hash = account.password_hash
    token = _mint_reset_token(account)

    resp = client.post(
        f"/account/reset-password/{token}",
        data={
            "new_password": WEAK_12_CHAR_PASSWORD,
            "confirm_password": WEAK_12_CHAR_PASSWORD,
        },
        follow_redirects=True,
    )

    # The same policy message validate_password returns must surface.
    assert _weak_reason.encode() in resp.data

    # Backend truth: the account's password must be untouched.
    db.session.refresh(account)
    assert account.password_hash == original_hash


def test_reset_password_post_strong_password_succeeds(client, db, make_account):
    account = make_account(username="resetuser2", password="OldPassword-2024:ABC#xyz")
    original_hash = account.password_hash
    token = _mint_reset_token(account)

    client.post(
        f"/account/reset-password/{token}",
        data={
            "new_password": STRONG_PASSWORD,
            "confirm_password": STRONG_PASSWORD,
        },
        follow_redirects=True,
    )

    db.session.refresh(account)
    assert account.password_hash != original_hash
    assert account.verify_password(STRONG_PASSWORD)


# =============================================================================
# O1 — /invite/<token> POST honors the real policy
# =============================================================================


def test_invite_accept_post_rejects_weak_12char_password(client, db, make_account):
    account = make_account(username="inviteuser", password=STRONG_PASSWORD)
    original_hash = account.password_hash
    token = _mint_invite_token(account)

    resp = client.post(
        f"/account/invite/{token}",
        data={
            "new_password": WEAK_12_CHAR_PASSWORD,
            "confirm_password": WEAK_12_CHAR_PASSWORD,
        },
        follow_redirects=True,
    )

    assert _weak_reason.encode() in resp.data

    db.session.refresh(account)
    assert account.password_hash == original_hash


def test_invite_accept_post_strong_password_succeeds(client, db, make_account):
    account = make_account(username="inviteuser2", password="OldPassword-2024:ABC#xyz")
    original_hash = account.password_hash
    token = _mint_invite_token(account)

    client.post(
        f"/account/invite/{token}",
        data={
            "new_password": STRONG_PASSWORD,
            "confirm_password": STRONG_PASSWORD,
        },
        follow_redirects=True,
    )

    db.session.refresh(account)
    assert account.password_hash != original_hash
    assert account.verify_password(STRONG_PASSWORD)


# =============================================================================
# O2 — complete_password_reset() itself gates on the real policy
# (defense in depth: safe regardless of caller)
# =============================================================================


def test_complete_password_reset_direct_rejects_weak_password(db, make_account):
    account = make_account(username="directuser", password=STRONG_PASSWORD)
    original_hash = account.password_hash
    raw_token = _mint_reset_token(account)

    success, message = complete_password_reset(account, WEAK_12_CHAR_PASSWORD, raw_token)

    assert success is False
    assert message == _weak_reason

    db.session.refresh(account)
    assert account.password_hash == original_hash


def test_complete_password_reset_direct_accepts_strong_password(db, make_account):
    account = make_account(username="directuser2", password="OldPassword-2024:ABC#xyz")
    original_hash = account.password_hash
    raw_token = _mint_reset_token(account)

    success, message = complete_password_reset(account, STRONG_PASSWORD, raw_token)

    assert success is True
    db.session.refresh(account)
    assert account.password_hash != original_hash
    assert account.verify_password(STRONG_PASSWORD)
