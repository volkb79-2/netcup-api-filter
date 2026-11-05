"""Review #15, static checks (the image itself is built by cmru, not in unit tests).

* Dockerfile.release switches to a non-root USER before CMD, and the writable paths are owned.
* .dockerignore is an allowlist that never lets .env*/.ciu reach the builder, but does include
  every path the repo-root Dockerfiles COPY or bind-mount.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOCKERFILES = [REPO / "Dockerfile.release", REPO / "tooling" / "test-runner" / "Dockerfile"]


def _ignore_lines() -> list[str]:
    return [line.strip() for line in (REPO / ".dockerignore").read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")]


def _included(path: str) -> bool:
    """Minimal .dockerignore semantics for the patterns used here (last match wins)."""
    included = True
    for line in _ignore_lines():
        negate = line.startswith("!")
        pattern = line[1:] if negate else line
        if pattern == "*" or path == pattern.rstrip("/") or path.startswith(pattern.rstrip("/") + "/") \
                or (pattern.startswith("**/") and path.endswith(pattern[3:].lstrip("*"))):
            included = negate
    return included


def test_release_image_runs_as_non_root():
    text = (REPO / "Dockerfile.release").read_text()
    users = re.findall(r"^USER\s+(\S+)", text, re.M)
    assert users and users[-1].split(":")[0] not in {"root", "0"}
    assert text.index("USER ") < text.index("CMD [")
    assert re.search(r"chown\s+naf:naf\s+/data\s+/config", text)
    assert "NETCUP_FILTER_LOG_FILE=/data/" in text and "NETCUP_FILTER_APP_ROOT=/config" in text


def test_dockerignore_is_an_allowlist_without_secrets():
    lines = _ignore_lines()
    assert lines[0] == "*"
    for path in (".env", ".env.workspace", ".env.services", ".ciu/secrets/naf/x", "netcup_filter.db",
                 "deploy-local/netcup_filter.db", ".worktrees/x/.env", "tests/conftest.py"):
        assert not _included(path), path


def test_every_copied_or_mounted_path_is_in_the_context():
    sources = []
    for dockerfile in DOCKERFILES:
        text = dockerfile.read_text()
        for match in re.finditer(r"^COPY\s+(?!--from)(.+)$", text, re.M):
            sources.extend(match.group(1).split()[:-1])
        sources.extend(re.findall(r"--mount=type=bind,source=([^,\s]+)", text))
    assert sources
    for src in sources:
        assert _included(src.rstrip("/")), f"{src} is COPY'd/mounted but excluded by .dockerignore"
