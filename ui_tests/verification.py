"""Independent backend-truth helpers for E2E tests.
Channel A (sqlite) is READ-ONLY by construction. Never import ui_tests.config at module level."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from typing import Any

DEFAULT_LOCAL_DB_PATH = "/workspaces/netcup-api-filter/deploy-local/netcup_filter.db"


# ---- Channel A: read-only sqlite ----

def db_path() -> str | None:
    """Return the database path: NAF_VERIFY_DB_PATH env > DEFAULT_LOCAL_DB_PATH if it exists > None."""
    override = os.environ.get("NAF_VERIFY_DB_PATH", "").strip()
    if override:
        return override
    if os.path.exists(DEFAULT_LOCAL_DB_PATH):
        return DEFAULT_LOCAL_DB_PATH
    return None


def db_available() -> bool:
    """Return True if a readable database file is present."""
    path = db_path()
    if not path:
        return False
    return os.path.isfile(path)


def require_db() -> str:
    """Return DB path or pytest.skip if no direct DB access for this target."""
    import pytest  # local import: only called from test context
    path = db_path()
    if not path or not os.path.isfile(path):
        pytest.skip("No direct DB access for this target")
    return path


@contextmanager
def ro_connection():
    """Open a read-only sqlite connection with retry on 'database is locked'.

    - mode=ro: OS-level read-only (write attempt raises OperationalError)
    - PRAGMA query_only=ON: extra guard at the sqlite level
    - busy_timeout=5000: wait up to 5 s for a shared lock
    - row_factory=sqlite3.Row: column-name access on rows
    - Retries 3x / 250 ms backoff on 'database is locked'
    """
    path = require_db()
    uri = f"file:{path}?mode=ro"
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            conn = sqlite3.connect(uri, uri=True, timeout=5.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA query_only=ON")
            try:
                yield conn
                return
            finally:
                conn.close()
        except sqlite3.OperationalError as exc:
            if "database is locked" in str(exc):
                last_exc = exc
                time.sleep(0.25)
                continue
            raise
    raise last_exc  # type: ignore[misc]


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    """Convert a sqlite3.Row to a plain dict, or return None."""
    if row is None:
        return None
    return dict(row)


def get_account(username: str) -> dict | None:
    """Return the accounts row for the given username, or None."""
    with ro_connection() as conn:
        cur = conn.execute(
            "SELECT * FROM accounts WHERE username = ?",
            (username,),
        )
        return _row_to_dict(cur.fetchone())


def get_account_by_email(email: str) -> dict | None:
    """Return the accounts row for the given email, or None."""
    with ro_connection() as conn:
        cur = conn.execute(
            "SELECT * FROM accounts WHERE email = ?",
            (email,),
        )
        return _row_to_dict(cur.fetchone())


def get_realm(
    *,
    realm_id: int | None = None,
    account_username: str | None = None,
    domain: str | None = None,
    realm_value: str | None = None,
) -> dict | None:
    """Return a single account_realms row matched by the given filter combination.

    Priority:
    1. realm_id alone
    2. account_username + domain + realm_value
    """
    with ro_connection() as conn:
        if realm_id is not None:
            cur = conn.execute(
                "SELECT * FROM account_realms WHERE id = ?",
                (realm_id,),
            )
            return _row_to_dict(cur.fetchone())

        if account_username is not None:
            account = get_account(account_username)
            if account is None:
                return None
            account_id = account["id"]
            filters = ["account_id = ?"]
            params: list[Any] = [account_id]
            if domain is not None:
                filters.append("domain = ?")
                params.append(domain)
            if realm_value is not None:
                filters.append("realm_value = ?")
                params.append(realm_value)
            cur = conn.execute(
                f"SELECT * FROM account_realms WHERE {' AND '.join(filters)} LIMIT 1",
                params,
            )
            return _row_to_dict(cur.fetchone())

        return None


def list_realms(account_username: str) -> list[dict]:
    """Return all account_realms rows for the given username."""
    with ro_connection() as conn:
        cur = conn.execute(
            """
            SELECT r.* FROM account_realms r
            JOIN accounts a ON a.id = r.account_id
            WHERE a.username = ?
            ORDER BY r.id
            """,
            (account_username,),
        )
        return [_row_to_dict(row) for row in cur.fetchall()]  # type: ignore[misc]


def get_token(
    *,
    token_id: int | None = None,
    token_name: str | None = None,
    token_prefix: str | None = None,
) -> dict | None:
    """Return an api_tokens row.

    Row includes: is_active, revoked_at (if column exists), expires_at,
    allowed_record_types, allowed_operations, allowed_ip_ranges,
    last_used_at, use_count.
    """
    with ro_connection() as conn:
        if token_id is not None:
            cur = conn.execute(
                "SELECT * FROM api_tokens WHERE id = ?",
                (token_id,),
            )
            return _row_to_dict(cur.fetchone())
        if token_prefix is not None:
            cur = conn.execute(
                "SELECT * FROM api_tokens WHERE token_prefix = ?",
                (token_prefix,),
            )
            return _row_to_dict(cur.fetchone())
        if token_name is not None:
            cur = conn.execute(
                "SELECT * FROM api_tokens WHERE token_name = ? LIMIT 1",
                (token_name,),
            )
            return _row_to_dict(cur.fetchone())
        return None


def count_activity(
    *,
    action: str | None = None,
    status: str | None = None,
    account_username: str | None = None,
    since: str | None = None,
) -> int:
    """Return count of activity_log rows matching the given filters."""
    with ro_connection() as conn:
        filters: list[str] = []
        params: list[Any] = []

        if action is not None:
            filters.append("l.action = ?")
            params.append(action)
        if status is not None:
            filters.append("l.status = ?")
            params.append(status)
        if account_username is not None:
            filters.append(
                "l.account_id = (SELECT id FROM accounts WHERE username = ?)"
            )
            params.append(account_username)
        if since is not None:
            filters.append("l.created_at >= ?")
            params.append(since)

        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        cur = conn.execute(f"SELECT COUNT(*) FROM activity_log l {where}", params)
        row = cur.fetchone()
        return int(row[0]) if row else 0


def latest_activity(
    *,
    action: str | None = None,
    account_username: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Return the most recent activity_log rows, newest first."""
    with ro_connection() as conn:
        filters: list[str] = []
        params: list[Any] = []

        if action is not None:
            filters.append("l.action = ?")
            params.append(action)
        if account_username is not None:
            filters.append(
                "l.account_id = (SELECT id FROM accounts WHERE username = ?)"
            )
            params.append(account_username)

        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(limit)
        cur = conn.execute(
            f"SELECT l.* FROM activity_log l {where} ORDER BY l.created_at DESC LIMIT ?",
            params,
        )
        return [_row_to_dict(row) for row in cur.fetchall()]  # type: ignore[misc]


def list_account_sessions(account_username: str, *, active_only: bool = True) -> list[dict]:
    """Return account_sessions rows for the given username.

    If active_only=True, only sessions without a revoked_at are returned.
    """
    with ro_connection() as conn:
        extra = "AND s.revoked_at IS NULL" if active_only else ""
        cur = conn.execute(
            f"""
            SELECT s.* FROM account_sessions s
            JOIN accounts a ON a.id = s.account_id
            WHERE a.username = ?
            {extra}
            ORDER BY s.created_at DESC
            """,
            (account_username,),
        )
        return [_row_to_dict(row) for row in cur.fetchall()]  # type: ignore[misc]


def get_setting_value(key: str) -> Any:
    """Return the settings.value for the given key, JSON-decoded when possible."""
    with ro_connection() as conn:
        cur = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        raw = row["value"]
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw


def wait_for(predicate, *, timeout: float = 5.0, interval: float = 0.25, message: str = "") -> None:
    """Poll until predicate() is truthy; raise AssertionError(message) on timeout.

    E2E tests call this after a UI submit so they don't race the request's commit.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionError(message or f"wait_for timed out after {timeout}s")


# ---- Channel B: authed JSON via page context (async, takes the logged-in Browser) ----

async def admin_api_accounts(browser) -> list[dict]:
    """Return list of accounts from GET /admin/api/accounts."""
    from ui_tests.deployment_state import get_base_url, get_deployment_target  # lazy
    base = get_base_url(get_deployment_target())
    url = base.rstrip("/") + "/admin/api/accounts"
    resp = await browser.request_get_json(url)
    assert resp["status"] == 200, f"admin_api_accounts: status={resp['status']}"
    return resp["json"]


async def admin_api_stats(browser) -> dict:
    """Return stats dict from GET /admin/api/stats."""
    from ui_tests.deployment_state import get_base_url, get_deployment_target  # lazy
    base = get_base_url(get_deployment_target())
    url = base.rstrip("/") + "/admin/api/stats"
    resp = await browser.request_get_json(url)
    assert resp["status"] == 200, f"admin_api_stats: status={resp['status']}"
    return resp["json"]


async def admin_security_events(browser, *, hours: int = 24, limit: int = 50) -> list[dict]:
    """Return list of security events from GET /admin/api/security/events."""
    from ui_tests.deployment_state import get_base_url, get_deployment_target  # lazy
    base = get_base_url(get_deployment_target())
    url = base.rstrip("/") + "/admin/api/security/events"
    resp = await browser.request_get_json(url, params={"hours": hours, "limit": limit})
    assert resp["status"] == 200, f"admin_security_events: status={resp['status']}"
    return resp["json"]


async def account_api_realms(browser) -> list[dict]:
    """Return list of realms from GET /account/api/realms."""
    from ui_tests.deployment_state import get_base_url, get_deployment_target  # lazy
    base = get_base_url(get_deployment_target())
    url = base.rstrip("/") + "/account/api/realms"
    resp = await browser.request_get_json(url)
    assert resp["status"] == 200, f"account_api_realms: status={resp['status']}"
    return resp["json"]


async def account_api_realm_tokens(browser, realm_id: int) -> list[dict]:
    """Return list of tokens from GET /account/api/realms/<realm_id>/tokens."""
    from ui_tests.deployment_state import get_base_url, get_deployment_target  # lazy
    base = get_base_url(get_deployment_target())
    url = base.rstrip("/") + f"/account/api/realms/{realm_id}/tokens"
    resp = await browser.request_get_json(url)
    assert resp["status"] == 200, f"account_api_realm_tokens: status={resp['status']}"
    return resp["json"]


# ---- Channel C: DNS truth ----

async def dns_api_list_records(token: str, domain: str) -> tuple[int, list[dict]]:
    """GET /api/dns/<domain>/records with Bearer token via httpx.

    Returns (status_code, records_list).
    """
    import httpx  # lazy: not always installed in unit-test environments
    from ui_tests.deployment_state import get_base_url, get_deployment_target  # lazy
    base = get_base_url(get_deployment_target())
    url = base.rstrip("/") + f"/api/dns/{domain}/records"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
    if resp.status_code == 200:
        try:
            data = resp.json()
            records = data if isinstance(data, list) else data.get("records", data)
            return resp.status_code, records
        except Exception:
            return resp.status_code, []
    return resp.status_code, []


def mock_netcup_available(base_url: str | None = None) -> bool:
    """Return True if the mock Netcup API health endpoint responds."""
    import urllib.request  # use stdlib to avoid extra deps
    url_base = base_url or os.environ.get(
        "MOCK_NETCUP_API_URL", "http://localhost:5555"
    )
    try:
        with urllib.request.urlopen(
            f"{url_base.rstrip('/')}/health", timeout=3
        ) as resp:
            return resp.status == 200
    except Exception:
        return False


def mock_netcup_records(domain: str, *, base_url: str | None = None) -> list[dict]:
    """Return DNS records for *domain* from the mock Netcup API.

    Strategy:
    1. Try GET {base}/_test/records/<domain>  (fast test-only route).
    2. Fall back to full CCP login / infoDnsRecords / logout flow.
    """
    import urllib.request
    import json as _json

    url_base = (
        base_url
        or os.environ.get("MOCK_NETCUP_API_URL", "http://localhost:5555")
    ).rstrip("/")

    # --- attempt 1: test-only shortcut ---
    try:
        with urllib.request.urlopen(
            f"{url_base}/_test/records/{domain}", timeout=5
        ) as resp:
            data = _json.loads(resp.read().decode())
            return data.get("records", [])
    except Exception:
        pass

    # --- attempt 2: CCP login / infoDnsRecords / logout ---
    from ui_tests import mock_netcup_api as _mock  # lazy
    import urllib.request as _req
    import urllib.error

    def _ccp_post(payload: dict) -> dict:
        raw = _json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{url_base}/run/webservice/servers/endpoint.php",
            data=raw,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with _req.urlopen(req, timeout=10) as r:
            return _json.loads(r.read().decode())

    # login
    login_resp = _ccp_post({
        "action": "login",
        "param": {
            "customernumber": _mock.MOCK_CUSTOMER_ID,
            "apikey": _mock.MOCK_API_KEY,
            "apipassword": _mock.MOCK_API_PASSWORD,
        },
    })
    session_id = login_resp.get("responsedata", {}).get("apisessionid", "")

    try:
        records_resp = _ccp_post({
            "action": "infoDnsRecords",
            "param": {
                "customernumber": _mock.MOCK_CUSTOMER_ID,
                "apikey": _mock.MOCK_API_KEY,
                "apisessionid": session_id,
                "domainname": domain,
            },
        })
        return records_resp.get("responsedata", {}).get("dnsrecords", [])
    finally:
        try:
            _ccp_post({
                "action": "logout",
                "param": {
                    "customernumber": _mock.MOCK_CUSTOMER_ID,
                    "apikey": _mock.MOCK_API_KEY,
                    "apisessionid": session_id,
                },
            })
        except Exception:
            pass


def find_record(
    records: list[dict],
    *,
    hostname: str,
    rtype: str,
    destination: str | None = None,
) -> dict | None:
    """Find a DNS record by hostname, type, and optionally destination."""
    for rec in records:
        if rec.get("hostname") != hostname:
            continue
        if rec.get("type") != rtype:
            continue
        if destination is not None and rec.get("destination") != destination:
            continue
        return rec
    return None
