"""Review findings #1/#2: first-boot initialization is serialized, and a failed start is fatal.

* Several processes (gunicorn workers, Passenger processes, the ciu hook CLI) initialize
  the SAME fresh database at once; exactly one may create the admin and none may fail.
* A start-up failure (e.g. no bootstrap admin configured) must make the import of
  passenger_wsgi fail -> the process exits non-zero; it must never install a stand-in
  WSGI app that renders the error text to clients.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from netcup_api_filter.bootstrap.init_lock import InitLockTimeout, init_lock, lock_path_for

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
PACKAGE = SRC / "netcup_api_filter"

# Each child waits for a common start time so the initializations really overlap.
_CHILD = r"""
import os, sys, time
start = float(sys.argv[1])
while time.time() < start:
    time.sleep(0.001)
from netcup_api_filter.app import create_app
create_app()
print("ok")
"""


def _clean_env(tmp_path, db_path, **extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("NAF_BOOTSTRAP_ADMIN_")}
    env.pop("SECRET_KEY_FILE", None)
    env.pop("NETCUP_FILTER_APP_ROOT", None)
    env.update(
        PYTHONPATH=str(SRC),
        NETCUP_FILTER_DB_PATH=str(db_path),
        NETCUP_FILTER_LOG_FILE=str(tmp_path / "app.log"),
        SECRET_KEY="k" * 32,
        FLASK_ENV="testing",
    )
    env.update(extra)
    return env


def _bootstrap(env, password="Init-Concurrency-" + "x" * 12 + "1@"):
    env.update(
        NAF_BOOTSTRAP_ADMIN_USERNAME="concurrent-admin",
        NAF_BOOTSTRAP_ADMIN_EMAIL="concurrent-admin@example.com",
        NAF_BOOTSTRAP_ADMIN_PASSWORD=password,
    )
    return env


def test_lock_excludes_a_second_holder_and_times_out(tmp_path):
    db = str(tmp_path / "x.db")
    with init_lock(db, timeout_seconds=5):
        assert Path(lock_path_for(db)).exists()
        started = time.monotonic()
        with pytest.raises(InitLockTimeout, match="still held"):
            with init_lock(db, timeout_seconds=0.3):
                pass  # pragma: no cover - must not be reached
        assert time.monotonic() - started >= 0.3
    with init_lock(db, timeout_seconds=0.3):  # released again
        pass


def test_memory_database_needs_no_lock(tmp_path):
    with init_lock(":memory:", timeout_seconds=0.01):
        with init_lock(":memory:", timeout_seconds=0.01):
            pass


def test_concurrent_first_boot_creates_exactly_one_admin(tmp_path):
    db = tmp_path / "fresh.db"
    env = _bootstrap(_clean_env(tmp_path, db))
    start = time.time() + 2.0
    procs = [
        subprocess.Popen([sys.executable, "-c", _CHILD, str(start)], env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(4)
    ]
    results = [p.communicate(timeout=120) + (p.returncode,) for p in procs]
    for out, err, code in results:
        assert code == 0, err[-2000:]
        assert out.strip().endswith("ok")
    conn = sqlite3.connect(db)
    try:
        admins = conn.execute("SELECT username FROM accounts WHERE is_admin = 1").fetchall()
    finally:
        conn.close()
    assert admins == [("concurrent-admin",)]


def _import_passenger(tmp_path, env):
    code = f"import runpy; runpy.run_path({str(PACKAGE / 'passenger_wsgi.py')!r}, run_name='passenger_wsgi')"
    return subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=120)


def test_start_without_bootstrap_admin_fails_the_process(tmp_path):
    result = _import_passenger(tmp_path, _clean_env(tmp_path, tmp_path / "none.db"))
    assert result.returncode != 0
    assert "BootstrapAdminError" in result.stderr
    assert "failed to start" in (tmp_path / "app.log").read_text()


def test_start_with_bootstrap_admin_succeeds(tmp_path):
    result = _import_passenger(tmp_path, _bootstrap(_clean_env(tmp_path, tmp_path / "ok.db")))
    assert result.returncode == 0, result.stderr[-2000:]


def test_no_stand_in_error_application_exists():
    source = (PACKAGE / "passenger_wsgi.py").read_text()
    assert "Application Failed to Start" not in source
