"""IP-allowlist enforcement round-trip test.

PATTERN: DNS API call with out-of-range client IP
  -> exact HTTP 403
  -> Channel A: activity_log has error_code='ip_denied', severity='critical', is_attack=1.
Second call with in-range IP (localhost, 127.0.0.1/8)
  -> not ip_denied (proceeds further, fails only at Netcup backend level).

Anti-false-green gate: deliberately make check_ip_allowed return True unconditionally
and confirm the test FAILS (error_code assertion no longer matches).

This test does NOT need mock-netcup for the IP-denied path: the permission check
runs BEFORE the Netcup call, so the 403 is returned without contacting Netcup.

Test setup uses a direct DB write to insert a throwaway token with IP restrictions
(no browser/Mailpit needed -- the UI path would require the full invite/login/2FA
flow which is covered by test_cross_role_account_lifecycle.py). The throwaway token
is deleted in a finally block. The demo-user account row is never modified.
"""
from __future__ import annotations

import json
import sqlite3
import time

import httpx
import pytest

from ui_tests import verification
from ui_tests.deployment_state import get_base_url, get_deployment_target

pytestmark = [pytest.mark.security]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# CIDR that deliberately excludes 127.0.0.1 (the test client's remote_addr).
# 203.0.113.0/24 is "TEST-NET-3" (RFC 5737) – documentation-only, never routed.
EXCLUDED_CIDR = "203.0.113.0/24"

# CIDR that includes 127.0.0.1.
INCLUDED_CIDR = "127.0.0.0/8"

# The demo-user realm (id=1, domain=example.com) is pre-seeded and approved.
DEMO_REALM_ID = 1
DOMAIN = "example.com"

# Token names for the two test tokens (must not collide with existing tokens).
TOKEN_NAME_DENIED  = "e3-ip-denied-test"
TOKEN_NAME_ALLOWED = "e3-ip-allowed-test"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_url() -> str:
    return get_base_url(get_deployment_target()).rstrip("/")


def _db_write_conn() -> sqlite3.Connection:
    """Open a writable sqlite connection (test-setup only — never assertion)."""
    path = verification.require_db()
    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _insert_test_token(
    conn: sqlite3.Connection,
    *,
    token_name: str,
    token_plain: str,
    realm_id: int,
    allowed_ip_ranges: list[str] | None,
) -> int:
    """Insert a test api_token row directly. Returns token_id."""
    from netcup_api_filter.models import hash_token, parse_token
    token_prefix = parse_token(token_plain)[1][:8]  # first 8 chars of random part
    token_hash = hash_token(token_plain)
    ip_json = json.dumps(allowed_ip_ranges) if allowed_ip_ranges is not None else None
    cur = conn.execute(
        """
        INSERT INTO api_tokens
            (realm_id, token_name, token_prefix, token_hash,
             allowed_ip_ranges, is_active, use_count, created_at)
        VALUES (?, ?, ?, ?, ?, 1, 0, datetime('now'))
        """,
        (realm_id, token_name, token_prefix, token_hash, ip_json),
    )
    conn.commit()
    return cur.lastrowid


def _delete_test_token(conn: sqlite3.Connection, token_id: int) -> None:
    """Best-effort cleanup of a test token row."""
    try:
        conn.execute("DELETE FROM api_tokens WHERE id = ?", (token_id,))
        conn.commit()
    except Exception:
        pass


def _dns_api_get(token_plain: str) -> httpx.Response:
    """Synchronous GET /api/dns/<domain>/records with Bearer auth."""
    url = _base_url() + f"/api/dns/{DOMAIN}/records"
    return httpx.get(
        url,
        headers={"Authorization": f"Bearer {token_plain}"},
        timeout=15.0,
    )


def _latest_ip_denied_log(token_id: int) -> dict | None:
    """Return the most recent activity_log row for this token with error_code=ip_denied."""
    with verification.ro_connection() as conn:
        cur = conn.execute(
            """
            SELECT * FROM activity_log
            WHERE token_id = ? AND error_code = 'ip_denied'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (token_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _get_demo_user_alias() -> str:
    """Return the user_alias of the demo-user account (needed to build a valid token)."""
    with verification.ro_connection() as conn:
        cur = conn.execute(
            "SELECT user_alias FROM accounts WHERE username = 'demo-user'",
        )
        row = cur.fetchone()
        assert row, "demo-user account not found in DB"
        return row["user_alias"]


def _generate_test_token_plain(user_alias: str) -> str:
    """Generate a valid naf_<user_alias>_<random64> token string for test use.

    Must use an existing account's user_alias so authenticate_token can resolve
    the account before reaching check_permission (the IP check lives there).
    """
    import secrets
    ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    random_part = "".join(secrets.choice(ALPHABET) for _ in range(64))
    return f"naf_{user_alias}_{random_part}"


# ---------------------------------------------------------------------------
# The test
# ---------------------------------------------------------------------------

def test_ip_allowlist_denied_logs_and_returns_403():
    """Round-trip: token restricted to EXCLUDED_CIDR -> 403 + Channel-A ip_denied row."""
    # Channel A: require DB
    verification.require_db()

    conn = _db_write_conn()
    user_alias = _get_demo_user_alias()
    denied_token_plain  = _generate_test_token_plain(user_alias)
    allowed_token_plain = _generate_test_token_plain(user_alias)
    denied_id:  int | None = None
    allowed_id: int | None = None

    try:
        # ---- SETUP: insert two test tokens ----
        # Token 1: IP range that EXCLUDES 127.0.0.1 (the test client remote_addr)
        denied_id = _insert_test_token(
            conn,
            token_name=TOKEN_NAME_DENIED,
            token_plain=denied_token_plain,
            realm_id=DEMO_REALM_ID,
            allowed_ip_ranges=[EXCLUDED_CIDR],
        )

        # Token 2: IP range that INCLUDES 127.0.0.1
        allowed_id = _insert_test_token(
            conn,
            token_name=TOKEN_NAME_ALLOWED,
            token_plain=allowed_token_plain,
            realm_id=DEMO_REALM_ID,
            allowed_ip_ranges=[INCLUDED_CIDR],
        )

        # ---- STEP 1: out-of-range IP -> expect 403 ----
        resp_denied = _dns_api_get(denied_token_plain)
        assert resp_denied.status_code == 403, (
            f"Expected 403 for out-of-range IP, got {resp_denied.status_code}. "
            f"Body: {resp_denied.text[:300]}"
        )

        # ---- STEP 2: Channel A -- verify ip_denied was logged ----
        # Poll for the log row (Flask's commit is synchronous but let's be safe)
        verification.wait_for(
            lambda: _latest_ip_denied_log(denied_id) is not None,
            timeout=10.0,
            message=f"No activity_log row with error_code='ip_denied' for token_id={denied_id}",
        )
        log_row = _latest_ip_denied_log(denied_id)
        assert log_row is not None  # guaranteed by wait_for above
        assert log_row["error_code"] == "ip_denied", (
            f"Expected error_code='ip_denied', got {log_row['error_code']!r}"
        )
        assert log_row["severity"] == "critical", (
            f"Expected severity='critical', got {log_row['severity']!r}"
        )
        assert log_row["is_attack"] == 1, (
            f"Expected is_attack=1, got {log_row['is_attack']!r}"
        )
        assert log_row["status"] == "denied", (
            f"Expected status='denied', got {log_row['status']!r}"
        )

        # ---- STEP 3: in-range IP -> NOT ip_denied ----
        # The call will succeed auth+permission (127.0.0.1 is in 127.0.0.0/8),
        # then fail at the Netcup backend (mock may or may not be running).
        # We only assert: status is NOT 403 with error_code ip_denied.
        # Acceptable outcomes: 200 (mock is up), 500/502 (no backend), anything != ip-403.
        resp_allowed = _dns_api_get(allowed_token_plain)
        # The permission layer should not deny it as ip_denied.
        # If 403, check body to ensure it's not ip_denied.
        if resp_allowed.status_code == 403:
            body = resp_allowed.json() if resp_allowed.headers.get("content-type", "").startswith("application/json") else {}
            msg = body.get("message", "")
            assert "whitelist" not in msg.lower(), (
                f"In-range IP was denied with IP-whitelist error: {msg!r}"
            )

        # Channel A: no new ip_denied row for the allowed token
        with verification.ro_connection() as rconn:
            cur = rconn.execute(
                "SELECT COUNT(*) FROM activity_log WHERE token_id = ? AND error_code = 'ip_denied'",
                (allowed_id,),
            )
            ip_denied_count = cur.fetchone()[0]
        assert ip_denied_count == 0, (
            f"In-range token got {ip_denied_count} ip_denied log rows; expected 0"
        )

    finally:
        # Cleanup: delete both test tokens and their activity_log rows
        try:
            if denied_id is not None:
                conn.execute("DELETE FROM activity_log WHERE token_id = ?", (denied_id,))
            if allowed_id is not None:
                conn.execute("DELETE FROM activity_log WHERE token_id = ?", (allowed_id,))
            conn.commit()
        except Exception:
            pass
        if denied_id is not None:
            _delete_test_token(conn, denied_id)
        if allowed_id is not None:
            _delete_test_token(conn, allowed_id)
        conn.close()
