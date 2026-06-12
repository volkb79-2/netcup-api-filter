"""Self-tests for ui_tests/verification.py — Channel A (sqlite read-only).

Run with:
    cd /workspaces/netcup-api-filter
    source .env.workspace && source .env.services
    DEPLOYMENT_TARGET=local python -m pytest ui_tests/tests/test_verification_selftest.py -v

These tests do NOT require a Playwright session — they exercise the sqlite
helpers directly against the live local deployment DB.
"""

from __future__ import annotations

import pytest
import sqlite3

from ui_tests import verification


# ---------------------------------------------------------------------------
# Case 1: db_available reflects the real DB presence
# ---------------------------------------------------------------------------

def test_db_available():
    """db_available() must return True when the local deployment DB exists."""
    assert verification.db_available(), (
        "Expected deploy-local/netcup_filter.db to be present. "
        "Ensure DEPLOYMENT_TARGET=local and the local stack is deployed."
    )


# ---------------------------------------------------------------------------
# Case 2: get_account returns the seeded admin row
# ---------------------------------------------------------------------------

def test_get_account_admin():
    """get_account('admin') must return a non-None dict with the expected fields."""
    verification.require_db()  # skip gracefully on non-local targets

    account = verification.get_account("admin")
    assert account is not None, "Admin account not found in DB"
    assert account["username"] == "admin"
    assert account["is_admin"] == 1, f"Expected is_admin=1, got {account['is_admin']}"
    assert account["is_active"] == 1, f"Expected is_active=1, got {account['is_active']}"
    assert "email" in account
    assert "id" in account


# ---------------------------------------------------------------------------
# Case 3: query_only enforcement — write through ro_connection must fail
# ---------------------------------------------------------------------------

def test_ro_connection_rejects_writes():
    """Attempting a write through ro_connection() must raise an OperationalError."""
    verification.require_db()  # skip on non-local targets

    with pytest.raises(sqlite3.OperationalError):
        with verification.ro_connection() as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('_selftest_write', '1')"
            )
            conn.commit()


# ---------------------------------------------------------------------------
# Case 4: wait_for raises AssertionError on timeout
# ---------------------------------------------------------------------------

def test_wait_for_timeout_raises():
    """wait_for() must raise AssertionError when the predicate never becomes truthy."""
    with pytest.raises(AssertionError, match="selftest_timeout"):
        verification.wait_for(
            lambda: False,
            timeout=0.3,
            interval=0.05,
            message="selftest_timeout",
        )
