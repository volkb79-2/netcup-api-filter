#!/usr/bin/env python3
"""Pass cmru's tarball publisher the variants declared in cmru.toml."""
from __future__ import annotations

import os
import subprocess
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _variant_specs() -> list[str]:
    with (REPO_ROOT / "cmru.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]
    variants = project.get("variants", [])
    if not variants:
        raise RuntimeError("cmru.toml declares no Passenger variants")
    specs: list[str] = []
    for variant in variants:
        name = variant.get("name")
        label = variant.get("label")
        if not isinstance(name, str) or not name:
            raise RuntimeError("each cmru.toml Passenger variant needs a name")
        if not isinstance(label, str) or not label:
            raise RuntimeError(f"Passenger variant {name!r} needs a publish label")
        specs.append(f"{name}={label}")
    return specs


def main() -> None:
    env = os.environ.copy()
    tag = env.get("CMRU_RELEASE_TAG", "")
    prefix = "naf-v"
    version = env.get("NAF_VERSION", "").strip()
    if not version and tag.startswith(prefix):
        version = tag[len(prefix):]
    if not version:
        raise SystemExit("NAF_VERSION or CMRU_RELEASE_TAG beginning with naf-v is required")
    env["NAF_VERSION"] = version
    command = [
        "cmru", "handler", "tarball-publish",
        "--prefix", "naf",
        "--cwd", ".",
        "--glob", "dist/naf-v*.tar.xz",
        "--version-env", "NAF_VERSION",
        "--notes-env", "NAF_RELEASE_NOTES",
    ]
    for variant in _variant_specs():
        command.extend(["--variant", variant])
    subprocess.run(command, cwd=REPO_ROOT, env=env, check=True)


if __name__ == "__main__":
    main()
