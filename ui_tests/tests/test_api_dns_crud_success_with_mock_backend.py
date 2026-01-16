"""DNS API success-path CRUD tests (mock-backed).

These tests validate the happy-path behavior of the REST DNS API when:
- A full-control token is used (create/update/delete permissions)
- Netcup API is configured to point at the mock Netcup CCP API service

Important: The mock backend must be reachable by the app under test.
- In production-parity runs, use: ./run-local-tests.sh --with-mocks
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest

from ui_tests.browser import browser_session
from ui_tests import workflows
from ui_tests.config import settings
from ui_tests.mock_netcup_api import MOCK_API_KEY, MOCK_API_PASSWORD, MOCK_CUSTOMER_ID


pytestmark = pytest.mark.asyncio


def _mock_endpoint_url() -> str | None:
    base = (os.environ.get("MOCK_NETCUP_API_URL") or "").strip()
    if not base:
        return None
    return f"{base}/run/webservice/servers/endpoint.php"


async def test_dns_api_crud_success_path_with_mock_backend(active_profile):
    mock_api_url = _mock_endpoint_url()
    if not mock_api_url:
        pytest.skip("MOCK_NETCUP_API_URL not set; run ./run-local-tests.sh --with-mocks")

    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)

        # Configure app to use mock Netcup API.
        await workflows.admin_configure_netcup_api(
            browser=browser,
            customer_id=str(MOCK_CUSTOMER_ID),
            api_key=MOCK_API_KEY,
            api_password=MOCK_API_PASSWORD,
            api_url=mock_api_url,
        )

        # Use the preseeded client token from deployment state.
        # This keeps the test config-driven and avoids relying on deprecated "client create" UI flows.
        token = (active_profile.client_token or "").strip()
        assert token, "Expected active_profile.client_token to be populated from deployment_state_*.json"

        domain = (active_profile.client_domain or "").strip()
        assert domain, "Expected active_profile.client_domain to be configured"

        # Unique hostname for isolation across re-runs.
        hostname = f"api-crud-{uuid.uuid4().hex[:8]}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
            # 1) LIST
            list_url = settings.url(f"/api/dns/{domain}/records")
            resp = await client.get(list_url, headers=headers)
            assert resp.status_code == 200, resp.text[:400]

            # 2) CREATE
            destination_create = "192.0.2.99"
            create_payload = {
                "hostname": hostname,
                "type": "A",
                "destination": destination_create,
            }
            resp = await client.post(list_url, headers=headers, json=create_payload)
            assert resp.status_code == 201, resp.text[:400]

            # 3) LIST → find created record id
            resp = await client.get(list_url, headers=headers)
            assert resp.status_code == 200, resp.text[:400]
            records = resp.json().get("records", [])
            created = None
            for rec in records:
                if rec.get("hostname") == hostname and rec.get("type") == "A" and rec.get("destination") == destination_create:
                    created = rec
                    break
            assert created is not None, f"Created record not found in: {records}"
            record_id = int(created["id"])

            # 4) UPDATE
            destination_update = "192.0.2.100"
            update_url = settings.url(f"/api/dns/{domain}/records/{record_id}")
            update_payload = {
                "hostname": hostname,
                "type": "A",
                "destination": destination_update,
            }
            resp = await client.put(update_url, headers=headers, json=update_payload)
            assert resp.status_code == 200, resp.text[:400]

            resp = await client.get(list_url, headers=headers)
            assert resp.status_code == 200, resp.text[:400]
            records = resp.json().get("records", [])
            updated = None
            for rec in records:
                if (
                    rec.get("hostname") == hostname
                    and rec.get("type") == "A"
                    and rec.get("destination") == destination_update
                ):
                    updated = rec
                    break
            assert updated is not None, f"Updated record not found in: {records}"

            # Some backends may implement update as delete+create, changing the record ID.
            effective_record_id = int(updated["id"])

            # 5) DELETE
            delete_url = settings.url(f"/api/dns/{domain}/records/{effective_record_id}")
            resp = await client.delete(delete_url, headers=headers)
            assert resp.status_code == 200, resp.text[:400]

            resp = await client.get(list_url, headers=headers)
            assert resp.status_code == 200, resp.text[:400]
            records = resp.json().get("records", [])
            assert all(int(r.get("id")) != effective_record_id for r in records if r.get("id") is not None)
