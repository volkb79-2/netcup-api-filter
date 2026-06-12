"""Contract tests for admin security JSON APIs.

Covers:
- GET /admin/api/security/stats
- GET /admin/api/security/timeline
- GET /admin/api/security/events

These tests validate schema stability (types + required keys) and ensure the
endpoints are accessible for authenticated admins.
"""

from __future__ import annotations

import datetime

import httpx
import pytest

from ui_tests import verification, workflows
from ui_tests.browser import Browser
from ui_tests.config import settings


pytestmark = pytest.mark.asyncio


async def test_admin_security_api_contracts(session_manager):
    admin_handle = await session_manager.admin_session()
    browser = Browser(admin_handle.page)
    await browser.reset()
    await workflows.ensure_admin_dashboard(browser)

    stats = await browser.request_get_json(
        settings.url("/admin/api/security/stats"),
        params={"hours": 24},
    )
    assert stats["status"] == 200
    payload = stats["json"]
    assert isinstance(payload, dict)
    assert isinstance(payload.get("by_error_code"), dict)
    assert isinstance(payload.get("by_severity"), dict)
    assert isinstance(payload.get("attack_events"), list)
    assert isinstance(payload.get("total_denied"), int)
    assert isinstance(payload.get("window_hours"), int)

    for event in payload.get("attack_events", [])[:5]:
        assert isinstance(event, dict)
        for key in {"id", "error_code", "severity", "source_ip", "account_id", "created_at"}:
            assert key in event

    timeline = await browser.request_get_json(
        settings.url("/admin/api/security/timeline"),
        params={"hours": 24},
    )
    assert timeline["status"] == 200
    timeline_payload = timeline["json"]
    assert isinstance(timeline_payload, list)
    for bucket in timeline_payload[:5]:
        assert isinstance(bucket, dict)
        assert isinstance(bucket.get("timestamp"), str)

    events = await browser.request_get_json(
        settings.url("/admin/api/security/events"),
        params={"hours": 24, "limit": 50},
    )
    assert events["status"] == 200
    events_payload = events["json"]
    assert isinstance(events_payload, list)
    for event in events_payload[:5]:
        assert isinstance(event, dict)
        for key in {
            "id",
            "created_at",
            "error_code",
            "severity",
            "source_ip",
            "user_agent",
            "account_id",
            "token_id",
            "status_reason",
            "is_attack",
        }:
            assert key in event


async def test_failed_token_auth_produces_security_event(session_manager):
    """A tampered token (valid prefix, wrong hash) produces a security event
    that appears in:
    - Channel B: GET /admin/api/security/events (new event with
      error_code='token_hash_mismatch' and the token prefix).
    - Channel A: ActivityLog row with action='dns_list' (or similar) and
      status='denied', error_code='token_hash_mismatch'.

    Token format: naf_<alias>_<random64>
    We keep the alias + prefix (first 8 chars of random_part) intact and
    replace the remaining chars so the lookup succeeds but hash fails.
    """
    if not verification.db_available():
        pytest.skip("Channel A (sqlite) not available for this target")

    # Get a valid token from Channel A to derive a tampered version.
    # Use the demo-user primary token (token_prefix='vt7zyENg' from deployment state).
    from ui_tests.config import settings as _settings
    token_plaintext = (_settings.client_token or "").strip()
    assert token_plaintext, "No client token available in settings"

    # Parse token: naf_<alias>_<random64>
    parts = token_plaintext.split("_", 2)
    assert len(parts) == 3, f"Unexpected token format: {token_plaintext[:20]}..."
    alias = parts[1]
    random_part = parts[2]
    token_prefix = random_part[:8]

    # Tamper: keep alias + prefix, scramble the rest
    tampered_suffix = "X" * (len(random_part) - 8)
    tampered_token = f"naf_{alias}_{token_prefix}{tampered_suffix}"

    # Snapshot baselines
    since_ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    domain = (_settings.client_domain or "example.com").strip()

    # Channel A baseline: count existing denied rows for this kind of failure
    activity_before = verification.count_activity(
        status="denied",
        since=since_ts,
    )

    # Channel B baseline: count existing events in the last hour
    admin_handle = await session_manager.admin_session()
    admin_browser = Browser(admin_handle.page)
    await admin_browser.reset()
    await workflows.ensure_admin_dashboard(admin_browser)

    events_before_resp = await admin_browser.request_get_json(
        settings.url("/admin/api/security/events"),
        params={"hours": 1, "limit": 200},
    )
    assert events_before_resp["status"] == 200
    events_before = events_before_resp["json"]
    ids_before = {e["id"] for e in events_before if isinstance(e, dict) and "id" in e}

    # Call the DNS API with the tampered token → must return 401
    list_url = settings.url(f"/api/dns/{domain}/records")
    async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
        resp = await client.get(
            list_url,
            headers={"Authorization": f"Bearer {tampered_token}"},
        )
    assert resp.status_code == 401, (
        f"Expected 401 for tampered token, got {resp.status_code}: {resp.text[:200]}"
    )

    # --- Channel A: ActivityLog row with status='denied' and
    #     error_code='token_hash_mismatch' ---
    verification.wait_for(
        lambda: verification.count_activity(status="denied", since=since_ts) > activity_before,
        timeout=10.0,
        message="Channel A: no new 'denied' ActivityLog row after tampered-token request",
    )

    # Verify the specific error_code is recorded
    rows = verification.latest_activity(action=None, limit=20)
    mismatch_rows = [
        r for r in rows
        if r.get("error_code") == "token_hash_mismatch"
        and (r.get("created_at") or "") >= since_ts
    ]
    assert len(mismatch_rows) >= 1, (
        f"Channel A: no ActivityLog row with error_code='token_hash_mismatch' "
        f"since {since_ts}; recent rows: {rows[:5]}"
    )

    # --- Channel B: /admin/api/security/events has a new event ---
    def _new_mismatch_event_present() -> bool:
        import urllib.request
        import json as _json
        from ui_tests.deployment_state import get_base_url, get_deployment_target
        base = get_base_url(get_deployment_target()).rstrip("/")
        url = base + "/admin/api/security/events"
        # We can't use the browser here (sync predicate); use a fresh channel-B
        # request via the Channel A data instead — the security event is sourced
        # from the same ActivityLog table, so Channel A confirmation is sufficient.
        # Return True once Channel A confirms the row.
        return len([
            r for r in verification.latest_activity(action=None, limit=50)
            if r.get("error_code") == "token_hash_mismatch"
            and (r.get("created_at") or "") >= since_ts
        ]) >= 1

    verification.wait_for(
        _new_mismatch_event_present,
        timeout=10.0,
        message="Channel A/B: token_hash_mismatch security event not recorded",
    )

    # Channel B: verify via admin API that a new event appears with the expected fields.
    events_after_resp = await admin_browser.request_get_json(
        settings.url("/admin/api/security/events"),
        params={"hours": 1, "limit": 200},
    )
    assert events_after_resp["status"] == 200
    events_after = events_after_resp["json"]

    new_events = [
        e for e in events_after
        if isinstance(e, dict)
        and e.get("id") not in ids_before
        and e.get("error_code") == "token_hash_mismatch"
    ]
    assert len(new_events) >= 1, (
        f"Channel B: no new security event with error_code='token_hash_mismatch' "
        f"found in /admin/api/security/events; "
        f"ids_before={ids_before}, events_after ids={[e.get('id') for e in events_after[:10]]}"
    )

    # Validate required fields on the new event
    evt = new_events[0]
    for key in {"id", "created_at", "error_code", "severity", "source_ip", "status_reason"}:
        assert key in evt, f"Security event missing field {key!r}: {evt}"
    assert evt["error_code"] == "token_hash_mismatch"
    assert evt["severity"] in {"high", "critical"}, (
        f"token_hash_mismatch should be high/critical severity, got: {evt['severity']!r}"
    )
