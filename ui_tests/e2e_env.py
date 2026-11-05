"""Throwaway app instances for the e2e suite (S3 of the credentials/test-setup plan).

Every e2e session (and every test that needs a pristine install of its own) gets:

1. a private work dir (``tempfile.mkdtemp`` inside the runner container);
2. a consistent copy of the **golden DB** — ``<repo>/<E2E_DEPLOY_DIR>/netcup_filter.db`` as
   ``run-gate local-build`` seeded it (bootstrap.instance.init_instance: the pre-set admin with
   ``must_change_password`` + Mailpit email config, nothing else). The copy is checked first:
   a golden DB that something has modified fails the session immediately;
3. optionally a ``prepare(db_path)`` step before the app starts (personas, ui_tests/personas.py);
4. the app itself — the SAME package and entry point as production
   (``gunicorn -c gunicorn.conf.py passenger_wsgi:application`` from the deploy tree) — on a
   free port of this runner, reachable by the pwmcp browser over the shared docker network at
   ``http://$NAF_E2E_ADVERTISE_HOST:<port>``.

The instance is stated, never inferred: ``FLASK_ENV=local_test`` and
``FLASK_SESSION_COOKIE_SECURE=false`` (the origin is plain HTTP by container name: a Secure
cookie would be dropped and every login would bounce), a random ``SECRET_KEY``, its own DB and
log file. Nothing it writes lives in the repository; an interrupted run leaves only an orphaned
tmp dir that no later run reads, so re-running after an interruption is always clean, and
concurrent sessions (worktrees) never share a database, port or cookie jar.
"""
from __future__ import annotations

import logging
import os
import secrets
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, TypeVar

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
T = TypeVar("T")


class E2EEnvironmentError(RuntimeError):
    """The e2e environment cannot be created; the session must stop, not flood."""


def _setting(key: str) -> str:
    """Config value: environment override, else .env.defaults (fail fast if neither)."""
    value = os.environ.get(key, "").strip()
    if value:
        return value
    from netcup_api_filter.config_defaults import require_default

    try:
        return require_default(key)
    except RuntimeError as exc:
        raise E2EEnvironmentError(str(exc)) from exc


def deploy_dir() -> Path:
    path = REPO_ROOT / _setting("E2E_DEPLOY_DIR")
    if not (path / "passenger_wsgi.py").is_file():
        raise E2EEnvironmentError(
            f"{path} is not a built deploy tree (no passenger_wsgi.py). "
            "Build it first: run-gate local-build --worktree \"$PWD\""
        )
    return path


def golden_db_path() -> Path:
    path = deploy_dir() / "netcup_filter.db"
    if not path.is_file():
        raise E2EEnvironmentError(f"golden DB missing: {path} (run-gate local-build)")
    return path


def advertise_host() -> str:
    host = os.environ.get("NAF_E2E_ADVERTISE_HOST", "").strip()
    if not host:
        raise E2EEnvironmentError(
            "NAF_E2E_ADVERTISE_HOST is not set: the runner's own container name, under which the "
            "pwmcp browser reaches the per-session app. It is set by "
            "tooling/test-runner/ciu.compose.yml.j2 (re-create the runners: ciu up --dir tooling/test-runner)."
        )
    return host


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("0.0.0.0", 0))
        return int(sock.getsockname()[1])


def copy_golden_db(destination: Path) -> None:
    """Consistent copy (SQLite online backup) of the golden DB, then verify it is pristine."""
    source = sqlite3.connect(f"file:{golden_db_path()}?mode=ro", uri=True)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
    finally:
        source.close()
        target.close()
    verify_pristine(destination)


def verify_pristine(db_path: Path) -> None:
    """The golden DB must contain exactly the shipped admin, still forced to change its password.

    Anything else means something served or mutated the golden DB (the incident of
    2026-11-05 in a new form): stop the session with one clear message.
    """
    from netcup_api_filter.config_defaults import require_default

    shipped = require_default("DEFAULT_ADMIN_USERNAME")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        accounts = conn.execute("SELECT username, is_admin, must_change_password FROM accounts").fetchall()
        lockouts = conn.execute(
            "SELECT key FROM settings WHERE key LIKE 'failed_login_user_%' AND value IS NOT NULL AND value != 'null'"
        ).fetchall()
    finally:
        conn.close()
    if accounts != [(shipped, 1, 1)] or lockouts:
        raise E2EEnvironmentError(
            f"golden DB copy {db_path} is not pristine (accounts={[a[0] for a in accounts]}, "
            f"lockouts={len(lockouts)}): something served or modified it. Rebuild it: "
            "run-gate local-build --worktree \"$PWD\""
        )


@dataclass(frozen=True)
class AppInstance:
    base_url: str
    db_path: Path
    workdir: Path
    log_path: Path


def _wait_ready(proc: subprocess.Popen, port: int, log_path: Path) -> None:
    deadline = time.monotonic() + float(_setting("E2E_APP_START_TIMEOUT_SECONDS"))
    url = f"http://127.0.0.1:{port}/admin/login"
    last_error = "no attempt"
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise E2EEnvironmentError(
                f"e2e app exited with status {proc.returncode} before becoming ready; log tail:\n"
                + _tail(log_path)
            )
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status == 200:
                    return
                last_error = f"HTTP {response.status}"
        except (urllib.error.URLError, OSError) as exc:
            last_error = str(exc)
        time.sleep(0.25)
    raise E2EEnvironmentError(f"e2e app not ready at {url} ({last_error}); log tail:\n" + _tail(log_path))


def _tail(path: Path, lines: int = 40) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return "(no log)"


def _stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=float(_setting("E2E_APP_STOP_TIMEOUT_SECONDS")))
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
    except ProcessLookupError:
        pass


@contextmanager
def app_instance(prepare: Callable[[Path], T] | None = None) -> Iterator[tuple[AppInstance, T | None]]:
    """Start a throwaway instance on a copy of the golden DB; yield ``(instance, prepare(db))``."""
    tree = deploy_dir()
    host = advertise_host()
    workdir = Path(tempfile.mkdtemp(prefix="naf-e2e-"))
    db_path = workdir / "netcup_filter.db"
    log_path = workdir / "app.log"
    proc: subprocess.Popen | None = None
    try:
        copy_golden_db(db_path)
        prepared = prepare(db_path) if prepare is not None else None

        port = _free_port()
        env = {key: value for key, value in os.environ.items() if not key.startswith("NAF_BOOTSTRAP_ADMIN_")}
        env.update({
            "NETCUP_FILTER_DB_PATH": str(db_path),
            "NETCUP_FILTER_LOG_FILE": str(workdir / "netcup_filter.log"),
            "FLASK_ENV": "local_test",
            "FLASK_SESSION_COOKIE_SECURE": "false",
            "SECRET_KEY": secrets.token_hex(32),
            "GUNICORN_BIND": f"0.0.0.0:{port}",
            "GUNICORN_WORKERS": _setting("E2E_APP_WORKERS"),
        })
        env.pop("SECRET_KEY_FILE", None)
        with log_path.open("ab") as log:
            proc = subprocess.Popen(
                [sys.executable, "-m", "gunicorn", "-c", str(REPO_ROOT / "gunicorn.conf.py"),
                 "passenger_wsgi:application"],
                cwd=tree, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
            )
        _wait_ready(proc, port, log_path)
        instance = AppInstance(f"http://{host}:{port}", db_path, workdir, log_path)
        logger.info("e2e app ready at %s (db %s)", instance.base_url, db_path)
        yield instance, prepared
    finally:
        if proc is not None:
            _stop(proc)
        if os.environ.get("NAF_E2E_KEEP_WORKDIR") == "1":
            logger.warning("NAF_E2E_KEEP_WORKDIR=1: keeping %s", workdir)
        else:
            shutil.rmtree(workdir, ignore_errors=True)
