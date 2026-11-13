"""PowerDNS 5.1 stack config and API bootstrap contracts."""

import importlib.util
import sys
from pathlib import Path

from jinja2 import Environment, StrictUndefined


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "tooling" / "backend-powerdns"


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


def test_powerdns_51_template_renders_api_and_gsqlite_options():
    template = (BACKEND / "pdns-auth.conf.j2").read_text(encoding="utf-8")
    variables = {
        "PDNS_AUTH_API": "yes",
        "POWERDNS_API_KEY": "unit-test-value",
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
        "PDNS_ALLOW_AXFR_IPS": "",
    }
    rendered = Environment(undefined=StrictUndefined).from_string(template).render(**variables)

    for expected in (
        "api=yes",
        "api-key=unit-test-value",
        "webserver=yes",
        "webserver-address=0.0.0.0",
        "webserver-port=8081",
        "webserver-allow-from=0.0.0.0/0,::/0",
        "webserver-password=unit-test-value",
        "launch=gsqlite3",
        "gsqlite3-database=/var/lib/powerdns/pdns.sqlite3",
        "gsqlite3-dnssec=yes",
        "disable-axfr=yes",
    ):
        assert expected in rendered.splitlines()


def test_powerdns_compose_uses_the_image_template_entrypoint_for_config():
    compose = (BACKEND / "ciu.compose.yml.j2").read_text(encoding="utf-8")

    assert "- TEMPLATE_FILES={{ backend_powerdns.api.template_name }}" in compose
    assert "- POWERDNS_API_KEY=${POWERDNS_API_KEY:?POWERDNS_API_KEY must be set}" in compose
    assert "/etc/powerdns/templates.d/{{ backend_powerdns.api.template_name }}.conf.j2:ro" in compose
    assert "- PDNS_AUTH_API_KEY=${POWERDNS_API_KEY" not in compose


def test_zone_create_payload_uses_explicit_soa_and_disabled_dnssec():
    hook = _load_zone_hook()
    payload = hook.build_zone_payload(
        "example.invalid",
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

    assert payload["name"] == "example.invalid."
    assert payload["kind"] == "Native"
    assert payload["nameservers"] == ["ns1.example.invalid."]
    assert payload["dnssec"] is False
    assert payload["api_rectify"] is False
    assert payload["soa_edit_api"] == "DEFAULT"
    assert payload["rrsets"] == [
        {
            "name": "example.invalid.",
            "type": "SOA",
            "ttl": 3600,
            "changetype": "REPLACE",
            "records": [
                {
                    "content": "ns1.example.invalid. hostmaster.example.invalid. 2026111300 10800 3600 604800 3600",
                    "disabled": False,
                }
            ],
        }
    ]


def test_zone_lookup_path_quotes_server_id_and_uses_fqdn_query():
    hook = _load_zone_hook()

    assert hook.build_zone_collection_path("server/id", "example.invalid") == (
        "/api/v1/servers/server%2Fid/zones?zone=example.invalid."
    )
