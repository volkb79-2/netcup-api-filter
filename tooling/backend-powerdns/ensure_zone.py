"""Ensure a PowerDNS zone exists (idempotent).

Config-driven: all inputs come from environment variables.

Required env vars:
- POWERDNS_API_URL
- POWERDNS_API_KEY
- DNS_TEST_DOMAIN (zone name)

Optional:
- POWERDNS_SERVER_ID (default: localhost)
- POWERDNS_NS_HOSTNAME (fallback: PUBLIC_FQDN)

This script is intended for local/dev test setups where live DNS verification
expects the DNS_TEST_DOMAIN zone to already exist in PowerDNS.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import httpx


def _require_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise SystemExit(f"Missing required env var: {name}")
    return value


def _ensure_trailing_dot(name: str) -> str:
    name = name.strip()
    return name if name.endswith(".") else f"{name}."


def main() -> int:
    api_url = _require_env("POWERDNS_API_URL").rstrip("/")
    api_key = _require_env("POWERDNS_API_KEY")
    zone = _require_env("DNS_TEST_DOMAIN").strip().rstrip(".")

    server_id = (os.environ.get("POWERDNS_SERVER_ID") or "localhost").strip()
    ns_hostname = (os.environ.get("POWERDNS_NS_HOSTNAME") or os.environ.get("PUBLIC_FQDN") or "").strip().rstrip(".")
    if not ns_hostname:
        raise SystemExit("Missing nameserver hostname: set POWERDNS_NS_HOSTNAME or PUBLIC_FQDN")

    zone_name = _ensure_trailing_dot(zone)
    ns_fqdn = _ensure_trailing_dot(ns_hostname)

    client = httpx.Client(
        base_url=api_url,
        headers={"X-API-Key": api_key},
        timeout=10.0,
    )

    zone_url = f"/api/v1/servers/{server_id}/zones/{zone_name}"

    try:
        resp = client.get(zone_url)
        if resp.status_code == 200:
            print(f"[ok] Zone already exists: {zone_name}")
            return 0
        if resp.status_code != 404:
            print(f"[error] Unexpected response checking zone ({resp.status_code}): {resp.text}", file=sys.stderr)
            return 2

        payload: dict[str, Any] = {
            "name": zone_name,
            "kind": "Native",
            "masters": [],
            "nameservers": [ns_fqdn],
        }

        create_url = f"/api/v1/servers/{server_id}/zones"
        create_resp = client.post(create_url, json=payload)
        if create_resp.status_code not in (200, 201):
            print(
                f"[error] Failed creating zone {zone_name} ({create_resp.status_code}): {create_resp.text}",
                file=sys.stderr,
            )
            return 3

        print(f"[ok] Created zone: {zone_name} (NS={ns_fqdn})")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
