"""tooling/app-local post_compose_init_instance.py, verified through fake ciu identities.

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
    "deploy": {"project_name": "naf", "environment_tag": "inst42"},
    "app_local": {
        "name": "app",
        "init_python": "/opt/tester-venv/bin/python",
        "init_pythonpath": "vendor:src",
        "mail": {"from_email": "naf@example.com", "admin_email": "admin@example.com",
                 "smtp_service": "mailpit", "smtp_port": 1025},
    },
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

    return SimpleNamespace(
        wait_healthy=wait_healthy,
        secret_file=secret_file,
        repo_root=REPO,
        selected_profiles=("full",),
    ), calls


def _runner(stdout, returncode=0, stderr=""):
    seen = []

    def run(argv, **kwargs):
        seen.append(argv)
        return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr=stderr)

    return run, seen


def test_argv_execs_the_package_initializer_in_the_app_container(monkeypatch):
    ctx, _ = _ctx()
    monkeypatch.setattr(
        hook,
        "container_for",
        lambda _ctx, stack, service: {
            ("tooling/app-local", "app"): "naf-inst42-app",
            ("tooling/mailpit", "mailpit"): "naf-inst42-mailpit",
        }[(stack, service)],
    )
    argv = hook.build_init_argv(CONFIG, ctx)
    assert argv[:2] == ["docker", "exec"]
    assert "naf-inst42-app" in argv
    assert "--enforce-admin" not in argv, "ciu up must not change an initialized instance"
    assert argv[argv.index("naf-inst42-app") + 1:][:4] == [
        "/opt/tester-venv/bin/python", "-m", "netcup_api_filter.bootstrap", "init"]
    assert argv[argv.index("--mock-smtp-host") + 1] == "naf-inst42-mailpit"
    assert argv[argv.index("--mock-smtp-port") + 1] == "1025"
    assert "PYTHONPATH=vendor:src" in argv
    assert not any("password" in part.lower() and "=" in part for part in argv), "never pass a secret on argv"


def test_run_waits_execs_and_prints_only_the_secret_path(capsys, monkeypatch):
    ctx, calls = _ctx()
    monkeypatch.setattr(
        hook,
        "container_for",
        lambda _ctx, stack, service: {
            ("tooling/app-local", "app"): "naf-inst42-app",
            ("tooling/mailpit", "mailpit"): "naf-inst42-mailpit",
        }[(stack, service)],
    )
    runner, seen = _runner("log line\n" + json.dumps(
        {"admin_username": "admin", "admin_action": "created", "admin_source": "environment"}) + "\n")
    assert hook.run(CONFIG, ctx, runner=runner) == {}
    assert calls == [("app", hook.HEALTH_TIMEOUT_S)]
    assert seen == [hook.build_init_argv(CONFIG, ctx)]
    out = capsys.readouterr().out
    assert "admin" in out and "created" in out
    assert "/repo/.ciu/secrets/naf/app_local_bootstrap_admin_password" in out


@pytest.mark.parametrize("ctx_kwargs,runner_args,match", [
    ({"healthy": False}, ("{}",), "did not become healthy"),
    ({}, ("", 2, "error: No administrator"), "init failed"),
    ({}, ("not json",), "unexpected init output"),
])
def test_run_failures_are_loud(ctx_kwargs, runner_args, match, monkeypatch):
    ctx, _ = _ctx(**ctx_kwargs)
    monkeypatch.setattr(
        hook,
        "container_for",
        lambda _ctx, stack, service: {
            ("tooling/app-local", "app"): "naf-inst42-app",
            ("tooling/mailpit", "mailpit"): "naf-inst42-mailpit",
        }[(stack, service)],
    )
    runner, _ = _runner(*runner_args)
    with pytest.raises(RuntimeError, match=match):
        hook.run(CONFIG, ctx, runner=runner)


def test_run_outside_the_engine_refuses(monkeypatch):
    ctx = SimpleNamespace(wait_healthy=None, secret_file=lambda name: Path("/x"))
    monkeypatch.setattr(hook, "container_for", lambda _ctx, _stack, _service: "naf-inst42-app")
    with pytest.raises(RuntimeError, match="runs inside `ciu up` only"):
        hook.run(CONFIG, ctx, runner=_runner("{}")[0])


def test_missing_config_names_the_key(monkeypatch):
    monkeypatch.setattr(hook, "container_for", lambda _ctx, _stack, _service: "naf-inst42-app")
    broken = {**CONFIG, "app_local": {**CONFIG["app_local"], "mail": {**CONFIG["app_local"]["mail"], "smtp_port": ""}}}
    with pytest.raises(ValueError, match="app_local.mail.smtp_port"):
        hook.build_init_argv(broken, _ctx()[0])


# --- hook ↔ stack config ↔ compose template agreement -------------------------

def _stack_defaults() -> dict:
    return tomllib.loads((STACK / "ciu.defaults.toml.j2").read_text())


def test_stack_declares_the_generated_secrets_and_runs_init_first():
    stack = _stack_defaults()["app_local"]
    assert stack["secrets"][hook.PASSWORD_SECRET].startswith("GEN_LOCAL:")
    assert stack["secrets"]["secret_key"].startswith("GEN_LOCAL:")
    assert stack["secrets"]["powerdns_api_key"]["directive"].startswith("GEN_LOCAL:")
    assert stack["hooks"]["pre_compose"] == ["pre_compose_validate.py"]
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


def test_compose_states_the_proxy_hops_and_canonical_public_origin():
    stack = _stack_defaults()["app_local"]
    compose = (STACK / "ciu.compose.yml.j2").read_text()

    assert stack["trusted_proxy_hops"] == 0
    assert stack["public_base_url"] == (
        "https://naf-$INSTANCE_ID.{{ topology.external.public_fqdn }}"
    )
    assert "TRUSTED_PROXY_HOPS={{ app_local.trusted_proxy_hops }}" in compose
    assert "PUBLIC_BASE_URL={{ app_local.public_base_url }}" in compose


def test_declared_mail_service_equals_the_mailpit_stack():
    """app-local declares the Mailpit name/port itself (a lone `ciu up --dir` does not load the Mailpit
    stack's config); this keeps the two declarations equal."""
    import re
    root = Path(__file__).resolve().parents[1]
    mailpit = (root / "tooling/mailpit/ciu.defaults.toml.j2").read_text()
    app = (root / "tooling/app-local/ciu.defaults.toml.j2").read_text()

    def value(text, key):
        found = re.search(rf'^{key}\s*=\s*"?([^"\n#]+?)"?\s*(?:#.*)?$', text, re.M)
        assert found, key
        return found.group(1)

    assert value(app, "smtp_service") == value(mailpit, "name")
    assert value(app, "smtp_port") == value(mailpit, "smtp_port")
