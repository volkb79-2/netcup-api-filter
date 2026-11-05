"""scripts/activate.py must carry the SECRET_KEY across a greenfield release DB.

A freshly seeded release database has NO secret_key row (the app creates it on first start), so the
restore has to insert, not only update; otherwise the key silently rotates on every release.
"""
import importlib.util
import sqlite3
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "activate.py"


def _load():
    spec = importlib.util.spec_from_file_location("naf_activate", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_db(path, rows=()):
    with sqlite3.connect(path) as con:
        con.execute(
            'CREATE TABLE settings (id INTEGER NOT NULL, "key" VARCHAR(100) NOT NULL, value TEXT, '
            "updated_at DATETIME NOT NULL, PRIMARY KEY (id), UNIQUE (\"key\"))"
        )
        for key, value in rows:
            con.execute("INSERT INTO settings (key, value, updated_at) VALUES (?, ?, '2026-01-01 00:00:00.000000')", (key, value))


def _value(path):
    with sqlite3.connect(path) as con:
        row = con.execute("SELECT value FROM settings WHERE key='secret_key'").fetchone()
    return row[0] if row else None


def test_restore_inserts_when_fresh_db_has_no_secret_row(tmp_path):
    activate = _load()
    db = tmp_path / "fresh.db"
    _make_db(db)
    activate._restore_secret(db, "carried-over-value")
    assert _value(db) == "carried-over-value"


def test_restore_overwrites_an_existing_row(tmp_path):
    activate = _load()
    db = tmp_path / "existing.db"
    _make_db(db, [("secret_key", "new-release-value")])
    activate._restore_secret(db, "carried-over-value")
    assert _value(db) == "carried-over-value"


def test_restore_without_a_previous_secret_leaves_the_db_alone(tmp_path):
    activate = _load()
    db = tmp_path / "none.db"
    _make_db(db)
    activate._restore_secret(db, None)
    assert _value(db) is None


def test_preserved_secret_round_trip(tmp_path):
    activate = _load()
    old, new = tmp_path / "old.db", tmp_path / "new.db"
    _make_db(old, [("secret_key", "stable-key")])
    _make_db(new)
    activate._restore_secret(new, activate._preserved_secret(old))
    assert _value(new) == "stable-key"
