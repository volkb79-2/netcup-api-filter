"""The gate wiring must agree with itself; every check here runs in the runner (no CLI needed).

* nyxloom's [gates.*] argv only point at lanes run-gate.toml declares (a renamed lane goes
  red here, not as `unknown lane` at dispatch time).
* every runner variant exists in all four places that must move together: cmru.toml
  (shipped Passenger variants), ciu defaults (runner services), run-gate.toml (exec
  environments + image tags) and docker-bake.hcl (release targets).
"""
import importlib.util
import re
import shlex
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _toml(rel):
    with (ROOT / rel).open("rb") as handle:
        return tomllib.load(handle)


def test_nyxloom_gate_pointers_name_declared_lanes():
    lanes = set(_toml("run-gate.toml")["lanes"])
    gates = _toml("nyxloom-trove/nyxloom.toml")["gates"]
    assert gates, "no gates declared"
    for name, gate in gates.items():
        joined = " ".join(gate["argv"])
        match = re.search(r"run-gate --worktree \{worktree\} (\S+)", joined)
        assert match, f"gate {name!r} is not a canonical run-gate pointer: {joined}"
        assert match.group(1) in lanes, f"gate {name!r} points at undeclared lane {match.group(1)!r}"


def test_runner_variants_agree_across_cmru_ciu_run_gate_and_bake():
    ciu_text = (ROOT / "tooling/test-runner/ciu.defaults.toml.j2").read_text()
    ciu_variants = set(re.findall(r'^name = "(py\d+)"', ciu_text, re.M))
    cmru_variants = {v["name"] for v in _toml("cmru.toml")["project"]["variants"]}
    envs = _toml("run-gate.toml")["environments"]
    bake_targets = set(re.findall(r'^target "(py\d+)"', (ROOT / "docker-bake.hcl").read_text(), re.M))

    assert ciu_variants, "no runner variants in ciu defaults"
    assert cmru_variants <= ciu_variants, "a shipped Passenger variant has no runner"
    assert ciu_variants == bake_targets, f"ciu {ciu_variants} != bake {bake_targets}"
    for name in ciu_variants:
        env = envs.get(f"test-runner-{name}")
        assert env is not None, f"run-gate.toml has no environment test-runner-{name}"
        assert env["image"].endswith(f"/test-runner:{name}"), env["image"]


def test_passenger_bundle_and_publish_use_the_cmru_variant_list(monkeypatch):
    """Reverting the handler path, stale-archive prune, or declared publisher variants fails."""
    cmru = _toml("cmru.toml")
    bundle = _toml("bundle.toml")
    variants = cmru["project"]["variants"]
    assert variants
    assert "variants" not in bundle
    assert bundle["archive"]["name_template"] == "naf-v{version}-{variant}.tar.xz"
    assert bundle["archive"]["version_env"] == "NAF_VERSION"
    assert bundle["archive"]["keep"] == [
        "app-defaults.env", "vendor/certifi/cacert.pem",
    ]
    assert bundle["archive"].get("keep_tree", False) is False
    assert bundle["manifest"]["name"] == "manifest.json"

    build_commands = cmru["steps"]["build"]["commands"]
    assert len(build_commands) == 1
    build_argv = build_commands[0]["argv"]
    assert build_argv[:2] == ["bash", "-c"]
    assert len(build_argv) == 3
    build_script = build_argv[2]
    assert "passenger_bundle_build.py prepare" in build_script
    assert "scripts/build_webhosting_tarball.py" not in build_script
    assert "NAF_BUNDLE_CMRU_CONFIG" not in build_script
    assert "cleanup_bundle_cmru_config" not in build_script
    assert "rm -f -- dist/naf-v*.tar.xz" in build_script
    assert build_script.index("rm -f -- dist/naf-v*.tar.xz") < build_script.index(
        "cmru handler bundle-build"
    )
    bundle_command = next(
        line.strip()
        for line in build_script.splitlines()
        if line.strip().startswith("cmru handler bundle-build ")
    )
    assert shlex.split(bundle_command) == [
        "cmru", "handler", "bundle-build", "--bundle-config", "bundle.toml",
        "--cmru-config", "cmru.toml", "--name", "naf", "--variant",
        "all", "||", "exit", "$?",
    ]

    publish_commands = [
        command["argv"]
        for command in cmru["steps"]["push"]["commands"]
        if command["argv"] == ["python3", "tooling/passenger_bundle_publish.py"]
    ]
    assert publish_commands == [["python3", "tooling/passenger_bundle_publish.py"]]
    publisher_spec = importlib.util.spec_from_file_location(
        "naf_passenger_bundle_publish", ROOT / "tooling/passenger_bundle_publish.py"
    )
    assert publisher_spec is not None and publisher_spec.loader is not None
    publisher = importlib.util.module_from_spec(publisher_spec)
    publisher_spec.loader.exec_module(publisher)
    expected_variants = [f"{variant['name']}={variant['label']}" for variant in variants]
    assert publisher._variant_specs() == expected_variants
    published = []

    def fake_run(command, **kwargs):
        published.append((command, kwargs))

    monkeypatch.setenv("NAF_VERSION", "1.2.3")
    monkeypatch.delenv("CMRU_RELEASE_TAG", raising=False)
    monkeypatch.setattr(publisher.subprocess, "run", fake_run)
    publisher.main()
    assert len(published) == 1
    publish_argv, publish_kwargs = published[0]
    expected_publish_argv = [
        "cmru", "handler", "tarball-publish", "--prefix", "naf", "--cwd", ".",
        "--glob", "dist/naf-v*.tar.xz", "--version-env",
        "NAF_VERSION", "--notes-env", "NAF_RELEASE_NOTES",
    ]
    for variant in expected_variants:
        expected_publish_argv.extend(["--variant", variant])
    assert publish_argv == expected_publish_argv
    assert publish_kwargs["cwd"] == ROOT
    assert publish_kwargs["env"]["NAF_VERSION"] == "1.2.3"

    installer = cmru["project"]["installer"]
    assert installer["asset_suffix"] == ".tar.xz"

    # The prefix values are names of environment variables, not checked-in runner identities.
    assert bundle["exec"]["env"] == {
        "root": "NAF_BUNDLE_RUNNER_ROOT",
        "container": "NAF_BUNDLE_RUNNER_CONTAINER",
    }
    assert "naf-" not in bundle["exec"]["prefix"][-1]


def test_e2e_lane_requires_its_services_and_emits_info_logs():
    """The runner gets browser and mail services, with no cockpit target selection."""
    lane = _toml("run-gate.toml")["lanes"]["e2e"]
    assert lane["required_env"] == ["PLAYWRIGHT_SERVER_WS", "MAILPIT_URL"]
    env = _toml("run-gate.toml")["environments"][lane["environment"]]
    assert {"PLAYWRIGHT_SERVER_WS", "MAILPIT_URL"} <= set(env["forward_env"])
    assert not {"UI_BASE_URL", "DEPLOYMENT_TARGET"} & set(env["forward_env"])
    command = " ".join(lane["argv"])
    assert "-o log_cli=true" in command
    assert "-o log_cli_level=INFO" in command
