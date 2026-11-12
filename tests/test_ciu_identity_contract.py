"""Drift guards for per-checkout ciu identity and resolved service names."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import tomllib
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
TOOLING = REPO / "tooling"
ENV_TAG_TOKEN = "{{ deploy.environment_tag }}"


def test_traefik_routers_services_and_middlewares_are_instance_derived():
    """Global names such as naf-app/naf-guard would collide across checkouts."""
    compose_templates = sorted(TOOLING.glob("*/ciu.compose.yml.j2"))
    assert compose_templates
    failures: list[str] = []
    for path in compose_templates:
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for kind, name in re.findall(
                r"traefik\.http\.(routers|services|middlewares)\.(.+?)"
                r"\.(?:rule=|entrypoints=|loadbalancer\.server\.port=|middlewares=|basicauth\.users=)",
                line,
            ):
                if ENV_TAG_TOKEN not in name:
                    failures.append(
                        f"{path.relative_to(REPO)}:{line_no}: {kind} {name!r} "
                        "is not derived from deploy.environment_tag"
                    )
    assert not failures, "\n".join(failures)

    app_defaults = tomllib.loads(
        (TOOLING / "app-local" / "ciu.defaults.toml.j2").read_text(encoding="utf-8")
    )
    assert app_defaults["app_local"]["external"]["subdomain"] == "naf-$INSTANCE_ID"


def test_every_checkout_uses_the_ciu_instance_identity_and_declares_worktree_artifacts():
    globals_doc = tomllib.loads(
        (REPO / "ciu.global.defaults.toml.j2").read_text(encoding="utf-8")
    )
    assert globals_doc["deploy"]["environment_tag"] == "$INSTANCE_ID"
    assert globals_doc["topology"]["dns"]["pdns_subdomain"] == "naf-pdns-$INSTANCE_ID"
    assert "build" in globals_doc["ciu"]["user_tables"]

    ignored = (REPO / ".gitignore").read_text(encoding="utf-8")
    for pattern in (
        "ciu.worktree-instance.json",
        "**/.ciu.worktree-instance.json.*.tmp",
        "**/.ciu.global.instance.toml.j2.*.tmp",
    ):
        assert pattern in ignored


def test_scripts_do_not_rebuild_container_names_from_deploy_tags():
    """Hooks, release scripts and shell consumers must read ciu identities."""
    checked = [
        REPO / ".env.services",
        REPO / "run-gate.toml",
        REPO / "build_deployment.py",
        REPO / "scripts" / "build_webhosting_tarball.py",
    ]
    checked += sorted(TOOLING.rglob("*.py"))
    concatenation_patterns = (
        re.compile(r"f\"\{project_name\}-\{environment_tag\}-"),
        re.compile(r"\$\{PROJECT_TAG\}(?:-\$\{ENV_TAG\}|.*\$\{ENV_TAG\})"),
    )
    failures = [
        f"{path.relative_to(REPO)}:{line_no}: {line.strip()}"
        for path in checked
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        for pattern in concatenation_patterns
        if pattern.search(line)
    ]
    assert not failures, "\n".join(failures)

    assert "ciu resolve --json" in (REPO / ".env.services").read_text(encoding="utf-8")
    release_builder = (REPO / "scripts" / "build_webhosting_tarball.py").read_text(
        encoding="utf-8"
    )
    assert "resolve_container(" in release_builder
    for hook_path in (
        TOOLING / "app-local" / "post_compose_init_instance.py",
        TOOLING / "app-local" / "post_compose_seed_domain.py",
        TOOLING / "backend-powerdns" / "post_compose_zone.py",
    ):
        assert "container_for(" in hook_path.read_text(encoding="utf-8")

    legacy_identity_fields = re.compile(
        r'["\'](?:deploy\.)?(?:project_name|environment_tag)["\']'
    )
    script_failures = [
        f"{path.relative_to(REPO)}:{line_no}: {line.strip()}"
        for path in checked
        if path.suffix in {".py", ".sh"}
        and path.name != "pre_compose_validate.py"
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if not line.lstrip().startswith("#") and legacy_identity_fields.search(line)
    ]
    assert not script_failures, "\n".join(script_failures)

    for compose in sorted(TOOLING.glob("*/ciu.compose.yml.j2")):
        for line_no, line in enumerate(compose.read_text(encoding="utf-8").splitlines(), 1):
            if "container_name:" in line:
                assert ENV_TAG_TOKEN in line, (
                    f"{compose.relative_to(REPO)}:{line_no}: explicit container_name "
                    "must be instance-derived"
                )


def test_ciu_identity_helper_uses_resolve_and_fails_closed():
    spec = importlib.util.spec_from_file_location(
        "naf_ciu_identity", TOOLING / "ciu_identity.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    calls = []

    def resolved(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({
                "resolved": {
                    "identities": {
                        "tooling/mailpit": {
                            "mailpit": {"container_name": "naf-instance42-mailpit"}
                        }
                    }
                },
                "schema_version": 1,
            }),
            stderr="",
        )

    assert module.resolve_container(
        "tooling/mailpit",
        "mailpit",
        profiles=("full",),
        repo_root="/repo",
        runner=resolved,
    ) == "naf-instance42-mailpit"
    assert calls[0][0] == [
        "ciu",
        "resolve",
        "--stack",
        "tooling/mailpit",
        "--service",
        "mailpit",
        "--profile",
        "full",
        "--root-folder",
        "/repo",
        "--json",
    ]

    def failed(command, **kwargs):
        return subprocess.CompletedProcess(command, 2, "", "no rendered identity")

    try:
        module.resolve_container("tooling/mailpit", "mailpit", runner=failed)
    except RuntimeError as exc:
        assert "no rendered identity" in str(exc)
    else:
        raise AssertionError("missing ciu identity did not fail closed")


def test_powerdns_key_is_generated_locally_and_never_literal():
    backend = tomllib.loads(
        (TOOLING / "backend-powerdns" / "ciu.defaults.toml.j2").read_text(encoding="utf-8")
    )
    app = tomllib.loads(
        (TOOLING / "app-local" / "ciu.defaults.toml.j2").read_text(encoding="utf-8")
    )
    backend_secret = backend["backend_powerdns"]["secrets"]["powerdns_api_key"]
    assert backend_secret["directive"] == "GEN_LOCAL:naf/powerdns_api_key"
    assert backend_secret["expose_env"] == "POWERDNS_API_KEY"
    assert (
        app["app_local"]["secrets"]["powerdns_api_key"]["directive"]
        == "GEN_LOCAL:naf/powerdns_api_key"
    )
    assert "POWERDNS_API_KEY=" not in (REPO / ".env.defaults").read_text(encoding="utf-8")

    assignment = re.compile(
        r"^\s*(?:export\s+)?POWERDNS_API_KEY\s*=\s*(?!\$\{|$)([^\s#]+)",
        re.MULTILINE,
    )
    scanned = [REPO / ".env", REPO / ".env.defaults", REPO / ".env.services"]
    failures = [
        f"{path.relative_to(REPO)}: literal {match.group(1)!r}"
        for path in scanned
        if path.is_file()
        for match in assignment.finditer(path.read_text(encoding="utf-8"))
    ]
    assert not failures, "\n".join(failures)


def test_app_local_proxy_and_public_origin_are_explicit_and_fail_fast():
    hook_path = TOOLING / "app-local" / "pre_compose_validate.py"
    spec = importlib.util.spec_from_file_location("naf_pre_compose_validate", hook_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    valid = {
        "deploy": {"environment_tag": "instance42"},
        "topology": {"external": {"public_fqdn": "example.test"}},
        "app_local": {
            "trusted_proxy_hops": 0,
            "public_base_url": "https://naf-instance42.example.test",
            "external": {"subdomain": "naf-instance42"},
            "secrets": {"powerdns_api_key": {"directive": "GEN_LOCAL:naf/powerdns_api_key"}},
        },
    }
    assert module.validate_config(valid, None) == []

    pre_change = {
        **valid,
        "app_local": {
            "trusted_proxy_hops": 1,
            "public_base_url_scheme": "https",
            "external": {"subdomain": "naf"},
            "secrets": {"powerdns_api_key": {"directive": "GEN_LOCAL:naf/powerdns_api_key"}},
        },
    }
    findings = module.validate_config(pre_change, None)
    assert any("instance-derived" in finding for finding in findings)
    assert any("trusted_proxy_hops" in finding for finding in findings)
    assert any("public_base_url" in finding for finding in findings)


def test_env_services_translator_uses_resolved_container_names(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "naf_ciu_resolve_env", TOOLING / "ciu_resolve_env.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    document = {
        "resolved": {
            "identities": {
                "tooling/mailpit": {"mailpit": {"container_name": "naf-instance42-mailpit"}},
                "tooling/netcup-api-mock": {
                    "mock-netcup-api": {
                        "container_name": "naf-instance42-mock-netcup-api"
                    }
                },
                "tooling/geoip-mock": {
                    "mock-geoip": {"container_name": "naf-instance42-mock-geoip"}
                },
                "tooling/backend-powerdns": {
                    "powerdns": {"container_name": "naf-instance42-powerdns"}
                },
            }
        },
        "schema_version": 1,
    }
    global_config = tmp_path / "ciu.global.toml"
    global_config.write_text(
        '[topology.external]\npublic_fqdn = "example.test"\n'
        '[topology.dns]\npdns_subdomain = "naf-pdns-instance42"\n',
        encoding="utf-8",
    )
    values = module.build_assignments(json.loads(json.dumps(document)), global_config)
    assert values["MAILPIT_HOST"] == "naf-instance42-mailpit"
    assert values["POWERDNS_API_URL_INTERNAL"] == "http://naf-instance42-powerdns:8081"
    assert values["POWERDNS_API_URL"] == "https://naf-pdns-instance42.example.test"
