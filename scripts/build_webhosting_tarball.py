#!/usr/bin/env python3
"""Build and publish vendored Passenger tarballs for cmru.

The build is intentionally narrow: package the webhosting runtime for one
interpreter, with all wheels already unpacked in ``vendor/``.  cmru owns release
versions, release tags, checksums, and publication; this script only supplies
naf's runtime tree and calls cmru's landed multi-variant publisher.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

import tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = REPO_ROOT / "dist"


def _target_versions() -> list[tuple[str, str]]:
    """Read cmru's single source of truth for Passenger variants."""
    with (REPO_ROOT / "cmru.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]
    versions: list[tuple[str, str]] = []
    for variant in project.get("variants", []):
        arg = variant.get("build_arg", "")
        key, separator, value = arg.partition("=")
        if key != "PYTHON_VERSION" or not separator or not value:
            raise RuntimeError(
                f"variant {variant.get('name')!r} needs build_arg PYTHON_VERSION=<major.minor>"
            )
        versions.append((str(variant["name"]), value))
    if not versions:
        raise RuntimeError("cmru.toml declares no naf Passenger variants")
    return versions


def _assert_target_interpreter(python_version: str) -> None:
    actual = f"{sys.version_info.major}.{sys.version_info.minor}"
    if actual != python_version:
        raise RuntimeError(
            f"refusing to build {python_version} wheels under Python {actual}; run "
            "run build-one inside the matching ciu test-runner (see build_all)"
        )


def _vendor_dependencies(vendor_dir: Path, python_version: str) -> None:
    with tempfile.TemporaryDirectory() as download_dir:
        command = [
            sys.executable, "-m", "pip", "download", "--disable-pip-version-check",
            "--only-binary", ":all:", "--python-version", python_version,
            "--platform", "manylinux2014_x86_64", "--platform", "any",
            "--dest", download_dir, "--requirement", "requirements-runtime.txt",
        ]
        subprocess.run(command, cwd=REPO_ROOT, check=True)
        wheels = sorted(Path(download_dir).glob("*.whl"))
        if not wheels:
            raise RuntimeError("pip download produced no wheels")
        for wheel in wheels:
            with zipfile.ZipFile(wheel) as archive:
                for member in archive.namelist():
                    if ".dist-info/" not in member:
                        archive.extract(member, vendor_dir)


def seed_database(staging: Path, *, target: str = "webhosting") -> tuple:
    """Seed a fresh database while the matching ABI is importable.

    This small public helper is also used by CI's source-tree bootstrap; unlike
    the release build, CI passes ``target=local`` so its Mailpit settings are
    seeded.  It never creates release state or an archive.
    """
    original_cwd = Path.cwd()
    src_dir = staging / "src"
    vendor_dir = staging / "vendor"
    sys.path[:0] = [str(vendor_dir), str(src_dir), str(staging)]
    try:
        os.chdir(staging)
        os.environ["DEPLOYMENT_TARGET"] = target
        os.environ["NETCUP_FILTER_DB_PATH"] = str(staging / "netcup_filter.db")
        from flask import Flask
        from netcup_api_filter import database
        from netcup_api_filter.bootstrap import seed_default_entities
        from netcup_api_filter.bootstrap.seeding import seed_settings_from_env

        app = Flask(__name__, template_folder=str(src_dir / "netcup_api_filter" / "templates"))
        app.config.update(
            SECRET_KEY="build-only-key",
            SQLALCHEMY_DATABASE_URI=f"sqlite:///{staging / 'netcup_filter.db'}",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        database.db.init_app(app)
        with app.app_context():
            database.db.create_all()
            seed_settings_from_env()
            return seed_default_entities(
                seed_demo_clients_flag=True, seed_mock_email=(target == "local")
            )
    finally:
        os.chdir(original_cwd)
        del sys.path[:3]


def _tar_xz(source: Path, output: Path) -> None:
    epoch = int(os.environ.get("SOURCE_DATE_EPOCH", "0"))
    with tarfile.open(output, "w:xz", preset=9) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_dir():
                continue
            info = archive.gettarinfo(str(path), arcname=str(path.relative_to(source)))
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            info.mtime = epoch
            with path.open("rb") as handle:
                archive.addfile(info, handle)


def build_one(python_version: str, output: Path) -> None:
    _assert_target_interpreter(python_version)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"naf-webhosting-py{python_version.replace('.', '')}-", dir=DIST_DIR) as temp:
        staging = Path(temp) / "app"
        staging.mkdir(parents=True)
        shutil.copy2(REPO_ROOT / ".env.defaults", staging / ".env.defaults")
        shutil.copy2(REPO_ROOT / "src/netcup_api_filter/passenger_wsgi.py", staging / "passenger_wsgi.py")
        shutil.copytree(REPO_ROOT / "src", staging / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copytree(REPO_ROOT / "scripts", staging / "scripts", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        vendor_dir = staging / "vendor"
        vendor_dir.mkdir()
        _vendor_dependencies(vendor_dir, python_version)
        seed_database(staging)
        _tar_xz(staging, output)
    print(f"[INFO] built {output.relative_to(REPO_ROOT)} for Python {python_version}")


def _runner_container(variant: str) -> str:
    """Name of the ciu-managed runner for a variant: <project>-<tag>-test-runner-<variant>.

    Derived from the rendered ciu.global.toml (the same rule run-gate uses); absence
    fails loudly instead of guessing a name.
    """
    toml_path = REPO_ROOT / "ciu.global.toml"
    if not toml_path.is_file():
        raise RuntimeError(f"{toml_path} missing: render it and start the runners (ciu up --dir tooling/test-runner)")
    with toml_path.open("rb") as handle:
        deploy = tomllib.load(handle).get("deploy", {})
    project, tag = deploy.get("project_name"), deploy.get("environment_tag")
    if not project or not tag:
        raise RuntimeError(f"{toml_path}: [deploy] project_name and environment_tag are required")
    return f"{project}-{tag}-test-runner-{variant}"


def _docker_out(*args: str) -> str:
    return subprocess.check_output(["docker", *args], text=True).strip()


def build_all() -> None:
    host_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    for variant, python_version in _target_versions():
        output = DIST_DIR / f"naf-{variant}.tar.xz"
        container = _runner_container(variant)
        # The runner bind-mounts ONE checkout. Refuse to build a release from a
        # tree other than the one cmru is releasing.
        runner_head = _docker_out(
            "exec", "-w", str(REPO_ROOT), container,
            "git", "-c", "safe.directory=*", "rev-parse", "HEAD",
        )
        if runner_head != host_head:
            raise RuntimeError(
                f"{container} sees {runner_head[:12]} at {REPO_ROOT}, release tree is {host_head[:12]}: "
                "the runner mounts a different checkout; start it from this tree"
            )
        image_id = _docker_out("inspect", "-f", "{{.Image}}", container)
        command = [
            "docker", "exec", "-e", f"NAF_BUILDER_IMAGE_DIGEST={image_id}",
            "-w", str(REPO_ROOT), container,
            "/opt/tester-venv/bin/python", "scripts/build_webhosting_tarball.py", "build-one",
            "--python-version", python_version, "--output", str(output.relative_to(REPO_ROOT)),
        ]
        print("[INFO] " + " ".join(command))
        subprocess.run(command, cwd=REPO_ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build")
    one = sub.add_parser("build-one")
    one.add_argument("--python-version", required=True)
    one.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "build":
        build_all()
    else:
        build_one(args.python_version, (REPO_ROOT / args.output).resolve())


if __name__ == "__main__":
    main()
