"""scripts/activate.py must carry the SECRET_KEY across a greenfield release DB.

A freshly seeded release database has NO secret_key row (the app creates it on first start), so the
restore has to insert, not only update; otherwise the key silently rotates on every release.
"""
import importlib.util
import sqlite3
import tarfile
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


def test_restore_failure_with_a_nonempty_secret_fails_loudly(tmp_path):
    import pytest

    activate = _load()
    db = tmp_path / "no_settings_table.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE unrelated (x INTEGER)")
    with pytest.raises(RuntimeError, match="could not restore existing SECRET_KEY"):
        activate._restore_secret(db, "carried-over-value")


def test_restore_with_an_empty_secret_is_a_noop_even_if_db_is_broken(tmp_path):
    activate = _load()
    activate._restore_secret(tmp_path / "missing_dir" / "x.db", "")


def test_archive_lookup_uses_the_canonical_versioned_variant_name(tmp_path):
    """Reverting activation to naf-<variant>.tar.xz misses the CMRU publisher's asset."""
    activate = _load()
    dist = tmp_path / "dist"
    dist.mkdir()
    artifact = dist / "naf-v1.2.3-py311.tar.xz"
    artifact.write_bytes(b"fixture")
    assert activate._archive(tmp_path, "py311") == artifact


def test_extract_strips_cmru_top_level_bundle_directory(tmp_path):
    """Reverting flat extraction leaves Passenger's entrypoint one directory too deep."""
    import io

    activate = _load()
    archive_path = tmp_path / "bundle.tar.xz"
    payload = b"passenger entrypoint"
    with tarfile.open(archive_path, "w:xz") as archive:
        member = tarfile.TarInfo("app/passenger_wsgi.py")
        member.size = len(payload)
        member.mode = 0o644
        archive.addfile(member, io.BytesIO(payload))
    root = tmp_path / "deployment"
    root.mkdir()
    with tarfile.open(archive_path, "r:xz") as archive:
        activate._extract(archive, root)
    assert (root / "passenger_wsgi.py").read_bytes() == payload
    assert not (root / "app/passenger_wsgi.py").exists()


def test_extract_rejects_traversal_inside_the_bundle_directory(tmp_path):
    """Reverting the rewritten-member traversal check could escape the deployment root."""
    import io

    activate = _load()
    archive_path = tmp_path / "unsafe.tar.xz"
    with tarfile.open(archive_path, "w:xz") as archive:
        member = tarfile.TarInfo("app/../../outside.txt")
        member.size = 1
        archive.addfile(member, io.BytesIO(b"x"))
    with tarfile.open(archive_path, "r:xz") as archive:
        try:
            activate._extract(archive, tmp_path / "deployment")
        except RuntimeError as exc:
            assert "unsafe tar member" in str(exc)
        else:
            raise AssertionError("bundle traversal was extracted")
