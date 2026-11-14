#!/usr/bin/env python3
"""Complete naf-specific Passenger staging inside the matching test runner."""
from __future__ import annotations

import fnmatch
import logging
import os
import shutil
import sys
import zipfile
from pathlib import Path


logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[1]

# These are the exact ignore patterns used by the retired copytree calls. cmru's
# copy step already excludes the first two; keeping the full set here pins the
# release tree's historical exclusion contract.
LEGACY_COPY_IGNORE_PATTERNS = ("__pycache__", "*.pyc", "*,cover")


def _runtime_python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def _assert_target_interpreter(expected: str) -> None:
    actual = _runtime_python_version()
    if actual != expected:
        raise RuntimeError(
            f"refusing to stage the {expected} Passenger bundle under Python {actual}; "
            "run bundle-build through the matching checkout test-runner"
        )


def _prune_legacy_copy_exclusions(bundle_dir: Path) -> None:
    """Apply the old copytree ignores to the two copied source trees."""
    for root_name in ("src", "scripts"):
        source_root = bundle_dir / root_name
        if not source_root.exists():
            continue
        candidates = sorted(
            source_root.rglob("*"),
            key=lambda path: (len(path.parts), path.as_posix()),
            reverse=True,
        )
        for path in candidates:
            if not any(
                fnmatch.fnmatch(path.name, pattern)
                for pattern in LEGACY_COPY_IGNORE_PATTERNS
            ):
                continue
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)


def _extract_vendor_wheels(vendor_dir: Path) -> None:
    """Expand downloaded wheels into the importable directory layout Passenger uses."""
    wheels = sorted(vendor_dir.glob("*.whl"))
    if not wheels:
        raise RuntimeError(f"cmru vendored no wheels into {vendor_dir}")
    for wheel in wheels:
        with zipfile.ZipFile(wheel) as archive:
            for member in archive.namelist():
                if ".dist-info/" not in member:
                    archive.extract(member, vendor_dir)
        wheel.unlink()


def seed_database(bundle_dir: Path) -> None:
    """Seed the shipped database using the staged application and ABI-specific vendor tree."""
    bundle_dir = bundle_dir.resolve()
    original_cwd = Path.cwd()
    original_sys_path = list(sys.path)
    env_names = ("DEPLOYMENT_TARGET", "NETCUP_FILTER_DB_PATH")
    previous_env = {name: os.environ.get(name) for name in env_names}
    src_dir = bundle_dir / "src"
    vendor_dir = bundle_dir / "vendor"
    sys.path[:0] = [str(vendor_dir), str(src_dir), str(bundle_dir)]
    os.environ["DEPLOYMENT_TARGET"] = "webhosting"
    os.environ["NETCUP_FILTER_DB_PATH"] = str(bundle_dir / "netcup_filter.db")
    try:
        os.chdir(bundle_dir)
        from flask import Flask
        from netcup_api_filter import database
        from netcup_api_filter.bootstrap import seed_shipped_database

        app = Flask(
            __name__,
            template_folder=str(src_dir / "netcup_api_filter" / "templates"),
        )
        app.config.update(
            SECRET_KEY="build-only-key",
            SQLALCHEMY_DATABASE_URI=f"sqlite:///{bundle_dir / 'netcup_filter.db'}",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        database.db.init_app(app)
        with app.app_context():
            database.db.create_all()
            seed_shipped_database(mock_email=None)
    finally:
        os.chdir(original_cwd)
        sys.path[:] = original_sys_path
        for name, value in previous_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def copy_seed_defaults(bundle_dir: Path, repo_root: Path) -> None:
    """Copy the build-only defaults for seeding; CMRU must not copy this protected input."""
    bundle_dir = bundle_dir.resolve()
    source = repo_root.resolve() / ".env.defaults"
    if not source.is_file():
        raise FileNotFoundError(f"Passenger seed defaults not found: {source}")
    shutil.copy2(source, bundle_dir / ".env.defaults")


def ship_runtime_defaults(bundle_dir: Path, repo_root: Path) -> None:
    """Replace the staged seed input with naf's allowlisted runtime defaults."""
    bundle_dir = bundle_dir.resolve()
    repo_root = repo_root.resolve()
    (bundle_dir / ".env.defaults").unlink()
    src_dir = str(bundle_dir / "src")
    original_sys_path = list(sys.path)
    sys.path.insert(0, src_dir)
    try:
        from netcup_api_filter.config_defaults import (
            SHIPPED_RUNTIME_OVERRIDES,
            write_shipped_defaults,
        )

        write_shipped_defaults(
            repo_root / ".env.defaults",
            bundle_dir,
            overrides=SHIPPED_RUNTIME_OVERRIDES,
        )
    finally:
        sys.path[:] = original_sys_path


def stage_bundle(
    bundle_dir: Path,
    python_version: str,
    *,
    repo_root: Path = REPO_ROOT,
    seed=seed_database,
    render_defaults=ship_runtime_defaults,
) -> None:
    """Apply naf's post-vendor, pre-manifest work to cmru's copied bundle tree."""
    bundle_dir = bundle_dir.resolve()
    _assert_target_interpreter(python_version)
    _prune_legacy_copy_exclusions(bundle_dir)
    _extract_vendor_wheels(bundle_dir / "vendor")
    copy_seed_defaults(bundle_dir, repo_root)
    seed(bundle_dir)
    render_defaults(bundle_dir, repo_root)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle_dir", type=Path)
    parser.add_argument("python_version")
    args = parser.parse_args()
    try:
        stage_bundle(args.bundle_dir, args.python_version, repo_root=REPO_ROOT)
    except Exception as exc:
        logger.error("Passenger bundle stage failed: %s", exc)
        raise SystemExit(1) from None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    main()
