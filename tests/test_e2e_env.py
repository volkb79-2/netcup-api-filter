"""Hermetic checks of the e2e session plumbing (ui_tests/e2e_env.py) that need no browser/app.

The golden-DB guard is what turns "something served or mutated deploy-local's DB" into ONE
clear session stop instead of hundreds of confusing login failures (S1 of the plan).
"""
from __future__ import annotations

import sqlite3

import pytest

from netcup_api_filter.config_defaults import require_default
from ui_tests import e2e_env
from ui_tests.e2e_env import E2EEnvironmentError, copy_golden_db, verify_pristine


def _golden(path, accounts, lockouts=()):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE accounts (username TEXT, is_admin INTEGER, must_change_password INTEGER)")
    conn.execute("CREATE TABLE settings (key TEXT, value TEXT)")
    conn.executemany("INSERT INTO accounts VALUES (?, ?, ?)", accounts)
    conn.executemany("INSERT INTO settings VALUES (?, ?)", lockouts)
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def shipped():
    return require_default("DEFAULT_ADMIN_USERNAME")


def test_pristine_golden_db_passes(tmp_path, shipped):
    verify_pristine(_golden(tmp_path / "g.db", [(shipped, 1, 1)]))


def test_cleared_lockout_value_is_still_pristine(tmp_path, shipped):
    verify_pristine(_golden(tmp_path / "g.db", [(shipped, 1, 1)], [(f"failed_login_user_{shipped}", "null")]))


@pytest.mark.parametrize("accounts,lockouts", [
    ([("SHIPPED", 1, 0)], ()),                                   # password already changed
    ([("SHIPPED", 1, 1), ("e2e-admin", 1, 0)], ()),              # personas leaked into the golden DB
    ([], ()),                                                    # no admin at all
    ([("SHIPPED", 1, 1)], [("failed_login_user_SHIPPED", '{"count": 5}')]),  # locked out
])
def test_mutated_golden_db_stops_the_session(tmp_path, shipped, accounts, lockouts):
    accounts = [(shipped if u == "SHIPPED" else u, a, m) for u, a, m in accounts]
    lockouts = [(k.replace("SHIPPED", shipped), v) for k, v in lockouts]
    with pytest.raises(E2EEnvironmentError, match="not pristine"):
        verify_pristine(_golden(tmp_path / "g.db", accounts, lockouts))


def test_copy_is_independent_of_the_golden_db(tmp_path, shipped, monkeypatch):
    golden = _golden(tmp_path / "g.db", [(shipped, 1, 1)])
    monkeypatch.setattr(e2e_env, "golden_db_path", lambda: golden)
    copy = tmp_path / "copy.db"
    copy_golden_db(copy)
    conn = sqlite3.connect(copy)
    conn.execute("UPDATE accounts SET must_change_password = 0")
    conn.commit()
    conn.close()
    verify_pristine(golden)  # the session's writes never reach the golden DB


def test_copy_refuses_a_mutated_golden_db(tmp_path, shipped, monkeypatch):
    golden = _golden(tmp_path / "g.db", [(shipped, 1, 0)])
    monkeypatch.setattr(e2e_env, "golden_db_path", lambda: golden)
    with pytest.raises(E2EEnvironmentError):
        copy_golden_db(tmp_path / "copy.db")


def test_deploy_dir_without_a_built_tree_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(e2e_env, "REPO_ROOT", tmp_path)
    monkeypatch.setenv("E2E_DEPLOY_DIR", "deploy-local")
    with pytest.raises(E2EEnvironmentError, match="local-build"):
        e2e_env.deploy_dir()


def test_advertise_host_is_required(monkeypatch):
    monkeypatch.delenv("NAF_E2E_ADVERTISE_HOST", raising=False)
    with pytest.raises(E2EEnvironmentError, match="NAF_E2E_ADVERTISE_HOST"):
        e2e_env.advertise_host()


# --- review #14 ---------------------------------------------------------------

def _accounts_db(path, username, password_hash="$2b$12$shipped"):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE accounts (username TEXT, is_admin INTEGER, must_change_password INTEGER, password_hash TEXT)")
    conn.execute("INSERT INTO accounts VALUES (?, 1, 1, ?)", (username, password_hash))
    conn.commit()
    conn.close()
    return path


def test_retire_shipped_admin_replaces_the_documented_password(tmp_path, shipped):
    import bcrypt

    db = _accounts_db(tmp_path / "s.db", shipped)
    e2e_env.retire_shipped_admin(db)
    (stored,) = sqlite3.connect(db).execute("SELECT password_hash FROM accounts").fetchone()
    assert stored != "$2b$12$shipped"
    assert not bcrypt.checkpw(require_default("DEFAULT_ADMIN_PASSWORD").encode(), stored.encode())


def test_retire_shipped_admin_requires_the_shipped_admin(tmp_path):
    db = _accounts_db(tmp_path / "s.db", "somebody-else")
    with pytest.raises(E2EEnvironmentError, match="shipped admin not found"):
        e2e_env.retire_shipped_admin(db)


class _FakeProc:
    pid = 0

    def poll(self):
        return 0


def test_a_port_taken_before_gunicorn_binds_is_retried(tmp_path, monkeypatch):
    tree = tmp_path / "deploy"
    tree.mkdir()
    attempts = []
    monkeypatch.setattr(e2e_env, "deploy_dir", lambda: tree)
    monkeypatch.setattr(e2e_env, "advertise_host", lambda: "runner")
    monkeypatch.setattr(e2e_env, "copy_golden_db", lambda dest: None)
    monkeypatch.setattr(e2e_env, "retire_shipped_admin", lambda db: None)
    monkeypatch.setattr(e2e_env.subprocess, "Popen", lambda *a, **k: _FakeProc())

    def wait_ready(proc, port, log_path):
        attempts.append(port)
        if len(attempts) == 1:
            raise e2e_env._PortTaken("taken")

    monkeypatch.setattr(e2e_env, "_wait_ready", wait_ready)
    with e2e_env.app_instance() as (instance, prepared):
        assert instance.base_url == f"http://runner:{attempts[-1]}"
        assert prepared is None
    assert len(attempts) == 2


def test_port_retries_are_bounded(tmp_path, monkeypatch):
    tree = tmp_path / "deploy"
    tree.mkdir()
    monkeypatch.setattr(e2e_env, "deploy_dir", lambda: tree)
    monkeypatch.setattr(e2e_env, "advertise_host", lambda: "runner")
    monkeypatch.setattr(e2e_env, "copy_golden_db", lambda dest: None)
    monkeypatch.setattr(e2e_env, "retire_shipped_admin", lambda db: None)
    monkeypatch.setattr(e2e_env.subprocess, "Popen", lambda *a, **k: _FakeProc())

    def always_taken(proc, port, log_path):
        raise e2e_env._PortTaken("taken")

    monkeypatch.setattr(e2e_env, "_wait_ready", always_taken)
    with pytest.raises(E2EEnvironmentError, match="no free port"):
        with e2e_env.app_instance():
            pass  # pragma: no cover


def test_keep_shipped_admin_skips_the_retirement(tmp_path, monkeypatch):
    tree = tmp_path / "deploy"
    tree.mkdir()
    retired = []
    monkeypatch.setattr(e2e_env, "deploy_dir", lambda: tree)
    monkeypatch.setattr(e2e_env, "advertise_host", lambda: "runner")
    monkeypatch.setattr(e2e_env, "copy_golden_db", lambda dest: None)
    monkeypatch.setattr(e2e_env, "retire_shipped_admin", retired.append)
    monkeypatch.setattr(e2e_env.subprocess, "Popen", lambda *a, **k: _FakeProc())
    monkeypatch.setattr(e2e_env, "_wait_ready", lambda *a: None)
    with e2e_env.app_instance(keep_shipped_admin=True):
        pass
    assert retired == []
    with e2e_env.app_instance():
        pass
    assert len(retired) == 1
