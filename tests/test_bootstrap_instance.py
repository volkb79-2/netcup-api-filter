"""bootstrap.init_instance — the one initializer — and its admin / SECRET_KEY rules (S2)."""
from __future__ import annotations

import json
import logging
import secrets

import pytest
from flask import Flask

from netcup_api_filter import database
from netcup_api_filter.app import create_app
from netcup_api_filter.bootstrap import (
    BootstrapAdmin,
    BootstrapAdminError,
    MockEmail,
    configured_admin_spec,
    init_instance,
    shipped_admin_spec,
)
from netcup_api_filter.bootstrap import __main__ as bootstrap_cli
from netcup_api_filter.config_defaults import require_default
from netcup_api_filter.database import ensure_persisted_secret_key, get_setting, get_system_config, set_system_config
from netcup_api_filter.models import Account, Settings

ENV_KEYS = (
    "NAF_BOOTSTRAP_ADMIN_USERNAME",
    "NAF_BOOTSTRAP_ADMIN_EMAIL",
    "NAF_BOOTSTRAP_ADMIN_PASSWORD",
    "NAF_BOOTSTRAP_ADMIN_PASSWORD_FILE",
)


def _password() -> str:
    return secrets.token_urlsafe(18) + "Aa1@"


@pytest.fixture
def no_bootstrap_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("NETCUP_FILTER_APP_ROOT", raising=False)


@pytest.fixture
def bare_app(tmp_path):
    """A minimal Flask app bound to a fresh file DB (what build seeding uses)."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_path / 'bare.db'}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    database.db.init_app(app)
    with app.app_context():
        yield app
        database.db.session.remove()
        database.db.drop_all()


def _spec(**overrides) -> BootstrapAdmin:
    values = dict(username="ops-admin", email="ops@example.com", password=_password(),
                  must_change_password=False, source="test")
    values.update(overrides)
    return BootstrapAdmin(**values)


# --- shipped admin (tarball / golden DB) -------------------------------------

def test_shipped_admin_is_seeded_with_forced_change_and_no_2fa(bare_app):
    report = init_instance(admin=shipped_admin_spec())
    admin = Account.query.filter_by(username=require_default("DEFAULT_ADMIN_USERNAME")).one()
    assert report.admin_action == "created"
    assert admin.is_admin == 1 and admin.must_change_password == 1
    assert admin.email_2fa_enabled == 0 and admin.totp_enabled == 0
    assert admin.verify_password(require_default("DEFAULT_ADMIN_PASSWORD"))
    assert Account.query.count() == 1, "a shipped DB contains exactly one account"
    assert get_setting("secret_key") is None, "the secret key is created at first start, not shipped"


def test_reseeding_never_resets_a_chosen_password(bare_app):
    init_instance(admin=shipped_admin_spec())
    admin = Account.query.one()
    chosen = _password()
    admin.set_password(chosen)
    database.db.session.commit()

    report = init_instance(admin=shipped_admin_spec())
    assert report.admin_action == "unchanged"
    assert Account.query.one().verify_password(chosen)


def test_enforce_reasserts_password_and_clears_lockout(bare_app):
    spec = _spec(must_change_password=False)
    init_instance(admin=spec)
    admin = Account.query.filter_by(username=spec.username).one()
    admin.set_password(_password())
    admin.is_active = 0
    admin.must_change_password = 1
    database.db.session.commit()
    set_system_config(f"failed_login_user_{spec.username}", {"count": 9, "lockout_until": "2999-01-01T00:00:00"})

    report = init_instance(admin=spec, enforce_admin=True)
    admin = Account.query.filter_by(username=spec.username).one()
    assert report.admin_action == "updated"
    assert admin.verify_password(spec.password)
    assert admin.is_active == 1 and admin.is_admin == 1 and admin.must_change_password == 0
    assert get_system_config(f"failed_login_user_{spec.username}") is None


def test_enforce_without_spec_is_an_error(bare_app):
    with pytest.raises(BootstrapAdminError, match="enforce_admin requires"):
        init_instance(admin=None, enforce_admin=True)


def test_initialized_db_without_any_admin_fails_fast(bare_app):
    with pytest.raises(BootstrapAdminError, match="No active administrator account exists"):
        init_instance(admin=None)


@pytest.mark.parametrize("field,value,match", [
    ("username", "", "username is empty"),
    ("email", "not-an-email", "email is missing or invalid"),
    ("password", "", "password is empty"),
])
def test_invalid_spec_is_rejected(bare_app, field, value, match):
    with pytest.raises(BootstrapAdminError, match=match):
        init_instance(admin=_spec(**{field: value}))


def test_spec_repr_never_contains_the_password():
    spec = _spec()
    assert spec.password not in repr(spec)


def test_mock_email_is_explicit_and_validated(bare_app):
    init_instance(admin=_spec(), mock_email=MockEmail("mailpit-host", 1025, "naf@example.com", "a@example.com"))
    config = get_setting("email_config")
    assert config["smtp_host"] == "mailpit-host" and config["smtp_port"] == 1025
    assert config["admin_email"] == "a@example.com"
    with pytest.raises(ValueError):
        MockEmail("", 1025, "naf@example.com", "a@example.com")
    with pytest.raises(ValueError):
        MockEmail("h", 0, "naf@example.com", "a@example.com")
    with pytest.raises(ValueError):
        MockEmail("h", 25, "nope", "a@example.com")


# --- configured admin (OCI image / ciu stack first boot) ---------------------

def test_env_spec_complete(no_bootstrap_env, monkeypatch):
    password = _password()
    monkeypatch.setenv("NAF_BOOTSTRAP_ADMIN_USERNAME", "ops-admin")
    monkeypatch.setenv("NAF_BOOTSTRAP_ADMIN_EMAIL", "ops@example.com")
    monkeypatch.setenv("NAF_BOOTSTRAP_ADMIN_PASSWORD", password)
    spec = configured_admin_spec(None)
    assert (spec.username, spec.email, spec.password, spec.must_change_password) == (
        "ops-admin", "ops@example.com", password, False)


def test_env_spec_password_file_wins_and_source_names_the_path(no_bootstrap_env, monkeypatch, tmp_path):
    password = _password()
    secret = tmp_path / "pw"
    secret.write_text(password + "\n")
    monkeypatch.setenv("NAF_BOOTSTRAP_ADMIN_USERNAME", "ops-admin")
    monkeypatch.setenv("NAF_BOOTSTRAP_ADMIN_EMAIL", "ops@example.com")
    monkeypatch.setenv("NAF_BOOTSTRAP_ADMIN_PASSWORD_FILE", str(secret))
    spec = configured_admin_spec(None)
    assert spec.password == password
    assert str(secret) in spec.source and password not in spec.source


def test_env_spec_errors(no_bootstrap_env, monkeypatch, tmp_path):
    monkeypatch.setenv("NAF_BOOTSTRAP_ADMIN_USERNAME", "ops-admin")
    with pytest.raises(BootstrapAdminError, match="incomplete"):
        configured_admin_spec(None)
    monkeypatch.setenv("NAF_BOOTSTRAP_ADMIN_EMAIL", "ops@example.com")
    monkeypatch.setenv("NAF_BOOTSTRAP_ADMIN_PASSWORD_FILE", str(tmp_path / "missing"))
    with pytest.raises(BootstrapAdminError, match="missing file"):
        configured_admin_spec(None)
    monkeypatch.setenv("NAF_BOOTSTRAP_ADMIN_PASSWORD", _password())
    with pytest.raises(BootstrapAdminError, match="only one of"):
        configured_admin_spec(None)


def test_no_configuration_means_no_spec(no_bootstrap_env, tmp_path):
    assert configured_admin_spec(None) is None
    assert configured_admin_spec(str(tmp_path)) is None  # app root without app-config.toml


def test_toml_admin_spec(no_bootstrap_env, tmp_path):
    password = _password()
    (tmp_path / "app-config.toml").write_text(
        "[[users]]\nusername = \"toml-admin\"\nemail = \"t@example.com\"\n"
        f"password = \"{password}\"\nis_admin = true\nmust_change_password = true\n"
    )
    spec = configured_admin_spec(str(tmp_path))
    assert (spec.username, spec.password, spec.must_change_password) == ("toml-admin", password, True)


def test_toml_admin_cannot_generate_its_password(no_bootstrap_env, tmp_path):
    (tmp_path / "app-config.toml").write_text(
        "[[users]]\nusername = \"toml-admin\"\nemail = \"t@example.com\"\n"
        "password = \"generate\"\nis_admin = true\n"
    )
    with pytest.raises(BootstrapAdminError, match="explicit password"):
        configured_admin_spec(str(tmp_path))


def test_toml_without_admin_users_is_no_spec(no_bootstrap_env, tmp_path):
    (tmp_path / "app-config.toml").write_text("[[users]]\nusername = \"u\"\nemail = \"u@example.com\"\n")
    assert configured_admin_spec(str(tmp_path)) is None


# --- app start (create_app → init_db) -----------------------------------------

def test_first_boot_without_bootstrap_config_refuses_to_start(no_bootstrap_env, monkeypatch, tmp_path):
    monkeypatch.setenv("NETCUP_FILTER_DB_PATH", str(tmp_path / "fresh.db"))
    monkeypatch.setenv("SECRET_KEY", secrets.token_hex(32))
    with pytest.raises(BootstrapAdminError, match="No active administrator account exists"):
        create_app()


def test_first_boot_creates_configured_admin_once(no_bootstrap_env, monkeypatch, tmp_path):
    password = _password()
    monkeypatch.setenv("NETCUP_FILTER_DB_PATH", str(tmp_path / "fresh.db"))
    monkeypatch.setenv("SECRET_KEY", secrets.token_hex(32))
    monkeypatch.setenv("NAF_BOOTSTRAP_ADMIN_USERNAME", "ops-admin")
    monkeypatch.setenv("NAF_BOOTSTRAP_ADMIN_EMAIL", "ops@example.com")
    monkeypatch.setenv("NAF_BOOTSTRAP_ADMIN_PASSWORD", password)
    app = create_app()
    with app.app_context():
        admin = Account.query.filter_by(is_admin=1).one()
        assert admin.username == "ops-admin" and admin.must_change_password == 0
        assert admin.verify_password(password)
        database.db.session.remove()

    # A second start with a DIFFERENT configured admin adds nobody: config is first-boot input only.
    monkeypatch.setenv("NAF_BOOTSTRAP_ADMIN_USERNAME", "someone-else")
    app = create_app()
    with app.app_context():
        assert [a.username for a in Account.query.filter_by(is_admin=1)] == ["ops-admin"]
        database.db.session.remove()


# --- SECRET_KEY ---------------------------------------------------------------

def test_persisted_secret_key_is_created_once_and_stable(bare_app):
    database.db.create_all()
    first = ensure_persisted_secret_key()
    second = ensure_persisted_secret_key()
    assert first == second and len(first) >= 32
    assert Settings.query.filter_by(key="secret_key").count() == 1


def test_existing_secret_key_row_wins(bare_app):
    database.db.create_all()
    carried = secrets.token_hex(32)
    row = Settings(key="secret_key")
    row.set_value(carried)
    database.db.session.add(row)
    database.db.session.commit()
    assert ensure_persisted_secret_key() == carried


def test_corrupt_secret_key_row_refuses(bare_app):
    database.db.create_all()
    database.db.session.add(Settings(key="secret_key", value="not json"))
    database.db.session.commit()
    with pytest.raises(RuntimeError, match="not valid JSON"):
        ensure_persisted_secret_key()


def test_create_app_without_secret_key_env_uses_the_db_key(monkeypatch, tmp_path):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("SECRET_KEY_FILE", raising=False)
    monkeypatch.setenv("NETCUP_FILTER_DB_PATH", str(tmp_path / "k.db"))
    app = create_app()
    with app.app_context():
        assert app.config["SECRET_KEY"] == get_setting("secret_key")
        database.db.session.remove()
    again = create_app()  # another worker / restart: the same key
    assert again.config["SECRET_KEY"] == app.config["SECRET_KEY"]


def test_secret_key_file(monkeypatch, tmp_path):
    key = secrets.token_hex(32)
    (tmp_path / "sk").write_text(key + "\n")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("SECRET_KEY_FILE", str(tmp_path / "sk"))
    monkeypatch.setenv("NETCUP_FILTER_DB_PATH", str(tmp_path / "f.db"))
    assert create_app().config["SECRET_KEY"] == key


@pytest.mark.parametrize("setup,match", [
    ({"SECRET_KEY": "short"}, "shorter than 16"),
    ({"SECRET_KEY": "x" * 32, "SECRET_KEY_FILE": "/nonexistent"}, "only one of"),
    ({"SECRET_KEY_FILE": "/nonexistent/secret"}, "not readable"),
])
def test_secret_key_misconfiguration_refuses(monkeypatch, tmp_path, setup, match):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("SECRET_KEY_FILE", raising=False)
    for key, value in setup.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("NETCUP_FILTER_DB_PATH", str(tmp_path / "m.db"))
    with pytest.raises(RuntimeError, match=match):
        create_app()


# --- CLI: python -m netcup_api_filter.bootstrap init ---------------------------

def _cli_env(monkeypatch, tmp_path, password):
    monkeypatch.setenv("NETCUP_FILTER_DB_PATH", str(tmp_path / "cli.db"))
    monkeypatch.setenv("NAF_BOOTSTRAP_ADMIN_USERNAME", "ops-admin")
    monkeypatch.setenv("NAF_BOOTSTRAP_ADMIN_EMAIL", "ops@example.com")
    pw_file = tmp_path / "pw"
    pw_file.write_text(password)
    monkeypatch.setenv("NAF_BOOTSTRAP_ADMIN_PASSWORD_FILE", str(pw_file))
    return pw_file


def _cli_db(tmp_path):
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_path / 'cli.db'}"
    database.db.init_app(app)
    return app


def test_cli_enforce_creates_then_updates_and_prints_no_password(no_bootstrap_env, monkeypatch, tmp_path, capsys):
    first = _password()
    pw_file = _cli_env(monkeypatch, tmp_path, first)
    assert bootstrap_cli.main(["init", "--enforce-admin"]) == 0
    out = capsys.readouterr()
    report = json.loads(out.out.strip().splitlines()[-1])
    assert report["admin_action"] == "created" and str(pw_file) in report["admin_source"]
    assert first not in out.out and first not in out.err

    second = _password()
    pw_file.write_text(second)  # the operator rotated the ciu secret
    assert bootstrap_cli.main(["init", "--enforce-admin",
                               "--mock-smtp-host", "mp", "--mock-smtp-port", "1025",
                               "--mock-from-email", "naf@example.com",
                               "--mock-admin-email", "a@example.com"]) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["admin_action"] == "updated"
    with _cli_db(tmp_path).app_context():
        assert Account.query.filter_by(username="ops-admin").one().verify_password(second)
        assert get_setting("email_config")["smtp_host"] == "mp"
        database.db.session.remove()


def test_cli_without_enforce_never_adds_a_second_admin(no_bootstrap_env, monkeypatch, tmp_path, capsys):
    _cli_env(monkeypatch, tmp_path, _password())
    assert bootstrap_cli.main(["init"]) == 0
    monkeypatch.setenv("NAF_BOOTSTRAP_ADMIN_USERNAME", "another-admin")
    assert bootstrap_cli.main(["init"]) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["admin_action"] == "existing"
    with _cli_db(tmp_path).app_context():
        assert Account.query.filter_by(is_admin=1).count() == 1
        database.db.session.remove()


def test_cli_configuration_errors_exit_2(no_bootstrap_env, monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("NETCUP_FILTER_DB_PATH", raising=False)
    assert bootstrap_cli.main(["init"]) == 2
    monkeypatch.setenv("NETCUP_FILTER_DB_PATH", str(tmp_path / "e.db"))
    assert bootstrap_cli.main(["init", "--enforce-admin"]) == 2  # nothing configured
    _cli_env(monkeypatch, tmp_path, _password())
    assert bootstrap_cli.main(["init", "--mock-smtp-host", "only-host"]) == 2
    assert "go together" in capsys.readouterr().err


# --- [[users]] import hygiene ---------------------------------------------------

def test_users_import_deletes_plaintext_and_never_logs_generated_password(bare_app, caplog):
    from netcup_api_filter.bootstrap.platform_backends import initialize_platform_backends
    from netcup_api_filter.database import set_setting

    init_instance(admin=_spec())
    explicit = _password()
    set_setting("users_config", [
        {"username": "explicit-user", "email": "e@example.com", "password": explicit,
         "is_approved": True, "must_change_password": False, "is_admin": False},
        {"username": "generated-user", "email": "g@example.com", "password": "generate",
         "is_approved": True, "must_change_password": False, "is_admin": False},
    ])
    with caplog.at_level(logging.DEBUG):
        initialize_platform_backends()

    assert Account.query.filter_by(username="explicit-user").one().verify_password(explicit)
    generated = Account.query.filter_by(username="generated-user").one()
    assert generated.must_change_password == 1
    assert Settings.query.filter_by(key="users_config").first() is None
    assert explicit not in caplog.text
    assert "SAVE THIS" not in caplog.text


# --- review #3: configured bootstrap admins obey the password policy -----------

@pytest.mark.parametrize("weak", ["a", "short-Pass1@", "b" * 19, "has-a-quote'-" + "Q1" * 10])
def test_configured_admin_with_a_weak_password_is_rejected(bare_app, weak):
    with pytest.raises(BootstrapAdminError, match="password policy") as excinfo:
        init_instance(admin=_spec(password=weak))
    if len(weak) > 3:
        assert weak not in str(excinfo.value)  # the reason names the rule, never the value
    assert Account.query.count() == 0


def test_weak_password_from_environment_fails_the_start(monkeypatch, tmp_path):
    from netcup_api_filter.bootstrap.admin import configured_admin_spec

    monkeypatch.setenv("NAF_BOOTSTRAP_ADMIN_USERNAME", "ops-admin")
    monkeypatch.setenv("NAF_BOOTSTRAP_ADMIN_EMAIL", "ops@example.com")
    monkeypatch.setenv("NAF_BOOTSTRAP_ADMIN_PASSWORD", "a")
    spec = configured_admin_spec(None)
    with pytest.raises(BootstrapAdminError, match="password policy"):
        spec.validate()


def test_shipped_tarball_admin_is_exempt_from_the_policy(bare_app):
    spec = shipped_admin_spec()
    assert spec.apply_password_policy is False
    spec.validate()  # the documented admin/admin; forced to change on first login


# --- review #6: never report success without an active admin -------------------

def test_username_taken_by_a_non_admin_is_an_error(bare_app, ):
    init_instance(admin=_spec(username="first-admin", email="first@example.com"))
    portal = Account(username="ops-admin", user_alias="u" * 16, email="portal@example.com",
                     is_admin=0, is_active=1, email_verified=1)
    portal.set_password(_password())
    database.db.session.add(portal)
    database.db.session.commit()
    with pytest.raises(BootstrapAdminError, match="taken by an existing non-admin account"):
        init_instance(admin=_spec())


def test_username_of_a_deactivated_admin_is_an_error(bare_app):
    init_instance(admin=_spec(username="first-admin", email="first@example.com"))
    init_instance(admin=_spec())
    Account.query.filter_by(username="ops-admin").one().is_active = 0
    database.db.session.commit()
    with pytest.raises(BootstrapAdminError, match="deactivated"):
        init_instance(admin=_spec())


def test_configured_email_collision_is_a_clear_error_not_integrity_error(bare_app):
    init_instance(admin=_spec(username="first-admin", email="ops@example.com"))
    with pytest.raises(BootstrapAdminError, match="already belongs to account 'first-admin'"):
        init_instance(admin=_spec(username="second-admin"))


def test_enforce_with_an_email_owned_by_another_account_is_an_error(bare_app):
    init_instance(admin=_spec(username="first-admin", email="first@example.com"))
    init_instance(admin=_spec())
    with pytest.raises(BootstrapAdminError, match="already belongs to account 'ops-admin'"):
        init_instance(admin=_spec(username="first-admin", email="ops@example.com"), enforce_admin=True)


def test_existing_database_with_only_deactivated_admins_fails(bare_app):
    init_instance(admin=_spec())
    Account.query.filter_by(username="ops-admin").one().is_active = 0
    database.db.session.commit()
    with pytest.raises(BootstrapAdminError, match="No active administrator"):
        init_instance(admin=None)
