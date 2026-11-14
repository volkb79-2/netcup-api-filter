from types import SimpleNamespace

import pytest

from ui_tests.tests.journeys import j3_comprehensive_states as j3
from ui_tests.tests.journeys.state_matrix import APITestSpec


@pytest.mark.asyncio
async def test_api_tester_expands_hostname_from_created_realm(monkeypatch):
    requests = []

    class FakeResponse:
        status_code = 201

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, url, *, headers, json):
            requests.append((url, headers, json))
            return FakeResponse()

    monkeypatch.setattr(j3, "settings", SimpleNamespace(base_url="http://app.test"))
    monkeypatch.setattr(j3.httpx, "AsyncClient", FakeClient)
    tester = j3.APITester(SimpleNamespace(created_tokens={
        "token-full": {
            "token_name": "token-full-random",
            "token_value": "test-token-value",
            "realm_fqdn": "managed-random.example.com",
        }
    }))

    result = await tester.run_test(APITestSpec(
        token_name="token-full",
        operation="create",
        record_type="TXT",
        hostname="validation.{realm}",
        expected_status=201,
        description="create within the token's generated realm",
    ))

    assert result["passed"] is True
    assert requests[0][0] == "http://app.test/api/dns/example.com/records"
    assert requests[0][2]["hostname"] == "validation.managed-random.example.com"


@pytest.mark.asyncio
async def test_expired_token_case_skips_when_read_only_db_confirms_no_expiry(monkeypatch):
    def unexpected_client(*args, **kwargs):
        pytest.fail("an unexpired token must not be sent as the expired-token oracle")

    monkeypatch.setattr(j3, "settings", SimpleNamespace(base_url="http://app.test"))
    monkeypatch.setattr(j3.httpx, "AsyncClient", unexpected_client)
    monkeypatch.setattr(j3.verification, "db_available", lambda: True)
    monkeypatch.setattr(j3.verification, "get_token", lambda **kwargs: {"expires_at": None})
    tester = j3.APITester(SimpleNamespace(created_tokens={
        "token-expired": {
            "token_name": "token-expired-random",
            "token_value": "test-token-value",
            "realm_fqdn": "k8s-random.example.com",
        }
    }))

    result = await tester.run_test(APITestSpec(
        token_name="token-expired",
        operation="read",
        record_type="A",
        hostname="{realm}",
        expected_status=401,
        description="expired token oracle",
    ))

    assert result["status"] == "skipped"
    assert "DB confirms this token is not expired" in result["reason"]


@pytest.mark.asyncio
async def test_api_tester_fails_when_required_token_was_not_created(monkeypatch):
    monkeypatch.setattr(j3, "settings", SimpleNamespace(base_url="http://app.test"))
    tester = j3.APITester(SimpleNamespace(created_tokens={}))

    result = await tester.run_test(APITestSpec(
        token_name="token-ddns",
        operation="update",
        record_type="A",
        hostname="{realm}",
        expected_status=200,
        description="DDNS update requires its created token",
    ))

    assert result["status"] == "failed"
    assert tester.results == [result]


@pytest.mark.asyncio
async def test_api_tester_records_request_errors_as_failed_results(monkeypatch):
    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def get(self, url, *, headers):
            raise ConnectionError("fake API connection failure")

    monkeypatch.setattr(j3, "settings", SimpleNamespace(base_url="http://app.test"))
    monkeypatch.setattr(j3.httpx, "AsyncClient", FakeClient)
    tester = j3.APITester(SimpleNamespace(created_tokens={
        "token-readonly": {
            "token_name": "token-readonly-random",
            "token_value": "test-token-value",
            "realm_fqdn": "managed-random.example.com",
        }
    }))

    result = await tester.run_test(APITestSpec(
        token_name="token-readonly",
        operation="read",
        record_type="A",
        hostname="{realm}",
        expected_status=200,
        description="a transport error must count as an API test failure",
    ))

    failed = sum(
        1 for recorded in tester.results if recorded.get("status") in {"failed", "error"}
    )
    assert result["status"] == "error"
    assert tester.results == [result]
    assert failed == 1
