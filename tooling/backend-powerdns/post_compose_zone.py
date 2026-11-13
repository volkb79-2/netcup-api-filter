#!/usr/bin/env python3
"""Bootstrap the configured PowerDNS zone through the Authoritative HTTP API.

The zone name comes from ``backend_powerdns.zone``. Bootstrap is an idempotent
no-op for an existing zone. New zones are created with explicit SOA content,
an apex nameserver, DNSSEC disabled, and the configured SOA-EDIT-API mode.

The hook runs on the host, outside the service network. It invokes Python
inside the PowerDNS container to call the loopback HTTP API, using the
container's ``POWERDNS_API_KEY`` environment value without placing the key in
the docker command line or logs.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ciu_identity import container_for


logger = logging.getLogger(__name__)

_API_REQUEST_SCRIPT = r"""
import json
import os
import sys
import urllib.error
import urllib.request

base_url, port, method, path, timeout, payload_json = sys.argv[1:]
api_key = os.environ.get("POWERDNS_API_KEY")
if not api_key:
    raise SystemExit("POWERDNS_API_KEY is unavailable in the PowerDNS container")

payload = payload_json.encode("utf-8") if payload_json else None
headers = {"Accept": "application/json", "X-API-Key": api_key}
if payload is not None:
    headers["Content-Type"] = "application/json"
request = urllib.request.Request(
    f"{base_url.rstrip('/')}:{port}{path}",
    data=payload,
    headers=headers,
    method=method,
)
try:
    with urllib.request.urlopen(request, timeout=float(timeout)) as response:
        body = response.read().decode("utf-8", errors="replace")
        status = response.status
except urllib.error.HTTPError as response:
    body = response.read().decode("utf-8", errors="replace")
    status = response.code
print(json.dumps({"status": status, "body": body}))
"""


def _require(value: Any, label: str) -> Any:
    if value in (None, ""):
        raise ValueError(f"[backend-powerdns post hook] Missing required value: {label}")
    return value


def _zone_fqdn(zone: str) -> str:
    normalized = zone.strip().rstrip(".")
    if not normalized:
        raise ValueError("[backend-powerdns post hook] Zone name is empty")
    return f"{normalized}."


def build_zone_collection_path(server_id: str, zone: str) -> str:
    """Build the filtered zone-list endpoint used for idempotency checks."""
    server = quote(server_id, safe="")
    query = urlencode({"zone": _zone_fqdn(zone)})
    return f"/api/v1/servers/{server}/zones?{query}"


def build_zone_payload(zone: str, serial: str, settings: dict[str, Any]) -> dict[str, Any]:
    """Build one complete create request with zone-derived NS and SOA records."""
    zone_name = _zone_fqdn(zone)
    nameserver = f"ns1.{zone_name}"
    hostmaster = f"hostmaster.{zone_name}"
    soa_content = " ".join(
        (
            nameserver,
            hostmaster,
            serial,
            str(_require(settings.get("soa_refresh"), "backend_powerdns.zone_bootstrap.soa_refresh")),
            str(_require(settings.get("soa_retry"), "backend_powerdns.zone_bootstrap.soa_retry")),
            str(_require(settings.get("soa_expire"), "backend_powerdns.zone_bootstrap.soa_expire")),
            str(_require(settings.get("soa_minimum_ttl"), "backend_powerdns.zone_bootstrap.soa_minimum_ttl")),
        )
    )
    return {
        "name": zone_name,
        "kind": "Native",
        "masters": [],
        "nameservers": [nameserver],
        "dnssec": False,
        "api_rectify": False,
        "soa_edit_api": _require(
            settings.get("soa_edit_api"), "backend_powerdns.zone_bootstrap.soa_edit_api"
        ),
        "rrsets": [
            {
                "name": zone_name,
                "type": "SOA",
                "ttl": int(_require(settings.get("soa_ttl"), "backend_powerdns.zone_bootstrap.soa_ttl")),
                "changetype": "REPLACE",
                "records": [{"content": soa_content, "disabled": False}],
            }
        ],
    }


def _docker_exec(container: str, *args: str, timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "exec", container, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _api_request(
    container: str,
    backend_cfg: dict[str, Any],
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    api_cfg = backend_cfg.get("api", {})
    ports = backend_cfg.get("ports", {})
    request_timeout = float(
        _require(api_cfg.get("request_timeout_seconds"), "backend_powerdns.api.request_timeout_seconds")
    )
    exec_timeout = float(
        _require(api_cfg.get("docker_exec_timeout_seconds"), "backend_powerdns.api.docker_exec_timeout_seconds")
    )
    payload_json = json.dumps(payload, separators=(",", ":")) if payload is not None else ""
    result = _docker_exec(
        container,
        "python3",
        "-c",
        _API_REQUEST_SCRIPT,
        str(_require(api_cfg.get("base_url"), "backend_powerdns.api.base_url")),
        str(_require(ports.get("api"), "backend_powerdns.ports.api")),
        method,
        path,
        str(request_timeout),
        payload_json,
        timeout=exec_timeout,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic output"
        raise RuntimeError(f"[backend-powerdns post hook] PowerDNS API transport failed: {detail}")
    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "[backend-powerdns post hook] PowerDNS API helper returned invalid JSON"
        ) from exc
    if not isinstance(response, dict) or "status" not in response or "body" not in response:
        raise RuntimeError("[backend-powerdns post hook] PowerDNS API helper returned an invalid response")
    return response


def _response_error(response: dict[str, Any]) -> str:
    return f"HTTP {response['status']}: {response['body']}"


def _zone_exists(container: str, backend_cfg: dict[str, Any], zone: str) -> bool:
    api_cfg = backend_cfg.get("api", {})
    server_id = str(_require(api_cfg.get("server_id"), "backend_powerdns.api.server_id"))
    response = _api_request(
        container,
        backend_cfg,
        "GET",
        build_zone_collection_path(server_id, zone),
    )
    if response["status"] != 200:
        raise RuntimeError(
            f"[backend-powerdns post hook] PowerDNS zone lookup failed: {_response_error(response)}"
        )
    try:
        zones = json.loads(response["body"])
    except json.JSONDecodeError as exc:
        raise RuntimeError("[backend-powerdns post hook] PowerDNS zone lookup returned invalid JSON") from exc
    if not isinstance(zones, list):
        raise RuntimeError("[backend-powerdns post hook] PowerDNS zone lookup did not return a list")
    expected_name = _zone_fqdn(zone)
    return any(isinstance(item, dict) and item.get("name") == expected_name for item in zones)


def _wait_until_healthy(container: str, service_name: str, api_cfg: dict[str, Any], ctx) -> None:
    readiness_timeout = float(
        _require(api_cfg.get("readiness_timeout_seconds"), "backend_powerdns.api.readiness_timeout_seconds")
    )
    if ctx.wait_healthy is not None:
        if not ctx.wait_healthy(service_name, timeout_s=readiness_timeout):
            raise RuntimeError(
                f"[backend-powerdns post hook] {container} did not become healthy; inspect its container logs"
            )
        return

    probe_timeout = float(
        _require(
            api_cfg.get("readiness_probe_timeout_seconds"),
            "backend_powerdns.api.readiness_probe_timeout_seconds",
        )
    )
    poll_interval = float(
        _require(api_cfg.get("readiness_poll_seconds"), "backend_powerdns.api.readiness_poll_seconds")
    )
    deadline = time.monotonic() + readiness_timeout
    while True:
        result = _docker_exec(container, "pdns_control", "version", timeout=probe_timeout)
        if result.returncode == 0:
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(poll_interval, remaining))
    raise RuntimeError(
        f"[backend-powerdns post hook] {container} did not become healthy; inspect its container logs"
    )


def run(config: dict, ctx) -> dict:
    """Bootstrap the delegated DNS zone (D-007) through the HTTP API."""
    backend_cfg = config.get("backend_powerdns", {})
    if not backend_cfg:
        raise ValueError(
            "[backend-powerdns post hook] backend_powerdns section missing from merged config"
        )

    zone = (backend_cfg.get("zone") or "").strip().rstrip(".")
    if not zone:
        logger.info(
            "topology.dns.delegated_zone is empty; skipping PowerDNS zone bootstrap"
        )
        return {}

    service_name = str(_require(backend_cfg.get("name"), "backend_powerdns.name"))
    container = container_for(ctx, "tooling/backend-powerdns", service_name)
    api_cfg = backend_cfg.get("api", {})
    zone_cfg = backend_cfg.get("zone_bootstrap", {})
    server_id = str(_require(api_cfg.get("server_id"), "backend_powerdns.api.server_id"))
    logger.info("bootstrapping PowerDNS zone %s in %s", zone, container)

    _wait_until_healthy(container, service_name, api_cfg, ctx)
    if _zone_exists(container, backend_cfg, zone):
        logger.info("PowerDNS zone %s already exists; leaving it untouched", zone)
        return {}

    serial_format = str(
        _require(zone_cfg.get("serial_format"), "backend_powerdns.zone_bootstrap.serial_format")
    )
    serial = datetime.now(timezone.utc).strftime(serial_format)
    if not serial.isdigit():
        raise ValueError("[backend-powerdns post hook] configured SOA serial format must produce digits")
    payload = build_zone_payload(zone, serial, zone_cfg)
    response = _api_request(
        container,
        backend_cfg,
        "POST",
        f"/api/v1/servers/{quote(server_id, safe='')}/zones",
        payload,
    )
    if response["status"] not in {200, 201}:
        # A concurrent bootstrap may create the zone after our lookup. Treat
        # that race as success only after the API confirms the zone exists.
        if _zone_exists(container, backend_cfg, zone):
            logger.info("PowerDNS zone %s was created concurrently", zone)
            return {}
        raise RuntimeError(
            f"[backend-powerdns post hook] PowerDNS zone creation failed: {_response_error(response)}"
        )

    logger.info(
        "PowerDNS zone %s created with apex NS %s and explicit SOA serial %s",
        _zone_fqdn(zone),
        payload["nameservers"][0],
        serial,
    )
    return {}


if __name__ == "__main__":
    logger.error("This hook is intended to be run by CIU.")
    raise SystemExit(1)
