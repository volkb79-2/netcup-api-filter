"""Hermetic guards for PowerDNS configuration having one authoritative source."""
from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
ENV_DEFAULTS = REPO / ".env.defaults"
ENV_SERVICES = REPO / ".env.services"
APP_LOCAL_HOOK = REPO / "tooling" / "app-local" / "post_compose_seed_domain.py"
CODE_ROOTS = ("src", "ui_tests", "tests", "tooling", "scripts")


def _tracked_text_files() -> list[tuple[Path, str]]:
    proc = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"git ls-files failed: {proc.stderr.strip()}"

    files: list[tuple[Path, str]] = []
    for relative in proc.stdout.split("\0"):
        if not relative:
            continue
        path = REPO / relative
        try:
            files.append((path, path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):
            continue
    return files


def _required_powerdns_keys() -> set[str]:
    keys: set[str] = set()
    for line in ENV_DEFAULTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("POWERDNS_") and "=" in line:
            keys.add(line.split("=", 1)[0].strip())
    return keys


def _consumer_patterns(key: str) -> tuple[re.Pattern[str], ...]:
    escaped = re.escape(key)
    return (
        re.compile(rf"os\.environ\.get\(\s*(['\"]){escaped}\1"),
        re.compile(rf"os\.environ\[\s*(['\"]){escaped}\1\s*\]"),
        re.compile(rf"os\.getenv\(\s*(['\"]){escaped}\1"),
        re.compile(rf"\${{{escaped}(?=[:}}])"),
        re.compile(rf"\${escaped}\b"),
    )


def test_no_retired_powerdns_paths_or_keys_are_committed():
    """Old proxy variables, the retired URL path, and the invented zone must stay gone."""
    stale_patterns = (
        re.compile("POWERDNS_" + "PROXY_"),
        # Exclude the legitimate filesystem directory `tooling/backend-powerdns`.
        re.compile(r"(?<!tooling)/backend-" + r"powerdns"),
        re.compile("powerhosts." + "vxxu.de"),
    )
    hits = [
        f"{path.relative_to(REPO)}: {pattern.pattern}"
        for path, text in _tracked_text_files()
        for pattern in stale_patterns
        if pattern.search(text)
    ]
    assert not hits, "retired PowerDNS configuration remains committed:\n" + "\n".join(hits)


def test_every_powerdns_default_is_consumed_by_code():
    """A catalog key with no consumer is stale config and must not ship."""
    code_files = [
        (path, text)
        for root in CODE_ROOTS
        for path, text in _tracked_text_files()
        if path.is_relative_to(REPO / root)
    ]
    unread = []
    for key in sorted(_required_powerdns_keys()):
        if not any(pattern.search(text) for pattern in _consumer_patterns(key) for _, text in code_files):
            unread.append(key)
    assert not unread, (
        "PowerDNS keys in .env.defaults have no code consumer; remove them or add a reader: "
        + ", ".join(unread)
    )


def _source_env_services(env: dict[str, str]) -> dict[str, str]:
    script = (
        "set -euo pipefail; "
        f"cd {REPO!s}; "
        "source .env.services; "
        'printf "%s\\n%s\\n" "$POWERDNS_API_URL" "$POWERDNS_API_URL_INTERNAL"'
    )
    proc = subprocess.run(
        ["bash", "-c", script],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"sourcing .env.services failed: {proc.stderr}"
    public_url, internal_url = proc.stdout.splitlines()
    return {"public": public_url, "internal": internal_url}


def _load_app_local_hook():
    spec = importlib.util.spec_from_file_location("naf_powerdns_hygiene_hook", APP_LOCAL_HOOK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_internal_url_has_one_source_and_matches_the_stack_derivation(monkeypatch):
    """`.env.services` and the app-local hook must build the same sample internal URL."""
    configured = _source_env_services({
        "PATH": "/usr/bin:/bin",
        "PROJECT_TAG": "sample",
        "ENV_TAG": "integration",
    })
    definition_files = {
        path.relative_to(REPO)
        for path, text in _tracked_text_files()
        for key in ("POWERDNS_API_URL", "POWERDNS_API_URL_INTERNAL")
        if re.search(rf"^\s*(?:export\s+)?{key}=", text, re.MULTILINE)
    }
    assert definition_files == {Path(".env.services")}, definition_files
    assert configured["public"] == ""

    hook = _load_app_local_hook()
    calls = []
    monkeypatch.setenv("POWERDNS_API_KEY", "test-only-key")

    def fake_exec(container, *args, timeout=30, env=None, secret_env=None):
        calls.append((container, env, secret_env))
        return subprocess.CompletedProcess(["docker"], 0, "[seed] ok", "")

    monkeypatch.setattr(hook, "_docker_exec", fake_exec)
    config = {
        "topology": {"dns": {"delegated_zone": "example.test"}},
        "deploy": {"project_name": "sample", "environment_tag": "integration"},
        "app_local": {"name": "app"},
        "backend_powerdns": {"name": "powerdns", "ports": {"api": 8081}},
    }
    assert hook.run(config, SimpleNamespace(wait_healthy=lambda *a, **k: True)) == {}

    container, seed_env, secret_env = calls[0]
    assert container == "sample-integration-app"
    assert seed_env["NAF_SEED_POWERDNS_API_URL"] == configured["internal"]
    assert secret_env["NAF_SEED_POWERDNS_API_KEY"] == "test-only-key"


def test_auto_url_reads_the_env_services_values_and_fails_without_one(monkeypatch):
    from netcup_api_filter.bootstrap import platform_backends

    monkeypatch.setattr(platform_backends, "get_setting", lambda _key: None)
    monkeypatch.delenv("POWERDNS_API_URL", raising=False)
    monkeypatch.delenv("POWERDNS_API_URL_INTERNAL", raising=False)

    with pytest.raises(RuntimeError, match="POWERDNS_API_URL_INTERNAL"):
        platform_backends.get_powerdns_api_url()

    monkeypatch.setenv("POWERDNS_API_URL", "https://naf-pdns.example.test")
    monkeypatch.setenv("POWERDNS_API_URL_INTERNAL", "http://sample-integration-powerdns:8081")
    assert (
        platform_backends.get_powerdns_api_url()
        == "http://sample-integration-powerdns:8081"
    )
