#!/usr/bin/env python3
"""Translate a `ciu resolve --json` document into `.env.services` assignments.

Container identities come from the JSON. The public PowerDNS URL is assembled
from ciu's rendered global topology facts, never from PROJECT_TAG/ENV_TAG or a
service-name convention in a script. Each identity the document lacks is
reported on stderr and its variables are unset; a malformed document fails.
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

# Container-side ports, equal to each stack's declared default (`ciu resolve`
# reports no port for these services). Mailpit's port and webroot are read
# together from its stack defaults below.
PORTS = {
    "MOCK_NETCUP_API_HOST": 80,    # tooling/netcup-api-mock netcup_api_mock.port
    "MOCK_GEOIP_HOST": 80,         # tooling/geoip-mock     geoip_mock.port
    "POWERDNS_HOST": 8081,         # tooling/backend-powerdns backend_powerdns.ports.api
}

MAILPIT_DEFAULTS_PATH = (
    Path(__file__).resolve().parent / "mailpit" / "ciu.defaults.toml.j2"
)

# Every variable derived from one identity. A missing identity UNSETS all of them,
# so a stale export from an earlier shell can never masquerade as current.
DERIVED = {
    "MAILPIT_HOST": ("MAILPIT_HOST", "MAILPIT_URL", "MAILPIT_API_URL"),
    "MOCK_NETCUP_API_HOST": ("MOCK_NETCUP_API_HOST", "MOCK_NETCUP_API_URL"),
    "MOCK_GEOIP_HOST": ("MOCK_GEOIP_HOST", "MOCK_GEOIP_API_URL"),
    "POWERDNS_HOST": ("POWERDNS_HOST", "POWERDNS_API_URL_INTERNAL"),
}


def _identities(document: dict) -> dict:
    try:
        identities = document["resolved"]["identities"]
    except (KeyError, TypeError) as exc:
        raise ValueError("ciu resolve document has no resolved.identities") from exc
    if not isinstance(identities, dict):
        raise ValueError("ciu resolve resolved.identities is not a mapping")
    return identities


def _container(identities: dict, stack: str, service: str) -> str | None:
    row = (identities.get(stack) or {}).get(service)
    if not isinstance(row, dict):
        return None
    name = row.get("container_name")
    return name if isinstance(name, str) and name else None


def _mailpit_web_settings() -> tuple[int, str]:
    """Read Mailpit's internal HTTP port and URL prefix from its stack config."""
    try:
        with MAILPIT_DEFAULTS_PATH.open("rb") as stream:
            mailpit = tomllib.load(stream)["mailpit"]
        web_port = mailpit["web_port"]
        web_root = mailpit["web_root"]
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(
            f"cannot read mailpit.web_port and mailpit.web_root from {MAILPIT_DEFAULTS_PATH}"
        ) from exc

    if not isinstance(web_port, int) or web_port < 1:
        raise ValueError("mailpit.web_port must be a positive integer")
    if (
        not isinstance(web_root, str)
        or (web_root and not web_root.startswith("/"))
        or web_root.endswith("/")
    ):
        raise ValueError(
            "mailpit.web_root must be empty or an absolute path without a trailing slash"
        )
    return web_port, web_root


def build_assignments(
    document: dict, global_config: Path
) -> tuple[dict[str, str], list[str]]:
    """(assignments, missing identities as `stack:service`).

    Exports every identity the document resolves. A missing one is reported, not
    fatal: the consumer that needs it fails fast on the unset variable
    (`build_deployment.py`, `${VAR:?}` in shell, the e2e preflight).
    """
    identities = _identities(document)
    values: dict[str, str] = {}
    missing: list[str] = []
    for env_name, (stack, service) in SERVICES.items():
        host = _container(identities, stack, service)
        if host is None:
            missing.append(f"{stack}:{service}")
            continue
        values[env_name] = host
    if "MAILPIT_HOST" in values:
        web_port, web_root = _mailpit_web_settings()
        base = f"http://{values['MAILPIT_HOST']}:{web_port}{web_root}"
        values["MAILPIT_URL"] = base
        values["MAILPIT_API_URL"] = f"{base}/api/v1"
    if "MOCK_NETCUP_API_HOST" in values:
        values["MOCK_NETCUP_API_URL"] = (
            f"http://{values['MOCK_NETCUP_API_HOST']}:{PORTS['MOCK_NETCUP_API_HOST']}"
        )
    if "MOCK_GEOIP_HOST" in values:
        values["MOCK_GEOIP_API_URL"] = (
            f"http://{values['MOCK_GEOIP_HOST']}:{PORTS['MOCK_GEOIP_HOST']}"
        )
    if "POWERDNS_HOST" in values:
        values["POWERDNS_API_URL_INTERNAL"] = (
            f"http://{values['POWERDNS_HOST']}:{PORTS['POWERDNS_HOST']}"
        )
    values["POWERDNS_API_URL"] = ""

    if global_config.is_file():
        with global_config.open("rb") as stream:
            global_facts = tomllib.load(stream)
        topology = global_facts.get("topology") or {}
        public_fqdn = ((topology.get("external") or {}).get("public_fqdn") or "").strip()
        pdns_subdomain = ((topology.get("dns") or {}).get("pdns_subdomain") or "").strip()
        if public_fqdn and pdns_subdomain:
            values["POWERDNS_API_URL"] = f"https://{pdns_subdomain}.{public_fqdn}"
    return values, missing


def unset_names(missing: list[str]) -> list[str]:
    """Every variable derived from a missing identity."""
    by_identity = {f"{stack}:{service}": env for env, (stack, service) in SERVICES.items()}
    return [name for item in missing for name in DERIVED[by_identity[item]]]


def render_shell(values: dict[str, str], unset: tuple[str, ...] | list[str] = ()) -> str:
    lines = [f"export {key}={shlex.quote(value)}" for key, value in values.items()]
    if unset:
        lines.append("unset " + " ".join(unset))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--global-config", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        document = json.load(sys.stdin)
        values, missing = build_assignments(document, args.global_config)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"[ERROR] cannot derive .env.services from ciu facts: {exc}", file=sys.stderr)
        return 2
    if missing:
        print(
            "[WARN] .env.services: no ciu identity for "
            + ", ".join(missing)
            + "; their variables stay unset (a consumer that needs one fails on it)",
            file=sys.stderr,
        )
    print(render_shell(values, unset_names(missing)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
