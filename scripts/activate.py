#!/usr/bin/env python3
"""Passenger activation adapter shared by cmru's installer and ciu --thin.

The webhoster invocation is ``python3 scripts/activate.py apply --variant py311``.
It only mutates the deployment root after a tarball is selected.  Secret-key
preservation uses Python's stdlib SQLite support: an absent/empty preserved secret is a
no-op, but a non-empty one that cannot be restored fails the activation loudly.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import tarfile
import time
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional


def _preserved_secret(database_path: Path) -> Optional[str]:
    try:
        with sqlite3.connect(database_path) as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = 'secret_key'"
            ).fetchone()
        return str(row[0]) if row and row[0] else None
    except sqlite3.Error:
        return None


def _restore_secret(database_path: Path, secret: Optional[str]) -> None:
    if not secret:
        return
    try:
        with sqlite3.connect(database_path) as connection:
            # UPSERT: a freshly seeded release DB has no secret_key row yet (the app creates it on
            # first start), so a bare UPDATE would silently rotate the key on every release.
            connection.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES ('secret_key', ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                (secret, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")),
            )
            connection.commit()
    except sqlite3.Error as error:
        # A non-empty preserved secret that cannot be restored would silently rotate SECRET_KEY
        # (invalidating every session/token): fail the activation instead of continuing.
        raise RuntimeError(f"could not restore existing SECRET_KEY into {database_path}: {error}") from error


def _health(url: str) -> None:
    last_error: Optional[Exception] = None
    for _attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                if 200 <= response.status < 400:
                    return
                raise RuntimeError(f"unexpected HTTP status {response.status}")
        except Exception as error:  # Passenger reload can briefly refuse a connection.
            last_error = error
            time.sleep(2)
    raise RuntimeError(f"health probe failed for {url}: {last_error}")


def _archive(root: Path, variant: str) -> Path:
    matches = sorted((root / "dist").glob(f"naf-{variant}.tar.xz"))
    if len(matches) != 1:
        raise RuntimeError(f"expected one dist/naf-{variant}.tar.xz under {root}")
    return matches[0]


def _extract(archive: tarfile.TarFile, root: Path) -> None:
    """Extract only regular archive members beneath the deployment root.

    ``tarfile``'s ``filter=`` API is too new for older Passenger Pythons.  Keep
    the same traversal protection explicitly so an archive can never escape
    the configured Passenger app root.
    """
    root = root.resolve()
    for member in archive.getmembers():
        destination = (root / member.name).resolve()
        if destination != root and root not in destination.parents:
            raise RuntimeError(f"refusing tar member outside deployment root: {member.name}")
        if member.issym() or member.islnk() or member.isdev():
            raise RuntimeError(f"refusing unsafe tar member: {member.name}")
    archive.extractall(root)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verb", choices=("bootstrap", "apply", "health", "rollback"))
    parser.add_argument("--release-root", type=Path, default=Path.cwd())
    parser.add_argument("--config")       # cmru adapter contract; naf needs no host TOML.
    parser.add_argument("--manifest")     # cmru adapter contract; tarball has no manifest.
    parser.add_argument("--variant", choices=("py311",))
    parser.add_argument("--health-url", default=os.environ.get("NAF_HEALTH_URL", "http://127.0.0.1/admin/login"))
    args = parser.parse_args()
    root = args.release_root.resolve()
    restart = root / "tmp" / "restart.txt"

    if args.verb == "bootstrap":
        restart.parent.mkdir(parents=True, exist_ok=True)
        return
    if args.verb == "health":
        _health(args.health_url)
        return
    if args.verb == "rollback":
        raise RuntimeError("rollback is unavailable: Passenger tarballs are greenfield releases")
    if not args.variant:
        raise RuntimeError("apply requires an explicit --variant (py311)")

    old_secret = _preserved_secret(root / "netcup_filter.db")
    with tarfile.open(_archive(root, args.variant), "r:xz") as archive:
        _extract(archive, root)
    _restore_secret(root / "netcup_filter.db", old_secret)
    restart.parent.mkdir(parents=True, exist_ok=True)
    restart.touch()
    _health(args.health_url)


if __name__ == "__main__":
    main()
