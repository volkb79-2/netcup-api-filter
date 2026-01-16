"""Contract tests for admin security JSON APIs.

Covers:
- GET /admin/api/security/stats
- GET /admin/api/security/timeline
- GET /admin/api/security/events

These tests validate schema stability (types + required keys) and ensure the
endpoints are accessible for authenticated admins.
"""

from __future__ import annotations

import pytest

from ui_tests import workflows
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
