"""PowerDNS 5.1 stack config and API bootstrap contracts."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from jinja2 import Environment, StrictUndefined


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "tooling" / "backend-powerdns"
ZONE = "example.invalid"


def _load_zone_hook():
    old_path = sys.path[:]
    spec = importlib.util.spec_from_file_location(
        "naf_powerdns_zone_hook_test", BACKEND / "post_compose_zone.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = old_path
    return module


def _run_config(zone=ZONE):
    return {
        "backend_powerdns": {
            "name": "powerdns",
            "zone": zone,
            "ports": {"api": 8081},
            "api": {
                "base_url": "http://127.0.0.1",
                "server_id": "localhost",
                "request_timeout_seconds": 30,
                "docker_exec_timeout_seconds": 35,
                "readiness_timeout_seconds": 90,
                "readiness_probe_timeout_seconds": 5,
                "readiness_poll_seconds": 2,
                "first_request_retry_attempts": 3,
                "first_request_retry_delay_seconds": 0.5,
            },
            "zone_bootstrap": {
                "serial_format": "%Y%m%d00",
                "soa_ttl": 3600,
                "soa_refresh": 10800,
                "soa_retry": 3600,
                "soa_expire": 604800,
                "soa_minimum_ttl": 3600,
                "soa_edit_api": "DEFAULT",
            },
        }
    }


def _completed(status, body):
    body_text = body if isinstance(body, str) else json.dumps(body)
    return subprocess.CompletedProcess(
        args=["fake-docker-exec"],
        returncode=0,
        stdout=json.dumps({"status": status, "body": body_text}),
        stderr="",
    )


def _install_run_fakes(monkeypatch, hook, responses):
    calls = []
    remaining = iter(responses)

    def fake_docker_exec(container, *argv, timeout):
        calls.append((container, argv, timeout))
        response = next(remaining)
        if isinstance(response, BaseException):
            raise response
        return response

    monkeypatch.setattr(hook, "_docker_exec", fake_docker_exec)
    monkeypatch.setattr(
        hook, "container_for", lambda ctx, stack_dir, service_name: "pdns-container"
    )
    monkeypatch.setattr(hook, "_wait_until_healthy", lambda *args: None)
    return calls


def _call_method_path_payload(call):
    argv = call[1]
    assert argv[0:2] == ("python3", "-c")
    payload = json.loads(argv[8]) if argv[8] else None
    return argv[5], argv[6], payload


def test_powerdns_51_template_renders_api_and_gsqlite_options():
    template = (BACKEND / "pdns-auth.conf.j2").read_text(encoding="utf-8")
    variables = {
        "PDNS_AUTH_API": "yes",
        "POWERDNS_API_KEY": "api-only-test-value",
        "POWERDNS_WEBSERVER_PASSWORD": "webserver-only-test-value",
        "PDNS_AUTH_WEBSERVER": "yes",
        "PDNS_AUTH_WEBSERVER_ADDRESS": "0.0.0.0",
        "PDNS_AUTH_WEBSERVER_PORT": "8081",
        "PDNS_AUTH_WEBSERVER_ALLOW_FROM": "0.0.0.0/0,::/0",
        "PDNS_LAUNCH": "gsqlite3",
        "PDNS_GSQLITE3_DATABASE": "/var/lib/powerdns/pdns.sqlite3",
        "PDNS_GSQLITE3_DNSSEC": "yes",
        "PDNS_LOGLEVEL": "4",
        "PDNS_LOG_DNS_QUERIES": "no",
        "PDNS_LOG_DNS_DETAILS": "no",
        "PDNS_DISABLE_AXFR": "yes",
    }
    rendered = Environment(undefined=StrictUndefined).from_string(template).render(**variables)

    for expected in (
        "api=yes",
        "api-key=api-only-test-value",
        "webserver=yes",
        "webserver-address=0.0.0.0",
        "webserver-port=8081",
        "webserver-allow-from=0.0.0.0/0,::/0",
        "webserver-password=webserver-only-test-value",
        "launch=gsqlite3",
        "gsqlite3-database=/var/lib/powerdns/pdns.sqlite3",
        "gsqlite3-dnssec=yes",
        "disable-axfr=yes",
    ):
        assert expected in rendered.splitlines()
    assert "webserver-password=api-only-test-value" not in rendered.splitlines()
    assert "allow-axfr-ips=" not in rendered


def test_powerdns_compose_uses_the_image_template_entrypoint_for_config():
    compose = (BACKEND / "ciu.compose.yml.j2").read_text(encoding="utf-8")

    assert "- TEMPLATE_FILES={{ backend_powerdns.api.template_name }}" in compose
    assert "- POWERDNS_API_KEY=${POWERDNS_API_KEY:?POWERDNS_API_KEY must be set}" in compose
    assert "- POWERDNS_WEBSERVER_PASSWORD=${POWERDNS_WEBSERVER_PASSWORD:?POWERDNS_WEBSERVER_PASSWORD must be set}" in compose
    assert "- powerdns_webserver_password" in compose
    # startup.py (auth-5.1.5) opens templates.d/<TEMPLATE_FILES entry>.j2; a
    # `.conf.j2` mount target would leave that file missing and crash the start.
    assert "/etc/powerdns/templates.d/{{ backend_powerdns.api.template_name }}.j2:ro" in compose
    assert "{{ backend_powerdns.api.template_name }}.conf.j2" not in compose
    assert "- PDNS_AUTH_API_KEY=${POWERDNS_API_KEY" not in compose
    assert "PDNS_ALLOW_AXFR_IPS" not in compose


def test_powerdns_webserver_password_is_its_own_checkout_secret():
    defaults = (BACKEND / "ciu.defaults.toml.j2").read_text(encoding="utf-8")

    assert (
        'powerdns_api_key = { directive = "GEN_LOCAL:naf/powerdns_api_key", '
        'expose_env = "POWERDNS_API_KEY" }'
    ) in defaults
    assert (
        'powerdns_webserver_password = { directive = "GEN_LOCAL:naf/powerdns_webserver_password", '
        'expose_env = "POWERDNS_WEBSERVER_PASSWORD" }'
    ) in defaults


def test_zone_create_payload_uses_explicit_soa_and_disabled_dnssec():
    hook = _load_zone_hook()
    payload = hook.build_zone_payload(
        ZONE,
        "2026111300",
        {
            "soa_ttl": 3600,
            "soa_refresh": 10800,
            "soa_retry": 3600,
            "soa_expire": 604800,
            "soa_minimum_ttl": 3600,
            "soa_edit_api": "DEFAULT",
        },
    )

    assert payload["name"] == f"{ZONE}."
    assert payload["kind"] == "Native"
    assert payload["nameservers"] == [f"ns1.{ZONE}."]
    assert payload["dnssec"] is False
    assert "api_rectify" not in payload
    assert payload["soa_edit_api"] == "DEFAULT"
    assert payload["rrsets"] == [
        {
            "name": f"{ZONE}.",
            "type": "SOA",
            "ttl": 3600,
            "changetype": "REPLACE",
            "records": [
                {
                    "content": f"ns1.{ZONE}. hostmaster.{ZONE}. 2026111300 10800 3600 604800 3600",
                    "disabled": False,
                }
            ],
        }
    ]


def test_zone_lookup_path_quotes_server_id_and_uses_fqdn_query():
    hook = _load_zone_hook()

    assert hook.build_zone_collection_path("server/id", ZONE) == (
        f"/api/v1/servers/server%2Fid/zones?zone={ZONE}."
    )


def test_run_existing_zone_issues_one_get_and_no_post(monkeypatch):
    hook = _load_zone_hook()
    calls = _install_run_fakes(
        monkeypatch,
        hook,
        [_completed(200, [{"name": f"{ZONE}."}])],
    )

    assert hook.run(_run_config(), SimpleNamespace(wait_healthy=None)) == {}
    assert [_call_method_path_payload(call)[0] for call in calls] == ["GET"]


def test_run_missing_zone_gets_then_posts_the_built_payload(monkeypatch):
    hook = _load_zone_hook()
    calls = _install_run_fakes(
        monkeypatch,
        hook,
        [_completed(200, []), _completed(201, "")],
    )

    assert hook.run(_run_config(), SimpleNamespace(wait_healthy=None)) == {}
    method_path_payload = [_call_method_path_payload(call) for call in calls]
    assert [call[0] for call in method_path_payload] == ["GET", "POST"]
    payload = method_path_payload[1][2]
    serial = payload["rrsets"][0]["records"][0]["content"].split()[2]
    assert payload == hook.build_zone_payload(
        ZONE, serial, _run_config()["backend_powerdns"]["zone_bootstrap"]
    )


def test_run_post_409_returns_success_only_after_get_confirms_zone(monkeypatch):
    hook = _load_zone_hook()
    calls = _install_run_fakes(
        monkeypatch,
        hook,
        [
            _completed(200, []),
            _completed(409, "zone already exists"),
            _completed(200, [{"name": f"{ZONE}."}]),
        ],
    )

    assert hook.run(_run_config(), SimpleNamespace(wait_healthy=None)) == {}
    assert [_call_method_path_payload(call)[0] for call in calls] == [
        "GET",
        "POST",
        "GET",
    ]


def test_run_post_500_raises_when_confirmation_lookup_is_empty(monkeypatch):
    hook = _load_zone_hook()
    calls = _install_run_fakes(
        monkeypatch,
        hook,
        [_completed(200, []), _completed(500, "server error"), _completed(200, [])],
    )

    with pytest.raises(RuntimeError, match="zone creation failed: HTTP 500"):
        hook.run(_run_config(), SimpleNamespace(wait_healthy=None))
    assert [_call_method_path_payload(call)[0] for call in calls] == [
        "GET",
        "POST",
        "GET",
    ]


def test_run_never_puts_api_key_value_in_recorded_argv(monkeypatch):
    hook = _load_zone_hook()
    fake_api_key = "pdns51-fake-api-key-for-argv-test"
    monkeypatch.setenv("POWERDNS_API_KEY", fake_api_key)
    calls = _install_run_fakes(
        monkeypatch,
        hook,
        [_completed(200, [{"name": f"{ZONE}."}])],
    )

    hook.run(_run_config(), SimpleNamespace(wait_healthy=None))
    assert all(fake_api_key not in repr(call[1]) for call in calls)


def test_api_transport_rejects_malformed_helper_response_shape(monkeypatch):
    hook = _load_zone_hook()
    config = _run_config()["backend_powerdns"]
    malformed = subprocess.CompletedProcess(
        args=["fake-docker-exec"],
        returncode=0,
        stdout='{"status":"200","body":[]}',
        stderr="",
    )
    monkeypatch.setattr(hook, "_docker_exec", lambda *args, **kwargs: malformed)

    with pytest.raises(
        RuntimeError,
        match="invalid response; expected an integer status and string body",
    ):
        hook._api_request(
            "pdns-container", config, "GET", "/api/v1/servers/localhost/zones"
        )


def test_run_retries_initial_transport_failure_using_configured_fake_sleep(monkeypatch):
    hook = _load_zone_hook()
    calls = _install_run_fakes(
        monkeypatch,
        hook,
        [
            subprocess.CompletedProcess(
                args=["fake-docker-exec"], returncode=1, stdout="", stderr="connection refused"
            ),
            _completed(200, [{"name": f"{ZONE}."}]),
        ],
    )
    sleeps = []
    monkeypatch.setattr(hook.time, "sleep", sleeps.append)
    config = _run_config()
    config["backend_powerdns"]["api"]["first_request_retry_delay_seconds"] = 0.25

    assert hook.run(config, SimpleNamespace(wait_healthy=None)) == {}
    assert [_call_method_path_payload(call)[0] for call in calls] == ["GET", "GET"]
    assert sleeps == [0.25]


def test_api_transport_timeout_has_clear_error(monkeypatch):
    hook = _load_zone_hook()
    config = _run_config()["backend_powerdns"]

    def timeout_exec(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["fake-docker-exec"], timeout=kwargs["timeout"])

    monkeypatch.setattr(hook, "_docker_exec", timeout_exec)
    with pytest.raises(
        hook.PowerDNSAPITransportError,
        match="API transport timed out after 35s",
    ):
        hook._api_request(
            "pdns-container", config, "GET", "/api/v1/servers/localhost/zones"
        )


def test_health_probe_timeout_has_clear_error(monkeypatch):
    hook = _load_zone_hook()
    api_config = _run_config()["backend_powerdns"]["api"]

    def timeout_exec(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["fake-docker-exec"], timeout=kwargs["timeout"])

    monkeypatch.setattr(hook, "_docker_exec", timeout_exec)
    with pytest.raises(RuntimeError, match="health probe timed out after 5s"):
        hook._wait_until_healthy(
            "pdns-container", "powerdns", api_config, SimpleNamespace(wait_healthy=None)
        )


def test_run_does_not_retry_transport_failure_after_initial_lookup(monkeypatch):
    hook = _load_zone_hook()
    calls = _install_run_fakes(
        monkeypatch,
        hook,
        [
            _completed(200, []),
            subprocess.CompletedProcess(
                args=["fake-docker-exec"], returncode=1, stdout="", stderr="connection reset"
            ),
        ],
    )
    sleeps = []
    monkeypatch.setattr(hook.time, "sleep", sleeps.append)

    with pytest.raises(hook.PowerDNSAPITransportError, match="API transport failed"):
        hook.run(_run_config(), SimpleNamespace(wait_healthy=None))
    assert [_call_method_path_payload(call)[0] for call in calls] == ["GET", "POST"]
    assert sleeps == []
