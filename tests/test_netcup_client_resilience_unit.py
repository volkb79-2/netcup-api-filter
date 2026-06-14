"""
Unit tests for netcup_client._make_request() and callers under bad upstream responses.

All tests assert that the client raises NetcupAPIError — never AttributeError, KeyError,
or JSONDecodeError — regardless of what the upstream sends back.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from netcup_api_filter.netcup_client import NetcupAPIError, NetcupClient


def _make_client():
    return NetcupClient(
        customer_id="123",
        api_key="key",
        api_password="pass",
        api_url="http://mock-api/",
    )


def _mock_response(body, status_code=200):
    """Build a mock requests.Response with the given body (str or bytes) and status."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(
            response=resp
        )
    raw = body.encode() if isinstance(body, str) else body
    resp.json = MagicMock(side_effect=lambda: json.loads(raw))
    return resp


# ---------------------------------------------------------------------------
# _make_request — JSON parse failures
# ---------------------------------------------------------------------------

class TestMakeRequestBadJson:
    def test_invalid_json_raises_netcup_error(self):
        resp = _mock_response("not-json")
        with patch("requests.post", return_value=resp):
            with pytest.raises(NetcupAPIError, match="Invalid JSON"):
                _make_client()._make_request("login", {})

    def test_empty_body_raises_netcup_error(self):
        resp = _mock_response("")
        with patch("requests.post", return_value=resp):
            with pytest.raises(NetcupAPIError, match="Invalid JSON"):
                _make_client()._make_request("login", {})

    def test_html_error_page_raises_netcup_error(self):
        resp = _mock_response("<html><body>Bad Gateway</body></html>")
        with patch("requests.post", return_value=resp):
            with pytest.raises(NetcupAPIError, match="Invalid JSON"):
                _make_client()._make_request("login", {})


# ---------------------------------------------------------------------------
# _make_request — wrong JSON shape (valid JSON, wrong type)
# ---------------------------------------------------------------------------

class TestMakeRequestWrongShape:
    def test_json_array_raises_netcup_error(self):
        resp = _mock_response("[]")
        with patch("requests.post", return_value=resp):
            with pytest.raises(NetcupAPIError, match="Unexpected response shape"):
                _make_client()._make_request("login", {})

    def test_json_null_raises_netcup_error(self):
        resp = _mock_response("null")
        with patch("requests.post", return_value=resp):
            with pytest.raises(NetcupAPIError, match="Unexpected response shape"):
                _make_client()._make_request("login", {})

    def test_json_scalar_raises_netcup_error(self):
        resp = _mock_response("42")
        with patch("requests.post", return_value=resp):
            with pytest.raises(NetcupAPIError, match="Unexpected response shape"):
                _make_client()._make_request("login", {})

    def test_json_string_raises_netcup_error(self):
        resp = _mock_response('"just a string"')
        with patch("requests.post", return_value=resp):
            with pytest.raises(NetcupAPIError, match="Unexpected response shape"):
                _make_client()._make_request("login", {})


# ---------------------------------------------------------------------------
# _make_request — HTTP-level errors
# ---------------------------------------------------------------------------

class TestMakeRequestHttpErrors:
    def test_http_500_raises_netcup_error(self):
        resp = _mock_response('{"status":"error"}', status_code=500)
        with patch("requests.post", return_value=resp):
            with pytest.raises(NetcupAPIError):
                _make_client()._make_request("login", {})

    def test_timeout_raises_netcup_error(self):
        with patch("requests.post", side_effect=requests.Timeout("timed out")):
            with pytest.raises(NetcupAPIError, match="Request failed"):
                _make_client()._make_request("login", {})

    def test_connection_error_raises_netcup_error(self):
        with patch("requests.post", side_effect=requests.ConnectionError("refused")):
            with pytest.raises(NetcupAPIError, match="Request failed"):
                _make_client()._make_request("login", {})


# ---------------------------------------------------------------------------
# _make_request — API-level error envelope
# ---------------------------------------------------------------------------

class TestMakeRequestApiErrorEnvelope:
    def test_api_error_status_raises_netcup_error(self):
        body = json.dumps({"status": "error", "longmessage": "bad domain", "statuscode": 4013})
        resp = _mock_response(body)
        with patch("requests.post", return_value=resp):
            with pytest.raises(NetcupAPIError, match="bad domain"):
                _make_client()._make_request("infoDnsRecords", {})

    def test_api_error_without_message_raises_netcup_error(self):
        body = json.dumps({"status": "error"})
        resp = _mock_response(body)
        with patch("requests.post", return_value=resp):
            with pytest.raises(NetcupAPIError):
                _make_client()._make_request("infoDnsRecords", {})


# ---------------------------------------------------------------------------
# Public methods — missing keys in a success envelope
# ---------------------------------------------------------------------------

class TestPublicMethodsMissingKeys:
    def _success_resp(self, responsedata):
        body = json.dumps({"status": "success", "responsedata": responsedata})
        return _mock_response(body)

    def _bare_success_resp(self):
        body = json.dumps({"status": "success"})
        return _mock_response(body)

    def test_login_missing_responsedata_raises(self):
        with patch("requests.post", return_value=self._bare_success_resp()):
            with pytest.raises(NetcupAPIError, match="Missing key"):
                _make_client().login()

    def test_login_missing_apisessionid_raises(self):
        with patch("requests.post", return_value=self._success_resp({})):
            with pytest.raises(NetcupAPIError, match="Missing key"):
                _make_client().login()

    def test_info_dns_zone_missing_responsedata_raises(self):
        client = _make_client()
        client.session_id = "fake-session"
        with patch("requests.post", return_value=self._bare_success_resp()):
            with pytest.raises(NetcupAPIError, match="Missing key"):
                client.info_dns_zone("example.com")

    def test_info_dns_records_missing_responsedata_raises(self):
        client = _make_client()
        client.session_id = "fake-session"
        with patch("requests.post", return_value=self._bare_success_resp()):
            with pytest.raises(NetcupAPIError, match="Missing key"):
                client.info_dns_records("example.com")

    def test_info_dns_records_missing_dnsrecords_raises(self):
        client = _make_client()
        client.session_id = "fake-session"
        with patch("requests.post", return_value=self._success_resp({})):
            with pytest.raises(NetcupAPIError, match="Missing key"):
                client.info_dns_records("example.com")

    def test_update_dns_records_missing_responsedata_raises(self):
        client = _make_client()
        client.session_id = "fake-session"
        with patch("requests.post", return_value=self._bare_success_resp()):
            with pytest.raises(NetcupAPIError, match="Missing key"):
                client.update_dns_records("example.com", [])
