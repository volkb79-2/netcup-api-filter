"""Hermetic guards for PowerDNS configuration having one authoritative source."""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
ENV_DEFAULTS = REPO / ".env.defaults"
ENV_SERVICES = REPO / ".env.services"
APP_LOCAL_HOOK = REPO / "tooling" / "app-local" / "post_compose_seed_domain.py"
CODE_ROOTS = ("src", "ui_tests", "tests", "tooling", "scripts")

# The supported test-runner mounts the checkout but not the common Git
# directory used by ciu-created worktrees. The fallback therefore walks only
# tracked top-level source roots and files, rather than trying to mirror every
# .gitignore rule.
_FALLBACK_SOURCE_ROOTS = frozenset({
    ".devcontainer",
    ".github",
    ".vscode",
    "docs",
    "nyxloom-trove",
    "scripts",
    "src",
    "tests",
    "tmp",
    "tooling",
    "tools",
    "ui_tests",
    "versions",
})

_FALLBACK_ROOT_FILES = frozenset({
    ".ciu.hosts.toml",
    ".dockerignore",
    ".env.defaults",
    ".env.services",
    ".gitignore",
    "AGENTS.md",
    "CHANGELOG.md",
    "CLIENT_TEMPLATES.md",
    "CLAUDE.md",
    "Dockerfile.release",
    "LICENSE",
    "PLAYWRIGHT_CONTAINER.md",
    "PYTHON_PACKAGES.md",
    "README.md",
    "app-config.example.toml",
    "assay.toml",
    "build_deployment.py",
    "ciu.global.defaults.toml.j2",
    "cmru.toml",
    "docker-bake.hcl",
    "gunicorn.conf.py",
    "mypy.ini",
    "pytest.ini",
    "requirements-runtime.txt",
    "requirements-test.txt",
    "ruff.toml",
    "run-gate.toml",
    "setup.cfg",
})

# Generated directories are pruned only inside the otherwise tracked roots.
_FALLBACK_GENERATED_DIR_NAMES = frozenset({
    ".ciu",
    "__pycache__",
    ".venv",
    "node_modules",
})

_FALLBACK_GENERATED_FILE_NAMES = frozenset({
    "ciu.compose.yml",
    "ciu.toml",
})

_FALLBACK_GENERATED_RELATIVE_DIRS = frozenset({
    Path("docs/_build"),
    Path("tooling/playwright/screenshots"),
    Path("tooling/playwright/vol-playwright-screenshots"),
})

_FALLBACK_EXTRA_FILES = frozenset({
    Path("tmp/restart.txt"),
})

# ciu worktrees point .git at a common directory that may not be mounted in
# the test runner. Only this known metadata-unavailable failure may fall back.
_GIT_METADATA_UNAVAILABLE_MARKER = "not a git repository"


def _read_text_files(paths):
    files: list[tuple[Path, str]] = []
    for path in paths:
        try:
            files.append((path, path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):
            continue
    return files


def _git_paths(repo: Path, *ls_files_args: str) -> set[Path] | None:
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-z", *ls_files_args],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        if exc.filename == "git" and shutil.which("git") is None:
            return None
        raise
    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        if _GIT_METADATA_UNAVAILABLE_MARKER in stderr:
            return None
        raise AssertionError(f"git ls-files failed: {stderr or '<no stderr>'}")
    return {
        Path(relative)
        for relative in proc.stdout.split("\0")
        if relative
    }


def _git_text_files(repo: Path = REPO) -> list[tuple[Path, str]] | None:
    relative_paths = _git_paths(repo)
    if relative_paths is None:
        return None
    return _read_text_files(repo / relative for relative in relative_paths)


def _git_ignored_or_untracked_paths(repo: Path = REPO) -> set[Path] | None:
    ignored = _git_paths(repo, "--others", "--ignored", "--exclude-standard")
    untracked = _git_paths(repo, "--others", "--exclude-standard")
    if ignored is None or untracked is None:
        return None
    return ignored | untracked


def _fallback_in_scope(relative: Path) -> bool:
    if len(relative.parts) == 1:
        return relative.name in _FALLBACK_ROOT_FILES
    return relative.parts[0] in _FALLBACK_SOURCE_ROOTS


def _fallback_excludes(relative: Path) -> bool:
    if relative == Path("tmp/restart.txt"):
        return False
    if not _fallback_in_scope(relative):
        return True
    if relative.parts and relative.parts[0] == "tmp":
        return True
    if relative.name in _FALLBACK_GENERATED_FILE_NAMES:
        return True
    relative_parents = relative.parents
    for parent in relative_parents:
        if parent == Path("."):
            break
        if parent.name in _FALLBACK_GENERATED_DIR_NAMES or parent.name.startswith("deploy"):
            return True
        if parent in _FALLBACK_GENERATED_RELATIVE_DIRS:
            return True
    return False


def _walk_root(repo: Path, root_name: str):
    root = repo / root_name
    if not root.is_dir():
        return
    for directory, dirnames, filenames in os.walk(root):
        relative_directory = Path(directory).relative_to(repo)
        dirnames[:] = [
            name
            for name in dirnames
            if not _fallback_excludes(relative_directory / name / "placeholder")
        ]
        for filename in filenames:
            relative = relative_directory / filename
            if not _fallback_excludes(relative):
                yield repo / relative


def _walk_text_files(repo: Path = REPO) -> list[tuple[Path, str]]:
    paths = [
        repo / relative
        for relative in _FALLBACK_ROOT_FILES
        if (repo / relative).is_file()
    ]
    for root_name in _FALLBACK_SOURCE_ROOTS:
        if root_name != "tmp":
            paths.extend(_walk_root(repo, root_name))
    paths.extend(
        repo / relative
        for relative in _FALLBACK_EXTRA_FILES
        if (repo / relative).is_file()
    )
    return _read_text_files(paths)


def _tracked_text_files() -> list[tuple[Path, str]]:
    git_files = _git_text_files()
    return git_files if git_files is not None else _walk_text_files()


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


def _assert_git_allowlist_coverage(git_paths: set[Path]):
    tracked_roots = {path.parts[0] for path in git_paths if len(path.parts) > 1}
    tracked_root_files = {path for path in git_paths if len(path.parts) == 1}
    allowed_root_files = {Path(name) for name in _FALLBACK_ROOT_FILES}
    assert tracked_roots <= _FALLBACK_SOURCE_ROOTS, (
        "git tracks top-level directories missing from the fallback allowlist: "
        f"{sorted(tracked_roots - _FALLBACK_SOURCE_ROOTS)}; extend "
        "_FALLBACK_SOURCE_ROOTS in tests/test_powerdns_config_hygiene.py"
    )
    assert tracked_root_files <= allowed_root_files, (
        "git tracks root-level files missing from the fallback allowlist: "
        f"{sorted(tracked_root_files - allowed_root_files)}; extend "
        "_FALLBACK_ROOT_FILES in tests/test_powerdns_config_hygiene.py"
    )


def _assert_fallback_matches_git(
    fallback_paths: set[Path],
    git_paths: set[Path],
    git_ignored_or_untracked: set[Path],
):
    """The fallback includes every tracked text file; extras are untracked or ignored."""
    _assert_git_allowlist_coverage(git_paths)
    missing = git_paths - fallback_paths
    assert not missing, (
        "filesystem fallback omitted tracked text files: "
        f"{sorted(missing)}"
    )
    unexplained = (fallback_paths - git_paths) - git_ignored_or_untracked
    assert not unexplained, (
        "filesystem fallback included files that Git does not report as ignored "
        f"or untracked: {sorted(unexplained)}"
    )


def test_tracked_text_files_falls_back_when_git_executable_is_missing(monkeypatch):
    """A genuinely absent Git executable may use the source-tree fallback."""
    git_files = _git_text_files()
    git_ignored_or_untracked = _git_ignored_or_untracked_paths()

    def missing_git(*_args, **_kwargs):
        raise FileNotFoundError(2, "No such file or directory", "git")

    monkeypatch.setattr(subprocess, "run", missing_git)
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    fallback_files = _tracked_text_files()
    fallback_paths = {path.relative_to(REPO) for path, _text in fallback_files}

    assert fallback_paths, "filesystem fallback returned no source files"
    assert Path("tmp/restart.txt") in fallback_paths

    if git_files is None:
        pytest.skip(
            "Git executable or repository metadata unavailable; fallback assertions "
            "ran, comparison baseline skipped"
        )
    assert git_ignored_or_untracked is not None
    git_paths = {path.relative_to(REPO) for path, _text in git_files}
    _assert_fallback_matches_git(
        fallback_paths,
        git_paths,
        git_ignored_or_untracked,
    )


def test_permission_error_launching_git_is_not_masked_by_fallback(monkeypatch):
    def inaccessible_git(*_args, **_kwargs):
        raise PermissionError(13, "Permission denied", "git")

    monkeypatch.setattr(subprocess, "run", inaccessible_git)
    with pytest.raises(PermissionError, match="Permission denied"):
        _tracked_text_files()


def test_missing_cwd_file_not_found_is_not_masked_by_fallback(monkeypatch):
    def missing_cwd(*_args, **_kwargs):
        raise FileNotFoundError(2, "No such file or directory", "/missing/worktree")

    monkeypatch.setattr(subprocess, "run", missing_cwd)
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/git")
    with pytest.raises(FileNotFoundError, match="/missing/worktree"):
        _tracked_text_files()


def test_not_a_git_repository_error_uses_fallback(monkeypatch):
    def unavailable_git(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            ["git", "ls-files", "-z"],
            128,
            "",
            "[ksm-optin] KSM enabled for this process (PR_SET_MEMORY_MERGE=1)\n"
            "fatal: not a git repository: "
            "/workspaces/netcup-api-filter/.git/worktrees/wp8\n",
        )

    monkeypatch.setattr(subprocess, "run", unavailable_git)
    assert _tracked_text_files() == _walk_text_files()


def test_other_git_errors_are_not_masked_by_fallback(monkeypatch):
    stderr = "fatal: bad config line 1 in file /tmp/example.gitconfig\n"

    def broken_git(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            ["git", "ls-files", "-z"],
            128,
            "",
            stderr,
        )

    monkeypatch.setattr(subprocess, "run", broken_git)
    with pytest.raises(AssertionError, match="fatal: bad config line"):
        _tracked_text_files()


def test_fallback_allowlist_reports_new_top_level_paths():
    with pytest.raises(AssertionError, match="extend _FALLBACK_SOURCE_ROOTS"):
        _assert_git_allowlist_coverage({Path("new-source-root/module.py")})
    with pytest.raises(AssertionError, match="extend _FALLBACK_ROOT_FILES"):
        _assert_git_allowlist_coverage({Path("new-root-script.py")})


def test_fallback_comparison_allows_ignored_and_untracked_but_not_missing_tracked(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git executable unavailable; comparison control cannot run")

    repo = tmp_path / "repo"

    def write(relative: str, text: str = "source\n"):
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    write(".gitignore", "*.log\n")
    write("README.md")
    write("src/tracked.py")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    write("src/runtime.log", "ignored runtime output\n")
    write("src/untracked.txt", "untracked local output\n")

    fallback_paths = {
        path.relative_to(repo)
        for path, _text in _walk_text_files(repo)
    }
    git_files = _git_text_files(repo)
    git_ignored_or_untracked = _git_ignored_or_untracked_paths(repo)
    assert git_files is not None
    assert git_ignored_or_untracked is not None
    git_paths = {path.relative_to(repo) for path, _text in git_files}

    assert {Path("src/runtime.log"), Path("src/untracked.txt")} <= fallback_paths - git_paths
    _assert_fallback_matches_git(fallback_paths, git_paths, git_ignored_or_untracked)

    with pytest.raises(AssertionError, match=r"omitted tracked text files.*src/tracked.py"):
        _assert_fallback_matches_git(
            fallback_paths - {Path("src/tracked.py")},
            git_paths,
            git_ignored_or_untracked,
        )


def test_fallback_ignores_generated_dirs_inside_and_outside_allowlist(tmp_path):
    repo = tmp_path / "repo"

    def write(relative: str, text: str = "source\n"):
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    write(
        ".gitignore",
        "/docs/_build/\n/target/\n/tooling/playwright/screenshots/\n",
    )
    write("README.md")
    write("docs/guide.md")
    write("src/source.py")
    write("tooling/README.md")
    write("docs/_build/x.md", "generated\n")
    write("target/y.md", "generated\n")
    write("tooling/playwright/screenshots/z.txt", "generated\n")

    expected = {
        Path(".gitignore"),
        Path("README.md"),
        Path("docs/guide.md"),
        Path("src/source.py"),
        Path("tooling/README.md"),
    }
    fallback_paths = {
        path.relative_to(repo)
        for path, _text in _walk_text_files(repo)
    }
    assert fallback_paths == expected

    if shutil.which("git") is None:
        pytest.skip("git executable unavailable; fallback exclusion assertions ran")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    git_files = _git_text_files(repo)
    assert git_files is not None
    git_paths = {path.relative_to(repo) for path, _text in git_files}
    assert git_paths == expected


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
