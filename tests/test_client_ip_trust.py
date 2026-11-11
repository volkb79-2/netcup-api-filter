"""Backend-truth checks that client-IP helpers use post-middleware remote_addr."""
from flask import jsonify, request

from netcup_api_filter.api.admin import _get_client_ip
from netcup_api_filter.api.ddns_protocols import get_client_ip as ddns_get_client_ip


def _register_ip_probe(app):
    """Attach a throwaway route that reports what the two helpers resolve.

    Registered directly on the test app instance (not on admin.py or
    ddns_protocols.py) so production code is not touched just to make it
    observable in a test.
    """
    @app.route("/__test_ip_probe__")
    def _ip_probe():
        return jsonify(
            remote_addr=request.remote_addr,
            admin_ip=_get_client_ip(),
            ddns_ip=ddns_get_client_ip(),
        )


def test_forwarded_xff_is_ignored_when_no_proxy_hops_are_declared(app):
    """The repository default trusts no proxy headers; the socket peer wins."""
    _register_ip_probe(app)
    client = app.test_client()

    forged_leftmost = "203.0.113.99"
    appended_peer = "198.51.100.7"
    proxy_socket_addr = "192.0.2.10"

    resp = client.get(
        "/__test_ip_probe__",
        headers={"X-Forwarded-For": f"{forged_leftmost}, {appended_peer}"},
        environ_overrides={"REMOTE_ADDR": proxy_socket_addr},
    )
    data = resp.get_json()

    assert data["remote_addr"] == proxy_socket_addr
    assert data["admin_ip"] == proxy_socket_addr
    assert data["ddns_ip"] == proxy_socket_addr
    assert data["admin_ip"] != forged_leftmost
    assert data["ddns_ip"] != forged_leftmost
    assert data["admin_ip"] != appended_peer
    assert data["ddns_ip"] != appended_peer


def test_no_xff_header_falls_back_to_remote_addr(app):
    """Without any X-Forwarded-For header, both helpers still resolve to
    the plain remote_addr (no regression to the no-proxy-header path)."""
    _register_ip_probe(app)
    client = app.test_client()

    direct_addr = "192.0.2.55"

    resp = client.get(
        "/__test_ip_probe__",
        environ_overrides={"REMOTE_ADDR": direct_addr},
    )
    data = resp.get_json()

    assert data["remote_addr"] == direct_addr
    assert data["admin_ip"] == direct_addr
    assert data["ddns_ip"] == direct_addr
