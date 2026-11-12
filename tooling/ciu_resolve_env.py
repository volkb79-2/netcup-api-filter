#!/usr/bin/env python3
"""Translate a `ciu resolve --json` document into `.env.services` assignments.

Container identities and the internal network come from the JSON. The public
PowerDNS URL is assembled from ciu's rendered global topology facts, never from
PROJECT_TAG/ENV_TAG or a service-name convention in a script.
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
import tomllib
from pathlib import Path


SERVICES = {
    "MAILPIT_HOST": ("tooling/mailpit", "mailpit"),
    "MOCK_NETCUP_API_HOST": ("tooling/netcup-api-mock", "mock-netcup-api"),
    "MOCK_GEOIP_HOST": ("tooling/geoip-mock", "mock-geoip"),
    "POWERDNS_HOST": ("tooling/backend-powerdns", "powerdns"),
}


def _identity(document: dict, stack: str, service: str) -> dict:
    try:
        row = document["resolved"]["identities"][stack][service]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"ciu resolve document has no identity for {stack}:{service}") from exc
    if not isinstance(row, dict) or not row.get("container_name"):
        raise ValueError(f"ciu resolve identity for {stack}:{service} has no container_name")
    return row


def build_assignments(document: dict, global_config: Path) -> dict[str, str]:
    hosts = {
        env_name: _identity(document, stack, service)["container_name"]
        for env_name, (stack, service) in SERVICES.items()
    }
    values = {
        **hosts,
        "MAILPIT_URL": f"http://{hosts['MAILPIT_HOST']}:8025/mailpit",
        "MAILPIT_API_URL": f"http://{hosts['MAILPIT_HOST']}:8025/mailpit/api/v1",
        "MOCK_NETCUP_API_URL": f"http://{hosts['MOCK_NETCUP_API_HOST']}:80",
        "MOCK_GEOIP_API_URL": f"http://{hosts['MOCK_GEOIP_HOST']}:80",
        "POWERDNS_API_URL_INTERNAL": f"http://{hosts['POWERDNS_HOST']}:8081",
        "POWERDNS_API_URL": "",
    }

    if global_config.is_file():
        with global_config.open("rb") as stream:
            global_facts = tomllib.load(stream)
        topology = global_facts.get("topology") or {}
        public_fqdn = ((topology.get("external") or {}).get("public_fqdn") or "").strip()
        pdns_subdomain = ((topology.get("dns") or {}).get("pdns_subdomain") or "").strip()
        if public_fqdn and pdns_subdomain:
            values["POWERDNS_API_URL"] = f"https://{pdns_subdomain}.{public_fqdn}"
    return values


def render_shell(values: dict[str, str]) -> str:
    return "\n".join(f"export {key}={shlex.quote(value)}" for key, value in values.items())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--global-config", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        document = json.load(sys.stdin)
        values = build_assignments(document, args.global_config)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"[ERROR] cannot derive .env.services from ciu facts: {exc}", file=sys.stderr)
        return 2
    print(render_shell(values))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
