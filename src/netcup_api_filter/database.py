"""
Database initialization for the Account → Realms → Tokens architecture.

This module provides:
- Database initialization with new schema
- The bootstrap-admin guarantee at start-up (bootstrap/admin.py)
- The race-free persisted SECRET_KEY (ensure_persisted_secret_key)
- Migration helpers

The new schema replaces the old Client model with:
- Account: Human users
- AccountRealm: Domain access permissions
- APIToken: Machine credentials
- ActivityLog: Audit trail
- RegistrationRequest: Pending registrations
- Settings: Key-value configuration
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError

# Import all models to ensure they're registered with SQLAlchemy
from .models import (  # noqa: F401  (registration side effect)
    Account,
    AccountRealm,
    APIToken,
    db,
    Settings,
)

logger = logging.getLogger(__name__)


def seed_multi_backend_infrastructure():
    """Seed enum tables and backend providers for multi-backend support."""
    from .bootstrap.seeding import seed_enum_tables, seed_backend_providers
    
    # Seed enum tables (test_status, visibility, owner_type, grant_type)
    seed_enum_tables()
    
    # Seed built-in backend providers (netcup, powerdns, etc.)
    seed_backend_providers()


def get_db_path() -> str:
    """
    Get database file path.
    Priority: environment variable > current directory
    """
    db_path = os.environ.get('NETCUP_FILTER_DB_PATH')
    if db_path:
        logger.info(f"Using database path from environment: {db_path}")
        return db_path
    
    # Default to current directory
    db_path = os.path.join(os.getcwd(), 'netcup_filter.db')
    logger.info(f"Using default database path: {db_path}")
    return db_path


def init_db(app):
    """
    Initialize database with Flask app.
    
    Creates all tables and seeds default admin account.
    """
    db_path = get_db_path()
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    # In-memory SQLite uses StaticPool, which rejects pool_size/pool_recycle;
    # only apply connection-pool tuning to a real file-based database.
    if ':memory:' in db_path:
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {}
    else:
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_size': 10,
            'pool_recycle': 3600,
            'pool_pre_ping': True,
        }
    
    db.init_app(app)

    with app.app_context():
        # create_all() only creates missing *tables*; run_lightweight_migrations()
        # reconciles additive column/index changes so a deployment that keeps its
        # database across an upgrade doesn't crash with 'no such column'.
        db.create_all()
        run_lightweight_migrations()

        # The one initializer (bootstrap/instance.py): enums/providers, default
        # settings, and the administrator. An initialized database already has an
        # admin; a first boot (OCI image, fresh stack) creates it from operator
        # config, or the start fails with a clear message.
        from .bootstrap.admin import configured_admin_spec
        from .bootstrap.instance import init_instance

        admin_spec = None
        if Account.query.filter_by(is_admin=1).first() is None:
            admin_spec = configured_admin_spec(os.environ.get('NETCUP_FILTER_APP_ROOT'))
        init_instance(admin=admin_spec)


def _column_default_sql(column) -> str | None:
    """Render a scalar column default as a SQL literal, or None if not scalar.

    Callable defaults (e.g. datetime.utcnow) are intentionally skipped — they
    apply to new rows via the ORM; existing rows get NULL, which is acceptable
    for the additive nullable columns this project adds.
    """
    default = column.default
    if default is None or not getattr(default, 'is_scalar', False):
        return None
    value = default.arg
    if isinstance(value, bool):
        return '1' if value else '0'
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return None


def run_lightweight_migrations():
    """Add columns/indexes present in the models but missing from the database.

    The app manages its schema with ``db.create_all()`` (no Alembic), which
    creates missing tables but never alters existing ones. When a release adds
    a nullable column to an existing table, an upgraded deployment that keeps
    its SQLite file would otherwise raise ``OperationalError: no such column``
    on the first query and fail to start. This bridges that gap for additive,
    nullable/scalar-default column changes and for declared single-table
    indexes. Anything more involved (drops, type changes, new constraints,
    backfills) still requires a hand-written migration.
    """
    from sqlalchemy import inspect as sa_inspect, text

    engine = db.engine
    if engine.dialect.name != 'sqlite':
        # Only the SQLite deployments rely on create_all()-style management.
        return

    inspector = sa_inspect(engine)
    existing_tables = set(inspector.get_table_names())

    added = 0
    with engine.begin() as conn:
        for table in db.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # brand-new table already handled by create_all()

            existing_cols = {c['name'] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_cols:
                    continue
                if not column.nullable and _column_default_sql(column) is None:
                    # Can't safely backfill a NOT NULL column without a default;
                    # leave it to fail loudly rather than corrupt existing rows.
                    logger.error(
                        "Lightweight migration cannot add NOT NULL column "
                        f"{table.name}.{column.name} without a scalar default"
                    )
                    continue
                col_type = column.type.compile(dialect=engine.dialect)
                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'
                default_sql = _column_default_sql(column)
                if default_sql is not None:
                    ddl += f' DEFAULT {default_sql}'
                logger.warning(f"Lightweight migration: {ddl}")
                conn.execute(text(ddl))
                added += 1

            existing_indexes = {ix['name'] for ix in inspector.get_indexes(table.name)}
            for index in table.indexes:
                if index.name in existing_indexes:
                    continue
                cols = ', '.join(f'"{c.name}"' for c in index.columns)
                unique = 'UNIQUE ' if index.unique else ''
                conn.execute(text(
                    f'CREATE {unique}INDEX IF NOT EXISTS "{index.name}" '
                    f'ON "{table.name}" ({cols})'
                ))

    if added:
        logger.info(f"Lightweight migration added {added} missing column(s)")


SECRET_KEY_SETTING = 'secret_key'


def ensure_persisted_secret_key() -> str:
    """Return the database-persisted SECRET_KEY, creating it exactly once.

    Used when no SECRET_KEY environment variable is set. Race-free across gunicorn
    workers: every worker does INSERT OR IGNORE of its own random candidate and then
    reads the row back, so all of them end up with the single winning value. The
    value is stored JSON-encoded like every other settings row (scripts/activate.py
    carries the raw row across greenfield releases).
    """
    import json
    import secrets
    from sqlalchemy import select
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    if db.engine.dialect.name != 'sqlite':
        raise RuntimeError("ensure_persisted_secret_key supports the SQLite deployments only")

    table = Settings.__table__
    candidate = json.dumps(secrets.token_hex(32))
    with db.engine.begin() as conn:
        conn.execute(
            sqlite_insert(table)
            .values(key=SECRET_KEY_SETTING, value=candidate, updated_at=datetime.utcnow())
            .on_conflict_do_nothing(index_elements=['key'])
        )
        stored = conn.execute(
            select(table.c.value).where(table.c.key == SECRET_KEY_SETTING)
        ).scalar_one()
    try:
        value = json.loads(stored) if stored else None
    except json.JSONDecodeError as exc:
        raise RuntimeError("settings.secret_key is not valid JSON; refusing to start") from exc
    if not isinstance(value, str) or len(value) < 32:
        raise RuntimeError("settings.secret_key is empty or too short; refusing to start")
    return value


def get_setting(key: str) -> Any | None:
    """Get setting value by key."""
    setting = Settings.query.filter_by(key=key).first()
    if setting:
        return setting.get_value()
    return None


def set_setting(key: str, value: Any):
    """Set setting value by key."""
    setting = Settings.query.filter_by(key=key).first()
    if setting:
        setting.set_value(value)
        setting.updated_at = datetime.utcnow()
    else:
        setting = Settings(key=key)
        setting.set_value(value)
        db.session.add(setting)

    try:
        db.session.commit()
    except IntegrityError:
        # Defensive: if the key was inserted concurrently (or the session got into a bad
        # state), recover by rolling back and updating the existing row.
        db.session.rollback()
        existing = Settings.query.filter_by(key=key).first()
        if not existing:
            raise
        existing.set_value(value)
        existing.updated_at = datetime.utcnow()
        db.session.commit()


# Aliases for compatibility during migration
get_system_config = get_setting
set_system_config = set_setting
