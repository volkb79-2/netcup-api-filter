"""``init_instance`` — the ONE idempotent initializer of a naf database.

Every way a naf database comes to life goes through this function:

========================================  ==============================================
caller                                     admin spec / mode
========================================  ==============================================
Passenger tarball build                    shipped_admin_spec() (must_change_password)
local golden DB (``run-gate local-build``) shipped_admin_spec() + Mailpit email config
app start (``init_db``; OCI first boot)    configured_admin_spec() only if no admin exists
ciu post_compose hook of the app stack     configured_admin_spec(), ``enforce_admin=True``
                                           (via ``python -m netcup_api_filter.bootstrap``)
========================================  ==============================================

Steps (each idempotent, create-if-missing unless stated):
schema (``create_all`` + lightweight migrations) → enum tables and backend providers →
default settings from the env defaults (absent keys only) → the admin → optionally the
Mailpit email config of a local stack. A database without any administrator after this
is an error: the app would be unusable.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ..models import Account, db
from .admin import CONFIG_HINT, BootstrapAdmin, BootstrapAdminError, seed_bootstrap_admin

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MockEmail:
    """Mailpit-style SMTP capture for LOCAL stacks only (no auth, no TLS)."""

    smtp_host: str
    smtp_port: int
    from_email: str
    admin_email: str

    def __post_init__(self) -> None:
        if not self.smtp_host:
            raise ValueError("MockEmail.smtp_host is required")
        if not (0 < int(self.smtp_port) < 65536):
            raise ValueError(f"MockEmail.smtp_port out of range: {self.smtp_port}")
        for name in ("from_email", "admin_email"):
            if "@" not in getattr(self, name):
                raise ValueError(f"MockEmail.{name} must be an email address")


@dataclass(frozen=True)
class InitReport:
    admin_username: str
    admin_action: str  # created | updated | unchanged | existing
    admin_source: str


def init_instance(
    *,
    admin: BootstrapAdmin | None,
    enforce_admin: bool = False,
    mock_email: MockEmail | None = None,
) -> InitReport:
    """Bring the database bound to the current app context to a known-good state.

    ``admin=None`` means "an administrator must already exist" (an app start on an
    initialized database); otherwise *admin* is created if missing, or — with
    ``enforce_admin`` — created or updated.
    """
    from ..database import run_lightweight_migrations
    from .seeding import seed_mock_email_config, seed_multi_backend_infrastructure, seed_settings_from_env

    if enforce_admin and admin is None:
        raise BootstrapAdminError("enforce_admin requires an admin spec. " + CONFIG_HINT)

    db.create_all()
    run_lightweight_migrations()
    seed_multi_backend_infrastructure()
    seed_settings_from_env()

    if admin is not None:
        account, action = seed_bootstrap_admin(admin, enforce=enforce_admin)
        report = InitReport(account.username, action, admin.source)
    else:
        existing = Account.query.filter_by(is_admin=1, is_active=1).order_by(Account.id).first()
        if existing is None:
            raise BootstrapAdminError(
                "No active administrator account exists and no bootstrap admin is configured. " + CONFIG_HINT
            )
        report = InitReport(existing.username, "existing", "database")

    if mock_email is not None:
        seed_mock_email_config(
            smtp_host=mock_email.smtp_host,
            smtp_port=mock_email.smtp_port,
            from_email=mock_email.from_email,
            admin_email=mock_email.admin_email,
        )
    logger.info(
        "init_instance: admin %s %s (source: %s)%s",
        report.admin_username, report.admin_action, report.admin_source,
        "; mock email configured" if mock_email else "",
    )
    return report
