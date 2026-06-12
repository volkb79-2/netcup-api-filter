"""Unit tests for run_lightweight_migrations().

Each test creates a full schema via db.create_all(), degrades it with raw SQL,
runs run_lightweight_migrations(), and asserts the expected outcome.

These tests use a file-based SQLite DB (via tmp_path) because an in-memory DB
cannot simulate an "old schema on disk" that persists across an ALTER TABLE
operation the way a file-based DB can.

Connection-pool note
--------------------
SQLite connections cache the schema version per-connection.  When one
connection DROPs a column, any other connection that previously read the schema
still sees the old version and will report a "duplicate column name" error if it
tries to ADD the same column.  The fix is to call ``engine.dispose()`` after
each raw DDL statement so the pool discards all stale connections before
run_lightweight_migrations() opens a fresh one.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from sqlalchemy import inspect as sa_inspect, text

from netcup_api_filter.app import create_app
from netcup_api_filter.database import db as _db, run_lightweight_migrations


@pytest.fixture()
def migration_app(tmp_path):
    """App fixture backed by a file-based SQLite DB (required for ALTER tests).

    Deliberately does NOT call _db.create_all() again after create_app() because
    create_app() → init_db() already does so.  A second call would leave an extra
    pool connection with a fresh schema view and interfere with DROP/ADD tests.
    """
    db_path = str(tmp_path / "migration_test.db")
    os.environ["SECRET_KEY"] = "test_secret_migration"
    os.environ["NETCUP_FILTER_DB_PATH"] = db_path
    os.environ.pop("NETCUP_FILTER_APP_ROOT", None)
    os.environ.pop("SEED_DEMO_ACCOUNTS", None)

    application = create_app()
    application.config["TESTING"] = True
    with application.app_context():
        yield application
        _db.session.remove()
        _db.drop_all()

    # Clean up env vars set above so they don't bleed into other tests.
    os.environ.pop("NETCUP_FILTER_DB_PATH", None)
    os.environ.pop("SECRET_KEY", None)


# ---------------------------------------------------------------------------
# Case 1 — Restores a dropped nullable/scalar-default column
#
# Column under test: accounts.notify_via_telegram
#   Defined as: db.Column(db.Integer, default=0)  — nullable (SQLAlchemy
#   default is nullable=True), scalar default 0.
#   This is a real notification-preference column that would be added in an
#   upgrade to an existing deployment keeping its SQLite DB.
# ---------------------------------------------------------------------------

def test_restores_dropped_nullable_column(migration_app):
    """Migration re-adds accounts.notify_via_telegram after it has been dropped."""
    engine = _db.engine

    # Verify the column exists after create_all()
    inspector = sa_inspect(engine)
    cols_before = {c["name"] for c in inspector.get_columns("accounts")}
    assert "notify_via_telegram" in cols_before, (
        "Pre-condition: notify_via_telegram should exist after create_all()"
    )

    # Degrade schema: drop the column (requires SQLite ≥ 3.35, Python ≥ 3.11)
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE "accounts" DROP COLUMN "notify_via_telegram"'))

    # Flush stale pooled connections so the next query sees the post-DROP schema.
    engine.dispose()

    # Confirm it is gone
    inspector = sa_inspect(engine)
    cols_after_drop = {c["name"] for c in inspector.get_columns("accounts")}
    assert "notify_via_telegram" not in cols_after_drop

    # Run migration
    run_lightweight_migrations()

    # Assert: column is back and selectable
    inspector = sa_inspect(engine)
    cols_restored = {c["name"] for c in inspector.get_columns("accounts")}
    assert "notify_via_telegram" in cols_restored

    # Also verify the column is actually queryable
    with engine.connect() as conn:
        result = conn.execute(text('SELECT "notify_via_telegram" FROM "accounts" LIMIT 1'))
        _ = result.fetchall()  # Must not raise


# ---------------------------------------------------------------------------
# Case 2 — Creates a missing index
#
# Index under test: ix_accounts_telegram_link_token_hash
#   Declared with index=True on accounts.telegram_link_token_hash.
#   Non-unique, single-column, on a table with real upgrade history.
#   The bot callback looks accounts up by this hash on every incoming update,
#   so the index is load-bearing in production.
# ---------------------------------------------------------------------------

def test_creates_missing_index(migration_app):
    """Migration recreates ix_accounts_telegram_link_token_hash after it is dropped."""
    engine = _db.engine

    # Confirm index exists after create_all()
    inspector = sa_inspect(engine)
    index_names_before = {ix["name"] for ix in inspector.get_indexes("accounts")}
    assert "ix_accounts_telegram_link_token_hash" in index_names_before

    # Degrade schema: drop the index
    with engine.begin() as conn:
        conn.execute(text('DROP INDEX IF EXISTS "ix_accounts_telegram_link_token_hash"'))

    # Flush stale pooled connections
    engine.dispose()

    # Confirm it is gone
    inspector = sa_inspect(engine)
    index_names_after_drop = {ix["name"] for ix in inspector.get_indexes("accounts")}
    assert "ix_accounts_telegram_link_token_hash" not in index_names_after_drop

    # Run migration
    run_lightweight_migrations()

    # Assert: index is recreated
    inspector = sa_inspect(engine)
    index_names_restored = {ix["name"] for ix in inspector.get_indexes("accounts")}
    assert "ix_accounts_telegram_link_token_hash" in index_names_restored


# ---------------------------------------------------------------------------
# Case 3 — Idempotent: running twice makes zero further changes
# ---------------------------------------------------------------------------

def test_idempotent_on_fresh_schema(migration_app):
    """Running run_lightweight_migrations() twice leaves schema identical."""
    engine = _db.engine

    def schema_snapshot():
        """Return a dict of {table: (sorted_columns, sorted_indexes)} for comparison."""
        inspector = sa_inspect(engine)
        snapshot = {}
        for table_name in inspector.get_table_names():
            cols = tuple(sorted(c["name"] for c in inspector.get_columns(table_name)))
            idxs = tuple(sorted(
                ix["name"] for ix in inspector.get_indexes(table_name) if ix["name"]
            ))
            snapshot[table_name] = (cols, idxs)
        return snapshot

    # First run (schema is already in sync — should be a no-op)
    run_lightweight_migrations()
    state_after_first = schema_snapshot()

    # Second run
    run_lightweight_migrations()
    state_after_second = schema_snapshot()

    assert state_after_first == state_after_second


# ---------------------------------------------------------------------------
# Case 4 — Refuses NOT NULL without scalar default
#
# The current models have no column that is simultaneously:
#   (a) NOT NULL, (b) missing a scalar default, and (c) droppable via SQLite
#   ALTER TABLE DROP COLUMN without violating other constraints.
#
# We therefore test the guard directly: temporarily inject a fake Column object
# into the `accounts` table's metadata that is NOT NULL and has no default.
# run_lightweight_migrations() should skip it (log an error, not raise) and must
# NOT add it to the real DB.  This matches the spec's "simulate by asserting on
# the function's internal predicate" approach.
# ---------------------------------------------------------------------------

def test_refuses_not_null_without_scalar_default(migration_app, caplog):
    """Migration skips a NOT NULL column that lacks a scalar default."""
    import logging
    from sqlalchemy import Column, Integer

    engine = _db.engine

    # Build a Column that is NOT NULL and has no default — the migration must skip it.
    fake_col = Column("fake_not_null_col", Integer, nullable=False)

    # Inject into the accounts table metadata so run_lightweight_migrations() sees it.
    accounts_table = _db.metadata.tables["accounts"]
    accounts_table.append_column(fake_col)

    try:
        with caplog.at_level(logging.ERROR, logger="netcup_api_filter.database"):
            run_lightweight_migrations()

        # The column must NOT have been added to the real DB
        inspector = sa_inspect(engine)
        real_cols = {c["name"] for c in inspector.get_columns("accounts")}
        assert "fake_not_null_col" not in real_cols

        # The migration must have logged an error mentioning the column and NOT NULL
        error_messages = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
        assert any(
            "fake_not_null_col" in m and "NOT NULL" in m
            for m in error_messages
        ), f"Expected error log about NOT NULL column; got: {error_messages}"

    finally:
        # Remove the fake column so it does not pollute subsequent tests.
        accounts_table._columns.remove(fake_col)


# ---------------------------------------------------------------------------
# Case 5 — Fresh DB is a no-op
#
# On a brand-new create_all() schema there are no missing columns or indexes.
# The migration should make no schema changes.
# ---------------------------------------------------------------------------

def test_fresh_db_is_noop(migration_app, caplog):
    """run_lightweight_migrations() does nothing on a freshly created schema."""
    import logging

    engine = _db.engine

    def col_snapshot():
        inspector = sa_inspect(engine)
        return {
            t: frozenset(c["name"] for c in inspector.get_columns(t))
            for t in inspector.get_table_names()
        }

    before = col_snapshot()

    with caplog.at_level(logging.WARNING, logger="netcup_api_filter.database"):
        run_lightweight_migrations()

    after = col_snapshot()
    assert before == after

    # No "Lightweight migration:" lines should have been emitted (those are DDL lines)
    migration_ddl_lines = [
        r for r in caplog.records
        if r.levelno >= logging.WARNING and "Lightweight migration:" in r.getMessage()
    ]
    assert migration_ddl_lines == []


# ---------------------------------------------------------------------------
# Case 6 — Non-sqlite early return
#
# The implementation has a guard at database.py line ~211:
#   if engine.dialect.name != 'sqlite':
#       return
# We monkeypatch the dialect name to 'postgresql' and confirm no DDL is run.
# ---------------------------------------------------------------------------

def test_non_sqlite_early_return(migration_app, monkeypatch):
    """run_lightweight_migrations() returns immediately for non-SQLite engines."""
    engine = _db.engine

    # Degrade the schema first: drop a column so that, if the guard were absent,
    # the migration would try to add it back.
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE "accounts" DROP COLUMN "notify_via_telegram"'))

    # Flush stale pool connections before monkeypatching
    engine.dispose()

    inspector = sa_inspect(engine)
    cols_before_run = {c["name"] for c in inspector.get_columns("accounts")}
    assert "notify_via_telegram" not in cols_before_run

    # Monkeypatch the dialect name to a non-sqlite value
    monkeypatch.setattr(engine.dialect, "name", "postgresql")

    # Run migration — should exit early without touching the DB
    run_lightweight_migrations()

    # Restore the real dialect so the inspector works correctly afterwards
    monkeypatch.undo()

    inspector = sa_inspect(engine)
    cols_after = {c["name"] for c in inspector.get_columns("accounts")}
    # Column must still be absent — migration did nothing
    assert "notify_via_telegram" not in cols_after
