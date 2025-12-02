"""
Reusable helpers for seeding default admin and demo accounts.

Updated for Account → Realms → Tokens architecture.
"""
from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Sequence, Tuple

from ..models import (
    Account,
    AccountRealm,
    ActivityLog,
    APIToken,
    db,
    generate_token,
    hash_token,
    validate_username,
)
from ..config_defaults import get_default, load_defaults, require_default

logger = logging.getLogger(__name__)

_ENV_DEFAULTS = load_defaults()


@dataclass
class AdminSeedOptions:
    """Options for seeding admin account."""
    username: str = None
    password: str = None
    email: str = None
    must_change_password: bool = True
    
    def __post_init__(self):
        if self.username is None:
            self.username = require_default("DEFAULT_ADMIN_USERNAME")
        if self.password is None:
            self.password = require_default("DEFAULT_ADMIN_PASSWORD")
        if self.email is None:
            self.email = get_default("DEFAULT_ADMIN_EMAIL", "admin@localhost")


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
ClientSeedOptions = TokenSeedOptions


def ensure_admin_account(options: AdminSeedOptions) -> Account:
    """Create or update admin account.
    
    Returns:
        The admin Account object
    """
    account = Account.query.filter_by(username=options.username).first()
    if not account:
        account = Account(
            username=options.username,
            email=options.email,
            email_verified=1,
            email_2fa_enabled=1,
            is_active=1,
            is_admin=1,
            approved_at=datetime.utcnow()
        )
        account.set_password(options.password)
        account.must_change_password = 1 if options.must_change_password else 0
        db.session.add(account)
        logger.info(f"Created admin account: {options.username}")
    else:
        logger.info(f"Admin account {options.username} already exists, keeping existing settings")
    return account


# Backwards compatibility alias
ensure_admin_user = ensure_admin_account


def ensure_account(options: DemoAccountSeedOptions, approved_by: Account = None) -> Account:
    """Create or update a user account.
    
    Returns:
        The Account object
    """
    account = Account.query.filter_by(username=options.username).first()
    if not account:
        account = Account(
            username=options.username,
            email=options.email,
            email_verified=1,
            email_2fa_enabled=1,
            is_active=1,
            is_admin=0,
            approved_by_id=approved_by.id if approved_by else None,
            approved_at=datetime.utcnow()
        )
        account.set_password(options.password)
        db.session.add(account)
        logger.info(f"Created account: {options.username}")
    else:
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


def ensure_token(realm: AccountRealm, options: TokenSeedOptions) -> Tuple[APIToken, str]:
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
    
    # Generate token
    account = realm.account
    full_token = generate_token(account.username)
    
    # Extract prefix (first 8 chars of random part)
    random_part_start = len(f"naf_{account.username}_")
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
def ensure_client(options):
    """Legacy compatibility stub. New schema uses ensure_account + ensure_realm + ensure_token."""
    logger.warning("ensure_client() is deprecated - use ensure_account/ensure_realm/ensure_token instead")
    return None


def generate_test_client_credentials() -> Tuple[str, str]:
    """Generate secure random credentials for test account.
    
    Returns:
        Tuple of (username, token)
    """
    # Generate random username suffix
    random_suffix = secrets.token_urlsafe(6)[:8].lower()
    username = f"test_{random_suffix}"
    
    # For new schema, token is generated when creating the actual token
    # This returns a placeholder password for the account
    password = secrets.token_urlsafe(16)
    
    return username, password


def create_default_test_client_options() -> TokenSeedOptions:
    """Create default test token options."""
    return TokenSeedOptions(
        token_name="test-token",
        description=_ENV_DEFAULTS.get("DEFAULT_TEST_CLIENT_DESCRIPTION", "Sample read-only token"),
    )


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


def seed_default_entities(
    admin_options: AdminSeedOptions | None = None,
    client_options = None,  # Ignored for backwards compat
    seed_demo_clients_flag: bool = False,
) -> Tuple[str | None, str | None, list]:
    """Seed default admin and optionally demo accounts.
    
    Args:
        admin_options: Optional admin account configuration
        client_options: Ignored (backwards compatibility)
        seed_demo_clients_flag: Whether to seed demo accounts
    
    Returns:
        Tuple of (primary_client_id, primary_secret_key, all_demo_clients)
    """
    # Ensure admin account exists
    admin = ensure_admin_account(admin_options or AdminSeedOptions())
    db.session.commit()
    
    all_demo_clients: list[Tuple[str, str, str]] = []
    primary_client_id = None
    primary_secret = None
    
    if seed_demo_clients_flag:
        # Get demo account config from env/defaults
        demo_username = os.environ.get('DEFAULT_TEST_CLIENT_ID') or get_default('DEFAULT_TEST_CLIENT_ID', 'demo-user')
        
        # Validate username format
        is_valid, error = validate_username(demo_username)
        if not is_valid:
            # Generate valid username
            demo_username = f"demouser{secrets.token_urlsafe(4)[:4].lower()}"
            logger.warning(f"Demo username invalid, using generated: {demo_username}")
        
        demo_password = "DemoPassword123!"
        
        # Parse realm config
        realm_fqdn = os.environ.get('DEFAULT_TEST_CLIENT_REALM_VALUE') or get_default('DEFAULT_TEST_CLIENT_REALM_VALUE', 'example.com')
        realm_type = os.environ.get('DEFAULT_TEST_CLIENT_REALM_TYPE') or get_default('DEFAULT_TEST_CLIENT_REALM_TYPE', 'host')
        
        # Extract domain from FQDN
        fqdn_parts = realm_fqdn.split('.')
        if len(fqdn_parts) > 2:
            realm_value = '.'.join(fqdn_parts[:-2])
            domain = '.'.join(fqdn_parts[-2:])
        else:
            realm_value = ''
            domain = realm_fqdn
        
        record_types_str = os.environ.get('DEFAULT_TEST_CLIENT_RECORD_TYPES') or get_default('DEFAULT_TEST_CLIENT_RECORD_TYPES', 'A,AAAA')
        record_types = [rt.strip() for rt in record_types_str.split(',')]
        
        operations_str = os.environ.get('DEFAULT_TEST_CLIENT_OPERATIONS') or get_default('DEFAULT_TEST_CLIENT_OPERATIONS', 'read')
        operations = [op.strip() for op in operations_str.split(',')]
        
        # Create demo account options
        demo_options = DemoAccountSeedOptions(
            username=demo_username,
            password=demo_password,
            email=f"{demo_username}@example.com",
            realm=RealmSeedOptions(
                domain=domain,
                realm_type=realm_type,
                realm_value=realm_value,
                record_types=record_types,
                operations=operations
            ),
            token=TokenSeedOptions(
                token_name='primary-token',
                description='Primary demo token'
            )
        )
        
        # Create account
        demo_account = ensure_account(demo_options, approved_by=admin)
        db.session.flush()
        
        # Create realm
        realm = ensure_realm(demo_account, demo_options.realm, approved_by=admin)
        db.session.flush()
        
        # Create token
        token, plain_token = ensure_token(realm, demo_options.token)
        db.session.commit()
        
        if plain_token:
            primary_client_id = demo_username
            primary_secret = plain_token
            all_demo_clients.append((demo_username, plain_token, "Primary demo account"))
            logger.info(f"Created demo account: {demo_username} with token")
        
        # Seed demo activity logs
        seed_demo_audit_logs(demo_account)
    
    return primary_client_id, primary_secret, all_demo_clients


def seed_from_config(config: dict) -> None:
    """Apply structured config to the database.
    
    This is for backwards compatibility - new schema uses database Settings.
    """
    from ..models import Settings
    import json
    
    netcup_config = config.get("netcup")
    if netcup_config:
        logger.info("Applying Netcup API configuration from config")
        setting = Settings.query.filter_by(key="netcup_config").first()
        if not setting:
            setting = Settings(key="netcup_config")
            db.session.add(setting)
        setting.value = json.dumps({
            "customer_id": netcup_config.get("customer_id", ""),
            "api_key": netcup_config.get("api_key", ""),
            "api_password": netcup_config.get("api_password", ""),
            "api_url": netcup_config.get(
                "api_url",
                "https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON",
            ),
            "timeout": int(netcup_config.get("timeout", 30)),
        })
        db.session.commit()
    
    # Legacy token import not supported - use admin UI instead
    tokens = config.get("tokens", [])
    if tokens:
        logger.warning("Token import from config not supported in new schema - use admin UI")
