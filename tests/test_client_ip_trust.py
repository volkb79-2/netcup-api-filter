"""
Backend-truth tests for spoofable X-Forwarded-For client-IP resolution.

app.py installs ProxyFix(app.wsgi_app, x_for=1, ...), which normalizes
request.remote_addr to the trusted (rightmost) X-Forwarded-For hop before
Flask ever sees the request. api/admin.py::_get_client_ip and
api/ddns_protocols.py::get_client_ip must both simply trust
request.remote_addr rather than re-parsing the raw header and taking the
attacker-controlled leftmost value.

These tests exercise the real WSGI stack (via the test client) so that
ProxyFix actually runs -- pushing a request context directly (e.g.
app.test_request_context()) would bypass the ProxyFix middleware and not
prove anything about the fix.
"""
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


def test_forged_leftmost_xff_is_not_trusted(app):
    """A forged leftmost X-Forwarded-For hop must not win over the
    ProxyFix-normalized remote_addr (O1)."""
    _register_ip_probe(app)
    client = app.test_client()

    forged_leftmost = "203.0.113.99"  # attacker-supplied, must be ignored
    real_peer = "198.51.100.7"        # appended by the trusted reverse proxy
    proxy_socket_addr = "127.0.0.1"   # raw WSGI REMOTE_ADDR (the proxy itself)

    resp = client.get(
        "/__test_ip_probe__",
        headers={"X-Forwarded-For": f"{forged_leftmost}, {real_peer}"},
        environ_overrides={"REMOTE_ADDR": proxy_socket_addr},
    )
    data = resp.get_json()

    # Sanity: ProxyFix (x_for=1) did normalize remote_addr to the trusted
    # hop. If this fails, the x_for count assumption this fix relies on no
    # longer holds and the test itself (not just the fix) is invalid.
    assert data["remote_addr"] == real_peer
    assert data["remote_addr"] != proxy_socket_addr

    # The actual oracle: both helpers must resolve to the trusted peer,
    # never to the attacker-controlled leftmost XFF value.
    assert data["admin_ip"] == real_peer
    assert data["ddns_ip"] == real_peer
    assert data["admin_ip"] != forged_leftmost
    assert data["ddns_ip"] != forged_leftmost


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
