"""The one bootstrap-admin seeder and the sources of its inputs.

There is exactly one function that creates (or, explicitly, re-asserts) an
administrator: :func:`seed_bootstrap_admin`. It is only ever called through
:func:`netcup_api_filter.bootstrap.instance.init_instance`. Where the inputs come
from is decided by the caller:

* :func:`shipped_admin_spec` — build time only (the Passenger tarball and the local
  golden database). The documented, non-secret ``DEFAULT_ADMIN_*`` defaults from
  ``.env.defaults``, always with ``must_change_password``.
* :func:`configured_admin_spec` — operator configuration for a container / long-lived
  stack: ``NAF_BOOTSTRAP_ADMIN_*`` environment variables (the password preferably as a
  mounted secret file, ``NAF_BOOTSTRAP_ADMIN_PASSWORD_FILE``), or an ``[[users]]``
  entry with ``is_admin = true`` in ``app-config.toml``. No default exists: an image
  never ships a published password.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..config_defaults import require_default
from ..models import Account, db, generate_user_alias

logger = logging.getLogger(__name__)

ENV_USERNAME = "NAF_BOOTSTRAP_ADMIN_USERNAME"
ENV_EMAIL = "NAF_BOOTSTRAP_ADMIN_EMAIL"
ENV_PASSWORD = "NAF_BOOTSTRAP_ADMIN_PASSWORD"
ENV_PASSWORD_FILE = "NAF_BOOTSTRAP_ADMIN_PASSWORD_FILE"

CONFIG_HINT = (
    f"Set {ENV_USERNAME}, {ENV_EMAIL} and {ENV_PASSWORD_FILE} (preferred: a mounted secret "
    f"file) or {ENV_PASSWORD}, or add an [[users]] entry with is_admin = true and an "
    "explicit password to app-config.toml in the app root. See docs/CONFIGURATION_GUIDE.md."
)


class BootstrapAdminError(RuntimeError):
    """The bootstrap-admin configuration is missing or invalid."""


@dataclass(frozen=True)
class BootstrapAdmin:
    """Inputs for :func:`seed_bootstrap_admin`. The password is never logged."""

    username: str
    email: str
    password: str
    must_change_password: bool
    source: str
    """Where the inputs came from, e.g. 'environment (password file /run/secrets/x)'.
    Safe to log: it names a location, never a value."""

    def __repr__(self) -> str:  # never leak the password through logs/tracebacks
        return (
            f"BootstrapAdmin(username={self.username!r}, email={self.email!r}, "
            f"must_change_password={self.must_change_password}, source={self.source!r})"
        )

    def validate(self) -> None:
        # Admin usernames are not bound by the portal's self-registration rules
        # (validate_username): the shipped default is the short, documented `admin`.
        if not self.username:
            raise BootstrapAdminError(f"bootstrap admin username is empty (source: {self.source})")
        if not self.email or "@" not in self.email:
            raise BootstrapAdminError(f"bootstrap admin email is missing or invalid (source: {self.source})")
        if not self.password:
            raise BootstrapAdminError(f"bootstrap admin password is empty (source: {self.source})")


def seed_bootstrap_admin(spec: BootstrapAdmin, *, enforce: bool = False) -> tuple[Account, str]:
    """Create the administrator *spec* describes; return ``(account, action)``.

    ``action`` is ``"created"``, ``"unchanged"`` or ``"updated"``.

    * Default (``enforce=False``): create-if-missing. An existing account with that
      username is left untouched — re-seeding never resets a password someone chose.
    * ``enforce=True`` (the ciu post_compose hook of a stack that owns the secret):
      create-or-update. The account is made an active admin with the configured
      password, email and ``must_change_password``, and its failed-login lockout is
      cleared — the configured secret is the source of truth for that instance.

    A new admin has no 2FA method enabled: email 2FA is switched on when an email is
    confirmed through the forced password change, or by the admin once SMTP works.
    """
    spec.validate()
    account = Account.query.filter_by(username=spec.username).first()

    if account is None:
        account = Account(
            username=spec.username,
            user_alias=generate_user_alias(),
            email=spec.email,
            email_verified=0,
            email_2fa_enabled=0,
            totp_enabled=0,
            telegram_enabled=0,
            is_active=1,
            is_admin=1,
            must_change_password=1 if spec.must_change_password else 0,
            approved_at=datetime.utcnow(),
        )
        account.set_password(spec.password)
        db.session.add(account)
        db.session.commit()
        logger.info(
            "Bootstrap admin %s created from %s (must_change_password=%s)",
            spec.username, spec.source, spec.must_change_password,
        )
        return account, "created"

    if not enforce:
        logger.info("Bootstrap admin %s already exists; left unchanged", spec.username)
        return account, "unchanged"

    account.set_password(spec.password)
    account.email = spec.email
    account.is_admin = 1
    account.is_active = 1
    account.must_change_password = 1 if spec.must_change_password else 0
    db.session.commit()
    from ..database import set_system_config
    set_system_config(f"failed_login_user_{spec.username}", None)
    logger.info("Bootstrap admin %s re-asserted from %s", spec.username, spec.source)
    return account, "updated"


def shipped_admin_spec() -> BootstrapAdmin:
    """The pre-set admin of the Passenger tarball / local golden DB (build time only)."""
    return BootstrapAdmin(
        username=require_default("DEFAULT_ADMIN_USERNAME"),
        email=require_default("DEFAULT_ADMIN_EMAIL"),
        password=require_default("DEFAULT_ADMIN_PASSWORD"),
        must_change_password=True,
        source=".env.defaults DEFAULT_ADMIN_* (documented shipped default)",
    )


def _spec_from_env() -> BootstrapAdmin | None:
    username = os.environ.get(ENV_USERNAME, "").strip()
    email = os.environ.get(ENV_EMAIL, "").strip()
    password = os.environ.get(ENV_PASSWORD, "")
    password_file = os.environ.get(ENV_PASSWORD_FILE, "").strip()

    if not (username or email or password or password_file):
        return None
    if password and password_file:
        raise BootstrapAdminError(f"set only one of {ENV_PASSWORD} and {ENV_PASSWORD_FILE}")
    source = f"environment ({ENV_PASSWORD})"
    if password_file:
        path = Path(password_file)
        if not path.is_file():
            raise BootstrapAdminError(f"{ENV_PASSWORD_FILE} points to a missing file: {password_file}")
        password = path.read_text(encoding="utf-8").rstrip("\r\n")
        source = f"environment (password file {password_file})"
    missing = [
        name for name, value in ((ENV_USERNAME, username), (ENV_EMAIL, email), ("password", password))
        if not value
    ]
    if missing:
        raise BootstrapAdminError(
            "incomplete bootstrap admin configuration, missing: " + ", ".join(missing) + ". " + CONFIG_HINT
        )
    # The operator chose (or ciu generated) this password: no forced change.
    return BootstrapAdmin(username, email, password, must_change_password=False, source=source)


def _spec_from_app_config(app_root: str | None) -> BootstrapAdmin | None:
    if not app_root:
        return None
    config_path = Path(app_root) / "app-config.toml"
    if not config_path.is_file():
        return None
    try:
        import tomllib as toml_parser
    except ImportError:  # Python < 3.11
        import tomli as toml_parser  # type: ignore[no-redef]
    with config_path.open("rb") as handle:
        config = toml_parser.load(handle)

    admins = [u for u in (config.get("users") or []) if isinstance(u, dict) and u.get("is_admin")]
    if not admins:
        return None
    admin = admins[0]
    password = admin.get("password") or ""
    if password == "generate":
        raise BootstrapAdminError(
            f"{config_path}: an [[users]] admin needs an explicit password; "
            "'generate' is only allowed for non-admin users"
        )
    return BootstrapAdmin(
        username=(admin.get("username") or "").strip(),
        email=(admin.get("email") or "").strip(),
        password=password,
        must_change_password=bool(admin.get("must_change_password", False)),
        source=f"{config_path} [[users]]",
    )


def configured_admin_spec(app_root: str | None) -> BootstrapAdmin | None:
    """Operator-configured bootstrap admin: environment first, then app-config.toml."""
    return _spec_from_env() or _spec_from_app_config(app_root)
