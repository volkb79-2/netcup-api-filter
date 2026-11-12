#!/usr/bin/env python3
"""Resolve service identities through ciu instead of rebuilding Compose names.

Post-compose hooks use this module after containers exist. CIU-118's JSON
document is the authority for names, Compose projects and networks; callers
must not concatenate deploy.project_name/environment_tag themselves.
"""

from __future__ import annotations

import json
import subprocess

# Identities are resolved against the profile that declares EVERY naf stack
# (`[deploy.profiles.full]` in ciu.global.defaults.toml.j2), never against the
# caller's selection: a hook of app-local needs PowerDNS's and Mailpit's names even
# when this checkout selects a narrower profile (`ciu.instance.service_profiles`,
# CIU_SERVICES_PROFILE, `--profile test`). Without `--profile`, `ciu resolve` uses
# that narrower default selection and fails closed for a peer outside it.
# tests/test_ciu_identity_contract.py keeps the profile covering every stack.
IDENTITY_PROFILE = "full"


def resolve_container(
    stack: str,
    service: str,
    *,
    profiles: tuple[str, ...] = (IDENTITY_PROFILE,),
    repo_root: str | None = None,
    runner=subprocess.run,
) -> str:
    """Return the exact rendered container identity for one stack service."""
    command = ["ciu", "resolve", "--stack", stack, "--service", service, "--json"]
    for profile in profiles:
        command += ["--profile", profile]
    if repo_root:
        command += ["--root-folder", repo_root]
    result = runner(command, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(
            f"[ciu identity] `ciu resolve` failed for {stack}:{service}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    try:
        document = json.loads(result.stdout)
        container = document["resolved"]["identities"][stack][service]["container_name"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise RuntimeError(
            f"[ciu identity] no resolved identity for {stack}:{service}"
        ) from exc
    if not isinstance(container, str) or not container:
        raise RuntimeError(f"[ciu identity] empty container identity for {stack}:{service}")
    return container


def container_for(ctx, stack: str, service: str) -> str:
    """HookContext adapter used by naf's post-compose hooks.

    Deliberately ignores ``ctx.selected_profiles``: a peer stack's identity does
    not depend on which stacks this invocation deploys (see IDENTITY_PROFILE).
    """
    return resolve_container(
        stack,
        service,
        repo_root=getattr(ctx, "repo_root", None),
    )
