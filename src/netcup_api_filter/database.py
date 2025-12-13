"""
Database initialization for the Account → Realms → Tokens architecture.

This module provides:
- Database initialization with new schema
- Seed functions for default admin account
- Migration helpers

The new schema replaces the old Client model with:
- Account: Human users
- AccountRealm: Domain access permissions
- APIToken: Machine credentials
- ActivityLog: Audit trail
- RegistrationRequest: Pending registrations
- Settings: Key-value configuration
"""
import logging
import os
from datetime import datetime
from typing import Any

from .config_defaults import get_default, require_default

# Import all models to ensure they're registered with SQLAlchemy
from .models import (
    Account,
    AccountRealm,
    ActivityLog,
    APIToken,
    db,
    generate_token,
    generate_user_alias,
    hash_token,
    RegistrationRequest,
    Settings,
    validate_username,
    # Multi-backend models
    BackendProvider,
    BackendService,
    ManagedDomainRoot,
    DomainRootGrant,
    OwnerTypeEnum,
    VisibilityEnum,
    TestStatusEnum,
    GrantTypeEnum,
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
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_size': 10,
        'pool_recycle': 3600,
        'pool_pre_ping': True,
    }
    
    db.init_app(app)
    
    with app.app_context():
        # Create all tables from models
        db.create_all()
        logger.info("Database tables created/verified")
        
        # Seed multi-backend infrastructure (enum tables + providers)
        seed_multi_backend_infrastructure()
        
        # Seed default admin account
        seed_admin_account()
        
        # Optionally seed demo data
        seed_demo = os.environ.get('SEED_DEMO_ACCOUNTS', '').lower() in {'1', 'true', 'yes'}
        if seed_demo:
            seed_demo_accounts()
            logger.info("Demo accounts seeded")


def seed_admin_account():
    """
    Seed default admin account if it doesn't exist.
    
    Reads credentials from environment or .env.defaults.
    """
    admin_username = os.environ.get('DEFAULT_ADMIN_USERNAME') or get_default('DEFAULT_ADMIN_USERNAME', 'admin')
    admin_password = os.environ.get('DEFAULT_ADMIN_PASSWORD') or require_default('DEFAULT_ADMIN_PASSWORD')
    admin_email = os.environ.get('DEFAULT_ADMIN_EMAIL') or get_default('DEFAULT_ADMIN_EMAIL', 'admin@localhost')
    
    # Check if admin already exists
    existing = Account.query.filter_by(username=admin_username).first()
    if existing:
        logger.debug(f"Admin account '{admin_username}' already exists")
        return
    
    # Generate unique user_alias for token attribution
    admin_alias = generate_user_alias()
    
    # Create admin account
    admin = Account(
        username=admin_username,
        user_alias=admin_alias,
        email=admin_email,
        email_verified=1,
        email_2fa_enabled=1,  # Email 2FA mandatory
        is_active=1,
        is_admin=1,
        approved_at=datetime.utcnow()
    )
    admin.set_password(admin_password)
    
    db.session.add(admin)
    db.session.commit()
    
    logger.info(f"Admin account created: {admin_username} (alias: {admin_alias[:4]}...)")


def seed_demo_accounts():
    """
    Seed demo accounts for testing.
    
    Creates:
    - A demo user with an approved realm and active token
    - A pending user awaiting approval
    """
    # Demo user with realm and token
    demo_username = os.environ.get('DEFAULT_TEST_CLIENT_ID') or get_default('DEFAULT_TEST_CLIENT_ID', 'demo-user')
    
    # Validate username format for new model
    is_valid, _ = validate_username(demo_username)
    if not is_valid:
        # Fallback to a valid username
        demo_username = 'demo-user'
    
    existing = Account.query.filter_by(username=demo_username).first()
    if existing:
        logger.debug(f"Demo account '{demo_username}' already exists")
        return
    
    # Get admin for approval reference
    admin = Account.query.filter_by(is_admin=1).first()
    if not admin:
        logger.warning("No admin account found for demo seeding")
        return
    
    # Create demo user
    demo_alias = generate_user_alias()
    demo_user = Account(
        username=demo_username,
        user_alias=demo_alias,
        email=f'{demo_username}@example.com',
        email_verified=1,
        email_2fa_enabled=1,
        is_active=1,
        is_admin=0,
        approved_by_id=admin.id,
        approved_at=datetime.utcnow()
    )
    demo_user.set_password('DemoPassword123!')
    
    db.session.add(demo_user)
    db.session.flush()  # Get ID
    
    # Create demo realm
    realm_type = os.environ.get('DEFAULT_TEST_CLIENT_REALM_TYPE') or get_default('DEFAULT_TEST_CLIENT_REALM_TYPE', 'host')
    realm_fqdn = os.environ.get('DEFAULT_TEST_CLIENT_REALM_VALUE') or get_default('DEFAULT_TEST_CLIENT_REALM_VALUE', 'demo.example.com')
    
    # Parse FQDN into domain and realm_value
    # For 'host' type: demo.example.com → domain=example.com, realm_value=demo
    # For apex: example.com → domain=example.com, realm_value=''
    fqdn_parts = realm_fqdn.split('.')
    if len(fqdn_parts) > 2:
        realm_value = '.'.join(fqdn_parts[:-2])  # All parts except last two (subdomain prefix)
        domain = '.'.join(fqdn_parts[-2:])  # Last two parts (base domain)
    else:
        realm_value = ''  # Apex domain
        domain = realm_fqdn
    
    # Parse record types and operations
    record_types_str = os.environ.get('DEFAULT_TEST_CLIENT_RECORD_TYPES') or get_default('DEFAULT_TEST_CLIENT_RECORD_TYPES', 'A,AAAA')
    record_types = [rt.strip() for rt in record_types_str.split(',')]
    
    operations_str = os.environ.get('DEFAULT_TEST_CLIENT_OPERATIONS') or get_default('DEFAULT_TEST_CLIENT_OPERATIONS', 'read')
    operations = [op.strip() for op in operations_str.split(',')]
    
    demo_realm = AccountRealm(
        account_id=demo_user.id,
        domain=domain,
        realm_type=realm_type,
        realm_value=realm_value,
        status='approved',
        requested_at=datetime.utcnow(),
        approved_by_id=admin.id,
        approved_at=datetime.utcnow()
    )
    demo_realm.set_allowed_record_types(record_types)
    demo_realm.set_allowed_operations(operations)
    
    db.session.add(demo_realm)
    db.session.flush()
    
    # Create demo token using user_alias (NOT username)
    token_name = 'demo-token'
    full_token = generate_token(demo_user.user_alias)
    
    # Extract prefix from token (after naf_<user_alias>_)
    from .models import USER_ALIAS_LENGTH, TOKEN_PREFIX
    random_part_start = len(TOKEN_PREFIX) + USER_ALIAS_LENGTH + 1  # +1 for underscore
    token_prefix = full_token[random_part_start:random_part_start + 8]
    
    demo_token = APIToken(
        realm_id=demo_realm.id,
        token_name=token_name,
        token_description='Demo token for testing',
        token_prefix=token_prefix,
        token_hash=hash_token(full_token),
        is_active=1
    )
    
    db.session.add(demo_token)
    db.session.commit()
    
    logger.info(f"Demo account created: {demo_username} (alias: {demo_alias[:4]}...)")
    logger.info(f"Demo token: {full_token}")  # Log for testing purposes


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
    
    db.session.commit()


# Aliases for compatibility during migration
get_system_config = get_setting
set_system_config = set_setting
