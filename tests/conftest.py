import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from datetime import datetime

# Hypothesis profiles — guarded so a missing install never breaks non-PBT test collection.
# Select via HYPOTHESIS_PROFILE env var (default: "ci").
# ci  — 50 examples, fast; used in the CI unit-tests job.
# dev — 500 examples; run locally with: HYPOTHESIS_PROFILE=dev pytest tests/
try:
    from hypothesis import settings, HealthCheck
    settings.register_profile("ci", max_examples=50, deadline=None,
                              suppress_health_check=[HealthCheck.too_slow])
    settings.register_profile("dev", max_examples=500, deadline=None)
    settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci"))
except ImportError:
    pass

from netcup_api_filter.app import create_app
from netcup_api_filter.database import db as _db
from netcup_api_filter.models import (
    Account, AccountRealm, APIToken,
    generate_token, generate_user_alias, hash_token,
    TOKEN_PREFIX, USER_ALIAS_LENGTH,
)


@pytest.fixture
def app(monkeypatch, tmp_path):
    # init_db() always seeds one admin (DEFAULT_ADMIN_USERNAME, default "admin").
    # SEED_DEMO_ACCOUNTS is neutralised so no extra accounts appear.
    # NETCUP_FILTER_APP_ROOT is cleared so app-config.toml is not loaded.
    # Factory tests must use usernames/emails that don't collide with "admin".
    monkeypatch.setenv("SECRET_KEY", "test_secret_key_for_testing_only")
    monkeypatch.setenv("NETCUP_FILTER_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("NETCUP_FILTER_APP_ROOT", raising=False)
    monkeypatch.delenv("SEED_DEMO_ACCOUNTS", raising=False)
    application = create_app()
    application.config["TESTING"] = True
    with application.app_context():
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def make_account(db):
    def _make(username="testuser", *, is_active=1, is_admin=0, email=None, password=None, **kw):
        if "password_hash" not in kw:
            kw["password_hash"] = "dummy_hash"
        account = Account(
            username=username,
            user_alias=generate_user_alias(),
            email=email or f"{username}@example.com",
            email_verified=1,
            approved_at=datetime.utcnow(),
            is_active=is_active,
            is_admin=is_admin,
            **kw,
        )
        if password is not None:
            account.set_password(password)
        _db.session.add(account)
        _db.session.commit()
        return account
    return _make


@pytest.fixture
def make_realm(db):
    def _make(account, *, domain="example.com", realm_type="host", realm_value="vpn",
              status="approved", record_types=("A", "AAAA"), operations=("read", "update"), **kw):
        realm = AccountRealm(
            account_id=account.id,
            domain=domain,
            realm_type=realm_type,
            realm_value=realm_value,
            status=status,
            **kw,
        )
        realm.set_allowed_record_types(list(record_types))
        realm.set_allowed_operations(list(operations))
        _db.session.add(realm)
        _db.session.commit()
        return realm
    return _make


@pytest.fixture
def make_token(db):
    def _make(realm, *, name="test-token", operations=None, record_types=None,
              ip_ranges=None, is_active=1, expires_at=None):
        plain = generate_token(realm.account.user_alias)
        # Slice mirrors database.seed_demo_accounts: skip "naf_" + alias + "_"
        random_part_start = len(TOKEN_PREFIX) + USER_ALIAS_LENGTH + 1
        prefix = plain[random_part_start:random_part_start + 8]
        token = APIToken(
            realm_id=realm.id,
            token_name=name,
            token_prefix=prefix,
            token_hash=hash_token(plain),
            is_active=is_active,
            expires_at=expires_at,
        )
        if record_types is not None:
            token.set_allowed_record_types(list(record_types))
        if operations is not None:
            token.set_allowed_operations(list(operations))
        if ip_ranges is not None:
            token.set_allowed_ip_ranges(list(ip_ranges))
        _db.session.add(token)
        _db.session.commit()
        return token, plain
    return _make
