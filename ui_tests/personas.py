"""Per-session e2e personas (S4 of the credentials/test-setup plan).

``provision(db_path)`` runs against the session's private copy of the golden DB BEFORE the
app starts and creates, with the product's own seeding helpers:

* ``admin``    — a dedicated administrator (never the shipped one), TOTP enabled with a
                 session-generated seed: logins are deterministic, no Mailpit polling;
* ``user``     — a portal account (email 2FA only, as required for regular accounts; tests that
                 exercise TOTP enable it themselves) with a full-CRUD ``subdomain`` realm on the
                 demo zone and one API token;
* ``mail_admin`` — a second administrator with EMAIL 2FA only, for the admin 2FA failure /
                 lockout tests (they may lock it; the main admin persona is never affected);
* ``readonly`` — a portal account with a read-only realm and token (write-denial tests);
* the public demo domain root (``dyn.example.com``) and a little activity history.

All passwords, TOTP seeds and tokens are random per session and exist only in memory (the
returned :class:`Personas`). Nothing is written to the repository or to a state file, and the
shipped admin is left exactly as shipped (``must_change_password``) for the one dedicated
forced-change test.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from pathlib import Path

import pyotp

ADMIN_USERNAME = "e2e-admin"
MAIL_ADMIN_USERNAME = "e2e-mail-admin"
USER_USERNAME = "e2e-user01"
READONLY_USERNAME = "e2e-readonly"


def new_password() -> str:
    """A random password that satisfies the product's password policy."""
    return secrets.token_urlsafe(24) + "Aa1@"


@dataclass(frozen=True)
class Persona:
    username: str
    password: str
    email: str
    totp_secret: str | None = None

    def totp_now(self) -> str:
        if not self.totp_secret:
            raise AssertionError(f"persona {self.username} has no TOTP")
        return pyotp.TOTP(self.totp_secret).now()

    def __repr__(self) -> str:  # never print secrets in test output
        return f"Persona({self.username!r})"


@dataclass(frozen=True)
class Personas:
    admin: Persona
    mail_admin: Persona
    user: Persona
    readonly: Persona
    user_token: str
    readonly_token: str
    client_domain: str

    def __repr__(self) -> str:
        return f"Personas(admin={self.admin.username}, user={self.user.username}, readonly={self.readonly.username})"


def _realm_shape(prefix: str) -> tuple[str, str, str, list[str], list[str]]:
    """Realm shape from .env.defaults (DEFAULT_TEST_CLIENT_* / DEFAULT_READONLY_TEST_CLIENT_*)."""
    from netcup_api_filter.config_defaults import require_default

    fqdn = require_default(f"{prefix}_REALM_VALUE")
    realm_type = require_default(f"{prefix}_REALM_TYPE")
    parts = fqdn.split(".")
    realm_value, domain = (".".join(parts[:-2]), ".".join(parts[-2:])) if len(parts) > 2 else ("", fqdn)
    record_types = [x.strip() for x in require_default(f"{prefix}_RECORD_TYPES").split(",")]
    operations = [x.strip() for x in require_default(f"{prefix}_OPERATIONS").split(",")]
    return domain, realm_type, realm_value, record_types, operations


def provision(db_path: Path) -> Personas:
    from flask import Flask

    from netcup_api_filter import database
    from netcup_api_filter.bootstrap import (
        DemoAccountSeedOptions,
        RealmSeedOptions,
        TokenSeedOptions,
        ensure_account,
        ensure_realm,
        ensure_token,
        seed_demo_audit_logs,
        seed_demo_domain_roots,
    )
    from netcup_api_filter.models import Account, generate_user_alias

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    database.db.init_app(app)

    admin = Persona(ADMIN_USERNAME, new_password(), f"{ADMIN_USERNAME}@example.com", pyotp.random_base32())
    mail_admin = Persona(MAIL_ADMIN_USERNAME, new_password(), f"{MAIL_ADMIN_USERNAME}@example.com")
    user = Persona(USER_USERNAME, new_password(), f"{USER_USERNAME}@example.com")
    readonly = Persona(READONLY_USERNAME, new_password(), f"{READONLY_USERNAME}@example.com")

    with app.app_context():
        admin_row = Account(
            username=admin.username, user_alias=generate_user_alias(), email=admin.email,
            email_verified=1, email_2fa_enabled=0, totp_enabled=1, totp_secret=admin.totp_secret,
            telegram_enabled=0, is_active=1, is_admin=1, must_change_password=0,
        )
        admin_row.set_password(admin.password)
        database.db.session.add(admin_row)
        mail_admin_row = Account(
            username=mail_admin.username, user_alias=generate_user_alias(), email=mail_admin.email,
            email_verified=1, email_2fa_enabled=1, totp_enabled=0,
            telegram_enabled=0, is_active=1, is_admin=1, must_change_password=0,
        )
        mail_admin_row.set_password(mail_admin.password)
        database.db.session.add(mail_admin_row)
        database.db.session.commit()

        seed_demo_domain_roots()

        tokens = {}
        for persona, prefix, token_name in (
            (user, "DEFAULT_TEST_CLIENT", "primary-token"),
            (readonly, "DEFAULT_READONLY_TEST_CLIENT", "readonly-token"),
        ):
            domain, realm_type, realm_value, record_types, operations = _realm_shape(prefix)
            account = ensure_account(
                DemoAccountSeedOptions(username=persona.username, password=persona.password, email=persona.email),
                approved_by=admin_row,
            )
            database.db.session.flush()
            realm = ensure_realm(
                account,
                RealmSeedOptions(domain=domain, realm_type=realm_type, realm_value=realm_value,
                                 record_types=record_types, operations=operations),
                approved_by=admin_row,
            )
            database.db.session.flush()
            _token, plain = ensure_token(realm, TokenSeedOptions(token_name=token_name))
            database.db.session.commit()
            if not plain:
                raise RuntimeError(f"persona token {token_name} already existed in a fresh session DB")
            tokens[persona.username] = (plain, domain)

        seed_demo_audit_logs(Account.query.filter_by(username=user.username).one())
        database.db.session.remove()

    user_token, client_domain = tokens[user.username]
    return Personas(admin, mail_admin, user, readonly, user_token, tokens[readonly.username][0], client_domain)


def provision_throwaway_admin(db_path: Path) -> Persona:
    """One extra admin WITHOUT 2FA, for a test that will change its own password.

    Used with ``e2e_env.app_instance(prepare=provision_throwaway_admin)``: the test owns the
    whole instance, so the change never reaches the session's personas.
    """
    from flask import Flask

    from netcup_api_filter import database
    from netcup_api_filter.models import Account, generate_user_alias

    persona = Persona("e2e-throwaway-admin", new_password(), "e2e-throwaway-admin@example.com")
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    database.db.init_app(app)
    with app.app_context():
        row = Account(
            username=persona.username, user_alias=generate_user_alias(), email=persona.email,
            email_verified=1, email_2fa_enabled=0, totp_enabled=0, telegram_enabled=0,
            is_active=1, is_admin=1, must_change_password=0,
        )
        row.set_password(persona.password)
        database.db.session.add(row)
        database.db.session.commit()
        database.db.session.remove()
    return persona
