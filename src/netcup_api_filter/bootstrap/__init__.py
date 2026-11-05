"""Bootstrap helpers for seeding databases during builds, first start and e2e sessions."""

from .admin import (
    BootstrapAdmin,
    BootstrapAdminError,
    configured_admin_spec,
    seed_bootstrap_admin,
    shipped_admin_spec,
)
from .instance import InitReport, MockEmail, init_instance
from .seeding import (
    DemoAccountSeedOptions,
    RealmSeedOptions,
    TokenSeedOptions,
    ensure_account,
    ensure_realm,
    ensure_token,
    seed_comprehensive_demo_data,
    seed_delegated_zone_domain_root,
    seed_demo_audit_logs,
    seed_demo_domain_roots,
    seed_mock_email_config,
    seed_shipped_database,
)

__all__ = [
    "BootstrapAdmin",
    "BootstrapAdminError",
    "InitReport",
    "MockEmail",
    "DemoAccountSeedOptions",
    "RealmSeedOptions",
    "TokenSeedOptions",
    "ensure_account",
    "configured_admin_spec",
    "init_instance",
    "ensure_realm",
    "ensure_token",
    "seed_bootstrap_admin",
    "seed_comprehensive_demo_data",
    "seed_delegated_zone_domain_root",
    "seed_demo_audit_logs",
    "seed_demo_domain_roots",
    "seed_mock_email_config",
    "shipped_admin_spec",
    "seed_shipped_database",
]
