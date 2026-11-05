"""tooling/app-local post_compose_init_instance.py, verified without `ciu up` (CIU-176).

The hook is loaded by path exactly as ciu loads it, driven with a fake HookContext and
a fake runner. A second group pins the agreement between the hook, the stack's
ciu.defaults.toml.j2 (secrets, hook order) and its compose template (secret mounts,
*_FILE env), so a rename on one side cannot silently break first boot.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
STACK = REPO / "tooling" / "app-local"


def _load_hook():
    spec = importlib.util.spec_from_file_location("app_local_init_hook", STACK / "post_compose_init_instance.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = _load_hook()

CONFIG = {
    "deploy": {"project_name": "naf", "environment_tag": "dev"},
    "app_local": {
        "name": "app",
        "init_python": "/opt/tester-venv/bin/python",
        "init_pythonpath": "vendor:src",
        "mail": {"from_email": "naf@example.com", "admin_email": "admin@example.com"},
    },
    "mailpit": {"name": "mailpit", "smtp_port": 1025},
}


def _ctx(*, healthy=True, store=Path("/repo/.ciu/secrets/naf/app_local_bootstrap_admin_password")):
    calls = []

    def wait_healthy(service, *, timeout_s):
        calls.append((service, timeout_s))
        return healthy

    def secret_file(name):
        if name != hook.PASSWORD_SECRET:
            raise KeyError(name)
        return store

    return SimpleNamespace(wait_healthy=wait_healthy, secret_file=secret_file), calls


def _runner(stdout, returncode=0, stderr=""):
    seen = []

    def run(argv, **kwargs):
        seen.append(argv)
        return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr=stderr)

    return run, seen


def test_argv_execs_the_package_initializer_in_the_app_container():
    argv = hook.build_init_argv(CONFIG)
    assert argv[:2] == ["docker", "exec"]
    assert "naf-dev-app" in argv
    assert "--enforce-admin" not in argv, "ciu up must not change an initialized instance"
    assert argv[argv.index("naf-dev-app") + 1:][:4] == [
        "/opt/tester-venv/bin/python", "-m", "netcup_api_filter.bootstrap", "init"]
    assert argv[argv.index("--mock-smtp-host") + 1] == "naf-dev-mailpit"
    assert argv[argv.index("--mock-smtp-port") + 1] == "1025"
    assert "PYTHONPATH=vendor:src" in argv
    assert not any("password" in part.lower() and "=" in part for part in argv), "never pass a secret on argv"


def test_run_waits_execs_and_prints_only_the_secret_path(capsys):
    ctx, calls = _ctx()
    runner, seen = _runner("log line\n" + json.dumps(
        {"admin_username": "admin", "admin_action": "created", "admin_source": "environment"}) + "\n")
    assert hook.run(CONFIG, ctx, runner=runner) == {}
    assert calls == [("app", hook.HEALTH_TIMEOUT_S)]
    assert seen == [hook.build_init_argv(CONFIG)]
    out = capsys.readouterr().out
    assert "admin" in out and "created" in out
    assert "/repo/.ciu/secrets/naf/app_local_bootstrap_admin_password" in out


@pytest.mark.parametrize("ctx_kwargs,runner_args,match", [
    ({"healthy": False}, ("{}",), "did not become healthy"),
    ({}, ("", 2, "error: No administrator"), "init failed"),
    ({}, ("not json",), "unexpected init output"),
])
def test_run_failures_are_loud(ctx_kwargs, runner_args, match):
    ctx, _ = _ctx(**ctx_kwargs)
    runner, _ = _runner(*runner_args)
    with pytest.raises(RuntimeError, match=match):
        hook.run(CONFIG, ctx, runner=runner)


def test_run_outside_the_engine_refuses():
    ctx = SimpleNamespace(wait_healthy=None, secret_file=lambda name: Path("/x"))
    with pytest.raises(RuntimeError, match="runs inside `ciu up` only"):
        hook.run(CONFIG, ctx, runner=_runner("{}")[0])


def test_missing_config_names_the_key():
    broken = {**CONFIG, "mailpit": {"name": "mailpit"}}
    with pytest.raises(ValueError, match="mailpit.smtp_port"):
        hook.build_init_argv(broken)


# --- hook ↔ stack config ↔ compose template agreement -------------------------

def _stack_defaults() -> dict:
    return tomllib.loads((STACK / "ciu.defaults.toml.j2").read_text())


def test_stack_declares_the_generated_secrets_and_runs_init_first():
    stack = _stack_defaults()["app_local"]
    assert stack["secrets"][hook.PASSWORD_SECRET].startswith("GEN_LOCAL:")
    assert stack["secrets"]["secret_key"].startswith("GEN_LOCAL:")
    assert stack["hooks"]["post_compose"][0] == "post_compose_init_instance.py"
    for script in stack["hooks"]["post_compose"]:
        assert (STACK / script).is_file(), script  # a missing hook file aborts ciu up
    for dotted in ("init_python", "init_pythonpath", "mail", "bootstrap_admin"):
        assert dotted in stack


def test_compose_mounts_the_secrets_and_points_the_app_at_them():
    compose = (STACK / "ciu.compose.yml.j2").read_text()
    for name in ("secret_key", hook.PASSWORD_SECRET):
        assert f"      - {name}\n" in compose
    assert f"NAF_BOOTSTRAP_ADMIN_PASSWORD_FILE=/run/secrets/{hook.PASSWORD_SECRET}" in compose
    assert "SECRET_KEY_FILE=/run/secrets/secret_key" in compose
    assert "NETCUP_FILTER_DB_PATH=/data/" in compose and "hostdir.data }}:/data" in compose
