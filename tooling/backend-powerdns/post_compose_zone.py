#!/usr/bin/env python3
"""tooling/backend-powerdns — post_compose hook (S9.1 / S9.4).

Bootstraps the delegated DNS zone (D-007) inside PowerDNS after `docker
compose up` brings the auth server online. The zone name is NOT invented
here — it comes entirely from `[backend_powerdns].zone`, which
ciu.defaults.toml.j2 flattens from the GLOBAL `{{ topology.dns.delegated_zone }}`
fact (env-ref `NAF_DELEGATED_DNS_ZONE`, committed default empty). This hook is
a pure no-op whenever that value is empty — it never guesses a zone or an SOA.
See nyxloom-trove/decisions.md D-007.

Talks to PowerDNS via `pdnsutil` INSIDE the container (docker exec), not the
HTTP API: the admin API port is intentionally NOT published to the host (see
ciu.compose.yml.j2's header) — it's reachable only via the project network or
traefik's ingress network, neither of which this hook (running as the ciu
host process) is attached to. `pdnsutil` talks straight to the gsqlite3
backend, so no network hop is needed.

Idempotent: if the zone already exists, this is a full no-op — nothing is
touched, including the SOA — so reruns can never regress an existing zone's
serial or content. SOA/NS content is set ONLY at first creation, derived
from the zone itself:
    NS:   <zone>.  IN  NS  ns1.<zone>.        (via `pdnsutil create-zone ZONE NSNAME`)
    SOA:  ns1.<zone>. hostmaster.<zone>. <serial> 10800 3600 604800 3600

This mirrors the old setup-zones.sh convention, minus any hardcoded
vxxu.de/ns1 default — those were exactly the invented values the previous
ciu-powerdns conversion attempt was rejected for.

VALIDATED 2026-07-21 against a live pdns-auth-48: create-zone + replace-rrset @ SOA
CLI docs, not yet exercised against a running PowerDNS container (see the
report from the conversion that added this file).

Returns {} (pure side-effect hook — no config values to persist).
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ciu_identity import container_for


def _require(value: Any, label: str) -> Any:
    if value in (None, ""):
        raise ValueError(f"[backend-powerdns post hook] Missing required value: {label}")
    return value


def _docker_exec(container: str, *args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "exec", container, *args],
        capture_output=True, text=True, timeout=timeout,
    )


def _zone_exists(container: str, zone: str) -> bool:
    """True iff `pdnsutil list-zone <zone>` succeeds.

    pdnsutil exits 0 and prints the zone's records if it exists; non-zero
    ("Zone '<zone>' not found") if not.
    """
    result = _docker_exec(container, "pdnsutil", "list-zone", zone)
    return result.returncode == 0


def run(config: dict, ctx) -> dict:
    """Post-compose hook: bootstrap the delegated zone (D-007).

    Pure side-effect; returns {}.
    """
    backend_cfg = config.get("backend_powerdns", {})
    if not backend_cfg:
        raise ValueError(
            "[backend-powerdns post hook] backend_powerdns section missing from merged config"
        )

    zone = (backend_cfg.get("zone") or "").strip().rstrip(".")
    if not zone:
        print(
            "[INFO] topology.dns.delegated_zone is empty (NAF_DELEGATED_DNS_ZONE "
            "not set) — skipping zone bootstrap. This is the expected no-op "
            "state until an operator delegates a real zone.",
            flush=True,
        )
        return {}

    service_name = _require(backend_cfg.get("name"), "backend_powerdns.name")
    container = container_for(ctx, "tooling/backend-powerdns", service_name)

    print(f"[INFO] Bootstrapping PowerDNS zone '{zone}' in {container}", flush=True)

    # Wait for the auth server's own healthcheck (pdns_control version) before
    # touching pdnsutil — post_compose runs right after `docker compose up -d`,
    # which races the daemon's startup (S9.3/CIU-4 readiness probe).
    if ctx.wait_healthy is not None:
        if not ctx.wait_healthy(service_name, timeout_s=90.0):
            raise RuntimeError(
                f"[backend-powerdns post hook] {container} did not become "
                f"healthy within 90s — see `docker logs {container}`"
            )
    else:
        # Bare/unit construction (HookContext docstring) — fall back to a
        # short manual poll so the hook still works outside the engine.
        for _ in range(30):
            check = _docker_exec(container, "pdns_control", "version", timeout=5)
            if check.returncode == 0:
                break
            time.sleep(2)

    if _zone_exists(container, zone):
        print(f"[INFO] Zone '{zone}' already exists — no-op (SOA left untouched)", flush=True)
        return {}

    ns_fqdn = f"ns1.{zone}"
    hostmaster = f"hostmaster.{zone}"

    # `create-zone ZONE NSNAME` creates the zone AND an apex NS record for
    # NSNAME in one step (pdnsutil docs).
    create = _docker_exec(container, "pdnsutil", "create-zone", zone, ns_fqdn, timeout=30)
    if create.returncode != 0:
        # Race: something else created it between our check and this call.
        # Treat "already exists" as success; anything else is a real failure.
        if "already exists" in (create.stdout + create.stderr).lower():
            print(f"[INFO] Zone '{zone}' created concurrently — no-op", flush=True)
            return {}
        raise RuntimeError(
            f"[backend-powerdns post hook] pdnsutil create-zone {zone} failed: "
            f"{create.stderr.strip() or create.stdout.strip()}"
        )
    print(f"[INFO] Zone '{zone}' created (apex NS -> {ns_fqdn}.)", flush=True)

    # Explicit SOA content, derived from the zone (D-007) — replaces the pdns
    # image's built-in "a.misconfigured.dns.server.invalid" placeholder SOA
    # that create-zone leaves behind by default. Only done at first creation
    # (see the no-op branch above) so reruns never touch the serial.
    serial = time.strftime("%Y%m%d00")
    soa_content = f"{ns_fqdn}. {hostmaster}. {serial} 10800 3600 604800 3600"
    soa = _docker_exec(
        container, "pdnsutil", "replace-rrset", zone, "@", "SOA", "3600", soa_content, timeout=30,
    )
    if soa.returncode != 0:
        raise RuntimeError(
            f"[backend-powerdns post hook] pdnsutil replace-rrset SOA for {zone} failed: "
            f"{soa.stderr.strip() or soa.stdout.strip()}"
        )
    print(f"[INFO] SOA set: {soa_content}", flush=True)

    print(f"[INFO] Zone '{zone}' bootstrap complete", flush=True)
    return {}


if __name__ == "__main__":
    print("[ERROR] This hook is intended to be run by CIU.", file=sys.stderr)
    raise SystemExit(1)
