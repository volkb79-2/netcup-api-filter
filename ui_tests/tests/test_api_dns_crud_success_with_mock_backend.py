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


def _mock_base_url() -> str | None:
    base = (os.environ.get("MOCK_NETCUP_API_URL") or "").strip()
    return base or None


def _mock_endpoint_url() -> str | None:
    base = _mock_base_url()
    if not base:
        return None
    return f"{base}/run/webservice/servers/endpoint.php"


async def _mock_is_reachable(base_url: str) -> bool:
    """HTTP-ping the mock Netcup API so we never rewrite the deployment's global
    netcup_config toward a mock that is actually down.

    The gate "MOCK_NETCUP_API_URL is set" is NOT sufficient on its own:
    run-local-tests.sh sources .env.services unconditionally, so the var is
    always populated even when ``--with-mocks`` was not used. Without a real
    reachability check this test would silently poison the global config and
    break every subsequent DNS test.
    """
    health_url = f"{base_url.rstrip('/')}/health"
    try:
        async with httpx.AsyncClient(verify=False, timeout=3.0) as client:
            resp = await client.get(health_url)
        return resp.status_code == 200
    except Exception:
        return False


async def _read_current_netcup_config(browser) -> dict[str, str]:
    """Read the currently-saved Netcup API config from the admin form fields.

    The config_netcup.html template pre-populates every field (including the
    password inputs) with the stored values, so we can capture the prior config
    here and restore it after the test instead of leaving the deployment pointed
    at the mock with no teardown.
    """
    await workflows.open_admin_netcup_config(browser)
    return await browser.evaluate(
        """
        () => {
            const val = (sel) => {
                const el = document.querySelector(sel);
                return el ? (el.value || "") : "";
            };
            return {
                customer_id: val('input[name="customer_id"]'),
                api_key: val('input[name="api_key"]'),
                api_password: val('input[name="api_password"]'),
                api_url: val('input[name="api_url"]'),
                timeout: val('input[name="timeout"]'),
            };
        }
        """
    )


async def test_dns_api_crud_success_path_with_mock_backend(active_profile):
    mock_base = _mock_base_url()
    mock_api_url = _mock_endpoint_url()
    if not mock_api_url or not mock_base:
        pytest.skip("MOCK_NETCUP_API_URL not set; run ./run-local-tests.sh --with-mocks")

    # Do not mutate the deployment's global config unless the mock is actually
    # reachable; otherwise we'd poison netcup_config while mocks are down.
    if not await _mock_is_reachable(mock_base):
        pytest.skip(
            f"Mock Netcup API not reachable at {mock_base}/health; "
            "run ./run-local-tests.sh --with-mocks"
        )

    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)

        # Capture the deployment's current Netcup config so we can restore it in
        # teardown (this test rewrites the GLOBAL config Setting toward the mock).
        prior_config = await _read_current_netcup_config(browser)

        try:
            # Configure app to use mock Netcup API.
            await workflows.admin_configure_netcup_api(
                browser=browser,
                customer_id=str(MOCK_CUSTOMER_ID),
                api_key=MOCK_API_KEY,
                api_password=MOCK_API_PASSWORD,
                api_url=mock_api_url,
            )

            await _run_crud_assertions(active_profile)
        finally:
            # Restore the previous global config so other tests are not affected.
            await _restore_netcup_config(browser, prior_config)


async def _restore_netcup_config(browser, prior_config: dict[str, str]) -> None:
    """Re-apply a previously captured Netcup config via the admin form.

    The form requires customer_id/api_key/api_password, so only restore when we
    actually captured non-empty credentials; otherwise leave a best-effort log
    instead of submitting an invalid form.
    """
    if not (prior_config.get("customer_id") and prior_config.get("api_key")
            and prior_config.get("api_password")):
        # Nothing meaningful to restore (deployment had no prior credentials).
        return
    await workflows.admin_configure_netcup_api(
        browser=browser,
        customer_id=prior_config["customer_id"],
        api_key=prior_config["api_key"],
        api_password=prior_config["api_password"],
        api_url=prior_config.get("api_url") or "",
        timeout=str(prior_config.get("timeout") or "30"),
    )


async def _run_crud_assertions(active_profile):
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
