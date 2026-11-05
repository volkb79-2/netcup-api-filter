#!/usr/bin/env python3
"""tooling/app-local — post_compose hook (D-007 app-side backend seed).

Seeds the delegated DNS zone (topology.dns.delegated_zone) into the app's own
database as a manageable domain root, once the app container is up: a
platform-owned PowerDNS BackendService pointing at the INTERNAL PowerDNS API
(app-to-app, same docker network — NEVER the public/traefik URL), plus a
ManagedDomainRoot for the zone bound to it, so a user/system owns the zone
and can create hosts under it.

This is the app-side analog of tooling/backend-powerdns/post_compose_zone.py:
that hook makes PowerDNS authoritative for the zone; this hook makes the app
aware the zone exists. The zone name is NOT invented here — it comes
entirely from config["topology"]["dns"]["delegated_zone"] (D-007's global
topology fact, env-ref NAF_DELEGATED_DNS_ZONE, committed default empty).
Pure no-op whenever that value is empty.

Runs the actual seed via `docker exec` into the ALREADY-RUNNING app
container, invoking a throwaway one-shot Python process that talks directly
to the app's SQLite database over SQLAlchemy — this hook never writes files
into the app container (that's a build artifact, not something a post_compose
hook should touch). The one-shot process mirrors build_deployment.py's own
initialize_database(): a minimal Flask+SQLAlchemy shell around
netcup_api_filter.bootstrap.seeding.seed_delegated_zone_domain_root(), NOT
the full create_app() factory (which needs SECRET_KEY/session/rate-limit
config this hook has no business supplying, and would duplicate what the
running gunicorn process already did at startup).

The seed function itself is idempotent (see its docstring for the exact
BackendService/ManagedDomainRoot shape); reruns of this hook are safe.

MULTI-DOMAIN note: one PowerDNS instance serves MANY zones. naf managing
several domains means naf creating additional zones via the pdns HTTP API as
users add domain roots — that runtime path is the backends/ wire-up
(D-002(a)/naf-P20), NOT this hook. This hook only ever establishes the ONE
dev/test domain root for the currently-delegated zone (the seed function's
shape is compatible with more roots being added later against the same
BackendService — see its docstring).

See nyxloom-trove/decisions.md D-007.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import Any


def _require(value: Any, label: str) -> Any:
    if value in (None, ""):
        raise ValueError(f"[app-local post hook] Missing required value: {label}")
    return value


def _docker_exec(
    container: str,
    *args: str,
    timeout: int = 30,
    env: dict[str, str] | None = None,
    secret_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """`docker exec` helper.

    ``env`` values travel on the command line (non-secret only). ``secret_env`` values are
    passed as ``-e NAME`` (no value) with the value in this subprocess's own environment,
    which docker reads — so a secret never appears in ``ps``/``/proc/<pid>/cmdline``.
    """
    cmd = ["docker", "exec"]
    if env:
        for key, value in env.items():
            cmd += ["-e", f"{key}={value}"]
    proc_env = None
    if secret_env:
        proc_env = {**os.environ, **secret_env}
        for key in secret_env:
            cmd += ["-e", key]
    cmd += [container, *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=proc_env)


# One-shot seed script executed INSIDE the app container via `docker exec`.
# Deliberately a minimal Flask+SQLAlchemy shell (matches
# build_deployment.py's initialize_database()) rather than the full
# create_app() factory — this only needs DB access. cwd is the container's
# configured working_dir (app_local.deploy_dir, e.g. "deploy-local"), which
# `docker exec` inherits by default, so the relative "src" import path and
# the default netcup_filter.db location both resolve the same way the
# running gunicorn process resolves them (see passenger_wsgi.py's
# NETCUP_FILTER_DB_PATH auto-detection).
_SEED_SNIPPET = """
import os, sys
sys.path.insert(0, "src")
from flask import Flask
from netcup_api_filter import database

db_path = os.environ.get("NETCUP_FILTER_DB_PATH") or os.path.join(os.getcwd(), "netcup_filter.db")
app = Flask(__name__)
app.config["SECRET_KEY"] = "app-local-seed-temp-key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + db_path
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
database.db.init_app(app)

with app.app_context():
    database.db.create_all()
    from netcup_api_filter.bootstrap.seeding import seed_delegated_zone_domain_root
    root = seed_delegated_zone_domain_root(
        os.environ["NAF_SEED_DELEGATED_ZONE"],
        api_url=os.environ["NAF_SEED_POWERDNS_API_URL"],
        api_key=os.environ["NAF_SEED_POWERDNS_API_KEY"],
    )
    database.db.session.commit()
    print(f"[seed] domain root: {root.root_domain if root else '(no-op)'}")
"""


def run(config: dict, ctx) -> dict:
    """Post-compose hook: seed the delegated-zone domain root into the app DB (D-007).

    Pure side-effect; returns {}.
    """
    dns_cfg = (config.get("topology") or {}).get("dns", {})
    zone = (dns_cfg.get("delegated_zone") or "").strip().rstrip(".")
    if not zone:
        print(
            "[INFO] topology.dns.delegated_zone is empty (NAF_DELEGATED_DNS_ZONE "
            "not set) — skipping app-side domain-root seed. This is the expected "
            "no-op state until an operator delegates a real zone.",
            flush=True,
        )
        return {}

    deploy_cfg = config.get("deploy", {})
    project_name = _require(deploy_cfg.get("project_name"), "deploy.project_name")
    environment_tag = _require(deploy_cfg.get("environment_tag"), "deploy.environment_tag")

    app_cfg = config.get("app_local", {})
    app_service = _require(app_cfg.get("name"), "app_local.name")
    app_container = f"{project_name}-{environment_tag}-{app_service}"

    # Internal PowerDNS URL, derived the same way backend-powerdns's own hook
    # derives its container name — NOT read from .env.services (that file is
    # bash-sourced by build_deployment.py/shell scripts, not by this Python
    # hook process). Mirrors .env.services' POWERDNS_API_URL_INTERNAL
    # construction exactly (same container-name + port convention).
    backend_cfg = config.get("backend_powerdns", {})
    pdns_service = _require(backend_cfg.get("name"), "backend_powerdns.name")
    pdns_api_port = _require((backend_cfg.get("ports") or {}).get("api"), "backend_powerdns.ports.api")
    pdns_container = f"{project_name}-{environment_tag}-{pdns_service}"
    powerdns_api_url_internal = f"http://{pdns_container}:{pdns_api_port}"

    # The API key is a SECRET — never part of ciu's rendered config (see
    # backend-powerdns/ciu.compose.yml.j2, which takes it straight from the
    # shell via ${POWERDNS_API_KEY:?...} at compose-interpolation time). This
    # hook process must have it in its own environment for the same reason
    # `docker compose up` for backend-powerdns needs it: both run from the
    # same operator shell that sourced .env before `ciu up`.
    powerdns_api_key = os.environ.get("POWERDNS_API_KEY")
    if not powerdns_api_key:
        raise RuntimeError(
            "[app-local post hook] POWERDNS_API_KEY not set in the environment "
            "(source .env before `ciu up` — see .env.defaults). Required to "
            "seed the delegated-zone BackendService; not invented (D-007)."
        )

    print(f"[INFO] Seeding delegated zone '{zone}' as a domain root in {app_container}", flush=True)

    # Wait for the app's own healthcheck (GET /admin/login == 200) before
    # exec'ing into it — post_compose runs right after `docker compose up
    # -d`, which races gunicorn/Flask startup (S9.3/CIU-4 readiness probe,
    # same reasoning as post_compose_zone.py).
    if ctx.wait_healthy is not None:
        if not ctx.wait_healthy(app_service, timeout_s=90.0):
            raise RuntimeError(
                f"[app-local post hook] {app_container} did not become "
                f"healthy within 90s — see `docker logs {app_container}`"
            )
    else:
        # Bare/unit construction (HookContext docstring) — fall back to a
        # short manual poll so the hook still works outside the engine.
        for _ in range(30):
            check = _docker_exec(app_container, "true", timeout=5)
            if check.returncode == 0:
                break
            time.sleep(2)

    seed_env = {
        "NAF_SEED_DELEGATED_ZONE": zone,
        "NAF_SEED_POWERDNS_API_URL": powerdns_api_url_internal,
    }
    result = _docker_exec(
        app_container,
        "/opt/tester-venv/bin/python", "-c", _SEED_SNIPPET,
        timeout=60,
        env=seed_env,
        secret_env={"NAF_SEED_POWERDNS_API_KEY": powerdns_api_key},
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"[app-local post hook] seed script failed in {app_container}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    print(result.stdout.strip() or "[INFO] Delegated-zone domain root seed complete", flush=True)

    return {}


if __name__ == "__main__":
    print("[ERROR] This hook is intended to be run by CIU.", file=sys.stderr)
    raise SystemExit(1)
