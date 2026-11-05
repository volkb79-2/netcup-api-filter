"""Serialize database initialization across processes (review finding #1).

Every gunicorn worker (``preload_app`` is off) and every Passenger process imports
``passenger_wsgi`` and runs ``create_app()`` -> ``init_db()``; the ciu hook additionally
runs ``python -m netcup_api_filter.bootstrap init`` next to them. Initialization is
check-then-insert (enum rows, the bootstrap admin), so on a FRESH database concurrent
initializers raced on unique constraints. An exclusive ``fcntl.flock`` on
``<db>.init.lock`` makes exactly one process initialize; the others wait, then find an
initialized database and do nothing.

Why a lock file and not "init once before forking": an entrypoint or a gunicorn
``on_starting`` hook covers only the container, while Passenger (webhosting) spawns its
processes itself and the ciu hook is a separate process. The lock covers all of them
with one mechanism, next to the database it protects.
"""
from __future__ import annotations

import errno
import fcntl
import logging
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager

logger = logging.getLogger(__name__)

TIMEOUT_KEY = "NAF_INIT_LOCK_TIMEOUT_SECONDS"
POLL_SECONDS = 0.1


class InitLockTimeout(RuntimeError):
    """Another process held the initialization lock for longer than the configured timeout."""


def lock_path_for(db_path: str) -> str:
    return f"{db_path}.init.lock"


def _timeout_seconds() -> float:
    from ..config_defaults import require_default

    raw = os.environ.get(TIMEOUT_KEY, "").strip() or require_default(TIMEOUT_KEY)
    value = float(raw)
    if value <= 0:
        raise ValueError(f"{TIMEOUT_KEY} must be > 0, got {raw!r}")
    return value


@contextmanager
def init_lock(db_path: str, *, timeout_seconds: float | None = None) -> Iterator[None]:
    """Hold the exclusive initialization lock of ``db_path`` (no-op for in-memory DBs)."""
    if not db_path or ":memory:" in db_path:
        yield
        return
    timeout = _timeout_seconds() if timeout_seconds is None else timeout_seconds
    path = lock_path_for(db_path)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        deadline = time.monotonic() + timeout
        waited = False
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
                    raise
                if time.monotonic() >= deadline:
                    raise InitLockTimeout(
                        f"database initialization lock {path} still held after {timeout:g}s "
                        f"(another process is initializing, or hung; {TIMEOUT_KEY})"
                    ) from exc
                if not waited:
                    logger.info(f"pid {os.getpid()} waiting for database initialization lock {path}")
                    waited = True
                time.sleep(POLL_SECONDS)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
