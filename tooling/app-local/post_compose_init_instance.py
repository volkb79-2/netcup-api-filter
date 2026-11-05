#!/usr/bin/env python3
"""tooling/app-local — post_compose hook: init-once of THIS app instance.

Shape copied from dstdns's infra hooks (readiness probe, then idempotent init). A `ciu up` must
NOT change state of an initialized instance: the hook only initializes what is missing. To change
the bootstrap credential, `ciu clean` the stack's volumes and `up` fresh:

1. wait until the app container is healthy (ctx.wait_healthy — the app's own
   healthcheck; the app has already created its bootstrap admin from the mounted
   ciu secret on first boot, see bootstrap/admin.py);
2. `docker exec` the app package's own initializer inside the running container:
   ``python -m netcup_api_filter.bootstrap init --mock-...``. On an uninitialized
   database it creates the bootstrap admin from the secret; on an initialized one it
   adds no second admin and rewrites no password. It points outgoing mail at the
   mailpit stack. The hook never writes
   files into the container and never sees the password: the container reads it
   from /run/secrets itself;
3. print WHERE the generated credential lives (the ciu store path), never the value.

Everything comes from the merged ciu config (``config``) and the HookContext; there
are no defaults here. ``build_init_argv`` and ``run`` are pure enough to unit-test
with a fake ctx and a fake runner (tests/test_app_local_init_hook.py), because ciu
stacks cannot be brought up from a managed worktree (CIU-176).
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from typing import Any

PASSWORD_SECRET = "bootstrap_admin_password"
HEALTH_TIMEOUT_S = 120.0


def _require(mapping: dict, dotted: str) -> Any:
    node: Any = mapping
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node or node[part] in (None, ""):
            raise ValueError(f"[app-local init hook] missing required config value: {dotted}")
        node = node[part]
    return node


def app_container(config: dict) -> str:
    return "-".join((
        str(_require(config, "deploy.project_name")),
        str(_require(config, "deploy.environment_tag")),
        str(_require(config, "app_local.name")),
    ))


def mailpit_host(config: dict) -> str:
    return "-".join((
        str(_require(config, "deploy.project_name")),
        str(_require(config, "deploy.environment_tag")),
        str(_require(config, "mailpit.name")),
    ))


def build_init_argv(config: dict) -> list[str]:
    """The exact `docker exec` argv of the in-container initializer."""
    return [
        "docker", "exec",
        "-e", f"PYTHONPATH={_require(config, 'app_local.init_pythonpath')}",
        app_container(config),
        str(_require(config, "app_local.init_python")),
        "-m", "netcup_api_filter.bootstrap", "init",
        "--mock-smtp-host", mailpit_host(config),
        "--mock-smtp-port", str(_require(config, "mailpit.smtp_port")),
        "--mock-from-email", str(_require(config, "app_local.mail.from_email")),
        "--mock-admin-email", str(_require(config, "app_local.mail.admin_email")),
    ]


def run(config: dict, ctx, *, runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> dict:
    service = str(_require(config, "app_local.name"))
    container = app_container(config)
    if ctx.wait_healthy is None:
        raise RuntimeError("[app-local init hook] no readiness probe: this hook runs inside `ciu up` only")
    if not ctx.wait_healthy(service, timeout_s=HEALTH_TIMEOUT_S):
        raise RuntimeError(
            f"[app-local init hook] {container} did not become healthy within "
            f"{HEALTH_TIMEOUT_S:.0f}s — see `docker logs {container}`"
        )

    result = runner(build_init_argv(config), capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(
            f"[app-local init hook] init failed in {container} (exit {result.returncode}): "
            f"{(result.stderr or result.stdout).strip()}"
        )
    lines = [line for line in (result.stdout or "").splitlines() if line.strip()]
    try:
        report = json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"[app-local init hook] unexpected init output: {result.stdout!r}") from exc

    password_path = ctx.secret_file(PASSWORD_SECRET)
    print(
        f"[INFO] {container}: bootstrap admin '{report['admin_username']}' {report['admin_action']}; "
        f"its password is the ciu secret '{PASSWORD_SECRET}' at {password_path} (value not shown)",
        flush=True,
    )
    return {}


if __name__ == "__main__":
    print("[ERROR] This hook is intended to be run by CIU.", file=sys.stderr)
    raise SystemExit(1)
