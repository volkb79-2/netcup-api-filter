"""Drift guards for per-checkout ciu identity and resolved service names."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import tomllib
from pathlib import Path
from types import SimpleNamespace

from tests.test_powerdns_config_hygiene import _tracked_text_files

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


_CONCATENATION_PATTERNS = (
    re.compile(r"f[\"']\{project_name\}-\{environment_tag\}-"),
    re.compile(r"\$\{?PROJECT_TAG\}?(?:-\$\{?ENV_TAG|.*\$\{?ENV_TAG\b)"),
)


def _concatenation_scope() -> list[Path]:
    """Every consumer that could rebuild a container name (review L1 scope)."""
    paths = {
        REPO / ".env.services",
        REPO / "run-gate.toml",
        REPO / "build_deployment.py",
    }
    for root, patterns in (
        (REPO / "scripts", ("*.py", "*.sh")),
        (TOOLING, ("*.py", "*.sh")),
        (REPO / ".devcontainer", ("*",)),
        (REPO / "ui_tests", ("*.py",)),
    ):
        for pattern in patterns:
            paths.update(
                path for path in root.rglob(pattern)
                if path.is_file() and "__pycache__" not in path.parts
            )
    return sorted(paths)


def _concatenation_hits(paths, root: Path = REPO) -> list[str]:
    """path:line of each name concatenation -- never the line itself."""
    hits: list[str] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        hits.extend(
            f"{path.relative_to(root)}:{line_no}: container name built from deploy tags"
            for line_no, line in enumerate(text.splitlines(), 1)
            if any(pattern.search(line) for pattern in _CONCATENATION_PATTERNS)
        )
    return hits


def test_concatenation_guard_covers_the_review_scope_and_catches_both_spellings(tmp_path):
    scope = {path.relative_to(REPO).as_posix() for path in _concatenation_scope()}
    for expected in (
        ".env.services",
        "run-gate.toml",
        "build_deployment.py",
        "scripts/build_webhosting_tarball.py",
        "tooling/ciu_identity.py",
        ".devcontainer/devcontainer.json",
        ".devcontainer/finalize.post.d/10-netcup-setup.sh",
        "ui_tests/mailpit_client.py",
    ):
        assert expected in scope, expected

    probe = tmp_path / "probe.sh"
    probe.write_text(
        'name="${PROJECT_TAG}-${ENV_TAG}-mailpit"\n'
        'host = f"{project_name}-{environment_tag}-app"\n'
        'name2="$PROJECT_TAG-$ENV_TAG-geoip"\n'
        'ok="$(ciu resolve --json)"\n',
        encoding="utf-8",
    )
    assert _concatenation_hits([probe], tmp_path) == [
        f"probe.sh:{line}: container name built from deploy tags" for line in (1, 2, 3)
    ]


def test_scripts_do_not_rebuild_container_names_from_deploy_tags():
    """Hooks, release scripts and shell consumers must read ciu identities."""
    checked = [
        REPO / ".env.services",
        REPO / "run-gate.toml",
        REPO / "build_deployment.py",
        REPO / "scripts" / "build_webhosting_tarball.py",
    ]
    checked += sorted(TOOLING.rglob("*.py"))
    failures = _concatenation_hits(_concatenation_scope())
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
        f"{path.relative_to(REPO)}:{line_no}: reads deploy.project_name/environment_tag"
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
        "--json",
        "--profile",
        "full",
        "--root-folder",
        "/repo",
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

    # The guarantee is about TRACKED files: a gitignored operator `.env` is not
    # the repository's content and is never read here.
    tracked = _tracked_text_files()
    assert any(path == REPO / ".env.defaults" for path, _text in tracked)
    assert not any(path == REPO / ".env" for path, _text in tracked)
    failures = _literal_key_assignments(tracked, REPO)
    assert not failures, "\n".join(failures)


_KEY_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?POWERDNS_API_KEY\s*=\s*(?!\$\{|$)\S")


def _literal_key_assignments(files, root: Path) -> list[str]:
    """path:line of every literal key assignment -- never the matched value.

    The value is a candidate secret: it must not reach pytest output or a gate log.
    """
    return [
        f"{path.relative_to(root)}:{line_no}: literal POWERDNS_API_KEY assignment"
        for path, text in files
        for line_no, line in enumerate(text.splitlines(), 1)
        if _KEY_ASSIGNMENT.search(line)
    ]


def test_literal_key_scan_reports_location_only_never_the_value(tmp_path):
    candidate = "x" * 24
    files = [
        (tmp_path / "ok.env", "POWERDNS_API_KEY=${POWERDNS_API_KEY}\nPOWERDNS_API_KEY=\n"),
        (tmp_path / "leak.env", f"# header\nexport POWERDNS_API_KEY={candidate}\n"),
    ]
    failures = _literal_key_assignments(files, tmp_path)
    assert failures == ["leak.env:2: literal POWERDNS_API_KEY assignment"]
    assert candidate not in "\n".join(failures)


def test_app_local_proxy_and_public_origin_are_explicit_and_fail_fast():
    hook_path = TOOLING / "app-local" / "pre_compose_validate.py"
    spec = importlib.util.spec_from_file_location("naf_pre_compose_validate", hook_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    valid = {
        "deploy": {"project_name": "naf", "environment_tag": "instance42"},
        "topology": {"external": {"public_fqdn": "example.test"}},
        "app_local": {
            "trusted_proxy_hops": 0,
            "public_base_url": "https://naf-instance42.example.test",
            "external": {"subdomain": "naf-instance42"},
            "secrets": {"powerdns_api_key": {"directive": "GEN_LOCAL:naf/powerdns_api_key"}},
        },
    }
    assert module.validate_config(valid, None) == []

    # The prefix is deploy.project_name, not a literal `naf-` (review L5).
    renamed = {
        **valid,
        "deploy": {"project_name": "other", "environment_tag": "instance42"},
        "app_local": {
            **valid["app_local"],
            "public_base_url": "https://other-instance42.example.test",
            "external": {"subdomain": "other-instance42"},
        },
    }
    assert module.validate_config(renamed, None) == []
    stale_prefix = {**renamed, "app_local": valid["app_local"]}
    assert any(
        "expected 'other-instance42'" in finding
        for finding in module.validate_config(stale_prefix, None)
    )
    no_project = {**valid, "deploy": {"environment_tag": "instance42"}}
    assert "deploy.project_name is missing" in module.validate_config(no_project, None)

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
    values, missing = module.build_assignments(json.loads(json.dumps(document)), global_config)
    assert missing == []
    assert values["MAILPIT_HOST"] == "naf-instance42-mailpit"
    assert values["POWERDNS_API_URL_INTERNAL"] == "http://naf-instance42-powerdns:8081"
    assert values["POWERDNS_API_URL"] == "https://naf-pdns-instance42.example.test"

    # Partial document (review M5): export what resolves, unset the rest.
    partial = json.loads(json.dumps(document))
    del partial["resolved"]["identities"]["tooling/backend-powerdns"]
    values, missing = module.build_assignments(partial, global_config)
    assert missing == ["tooling/backend-powerdns:powerdns"]
    assert "POWERDNS_HOST" not in values and "POWERDNS_API_URL_INTERNAL" not in values
    assert values["MOCK_NETCUP_API_URL"] == "http://naf-instance42-mock-netcup-api:80"
    assert module.unset_names(missing) == ["POWERDNS_HOST", "POWERDNS_API_URL_INTERNAL"]
    shell = module.render_shell(values, module.unset_names(missing))
    assert shell.splitlines()[-1] == "unset POWERDNS_HOST POWERDNS_API_URL_INTERNAL"

    try:
        module.build_assignments({"schema_version": 1}, global_config)
    except ValueError as exc:
        assert "resolved.identities" in str(exc)
    else:
        raise AssertionError("a malformed resolve document did not fail")


def test_env_services_ports_equal_the_stack_defaults():
    """The translator's ports drift with nothing else unless pinned here (review L4)."""
    module = _load_tooling_module("naf_ciu_resolve_env_ports", "ciu_resolve_env.py")

    def stack(name: str) -> dict:
        return tomllib.loads(
            (TOOLING / name / "ciu.defaults.toml.j2").read_text(encoding="utf-8")
        )

    assert module.PORTS == {
        "MAILPIT_HOST": stack("mailpit")["mailpit"]["web_port"],
        "MOCK_NETCUP_API_HOST": stack("netcup-api-mock")["netcup_api_mock"]["port"],
        "MOCK_GEOIP_HOST": stack("geoip-mock")["geoip_mock"]["port"],
        "POWERDNS_HOST": stack("backend-powerdns")["backend_powerdns"]["ports"]["api"],
    }
    assert set(module.PORTS) == set(module.SERVICES) == set(module.DERIVED)


def _common_dir_block() -> tuple[str, str]:
    """(full template, the linked-worktree common-dir block) of the runner template."""
    template = (TOOLING / "test-runner" / "ciu.compose.yml.j2").read_text(encoding="utf-8")
    match = re.search(
        r"^\{% if '/\.worktrees/' in ciu\.repo_root\|string %\}\n(?P<body>.*?)^\{% endif %\}\n",
        template,
        re.MULTILINE | re.DOTALL,
    )
    assert match, "test-runner template lacks the linked-worktree common-dir block"
    return template, match.group(0)


def test_linked_worktree_runner_mounts_the_git_common_dir():
    """A per-checkout runner of a linked worktree must see <main>/.git (review H1).

    Without it every git call in the runner exits 128 and assay lanes abort with
    ERROR/GIT_FAILED. The block is conditional on `/.worktrees/` (the main
    checkout's runner already mounts its whole checkout) and both paths derive
    from ciu facts, never from configuration.
    """
    from jinja2 import Environment, StrictUndefined

    template, block = _common_dir_block()
    # Inside the service `volumes:` list: after the run-gate state volume and
    # before the next service key.
    volumes_at = template.index("    volumes:\n")
    state_at = template.index("target: {{ test_runner.run_gate.state_root }}")
    block_at = template.index(block)
    ulimits_at = template.index("    ulimits:\n")
    assert volumes_at < state_at < block_at < ulimits_at

    mounts = [line.strip() for line in block.splitlines() if line.strip().startswith("- ")]
    assert mounts == [
        "- ${PHYSICAL_REPO_ROOT:?required host path — source ciu.env}/../../.git:"
        "{{ (ciu.repo_root|string).split('/.worktrees/')[0] }}/.git:rw"
    ]

    env = Environment(undefined=StrictUndefined)
    rendered_worktree = env.from_string(block).render(
        ciu={"repo_root": "/srv/checkout/.worktrees/wp1"}
    )
    worktree_mounts = [
        line.strip() for line in rendered_worktree.splitlines() if line.strip().startswith("- ")
    ]
    assert worktree_mounts == [
        "- ${PHYSICAL_REPO_ROOT:?required host path — source ciu.env}/../../.git:"
        "/srv/checkout/.git:rw"
    ]
    rendered_main = env.from_string(block).render(ciu={"repo_root": "/srv/checkout"})
    assert rendered_main.strip() == ""


def _load_tooling_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, TOOLING / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_peer_identities_resolve_against_the_full_profile_not_the_selection(monkeypatch):
    """A hook's peer lookup must not inherit a narrow selection (review M5)."""
    module = _load_tooling_module("naf_ciu_identity_profile", "ciu_identity.py")
    commands = []

    def runner(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({
                "resolved": {"identities": {"tooling/backend-powerdns": {
                    "powerdns": {"container_name": "naf-instance42-powerdns"}
                }}},
            }),
            stderr="",
        )

    original = module.resolve_container
    monkeypatch.setattr(
        module,
        "resolve_container",
        lambda *args, **kwargs: original(*args, runner=runner, **kwargs),
    )
    ctx = SimpleNamespace(selected_profiles=("test",), repo_root="/repo")
    assert module.container_for(ctx, "tooling/backend-powerdns", "powerdns") == (
        "naf-instance42-powerdns"
    )
    command = commands[0]
    profiles = [command[i + 1] for i, arg in enumerate(command) if arg == "--profile"]
    assert profiles == [module.IDENTITY_PROFILE]

    # The identity profile must declare every stack a consumer resolves.
    globals_doc = tomllib.loads(
        (REPO / "ciu.global.defaults.toml.j2").read_text(encoding="utf-8")
    )
    declared = set(globals_doc["deploy"]["profiles"][module.IDENTITY_PROFILE]["stacks"])
    stacks = {
        path.parent.relative_to(REPO).as_posix()
        for path in TOOLING.glob("*/ciu.compose.yml.j2")
    }
    assert stacks <= declared, sorted(stacks - declared)
    env_services = (REPO / ".env.services").read_text(encoding="utf-8")
    assert f"ciu resolve --json --profile {module.IDENTITY_PROFILE}" in env_services


def _load_release_builder():
    spec = importlib.util.spec_from_file_location(
        "naf_build_webhosting_tarball_runner", REPO / "scripts" / "build_webhosting_tarball.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_builder_fails_with_an_instruction_when_its_runner_is_down():
    """cmru builds in a release worktree whose runner nothing starts (review M4)."""
    builder = _load_release_builder()
    seen = []

    def probe(stdout: str, returncode: int):
        def run(command, **kwargs):
            seen.append(command)
            return subprocess.CompletedProcess(command, returncode, stdout, "")
        return run

    builder._require_running("naf-rel-test-runner-py311", runner=probe("true\n", 0))
    assert seen[0] == [
        "docker", "inspect", "-f", "{{.State.Running}}", "naf-rel-test-runner-py311",
    ]
    for stdout, returncode, state in (("false\n", 0, "not running"), ("", 1, "absent")):
        try:
            builder._require_running(
                "naf-rel-test-runner-py311", runner=probe(stdout, returncode)
            )
        except RuntimeError as exc:
            message = str(exc)
        else:
            raise AssertionError(f"a {state} runner did not stop the release build")
        assert f"naf-rel-test-runner-py311 is {state}" in message
        assert "ciu up --dir tooling/test-runner" in message
        assert str(builder.REPO_ROOT) in message
