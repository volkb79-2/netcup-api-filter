#!/usr/bin/env python3
"""Preflight this checkout's Passenger runner and export cmru bundle-build inputs."""
from __future__ import annotations

import logging
import os
import shlex
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)
RUNNER_UP_INSTRUCTION = (
    "every checkout runs its own test runners, including a cmru release worktree: "
    "run `ciu up --dir tooling/test-runner` in {root} first (with its ciu env loaded: "
    "`eval \"$(ciu env print)\"`, PWMCP_NETWORK), then retry"
)


def _project_variants() -> list[dict[str, str]]:
    with (REPO_ROOT / "cmru.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]
    variants = project.get("variants", [])
    if not variants:
        raise RuntimeError("cmru.toml declares no Passenger variants")
    # KI-126 applies one [exec].prefix to every selected variant. Naf currently
    # has one ABI; refuse a second until cmru can select a runner per variant.
    if len(variants) != 1:
        raise RuntimeError(
            "naf's bundle.toml has one runner prefix for all variants; "
            "cmru currently cannot select a different [exec] runner per variant"
        )
    variant = variants[0]
    if not isinstance(variant.get("name"), str) or not variant["name"]:
        raise RuntimeError("each cmru.toml Passenger variant needs a name")
    return variants


def _release_version(environ: dict[str, str]) -> str:
    explicit = environ.get("NAF_VERSION", "").strip()
    if explicit:
        return explicit
    tag = environ.get("CMRU_RELEASE_TAG", "").strip()
    prefix = "naf-v"
    if not tag.startswith(prefix) or not tag[len(prefix):]:
        raise RuntimeError(
            "NAF_VERSION or a CMRU_RELEASE_TAG beginning with naf-v is required"
        )
    return tag[len(prefix):]


def _write_bundle_cmru_config() -> Path:
    """Normalize cmru's tag prefix for KI-126's current manifest-tag implementation.

    naf's project.prefix follows cmru's checked-in template convention (`naf-v`), while
    bundle-build currently passes that value to version_to_tag(), which adds another `-v`.
    Keep the declared variants and all other config bytes intact, changing only the temporary
    copy's prefix to `naf` so the resulting manifest tag matches the release tag.
    """
    source = REPO_ROOT / "cmru.toml"
    raw = source.read_text(encoding="utf-8")
    with source.open("rb") as handle:
        project = tomllib.load(handle)["project"]
    prefix = project.get("prefix")
    if project.get("id") != "naf" or not isinstance(prefix, str) or not prefix.endswith("-v"):
        raise RuntimeError("expected cmru.toml project.id=naf and a project.prefix ending in -v")
    old_line = f'prefix = "{prefix}"'
    if raw.count(old_line) != 1:
        raise RuntimeError("could not safely normalize the cmru.toml project prefix")
    normalized = raw.replace(old_line, f'prefix = "{prefix.removesuffix("-v")}"', 1)
    directory = Path(tempfile.mkdtemp(prefix=".naf-bundle-cmru-", dir=REPO_ROOT))
    path = directory / "cmru.toml"
    try:
        path.write_text(normalized, encoding="utf-8")
    except Exception:
        path.unlink(missing_ok=True)
        directory.rmdir()
        raise
    return path


def _runner_container(variant: str) -> str:
    sys.path.insert(0, str(REPO_ROOT / "tooling"))
    try:
        from ciu_identity import resolve_container

        try:
            return resolve_container(
                "tooling/test-runner",
                f"test-runner-{variant}",
                repo_root=str(REPO_ROOT),
            )
        except RuntimeError as exc:
            raise RuntimeError(
                f"cannot resolve this checkout's test-runner-{variant}: {exc}; "
                + RUNNER_UP_INSTRUCTION.format(root=REPO_ROOT)
            ) from exc
    finally:
        sys.path.pop(0)


def _require_running(container: str, *, runner=subprocess.run) -> None:
    probe = runner(
        ["docker", "inspect", "-f", "{{.State.Running}}", container],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        state = "absent" if probe.returncode != 0 else "not running"
        raise RuntimeError(
            f"release runner {container} is {state}; "
            + RUNNER_UP_INSTRUCTION.format(root=REPO_ROOT)
        )


def _host_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
    ).strip()


def _runner_head(container: str) -> str:
    return subprocess.check_output(
        [
            "docker", "exec", "-w", str(REPO_ROOT), container,
            "git", "-c", "safe.directory=*", "rev-parse", "HEAD",
        ],
        text=True,
    ).strip()


def _prepare_environment(environ: dict[str, str] | None = None) -> dict[str, str]:
    environment = dict(os.environ if environ is None else environ)
    variant = _project_variants()[0]["name"]
    version = _release_version(environment)
    container = _runner_container(variant)
    _require_running(container)
    host_head = _host_head()
    runner_head = _runner_head(container)
    if runner_head != host_head:
        raise RuntimeError(
            f"{container} sees {runner_head[:12]} at {REPO_ROOT}, release tree is "
            f"{host_head[:12]}: the runner mounts a different checkout; start it from this tree"
        )
    return {
        "NAF_BUNDLE_RUNNER_ROOT": str(REPO_ROOT),
        "NAF_BUNDLE_RUNNER_CONTAINER": container,
        "NAF_VERSION": version,
        "NAF_BUNDLE_CMRU_CONFIG": str(_write_bundle_cmru_config()),
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare",))
    parser.parse_args()
    try:
        values = _prepare_environment()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        logger.error("Passenger bundle runner preflight failed: %s", exc)
        raise SystemExit(2) from None
    for name, value in values.items():
        print(f"export {name}={shlex.quote(value)}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    main()
