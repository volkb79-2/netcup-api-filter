"""Resilience tests: NetcupClient against the mock server in error-injection modes.

Verifies that when the upstream Netcup API misbehaves (HTTP 500, invalid JSON,
empty body, missing response keys), the client always raises NetcupAPIError —
never AttributeError, KeyError, or JSONDecodeError.

Run with: pytest -m upstream_resilience ui_tests/tests/mocks/test_netcup_resilience.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import requests

pytestmark = [pytest.mark.mock_selftest, pytest.mark.upstream_resilience]

# Make the src tree importable when running outside of the normal pytest root.
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from netcup_api_filter.netcup_client import NetcupAPIError, NetcupClient  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client(server) -> NetcupClient:
    return NetcupClient(
        customer_id="123456",
        api_key="test-api-key",
        api_password="test-api-password",
        api_url=server.url,
    )


def _base_url(server) -> str:
    return f"http://{server.host}:{server.port}"


def _set_error_mode(server, mode: str) -> None:
    resp = requests.post(f"{_base_url(server)}/_test/set-error-mode", json={"mode": mode})
    resp.raise_for_status()


def _clear_error_mode(server) -> None:
    requests.post(f"{_base_url(server)}/_test/set-error-mode", json={"mode": "off"})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestUpstreamHttpError:
    def test_upstream_500_raises_netcup_error(self, mock_netcup_api_server):
        """HTTP 500 from upstream → NetcupAPIError, not unhandled exception."""
        _set_error_mode(mock_netcup_api_server, "500")
        try:
            with pytest.raises(NetcupAPIError):
                _client(mock_netcup_api_server).login()
        finally:
            _clear_error_mode(mock_netcup_api_server)


class TestUpstreamBadBody:
    def test_invalid_json_raises_netcup_error(self, mock_netcup_api_server):
        """Non-JSON body from upstream → NetcupAPIError, not JSONDecodeError."""
        _set_error_mode(mock_netcup_api_server, "invalid_json")
        try:
            with pytest.raises(NetcupAPIError):
                _client(mock_netcup_api_server).login()
        finally:
            _clear_error_mode(mock_netcup_api_server)

    def test_empty_body_raises_netcup_error(self, mock_netcup_api_server):
        """Empty body from upstream → NetcupAPIError, not JSONDecodeError."""
        _set_error_mode(mock_netcup_api_server, "empty")
        try:
            with pytest.raises(NetcupAPIError):
                _client(mock_netcup_api_server).login()
        finally:
            _clear_error_mode(mock_netcup_api_server)


class TestUpstreamMissingKeys:
    def test_missing_responsedata_in_login_raises_netcup_error(self, mock_netcup_api_server):
        """success envelope without responsedata → NetcupAPIError, not KeyError."""
        _set_error_mode(mock_netcup_api_server, "missing_keys")
        try:
            with pytest.raises(NetcupAPIError):
                _client(mock_netcup_api_server).login()
        finally:
            _clear_error_mode(mock_netcup_api_server)

    def test_missing_responsedata_in_info_dns_records_raises_netcup_error(self, mock_netcup_api_server):
        """success envelope without responsedata on info_dns_records → NetcupAPIError, not KeyError."""
        client = _client(mock_netcup_api_server)
        # Login succeeds (normal mode)
        client.login()
        # Now inject error for subsequent call
        _set_error_mode(mock_netcup_api_server, "missing_keys")
        try:
            with pytest.raises(NetcupAPIError):
                client.info_dns_records("test.example.com")
        finally:
            _clear_error_mode(mock_netcup_api_server)


class TestErrorModeIsolation:
    def test_reset_restores_normal_behaviour(self, mock_netcup_api_server):
        """After clearing error mode, client succeeds again."""
        _set_error_mode(mock_netcup_api_server, "500")
        with pytest.raises(NetcupAPIError):
            _client(mock_netcup_api_server).login()

        _clear_error_mode(mock_netcup_api_server)
        session_id = _client(mock_netcup_api_server).login()
        assert session_id, "login should succeed after error mode is cleared"
