"""
Reusable helpers for seeding default admin and demo accounts.

Updated for Account → Realms → Tokens architecture.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from collections.abc import Sequence

from ..models import (
    Account,
    AccountRealm,
    ActivityLog,
    APIToken,
    USER_ALIAS_LENGTH,
    db,
    generate_token,
    generate_user_alias,
    hash_token,
    # Multi-backend models
    BackendProvider,
    BackendService,
    GrantTypeEnum,
    ManagedDomainRoot,
    OwnerTypeEnum,
    TestStatusEnum,
    VisibilityEnum,
)
from ..config_defaults import load_defaults
from ..utils import parse_bool

logger = logging.getLogger(__name__)

# Lazy-load environment defaults only when needed (not at module import)
# This allows the module to be imported without .env/.env.defaults present
_ENV_DEFAULTS = None

def _get_env_defaults():
    """Lazy-load environment defaults only when actually seeding."""
    global _ENV_DEFAULTS
    if _ENV_DEFAULTS is None:
        _ENV_DEFAULTS = load_defaults()
    return _ENV_DEFAULTS


def seed_settings_from_env():
    """Seed Settings table from .env/.env.defaults if not already set.
    
    This is called during database creation (build_deployment.py) to populate
    the Settings table with default values from .env/.env.defaults.
    
    Hierarchy:
    1. Environment variables (runtime overrides)
    2. Settings table (admin UI changes) ← We populate this
    3. .env/.env.defaults (defaults) ← We read from this
    
    Settings that should be seeded:
    - Rate limits (admin, account, API)
    - Password reset expiry
    - Invite link expiry
    - Session settings (already handled by Flask config)
    
    Settings that should NOT be seeded (must be configured per deployment):
    - Email (SMTP credentials)
    - Netcup API (API keys)
    - GeoIP (MaxMind credentials)
    - SECRET_KEY (generated per deployment)
    """
    from ..database import set_setting, get_setting

    defaults = _get_env_defaults()

    deployment_target = os.environ.get("DEPLOYMENT_TARGET", "").strip().lower()
    if deployment_target == "local":
        demo_pages_default_raw = defaults.get("DEMO_PAGES_ENABLED_LOCAL", "true")
    elif deployment_target == "webhosting":
        demo_pages_default_raw = defaults.get("DEMO_PAGES_ENABLED_WEBHOSTING", "false")
    else:
        # Safe default when target is unknown: prefer webhosting behavior.
        demo_pages_default_raw = defaults.get(
            "DEMO_PAGES_ENABLED_WEBHOSTING",
            defaults.get("DEMO_PAGES_ENABLED_LOCAL", "false"),
        )
    demo_pages_enabled = parse_bool(demo_pages_default_raw, default=False)
    
    # Map of Settings table keys to env defaults keys
    settings_map = {
        'admin_rate_limit': defaults.get('ADMIN_RATE_LIMIT', '50 per minute'),
        'account_rate_limit': defaults.get('ACCOUNT_RATE_LIMIT', '50 per minute'),
        'api_rate_limit': defaults.get('API_RATE_LIMIT', '60 per minute'),
        'password_reset_expiry_hours': '1',  # Conservative default
        'invite_expiry_hours': '48',  # 2 days
        'enable_demo_pages': demo_pages_enabled,
    }
    
    seeded_count = 0
    for setting_key, default_value in settings_map.items():
        # Seed only when the key is truly absent. `if not get_setting(...)` would
        # treat a deliberately-stored falsy value (e.g. enable_demo_pages = False)
        # as unseeded and overwrite it with the env default on every build.
        if get_setting(setting_key) is None:
            set_setting(setting_key, default_value)
            seeded_count += 1
            logger.info(f"Seeded setting '{setting_key}' = '{default_value}'")
    
    if seeded_count > 0:
        db.session.commit()
        logger.info(f"Seeded {seeded_count} settings from .env/.env.defaults")
    else:
        logger.info("Settings table already populated, skipping seeding")
    
    return seeded_count


@dataclass
class RealmSeedOptions:
    """Options for seeding a realm."""
    domain: str
    realm_type: str = "host"  # host, subdomain, zone
    realm_value: str = ""  # Subdomain prefix or empty for apex
    record_types: Sequence[str] = field(default_factory=lambda: ["A", "AAAA"])
    operations: Sequence[str] = field(default_factory=lambda: ["read"])


@dataclass
class TokenSeedOptions:
    """Options for seeding a token."""
    token_name: str
    description: str = ""
    record_types: Sequence[str] | None = None  # None = inherit from realm
    operations: Sequence[str] | None = None  # None = inherit from realm
    ip_ranges: Sequence[str] | None = None


@dataclass
class DemoAccountSeedOptions:
    """Options for seeding a demo account with realm and token."""
    username: str
    password: str
    email: str = None
    realm: RealmSeedOptions = None
    token: TokenSeedOptions = None
    
    def __post_init__(self):
        if self.email is None:
            self.email = f"{self.username}@example.com"


# Backwards compatibility aliases


def ensure_account(options: DemoAccountSeedOptions, approved_by: Account = None) -> Account:
    """Create or update a user account.
    
    Returns:
        The Account object
    """
    account = Account.query.filter_by(username=options.username).first()
    if not account:
        # Generate unique user_alias for token attribution
        user_alias = generate_user_alias()
        account = Account(
            username=options.username,
            user_alias=user_alias,
            email=options.email,
            email_verified=1,
            email_2fa_enabled=1,
            totp_enabled=0,
            telegram_enabled=0,
            is_active=1,
            is_admin=0,
            approved_by_id=approved_by.id if approved_by else None,
            approved_at=datetime.utcnow()
        )
        account.set_password(options.password)
        db.session.add(account)
        logger.info(f"Created account: {options.username} (alias: {user_alias[:4]}...)")
    else:
        # Ensure existing account has user_alias
        if not account.user_alias:
            account.user_alias = generate_user_alias()
            logger.info(f"Added user_alias to existing account: {options.username}")
        # Do NOT force email_verified / email_2fa_enabled here. Re-seeding (every
        # build) would otherwise silently re-enable flags an operator or test had
        # deliberately cleared. These flags are set once, at account creation.
        logger.info(f"Account {options.username} already exists")
    return account


def ensure_realm(account: Account, options: RealmSeedOptions, approved_by: Account = None) -> AccountRealm:
    """Create or update a realm for an account.
    
    Returns:
        The AccountRealm object
    """
    # Check if realm already exists
    realm = AccountRealm.query.filter_by(
        account_id=account.id,
        domain=options.domain,
        realm_type=options.realm_type,
        realm_value=options.realm_value
    ).first()
    
    if not realm:
        realm = AccountRealm(
            account_id=account.id,
            domain=options.domain,
            realm_type=options.realm_type,
            realm_value=options.realm_value,
            status='approved',
            requested_at=datetime.utcnow(),
            approved_by_id=approved_by.id if approved_by else None,
            approved_at=datetime.utcnow()
        )
        realm.set_allowed_record_types(list(options.record_types))
        realm.set_allowed_operations(list(options.operations))
        db.session.add(realm)
        logger.info(f"Created realm: {options.realm_type}:{options.realm_value}@{options.domain}")
    else:
        logger.info(f"Realm already exists for {account.username}")
    
    return realm


def ensure_token(realm: AccountRealm, options: TokenSeedOptions) -> tuple[APIToken, str]:
    """Create a token for a realm.
    
    Returns:
        Tuple of (APIToken object, plain token string)
    """
    # Check if token with same name exists
    existing = APIToken.query.filter_by(
        realm_id=realm.id,
        token_name=options.token_name
    ).first()
    
    if existing:
        logger.info(f"Token {options.token_name} already exists, skipping")
        return existing, None  # Can't return plain token for existing
    
    # Generate token using user_alias (not username for security)
    account = realm.account
    full_token = generate_token(account.user_alias)
    
    # Extract prefix (first 8 chars of random part)
    # Token format: naf_<user_alias>_<random64> where user_alias is 16 chars
    random_part_start = 4 + USER_ALIAS_LENGTH + 1  # "naf_" + alias + "_"
    token_prefix = full_token[random_part_start:random_part_start + 8]
    
    token = APIToken(
        realm_id=realm.id,
        token_name=options.token_name,
        token_description=options.description,
        token_prefix=token_prefix,
        token_hash=hash_token(full_token),
        is_active=1
    )
    
    # Optional overrides
    if options.record_types:
        token.set_allowed_record_types(list(options.record_types))
    if options.operations:
        token.set_allowed_operations(list(options.operations))
    if options.ip_ranges:
        token.set_allowed_ip_ranges(list(options.ip_ranges))
    
    db.session.add(token)
    logger.info(f"Created token: {options.token_name} for realm {realm.id}")
    
    return token, full_token


# Legacy compatibility - no-op, new schema doesn't use this
def seed_demo_audit_logs(account: Account = None) -> None:
    """Seed demo audit logs for testing."""
    import json
    from datetime import timedelta
    
    # Only seed if no logs exist
    if ActivityLog.query.first():
        logger.info("Activity logs already exist, skipping demo seed")
        return
    
    logger.info("Seeding demo activity logs")
    base_time = datetime.utcnow() - timedelta(hours=2)
    
    demo_logs = [
        {"action": "login", "ip": "192.168.1.100", "minutes_ago": 120, "success": True},
        {"action": "create_token", "ip": "192.168.1.100", "minutes_ago": 115, "success": True},
        {"action": "api_call", "ip": "192.168.1.100", "minutes_ago": 110, "success": True},
        {"action": "api_call", "ip": "10.0.0.50", "minutes_ago": 90, "success": True},
        {"action": "api_call", "ip": "192.168.1.100", "minutes_ago": 60, "success": True},
        {"action": "api_call", "ip": "203.0.113.42", "minutes_ago": 45, "success": False},
        {"action": "logout", "ip": "192.168.1.100", "minutes_ago": 30, "success": True},
    ]
    
    for log_data in demo_logs:
        timestamp = base_time + timedelta(minutes=log_data["minutes_ago"])
        log = ActivityLog(
            account_id=account.id if account else None,
            action=log_data["action"],
            source_ip=log_data["ip"], status="success" if log_data["success"] else "error",
            user_agent="Demo User Agent",
            request_data=json.dumps({"demo": True}),
            
            created_at=timestamp
        )
        db.session.add(log)
    
    db.session.commit()
    logger.info(f"Seeded {len(demo_logs)} demo activity logs")


def seed_mock_email_config(*, smtp_host: str, smtp_port: int, from_email: str, admin_email: str) -> None:
    """Point the app's email config at a local Mailpit-style capture (no auth, no TLS).

    Local stacks only; every value is explicit (the caller resolves it from its own
    configuration, see bootstrap.instance.MockEmail). Fields are stored with both
    internal names (smtp_server, sender_email) and HTML form names (smtp_host,
    from_email) for template compatibility.
    """
    from ..models import Settings
    import json

    email_config = {
        # Internal field names (used by email_notifier)
        "smtp_server": smtp_host,
        "sender_email": from_email,
        "sender_name": "Netcup API Filter",
        # HTML form field names (used by templates)
        "smtp_host": smtp_host,
        "from_email": from_email,
        "from_name": "Netcup API Filter",
        # Common fields
        "smtp_port": int(smtp_port),
        "smtp_security": "none",  # Mailpit doesn't use TLS
        "smtp_username": "",  # Mailpit doesn't require auth
        "smtp_password": "",
        "use_ssl": False,
        "reply_to": "",
        "admin_email": admin_email,
        "notify_new_account": True,
        "notify_realm_request": True,
        "notify_security": True,
    }

    setting = Settings.query.filter_by(key="email_config").first()
    if not setting:
        setting = Settings(key="email_config")
        db.session.add(setting)
    setting.value = json.dumps(email_config)
    db.session.commit()
    logger.info(f"Seeded email config for mock mode: {smtp_host}:{smtp_port} from {from_email}")


def seed_mock_netcup_config(mock) -> None:
    """Point the global ``netcup_config`` at the Netcup CCP mock (bootstrap.instance.MockNetcup).

    Local/e2e stacks only. Same JSON shape the admin UI saves (``api/admin.py``), so the admin
    form, ``dns_api.get_netcup_client`` and tests that rewrite and restore it through the UI
    keep working unchanged.
    """
    from ..database import set_setting

    set_setting("netcup_config", {
        "customer_id": mock.customer_id,
        "api_key": mock.api_key,
        "api_password": mock.api_password,
        "api_url": mock.api_url,
        "timeout": int(mock.timeout),
    })
    logger.info("Seeded netcup_config for the mock backend: %s", mock.api_url)


def seed_shipped_database(*, mock_email=None, mock_netcup=None) -> Account:
    """Seed everything a shipped/golden database contains — and nothing else.

    Thin wrapper over bootstrap.instance.init_instance with the pre-set admin
    (``DEFAULT_ADMIN_*``, ``must_change_password``) and, for local builds only, a
    Mailpit email config and mock Netcup backend (*mock_email* / *mock_netcup*:
    bootstrap.instance.MockEmail / MockNetcup). No demo
    accounts, tokens, domain roots or audit logs: e2e personas are provisioned per
    session (ui_tests/personas.py), screenshot data only via ``--seed-demo``.
    """
    from .admin import shipped_admin_spec
    from .instance import init_instance

    init_instance(admin=shipped_admin_spec(), mock_email=mock_email, mock_netcup=mock_netcup)
    return Account.query.filter_by(username=shipped_admin_spec().username).one()


def seed_comprehensive_demo_data(admin: Account) -> None:
    """Seed comprehensive demo data for UI screenshots and testing.
    
    This creates:
    - 6 accounts in different states (active, pending, disabled)
    - Multiple realms per account in different states (approved, pending, rejected)
    - Multiple tokens in different states (active, expired, revoked)
    - Comprehensive activity logs covering all event types
    
    Call this from build_deployment.py with --seed-demo flag.
    """
    import json
    from datetime import timedelta
    from ..models import AccountRealm, APIToken, ActivityLog
    
    logger.info("=== Seeding Comprehensive Demo Data ===")
    
    # Skip if demo data already exists (check for demo-active account)
    if Account.query.filter_by(username="demo-active").first():
        logger.info("Demo data already exists, skipping")
        return
    
    # =========================================================================
    # 1. Create Demo Accounts with Various States
    # =========================================================================
    
    demo_accounts = [
        {"username": "demo-active", "email": "active@demo.example.com", 
         "is_active": True, "email_verified": True, "approved": True},
        {"username": "demo-pending-approval", "email": "pending@demo.example.com",
         "is_active": False, "email_verified": True, "approved": False},
        {"username": "demo-pending-email", "email": "unverified@demo.example.com",
         "is_active": False, "email_verified": False, "approved": False},
        {"username": "demo-disabled", "email": "disabled@demo.example.com",
         "is_active": False, "email_verified": True, "approved": True},
        {"username": "demo-power-user", "email": "power@demo.example.com",
         "is_active": True, "email_verified": True, "approved": True},
        {"username": "demo-readonly", "email": "readonly@demo.example.com",
         "is_active": True, "email_verified": True, "approved": True},
    ]
    
    created_accounts = {}
    for acc_data in demo_accounts:
        # Get-or-create (B-BUILD): re-running the demo seed on the same DB must not trip
        # `UNIQUE constraint failed: accounts.username`; reuse the existing row instead.
        existing = Account.query.filter_by(username=acc_data["username"]).first()
        if existing is not None:
            created_accounts[acc_data["username"]] = existing
            logger.info(f"Reusing existing account: {acc_data['username']}")
            continue
        # Generate unique user_alias for token attribution
        user_alias = generate_user_alias()
        account = Account(
            username=acc_data["username"],
            user_alias=user_alias,
            email=acc_data["email"],
            email_verified=1 if acc_data["email_verified"] else 0,
            is_active=1 if acc_data["is_active"] else 0,
            is_admin=0,
            approved_by_id=admin.id if acc_data["approved"] else None,
            approved_at=datetime.utcnow() if acc_data["approved"] else None,
            created_at=datetime.utcnow() - timedelta(days=30)
        )
        # Screenshot data: nobody logs in as these accounts; never a known password.
        account.set_password(secrets.token_urlsafe(24) + "Aa1@")
        db.session.add(account)
        created_accounts[acc_data["username"]] = account
        logger.info(f"Created account: {acc_data['username']} (alias: {user_alias[:4]}...)")
    
    db.session.flush()
    
    # =========================================================================
    # 2. Create Realms with Various States
    # =========================================================================
    
    demo_realms = [
        # demo-active: 2 approved realms
        {"account": "demo-active", "domain": "example.com", "realm_type": "host",
         "realm_value": "home", "status": "approved",
         "record_types": ["A", "AAAA"], "operations": ["read", "update"]},
        {"account": "demo-active", "domain": "example.com", "realm_type": "subdomain",
         "realm_value": "iot", "status": "approved",
         "record_types": ["A", "AAAA", "TXT", "CNAME"], "operations": ["read", "create", "update", "delete"]},
        
        # demo-power-user: 5 realms (various states)
        {"account": "demo-power-user", "domain": "vxxu.de", "realm_type": "subdomain_only",
         "realm_value": "client1", "status": "approved",
         "record_types": ["A", "AAAA", "TXT"], "operations": ["read", "create", "update", "delete"]},
        {"account": "demo-power-user", "domain": "example.com", "realm_type": "host",
         "realm_value": "vpn", "status": "approved",
         "record_types": ["A", "AAAA"], "operations": ["read", "update"]},
        {"account": "demo-power-user", "domain": "example.com", "realm_type": "subdomain",
         "realm_value": "acme", "status": "pending",
         "record_types": ["TXT"], "operations": ["create", "delete"]},
        {"account": "demo-power-user", "domain": "example.com", "realm_type": "host",
         "realm_value": "rejected", "status": "rejected",
         "record_types": ["A"], "operations": ["read"]},
        {"account": "demo-power-user", "domain": "example.com", "realm_type": "host",
         "realm_value": "revoked", "status": "rejected",
         "record_types": ["A"], "operations": ["read"]},
        
        # demo-disabled: 1 revoked realm
        {"account": "demo-disabled", "domain": "example.com", "realm_type": "host",
         "realm_value": "old", "status": "rejected",
         "record_types": ["A"], "operations": ["read"]},
        
        # demo-readonly: 1 read-only realm
        {"account": "demo-readonly", "domain": "example.com", "realm_type": "host",
         "realm_value": "monitor", "status": "approved",
         "record_types": ["A", "AAAA", "TXT", "MX"], "operations": ["read"]},
    ]
    
    created_realms = {}
    for realm_data in demo_realms:
        account = created_accounts[realm_data["account"]]
        realm_key = f"{realm_data['realm_type']}:{realm_data['realm_value']}@{realm_data['domain']}"
        
        realm = AccountRealm(
            account_id=account.id,
            domain=realm_data["domain"],
            realm_type=realm_data["realm_type"],
            realm_value=realm_data["realm_value"],
            status=realm_data["status"],
            requested_at=datetime.utcnow() - timedelta(days=25),
            approved_by_id=admin.id if realm_data["status"] == "approved" else None,
            approved_at=datetime.utcnow() - timedelta(days=20) if realm_data["status"] == "approved" else None
        )
        realm.set_allowed_record_types(realm_data["record_types"])
        realm.set_allowed_operations(realm_data["operations"])
        db.session.add(realm)
        created_realms[realm_key] = realm
        logger.info(f"Created realm: {realm_key} ({realm_data['status']})")
    
    db.session.flush()
    
    # =========================================================================
    # 3. Create Tokens with Various States
    # =========================================================================
    
    demo_tokens = [
        # demo-active tokens
        {"realm_key": "host:home@example.com", "token_name": "home-router",
         "description": "Home router DDNS", "is_active": True, "expires": None,
         "ip_ranges": ["192.168.1.0/24"]},
        {"realm_key": "host:home@example.com", "token_name": "backup-updater",
         "description": "Backup updater with expiry", "is_active": True, 
         "expires": datetime.utcnow() + timedelta(days=365),
         "ip_ranges": None},
        {"realm_key": "subdomain:iot@example.com", "token_name": "fleet-manager",
         "description": "IoT fleet manager full access", "is_active": True,
         "expires": None, "ip_ranges": None},
        {"realm_key": "subdomain:iot@example.com", "token_name": "monitoring",
         "description": "Monitoring read-only", "is_active": True,
         "expires": None, "ip_ranges": None,
         "record_types_override": ["A", "AAAA"], "operations_override": ["read"]},
        
        # demo-power-user tokens
        {"realm_key": "subdomain_only:client1@vxxu.de", "token_name": "certbot-prod",
         "description": "Certbot production DNS-01", "is_active": True,
         "expires": None, "ip_ranges": None},
        {"realm_key": "subdomain_only:client1@vxxu.de", "token_name": "certbot-staging",
         "description": "Certbot staging (EXPIRED)", "is_active": False,
         "expires": datetime.utcnow() - timedelta(days=30), "ip_ranges": None},
        {"realm_key": "subdomain_only:client1@vxxu.de", "token_name": "old-system",
         "description": "Old system (REVOKED)", "is_active": False,
         "expires": None, "ip_ranges": None},
        {"realm_key": "host:vpn@example.com", "token_name": "vpn-gateway",
         "description": "VPN gateway updater", "is_active": True,
         "expires": None, "ip_ranges": ["10.0.0.0/8"]},
        {"realm_key": "host:vpn@example.com", "token_name": "vpn-backup",
         "description": "VPN backup (never used)", "is_active": True,
         "expires": None, "ip_ranges": None},
        
        # demo-readonly token
        {"realm_key": "host:monitor@example.com", "token_name": "grafana",
         "description": "Grafana dashboard read-only", "is_active": True,
         "expires": None, "ip_ranges": ["10.0.0.0/8"]},
    ]
    
    created_tokens = {}
    for token_data in demo_tokens:
        realm_key = token_data["realm_key"]
        if realm_key not in created_realms:
            logger.warning(f"Skipping token {token_data['token_name']} - realm {realm_key} not found")
            continue
        
        realm = created_realms[realm_key]
        account = realm.account
        
        # Generate token using user_alias (not username for security)
        full_token = generate_token(account.user_alias)
        # Token format: naf_<user_alias>_<random64> where user_alias is 16 chars
        random_part_start = 4 + USER_ALIAS_LENGTH + 1  # "naf_" + alias + "_"
        token_prefix = full_token[random_part_start:random_part_start + 8]
        
        token = APIToken(
            realm_id=realm.id,
            token_name=token_data["token_name"],
            token_description=token_data["description"],
            token_prefix=token_prefix,
            token_hash=hash_token(full_token),
            is_active=1 if token_data["is_active"] else 0,
            expires_at=token_data.get("expires"),
            created_at=datetime.utcnow() - timedelta(days=15)
        )
        
        # Optional overrides
        if token_data.get("record_types_override"):
            token.set_allowed_record_types(token_data["record_types_override"])
        if token_data.get("operations_override"):
            token.set_allowed_operations(token_data["operations_override"])
        if token_data.get("ip_ranges"):
            token.set_allowed_ip_ranges(token_data["ip_ranges"])
        
        db.session.add(token)
        created_tokens[token_data["token_name"]] = token
        logger.info(f"Created token: {token_data['token_name']} ({realm_key})")
    
    db.session.flush()
    
    # =========================================================================
    # 4. Create Activity Logs covering all event types
    # =========================================================================
    
    base_time = datetime.utcnow() - timedelta(hours=48)
    
    activity_logs = [
        # Admin login events
        {"action": "admin_login", "ip": "192.168.1.100", "hours_ago": 48,
         "success": True, "details": {"username": "admin"}},
        {"action": "admin_login", "ip": "203.0.113.42", "hours_ago": 47,
         "success": False, "details": {"username": "admin", "reason": "invalid_password"}},
        
        # Account registration
        {"action": "account_register", "ip": "198.51.100.10", "hours_ago": 46,
         "success": True, "account": "demo-active", "details": {"email": "active@demo.example.com"}},
        {"action": "account_verify_email", "ip": "198.51.100.10", "hours_ago": 45,
         "success": True, "account": "demo-active", "details": {}},
        {"action": "account_approved", "ip": "192.168.1.100", "hours_ago": 44,
         "success": True, "account": "demo-active", "details": {"approved_by": "admin"}},
        
        # Realm requests
        {"action": "realm_request", "ip": "198.51.100.10", "hours_ago": 43,
         "success": True, "account": "demo-active", "details": {"realm": "host:home@example.com"}},
        {"action": "realm_approved", "ip": "192.168.1.100", "hours_ago": 42,
         "success": True, "account": "demo-active", "details": {"realm": "host:home@example.com"}},
        {"action": "realm_request", "ip": "198.51.100.20", "hours_ago": 30,
         "success": True, "account": "demo-power-user", "details": {"realm": "subdomain:acme@example.com"}},
        {"action": "realm_rejected", "ip": "192.168.1.100", "hours_ago": 29,
         "success": True, "account": "demo-power-user", 
         "details": {"realm": "host:rejected@example.com", "reason": "Domain not verified"}},
        
        # Token operations
        {"action": "token_create", "ip": "198.51.100.10", "hours_ago": 41,
         "success": True, "account": "demo-active", 
         "details": {"token_name": "home-router", "realm": "host:home@example.com"}},
        {"action": "token_revoke", "ip": "198.51.100.20", "hours_ago": 20,
         "success": True, "account": "demo-power-user",
         "details": {"token_name": "old-system", "reason": "Security rotation"}},
        
        # API calls - successful
        {"action": "api_call", "ip": "192.168.1.1", "hours_ago": 36,
         "success": True, "account": "demo-active", "token": "home-router",
         "details": {"operation": "read", "domain": "example.com", "record": "home.example.com", "type": "A"}},
        {"action": "api_call", "ip": "192.168.1.1", "hours_ago": 24,
         "success": True, "account": "demo-active", "token": "home-router",
         "details": {"operation": "update", "domain": "example.com", "record": "home.example.com", "type": "A", "value": "1.2.3.4"}},
        {"action": "api_call", "ip": "10.0.0.50", "hours_ago": 12,
         "success": True, "account": "demo-active", "token": "fleet-manager",
         "details": {"operation": "create", "domain": "example.com", "record": "sensor1.iot.example.com", "type": "A"}},
        {"action": "api_call", "ip": "52.94.76.8", "hours_ago": 6,
         "success": True, "account": "demo-power-user", "token": "certbot-prod",
         "details": {"operation": "create", "domain": "vxxu.de", "record": "_acme-challenge.client1.vxxu.de", "type": "TXT"}},
        {"action": "api_call", "ip": "52.94.76.8", "hours_ago": 5,
         "success": True, "account": "demo-power-user", "token": "certbot-prod",
         "details": {"operation": "delete", "domain": "vxxu.de", "record": "_acme-challenge.client1.vxxu.de", "type": "TXT"}},
        
        # API calls - denied
        {"action": "api_call", "ip": "203.0.113.50", "hours_ago": 18,
         "success": False, "account": "demo-readonly", "token": "grafana",
         "details": {"operation": "update", "reason": "read-only token", "domain": "example.com"}},
        {"action": "api_call", "ip": "123.45.67.89", "hours_ago": 15,
         "success": False, "account": "demo-active", "token": "home-router",
         "details": {"operation": "update", "reason": "IP not in whitelist", "source_ip": "123.45.67.89"}},
        
        # API auth failures
        {"action": "api_auth_failure", "ip": "185.220.101.42", "hours_ago": 10,
         "success": False, "details": {"reason": "invalid_token"}},
        {"action": "api_auth_failure", "ip": "195.54.160.12", "hours_ago": 8,
         "success": False, "details": {"reason": "expired_token", "token_prefix": "abc12345"}},
        
        # Password changes
        {"action": "password_change", "ip": "198.51.100.10", "hours_ago": 2,
         "success": True, "account": "demo-active", "details": {}},
        
        # Account disabled
        {"action": "account_disabled", "ip": "192.168.1.100", "hours_ago": 1,
         "success": True, "account": "demo-disabled", "details": {"reason": "Inactive for 90 days"}},
    ]
    
    for log_data in activity_logs:
        timestamp = base_time + timedelta(hours=(48 - log_data["hours_ago"]))
        
        account = created_accounts.get(log_data.get("account"))
        token = created_tokens.get(log_data.get("token"))
        
        log = ActivityLog(
            account_id=account.id if account else None,
            token_id=token.id if token else None,
            action=log_data["action"],
            source_ip=log_data["ip"],
            status="success" if log_data["success"] else "error",
            user_agent="Mozilla/5.0 Demo User Agent",
            request_data=json.dumps(log_data["details"]),
            created_at=timestamp
        )
        db.session.add(log)
    
    db.session.commit()
    logger.info(f"Created {len(activity_logs)} activity log entries")
    
    logger.info("=== Comprehensive Demo Data Seeding Complete ===")
    logger.info(f"  Accounts: {len(demo_accounts)}")
    logger.info(f"  Realms: {len(demo_realms)}")
    logger.info(f"  Tokens: {len(demo_tokens)}")
    logger.info(f"  Activity logs: {len(activity_logs)}")


# ============================================================================
# Multi-Backend Seeding
# ============================================================================

def seed_enum_tables() -> None:
    """Seed enum tables with predefined values.
    
    Called during database initialization to ensure all enum values exist.
    """
    logger.info("Seeding enum tables for multi-backend architecture...")
    
    # Test Status Enum
    test_statuses = [
        (TestStatusEnum.PENDING, "Pending"),
        (TestStatusEnum.SUCCESS, "Success"),
        (TestStatusEnum.FAILED, "Failed"),
    ]
    for code, name in test_statuses:
        if not TestStatusEnum.query.filter_by(status_code=code).first():
            db.session.add(TestStatusEnum(status_code=code, display_name=name))
    
    # Visibility Enum
    visibilities = [
        (VisibilityEnum.PUBLIC, "Public", "Any authenticated user can request subdomains"),
        (VisibilityEnum.PRIVATE, "Private", "Only explicitly granted users can request subdomains"),
        (VisibilityEnum.INVITE, "Invite Only", "Users need invitation code to request subdomains"),
    ]
    for code, name, desc in visibilities:
        if not VisibilityEnum.query.filter_by(visibility_code=code).first():
            db.session.add(VisibilityEnum(visibility_code=code, display_name=name, description=desc))
    
    # Owner Type Enum
    owner_types = [
        (OwnerTypeEnum.PLATFORM, "Platform"),
        (OwnerTypeEnum.USER, "User"),
    ]
    for code, name in owner_types:
        if not OwnerTypeEnum.query.filter_by(owner_code=code).first():
            db.session.add(OwnerTypeEnum(owner_code=code, display_name=name))
    
    # Grant Type Enum
    grant_types = [
        (GrantTypeEnum.STANDARD, "Standard"),
        (GrantTypeEnum.ADMIN, "Administrator"),
        (GrantTypeEnum.INVITE_ONLY, "Invite Only"),
    ]
    for code, name in grant_types:
        if not GrantTypeEnum.query.filter_by(grant_code=code).first():
            db.session.add(GrantTypeEnum(grant_code=code, display_name=name))
    
    db.session.commit()
    logger.info("Enum tables seeded successfully")


def seed_backend_providers() -> None:
    """Seed built-in backend providers with their configurations.
    
    Called during database initialization to register available DNS providers.
    """
    logger.info("Seeding backend providers...")
    
    providers = [
        {
            "provider_code": "netcup",
            "display_name": "Netcup CCP API",
            "description": "Netcup Customer Control Panel DNS API",
            "config_schema": json.dumps({
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string", "minLength": 1, "description": "Netcup customer number"},
                    "api_key": {"type": "string", "minLength": 1, "description": "API key from CCP"},
                    "api_password": {"type": "string", "minLength": 1, "description": "API password from CCP"},
                    "api_url": {"type": "string", "format": "uri", "description": "API endpoint URL"},
                    "timeout": {"type": "integer", "minimum": 5, "maximum": 120, "default": 30}
                },
                "required": ["customer_id", "api_key", "api_password"]
            }),
            "supports_zone_list": False,
            "supports_zone_create": False,
            "supports_dnssec": False,
            "supported_record_types": json.dumps(["A", "AAAA", "CNAME", "MX", "TXT", "NS", "SRV", "CAA"]),
            "is_enabled": True,
            "is_builtin": True,
        },
        {
            "provider_code": "powerdns",
            "display_name": "PowerDNS",
            "description": "PowerDNS Authoritative Server HTTP API",
            "config_schema": json.dumps({
                "type": "object",
                "properties": {
                    "api_url": {"type": "string", "format": "uri", "description": "PowerDNS API URL"},
                    "api_key": {"type": "string", "minLength": 1, "description": "X-API-Key header value"},
                    "timeout": {"type": "integer", "minimum": 5, "maximum": 120, "default": 30},
                    "server_id": {"type": "string", "default": "localhost", "description": "PowerDNS server ID"}
                },
                "required": ["api_url", "api_key"]
            }),
            "supports_zone_list": True,
            "supports_zone_create": True,
            "supports_dnssec": True,
            "supported_record_types": json.dumps(["A", "AAAA", "CNAME", "MX", "TXT", "NS", "SRV", "CAA", "SOA", "PTR"]),
            "is_enabled": True,
            "is_builtin": True,
        },
        {
            "provider_code": "cloudflare",
            "display_name": "Cloudflare DNS",
            "description": "Cloudflare DNS API (not yet implemented)",
            "config_schema": json.dumps({
                "type": "object",
                "properties": {
                    "api_token": {"type": "string", "minLength": 1, "description": "Cloudflare API token"},
                    "zone_id": {"type": "string", "pattern": "^[a-f0-9]{32}$", "description": "Zone ID"}
                },
                "required": ["api_token"]
            }),
            "supports_zone_list": True,
            "supports_zone_create": False,
            "supports_dnssec": True,
            "supported_record_types": json.dumps(["A", "AAAA", "CNAME", "MX", "TXT", "NS", "SRV"]),
            "is_enabled": False,  # Not yet implemented
            "is_builtin": True,
        },
        {
            "provider_code": "route53",
            "display_name": "AWS Route 53",
            "description": "Amazon Route 53 DNS API (not yet implemented)",
            "config_schema": json.dumps({
                "type": "object",
                "properties": {
                    "access_key_id": {"type": "string", "description": "AWS Access Key ID"},
                    "secret_access_key": {"type": "string", "minLength": 40, "description": "AWS Secret Access Key"},
                    "region": {"type": "string", "default": "us-east-1", "description": "AWS Region"}
                },
                "required": ["access_key_id", "secret_access_key"]
            }),
            "supports_zone_list": True,
            "supports_zone_create": True,
            "supports_dnssec": True,
            "supported_record_types": json.dumps(["A", "AAAA", "CNAME", "MX", "TXT", "NS", "SRV", "SOA"]),
            "is_enabled": False,  # Not yet implemented
            "is_builtin": True,
        },
    ]
    
    for provider_data in providers:
        existing = BackendProvider.query.filter_by(provider_code=provider_data["provider_code"]).first()
        if not existing:
            provider = BackendProvider(**provider_data)
            db.session.add(provider)
            logger.info(f"Added backend provider: {provider_data['provider_code']}")
        else:
            logger.info(f"Backend provider {provider_data['provider_code']} already exists")
    
    db.session.commit()
    logger.info("Backend providers seeded successfully")


def seed_multi_backend_infrastructure() -> None:
    """Seed all multi-backend infrastructure (enums + providers).
    
    Main entry point for setting up the multi-backend system.
    Call this during database initialization.
    """
    seed_enum_tables()
    seed_backend_providers()


def get_or_create_owner_type(code: str) -> OwnerTypeEnum:
    """Get or create an owner type enum by code."""
    owner_type = OwnerTypeEnum.query.filter_by(owner_code=code).first()
    if not owner_type:
        seed_enum_tables()
        owner_type = OwnerTypeEnum.query.filter_by(owner_code=code).first()
    return owner_type


def get_or_create_visibility(code: str) -> VisibilityEnum:
    """Get or create a visibility enum by code."""
    visibility = VisibilityEnum.query.filter_by(visibility_code=code).first()
    if not visibility:
        seed_enum_tables()
        visibility = VisibilityEnum.query.filter_by(visibility_code=code).first()
    return visibility


def create_backend_service(
    provider_code: str,
    service_name: str,
    display_name: str,
    config: dict,
    owner_type: str = "platform",
    owner: Account = None,
    is_active: bool = True,
) -> BackendService:
    """Create a backend service.
    
    Args:
        provider_code: Provider identifier (e.g., 'netcup', 'powerdns')
        service_name: Unique service name
        display_name: Human-readable display name
        config: Provider-specific configuration dict
        owner_type: 'platform' or 'user'
        owner: Account that owns this service (for user-owned)
        is_active: Whether the service is active
    
    Returns:
        Created BackendService
    """
    provider = BackendProvider.query.filter_by(provider_code=provider_code).first()
    if not provider:
        seed_backend_providers()
        provider = BackendProvider.query.filter_by(provider_code=provider_code).first()
        if not provider:
            raise ValueError(f"Unknown provider: {provider_code}")
    
    owner_type_enum = get_or_create_owner_type(owner_type)
    
    service = BackendService(
        provider_id=provider.id,
        service_name=service_name,
        display_name=display_name,
        config=json.dumps(config),
        owner_type_id=owner_type_enum.id,
        owner_id=owner.id if owner else None,
        is_active=is_active,
    )
    db.session.add(service)
    db.session.commit()
    logger.info(f"Created backend service: {service_name} ({provider_code})")
    return service


def create_domain_root(
    backend_service: BackendService,
    root_domain: str,
    dns_zone: str = None,
    visibility: str = "private",
    display_name: str = None,
    description: str = None,
    allowed_record_types: list = None,
    allowed_operations: list = None,
) -> ManagedDomainRoot:
    """Create a managed domain root.
    
    Args:
        backend_service: BackendService that manages this domain
        root_domain: The domain root (e.g., 'dyn.vxxu.de')
        dns_zone: Actual zone in backend (defaults to root_domain)
        visibility: 'public', 'private', or 'invite'
        display_name: Human-readable name
        description: Description for users
        allowed_record_types: List of allowed record types (None = all)
        allowed_operations: List of allowed operations (None = all)
    
    Returns:
        Created ManagedDomainRoot
    """
    visibility_enum = get_or_create_visibility(visibility)
    
    root = ManagedDomainRoot(
        backend_service_id=backend_service.id,
        root_domain=root_domain,
        dns_zone=dns_zone or root_domain,
        visibility_id=visibility_enum.id,
        display_name=display_name or root_domain,
        description=description,
        is_active=True,
        verified_at=datetime.utcnow(),
    )
    
    if allowed_record_types:
        root.set_allowed_record_types(allowed_record_types)
    if allowed_operations:
        root.set_allowed_operations(allowed_operations)
    
    db.session.add(root)
    db.session.commit()
    logger.info(f"Created domain root: {root_domain} (backend: {backend_service.service_name})")
    return root


def seed_demo_domain_roots() -> tuple[BackendService, ManagedDomainRoot]:
    """Seed demo backend and domain root for testing.
    
    Creates a mock netcup backend and a public domain root at dyn.example.com
    that users can request subdomains under.
    
    Returns:
        Tuple of (demo_backend, demo_domain_root)
    """
    # Check if demo backend already exists
    existing_service = BackendService.query.filter_by(service_name='demo-netcup').first()
    
    if existing_service:
        # Service exists - check if domain root also exists
        existing_root = ManagedDomainRoot.query.filter_by(
            backend_service_id=existing_service.id,
            root_domain='dyn.example.com'
        ).first()
        if existing_root:
            logger.info("Demo domain root already exists, skipping")
            return existing_service, existing_root
        else:
            # Service exists but domain root doesn't - create only the root
            logger.info("Demo backend exists, creating missing domain root")
            demo_root = create_domain_root(
                backend_service=existing_service,
                root_domain='dyn.example.com',
                dns_zone='example.com',
                visibility='public',
                display_name='Demo Dynamic DNS',
                description='Public zone for testing - request any subdomain',
                allowed_record_types=['A', 'AAAA', 'TXT'],
                allowed_operations=['read', 'update'],
            )
            return existing_service, demo_root
    
    # Create demo backend service
    demo_backend = create_backend_service(
        provider_code='netcup',
        service_name='demo-netcup',
        display_name='Demo Netcup Backend',
        config={
            'customer_id': 'demo123456',
            'api_key': 'demo-api-key-mock',
            'api_password': 'demo-api-password-mock',
        },
        owner_type='platform',
        is_active=True,
    )
    
    # Create public domain root for testing
    demo_root = create_domain_root(
        backend_service=demo_backend,
        root_domain='dyn.example.com',
        dns_zone='example.com',
        visibility='public',
        display_name='Demo Dynamic DNS',
        description='Public zone for testing - request any subdomain',
        allowed_record_types=['A', 'AAAA', 'TXT'],
        allowed_operations=['read', 'update'],
    )
    
    logger.info("Demo backend and domain root created for testing")
    return demo_backend, demo_root


# ============================================================================
# Delegated Zone Seeding (D-007)
# ============================================================================

# Fixed service name for the BackendService fronting the operator-delegated
# PowerDNS zone. Deliberately distinct from 'platform-powerdns' (the legacy
# app-config.toml [platform_backends] path in bootstrap/platform_backends.py
# -> setup_platform_powerdns()) so the two seeding paths can never collide if
# both are ever exercised against the same database.
DELEGATED_ZONE_BACKEND_SERVICE_NAME = "delegated-powerdns"


def seed_delegated_zone_domain_root(
    zone: str,
    *,
    api_url: str | None = None,
    api_key: str | None = None,
) -> ManagedDomainRoot | None:
    """Idempotently offer the operator-delegated PowerDNS zone as a manageable
    domain root (D-007, nyxloom-trove/decisions.md).

    Ensures exactly one platform-owned PowerDNS ``BackendService`` pointing at
    the INTERNAL PowerDNS API (app-to-app, inside the docker network — never
    the public/traefik URL), and one ``ManagedDomainRoot`` for ``zone`` bound
    to that service, so a user/system owns the zone and can create hosts
    (subdomains) under it.

    No-op when ``zone`` is empty — the committed default before an operator
    sets NAF_DELEGATED_DNS_ZONE (see ciu.global.defaults.toml.j2
    [topology.dns].delegated_zone) — and idempotent (no-op) when the
    BackendService/ManagedDomainRoot rows already exist.

    MULTI-DOMAIN note: one PowerDNS instance can serve MANY zones. This
    function deliberately keys the BackendService by a FIXED service name
    (not per-zone) and the ManagedDomainRoot by (backend_service_id,
    root_domain) — the same BackendService row can grow additional
    ManagedDomainRoot rows for further zones later, once naf can create zones
    itself via the pdns HTTP API (the backends/ wire-up, D-002(a)/naf-P20).
    This function only ever establishes the ONE dev/test root for the
    currently-delegated zone; it does not assume there is only ever one.

    Visibility is 'private' (VisibilityEnum.PRIVATE) — the same default
    create_domain_root() already uses when a caller doesn't override it, and
    matches ManagedDomainRoot's own docstring ("admin-controlled zone").
    Granting specific users access is DomainRootGrant, out of scope here.

    Args:
        zone: The delegated DNS zone (e.g. 'managed.vxxu.de'). Callers read
            this from config["topology"]["dns"]["delegated_zone"].
        api_url: PowerDNS API URL to store in the backend config. Defaults to
            POWERDNS_API_URL_INTERNAL from the environment (see
            .env.services) — overridable so callers/tests don't need to touch
            the environment.
        api_key: PowerDNS API key. Defaults to POWERDNS_API_KEY from the
            environment — overridable for the same reason.

    Returns:
        The (possibly pre-existing) ManagedDomainRoot, or None if zone is empty.

    Raises:
        RuntimeError: zone is non-empty but api_url/api_key cannot be
            resolved from either the arguments or the environment. This seed
            never invents DNS backend credentials (the D-007 lesson).
    """
    zone = (zone or "").strip().rstrip(".")
    if not zone:
        logger.info(
            "delegated_zone is empty (NAF_DELEGATED_DNS_ZONE not set) — "
            "skipping delegated-zone domain-root seed (no-op)"
        )
        return None

    api_url = api_url or os.environ.get("POWERDNS_API_URL_INTERNAL")
    api_key = api_key or os.environ.get("POWERDNS_API_KEY")
    if not api_url or not api_key:
        raise RuntimeError(
            f"Cannot seed delegated-zone domain root for '{zone}': "
            "POWERDNS_API_URL_INTERNAL and POWERDNS_API_KEY must both be "
            "resolvable (explicit args or environment) — see .env.services / "
            "POWERDNS_API_KEY in .env. Not invented (D-007)."
        )

    service = BackendService.query.filter_by(
        service_name=DELEGATED_ZONE_BACKEND_SERVICE_NAME
    ).first()
    if not service:
        service = create_backend_service(
            provider_code="powerdns",
            service_name=DELEGATED_ZONE_BACKEND_SERVICE_NAME,
            display_name="Delegated PowerDNS Backend",
            config={"api_url": api_url, "api_key": api_key, "server_id": "localhost"},
            owner_type=OwnerTypeEnum.PLATFORM,
            is_active=True,
        )
        logger.info("Created delegated PowerDNS backend service (id=%s)", service.id)
    else:
        logger.info("Delegated PowerDNS backend service already exists (id=%s)", service.id)

    existing_root = ManagedDomainRoot.query.filter_by(
        backend_service_id=service.id,
        root_domain=zone,
    ).first()
    if existing_root:
        logger.info("Domain root for delegated zone '%s' already exists", zone)
        return existing_root

    root = create_domain_root(
        backend_service=service,
        root_domain=zone,
        dns_zone=zone,
        visibility=VisibilityEnum.PRIVATE,
        display_name=f"Delegated zone: {zone}",
        description=(
            "Operator-delegated DNS zone (D-007), authoritative in the "
            "app-local PowerDNS backend. Seeded so a user/system owns the "
            "root and can create hosts (subdomains) under it."
        ),
    )
    logger.info("Created delegated-zone domain root: %s", zone)
    return root
