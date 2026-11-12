#!/usr/bin/env python3
"""Side-effect-free validation for app-local's rendered stack facts.

`ciu check` and `ciu up` call this before any container exists. It rejects the
global names that used to make a second checkout collide, and requires the
canonical public origin and proxy trust to be explicit rather than inferred.
"""

from __future__ import annotations

from urllib.parse import urlsplit


def run(config: dict, ctx) -> dict:
    """No-op execution hook; validation happens in `validate_config`."""
    return {}


def validate_config(config: dict, ctx) -> list:
    findings: list = []
    deploy = config.get("deploy") or {}
    app = config.get("app_local") or {}
    external = app.get("external") or {}
    topology = config.get("topology") or {}
    instance = deploy.get("environment_tag")
    project = deploy.get("project_name")
    public_fqdn = ((topology.get("external") or {}).get("public_fqdn") or "").strip()
    subdomain = (external.get("subdomain") or "").strip()
    public_base_url = (app.get("public_base_url") or "").strip()
    hops = app.get("trusted_proxy_hops")

    if not instance:
        findings.append("deploy.environment_tag is missing")
    if not project:
        findings.append("deploy.project_name is missing")
    if instance and project and subdomain != f"{project}-{instance}":
        findings.append(
            "app_local.external.subdomain must be instance-derived "
            f"(expected '{project}-{instance}', got {subdomain!r})"
        )
    if not public_fqdn:
        findings.append("topology.external.public_fqdn is required by app-local")
    if not public_base_url:
        findings.append("app_local.public_base_url is missing")
    else:
        parsed = urlsplit(public_base_url)
        if parsed.scheme != "https" or not parsed.hostname:
            findings.append("app_local.public_base_url must be an https URL with a host")
        elif public_fqdn and parsed.hostname != f"{subdomain}.{public_fqdn}":
            findings.append(
                "app_local.public_base_url must match the derived frontend host "
                f"({subdomain}.{public_fqdn})"
            )
    if hops != 0:
        findings.append(
            "app_local.trusted_proxy_hops must be 0 until the hop chain is measured "
            "(WP4b-2/WP5); app-local sits behind host traefik with no trusted hop"
        )
    if "powerdns_api_key" not in (app.get("secrets") or {}):
        findings.append("app_local.secrets.powerdns_api_key is not declared")
    return findings
