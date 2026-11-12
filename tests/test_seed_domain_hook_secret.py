"""The app-local seed hook must not put the PowerDNS API key on the docker command line (visible in ps)."""
import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace

HOOK = Path(__file__).resolve().parents[1] / "tooling" / "app-local" / "post_compose_seed_domain.py"
SECRET = "s3cret-pdns-key-for-test"


def _load():
    spec = importlib.util.spec_from_file_location("naf_seed_hook", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_api_key_travels_via_process_env_not_argv(monkeypatch, tmp_path):
    hook = _load()
    secret_file = tmp_path / "powerdns_api_key"
    secret_file.write_text(SECRET)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, "[seed] ok", "")

    monkeypatch.setattr(hook.subprocess, "run", fake_run)
    monkeypatch.setattr(
        hook,
        "container_for",
        lambda _ctx, stack, service: {
            ("tooling/app-local", "app"): "sample-instance-app",
            ("tooling/backend-powerdns", "pdns"): "sample-instance-pdns",
        }[(stack, service)],
    )
    config = {
        "topology": {"dns": {"delegated_zone": "managed.example.test"}},
        "deploy": {"project_name": "sample", "environment_tag": "instance"},
        "app_local": {"name": "app"},
        "backend_powerdns": {"name": "pdns", "ports": {"api": 8081}},
    }
    ctx = SimpleNamespace(
        wait_healthy=lambda *a, **k: True,
        secret_file=lambda name: secret_file,
        repo_root=None,
        selected_profiles=(),
    )
    hook.run(config, ctx)

    (cmd, kwargs), = [c for c in calls if "NAF_SEED_POWERDNS_API_KEY" in " ".join(c[0])]
    assert SECRET not in " ".join(cmd)
    assert "NAF_SEED_POWERDNS_API_KEY" in cmd  # bare name: docker reads the value from its env
    assert kwargs["env"]["NAF_SEED_POWERDNS_API_KEY"] == SECRET
