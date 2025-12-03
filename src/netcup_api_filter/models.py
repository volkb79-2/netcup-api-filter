"""
Database models for netcup-api-filter (Account → Realms → Tokens architecture)

This module defines the three-tier permission hierarchy:
- Account: Human users who log into the UI
- AccountRealm: What domains/subdomains an account can access
- APIToken: Machine credentials scoped to a realm

Token Format: naf_<username>_<random64>
  - username: 8-32 chars, lowercase alphanumeric + hyphen
  - random: 64 chars, [a-zA-Z0-9]
  - Total: 77-101 characters
  - Entropy: ~381 bits

Authentication: Bearer token only for API, bcrypt hashed storage
"""
import json
import logging
import re
import secrets
from datetime import datetime
from typing import Any, Optional

import bcrypt
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint

logger = logging.getLogger(__name__)

# Database instance (shared with database.py during migration)
db = SQLAlchemy()

# Token format constants
TOKEN_PREFIX = "naf_"
USERNAME_MIN_LENGTH = 8
USERNAME_MAX_LENGTH = 32
RANDOM_PART_LENGTH = 64
TOKEN_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

# Username validation pattern
USERNAME_PATTERN = re.compile(r'^[a-z][a-z0-9-]{6,30}[a-z0-9]$')

# Token parsing pattern
TOKEN_PATTERN = re.compile(
    rf'^{TOKEN_PREFIX}([a-z][a-z0-9-]{{6,30}}[a-z0-9])_([a-zA-Z0-9]{{{RANDOM_PART_LENGTH}}})$'
)

# Reserved usernames (cannot be registered)
RESERVED_USERNAMES = frozenset({
    'admin', 'root', 'system', 'api', 'naf', 'test',
    'administrator', 'superuser', 'operator', 'support',
})


def validate_username(username: str) -> tuple[bool, str | None]:
    """
    Validate username format.
    
    Rules:
    - 8-32 characters
    - Lowercase letters, numbers, hyphens
    - Must start with letter
    - Cannot end with hyphen
    - Cannot be reserved
    
    Returns:
        (is_valid, error_message)
    """
    if not username:
        return False, "Username is required"
    
    if len(username) < USERNAME_MIN_LENGTH:
        return False, f"Username must be at least {USERNAME_MIN_LENGTH} characters"
    
    if len(username) > USERNAME_MAX_LENGTH:
        return False, f"Username cannot exceed {USERNAME_MAX_LENGTH} characters"
    
    if username.lower() in RESERVED_USERNAMES:
        return False, "This username is reserved"
    
    if not USERNAME_PATTERN.match(username):
        return False, "Username must start with a letter, contain only lowercase letters, numbers, and hyphens, and not end with a hyphen"
    
    return True, None


def generate_token(username: str) -> str:
    """
    Generate a new API token for the given username.
    
    Format: naf_<username>_<random64>
    
    Returns:
        Full token string (store hash, show once to user)
    """
    random_part = ''.join(secrets.choice(TOKEN_ALPHABET) for _ in range(RANDOM_PART_LENGTH))
    return f"{TOKEN_PREFIX}{username}_{random_part}"


def parse_token(token: str) -> tuple[str, str] | None:
    """
    Parse token into (username, random_part) or None if invalid format.
    
    This allows routing/logging before database lookup.
    """
    if not token:
        return None
    
    match = TOKEN_PATTERN.match(token)
    if not match:
        return None
    
    return match.group(1), match.group(2)


def hash_token(token: str) -> str:
    """Hash a token with bcrypt for storage.
    
    Since tokens can be > 72 bytes (bcrypt limit), we pre-hash with SHA256.
    This is a standard pattern for long passwords/tokens.
    """
    import hashlib
    # Pre-hash with SHA256 to handle long tokens (tokens are 77-101 chars)
    token_sha = hashlib.sha256(token.encode('utf-8')).hexdigest()
    return bcrypt.hashpw(token_sha.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_token_hash(token: str, token_hash: str) -> bool:
    """Verify a token against its bcrypt hash."""
    import hashlib
    try:
        # Pre-hash with SHA256 (same as hash_token)
        token_sha = hashlib.sha256(token.encode('utf-8')).hexdigest()
        return bcrypt.checkpw(token_sha.encode('utf-8'), token_hash.encode('utf-8'))
    except (ValueError, TypeError):
        return False


class Account(db.Model):
    """
    User account (human who logs into UI).
    
    Each account can have multiple realms and tokens.
    Accounts require email verification and admin approval.
    """
    __tablename__ = 'accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    email_verified = db.Column(db.Integer, default=0)
    password_hash = db.Column(db.String(255), nullable=False)
    
    # 2FA (email mandatory, others optional)
    totp_secret = db.Column(db.String(32))  # NULL = TOTP not enabled
    totp_enabled = db.Column(db.Integer, default=0)
    email_2fa_enabled = db.Column(db.Integer, default=1)  # Mandatory
    telegram_chat_id = db.Column(db.String(64))  # NULL = Telegram not linked
    telegram_enabled = db.Column(db.Integer, default=0)
    
    # Recovery codes (JSON array of hashed codes, NULL = not generated)
    recovery_codes = db.Column(db.Text)  # JSON: ["hash1", "hash2", ...]
    recovery_codes_generated_at = db.Column(db.DateTime)
    
    # Notifications (separate from login email)
    notification_email = db.Column(db.String(255))  # Optional, for alerts
    notify_new_ip = db.Column(db.Integer, default=1)
    notify_failed_auth = db.Column(db.Integer, default=1)
    notify_successful_auth = db.Column(db.Integer, default=0)
    notify_token_expiring = db.Column(db.Integer, default=1)
    notify_realm_status = db.Column(db.Integer, default=1)
    
    # Status
    is_active = db.Column(db.Integer, default=0)  # Requires admin approval
    is_admin = db.Column(db.Integer, default=0)
    must_change_password = db.Column(db.Integer, default=0)  # Force password change on next login
    approved_by_id = db.Column(db.Integer, db.ForeignKey('accounts.id'))
    approved_at = db.Column(db.DateTime)
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = db.Column(db.DateTime)
    
    # Relationships
    realms = db.relationship('AccountRealm', back_populates='account', cascade='all, delete-orphan',
                             foreign_keys='AccountRealm.account_id')
    approved_by = db.relationship('Account', remote_side=[id], foreign_keys=[approved_by_id])
    
    __table_args__ = (
        CheckConstraint(
            'email_2fa_enabled = 1 OR totp_enabled = 1 OR telegram_enabled = 1',
            name='check_2fa_enabled'
        ),
    )
    
    def set_password(self, password: str):
        """Hash and set password."""
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    def verify_password(self, password: str) -> bool:
        """Verify password against hash."""
        try:
            return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))
        except (ValueError, TypeError):
            return False
    
    def __repr__(self):
        return f'<Account {self.username}>'


class AccountRealm(db.Model):
    """
    Realm (what domains/subdomains an account can access).
    
    Realm Types:
    - host: Exact match only (e.g., vpn.example.com)
    - subdomain: Apex + all children (e.g., iot.example.com, device.iot.example.com)
    - subdomain_only: Children only, NOT apex (e.g., host1.client.vxxu.de)
    
    Structure:
    - domain: The base domain (e.g., example.com)
    - realm_type: How matching is done
    - realm_value: The specific host/subdomain prefix (e.g., "iot", "vpn", or empty for apex)
    """
    __tablename__ = 'account_realms'
    
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False, index=True)
    
    domain = db.Column(db.String(255), nullable=False, index=True)  # Base domain (e.g., example.com)
    realm_type = db.Column(db.String(20), nullable=False)  # 'host', 'subdomain', 'subdomain_only'
    realm_value = db.Column(db.String(255), nullable=False)  # Prefix/host portion (e.g., 'iot', 'vpn', '')
    
    allowed_record_types = db.Column(db.Text, nullable=False)  # JSON array
    allowed_operations = db.Column(db.Text, nullable=False)  # JSON array
    
    # Request/approval workflow
    status = db.Column(db.String(20), default='pending')  # 'pending', 'approved', 'rejected'
    requested_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    approved_by_id = db.Column(db.Integer, db.ForeignKey('accounts.id'))
    approved_at = db.Column(db.DateTime)
    rejection_reason = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    account = db.relationship('Account', back_populates='realms', foreign_keys=[account_id])
    approved_by = db.relationship('Account', foreign_keys=[approved_by_id])
    tokens = db.relationship('APIToken', back_populates='realm', cascade='all, delete-orphan')
    
    __table_args__ = (
        db.UniqueConstraint('account_id', 'domain', 'realm_type', 'realm_value', name='uq_account_realm'),
        CheckConstraint("realm_type IN ('host', 'subdomain', 'subdomain_only')", name='check_realm_type'),
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name='check_realm_status'),
    )
    
    def get_allowed_record_types(self) -> list[str]:
        """Parse allowed_record_types from JSON."""
        try:
            return json.loads(self.allowed_record_types) if self.allowed_record_types else []
        except (json.JSONDecodeError, TypeError):
            logger.error(f"Failed to parse allowed_record_types for realm {self.id}")
            return []
    
    def set_allowed_record_types(self, types: list[str]):
        """Set allowed_record_types as JSON."""
        self.allowed_record_types = json.dumps(types)
    
    def get_allowed_operations(self) -> list[str]:
        """Parse allowed_operations from JSON."""
        try:
            return json.loads(self.allowed_operations) if self.allowed_operations else []
        except (json.JSONDecodeError, TypeError):
            logger.error(f"Failed to parse allowed_operations for realm {self.id}")
            return []
    
    def set_allowed_operations(self, operations: list[str]):
        """Set allowed_operations as JSON."""
        self.allowed_operations = json.dumps(operations)
    
    def get_fqdn(self) -> str:
        """
        Get the fully qualified domain name for this realm.
        
        Returns:
            FQDN like 'iot.example.com' or 'example.com' (if realm_value is empty)
        """
        if self.realm_value:
            return f"{self.realm_value}.{self.domain}"
        return self.domain
    
    def matches_hostname(self, hostname: str) -> bool:
        """
        Check if a hostname matches this realm.
        
        Args:
            hostname: Hostname to check (e.g., device1.iot.example.com)
        
        Returns:
            True if hostname is within realm scope
        """
        hostname_lower = hostname.lower()
        fqdn_lower = self.get_fqdn().lower()
        
        if self.realm_type == 'host':
            # Exact match only
            return hostname_lower == fqdn_lower
        
        elif self.realm_type == 'subdomain':
            # Apex + all children
            return hostname_lower == fqdn_lower or hostname_lower.endswith('.' + fqdn_lower)
        
        elif self.realm_type == 'subdomain_only':
            # Children only, NOT apex
            return hostname_lower.endswith('.' + fqdn_lower) and hostname_lower != fqdn_lower
        
        logger.warning(f"Unknown realm_type: {self.realm_type}")
        return False
    
    def matches_domain(self, domain: str) -> bool:
        """
        Check if a domain (zone) matches this realm's authorized domain.
        
        This is used to verify API calls are targeting the correct DNS zone.
        The realm must be for the same domain that's being accessed.
        
        Args:
            domain: Domain/zone being accessed (e.g., example.com)
        
        Returns:
            True if the realm authorizes access to this domain
        """
        return domain.lower() == self.domain.lower()
    
    def __repr__(self):
        return f'<AccountRealm {self.domain}:{self.realm_type}:{self.realm_value}>'


class APIToken(db.Model):
    """
    API Token (machine credentials scoped to a realm).
    
    Tokens are created by users for their approved realms.
    Each token can have restricted scope (subset of realm permissions).
    """
    __tablename__ = 'api_tokens'
    
    id = db.Column(db.Integer, primary_key=True)
    realm_id = db.Column(db.Integer, db.ForeignKey('account_realms.id', ondelete='CASCADE'), nullable=False, index=True)
    
    token_name = db.Column(db.String(64), nullable=False)  # Human label: "aws-lambda-updater"
    token_description = db.Column(db.Text)  # "Updates host1 A record from AWS"
    token_prefix = db.Column(db.String(8), nullable=False, index=True)  # First 8 chars for lookup
    token_hash = db.Column(db.String(255), nullable=False)  # bcrypt(full_token)
    
    # Scope restrictions (subset of realm permissions, NULL = inherit)
    allowed_record_types = db.Column(db.Text)  # JSON array, NULL = use realm's
    allowed_operations = db.Column(db.Text)  # JSON array, NULL = use realm's
    allowed_ip_ranges = db.Column(db.Text)  # JSON array, NULL = no restriction
    
    # Lifecycle
    expires_at = db.Column(db.DateTime)  # NULL = never
    last_used_at = db.Column(db.DateTime)
    last_used_ip = db.Column(db.String(45))
    use_count = db.Column(db.Integer, default=0)
    
    # Status
    is_active = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    revoked_at = db.Column(db.DateTime)
    revoked_reason = db.Column(db.Text)
    
    # Relationships
    realm = db.relationship('AccountRealm', back_populates='tokens')
    activity = db.relationship('ActivityLog', back_populates='token', cascade='all, delete-orphan')
    
    __table_args__ = (
        db.UniqueConstraint('realm_id', 'token_name', name='uq_realm_token_name'),
    )
    
    def get_allowed_record_types(self) -> list[str] | None:
        """Parse allowed_record_types from JSON. Returns None if not restricted."""
        if self.allowed_record_types is None:
            return None
        try:
            return json.loads(self.allowed_record_types)
        except (json.JSONDecodeError, TypeError):
            return None
    
    def set_allowed_record_types(self, types: list[str] | None):
        """Set allowed_record_types as JSON."""
        self.allowed_record_types = json.dumps(types) if types else None
    
    def get_allowed_operations(self) -> list[str] | None:
        """Parse allowed_operations from JSON. Returns None if not restricted."""
        if self.allowed_operations is None:
            return None
        try:
            return json.loads(self.allowed_operations)
        except (json.JSONDecodeError, TypeError):
            return None
    
    def set_allowed_operations(self, operations: list[str] | None):
        """Set allowed_operations as JSON."""
        self.allowed_operations = json.dumps(operations) if operations else None
    
    def get_allowed_ip_ranges(self) -> list[str]:
        """Parse allowed_ip_ranges from JSON."""
        if self.allowed_ip_ranges is None:
            return []
        try:
            return json.loads(self.allowed_ip_ranges)
        except (json.JSONDecodeError, TypeError):
            return []
    
    def set_allowed_ip_ranges(self, ranges: list[str] | None):
        """Set allowed_ip_ranges as JSON."""
        self.allowed_ip_ranges = json.dumps(ranges) if ranges else None
    
    def get_effective_record_types(self) -> list[str]:
        """Get effective record types (token-level or fall back to realm)."""
        types = self.get_allowed_record_types()
        if types is not None:
            return types
        return self.realm.get_allowed_record_types()
    
    def get_effective_operations(self) -> list[str]:
        """Get effective operations (token-level or fall back to realm)."""
        ops = self.get_allowed_operations()
        if ops is not None:
            return ops
        return self.realm.get_allowed_operations()
    
    def is_expired(self) -> bool:
        """Check if token has expired."""
        if self.expires_at is None:
            return False
        return self.expires_at < datetime.utcnow()
    
    def record_usage(self, ip_address: str):
        """Record token usage (call after successful auth)."""
        self.last_used_at = datetime.utcnow()
        self.last_used_ip = ip_address
        self.use_count = (self.use_count or 0) + 1
    
    def verify(self, full_token: str) -> bool:
        """Verify token against stored hash."""
        return verify_token_hash(full_token, self.token_hash)
    
    def __repr__(self):
        return f'<APIToken {self.token_name}>'


class ActivityLog(db.Model):
    """
    Activity log (per-token audit trail).
    
    Records all API calls, login attempts, and administrative actions.
    """
    __tablename__ = 'activity_log'
    
    id = db.Column(db.Integer, primary_key=True)
    token_id = db.Column(db.Integer, db.ForeignKey('api_tokens.id', ondelete='SET NULL'), index=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id', ondelete='SET NULL'), index=True)
    
    action = db.Column(db.String(50), nullable=False, index=True)  # 'api_call', 'login', 'token_created', etc.
    operation = db.Column(db.String(20))  # 'read', 'update', 'create', 'delete'
    
    realm_type = db.Column(db.String(20))
    realm_value = db.Column(db.String(255))
    record_type = db.Column(db.String(10))
    record_name = db.Column(db.String(255))
    
    source_ip = db.Column(db.String(45), nullable=False, index=True)
    user_agent = db.Column(db.Text)
    
    status = db.Column(db.String(20), nullable=False, index=True)  # 'success', 'denied', 'error'
    status_reason = db.Column(db.Text)  # "IP not whitelisted", "Token expired"
    
    request_data = db.Column(db.Text)  # JSON: sanitized request details
    response_summary = db.Column(db.Text)  # JSON: result summary
    
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # Relationships
    token = db.relationship('APIToken', back_populates='activity')
    account = db.relationship('Account')
    
    def get_request_data(self) -> dict[str, Any]:
        """Parse request_data from JSON."""
        try:
            return json.loads(self.request_data) if self.request_data else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_request_data(self, data: dict[str, Any]):
        """Set request_data as JSON (with sensitive data masked)."""
        if data:
            masked_data = data.copy()
            # Mask sensitive fields
            for key in ['password', 'token', 'apipassword', 'apisessionid', 'apikey']:
                if key in masked_data:
                    masked_data[key] = '***MASKED***'
                if 'param' in masked_data and isinstance(masked_data['param'], dict):
                    if key in masked_data['param']:
                        masked_data['param'][key] = '***MASKED***'
            self.request_data = json.dumps(masked_data)
        else:
            self.request_data = None
    
    def get_response_summary(self) -> dict[str, Any]:
        """Parse response_summary from JSON."""
        try:
            return json.loads(self.response_summary) if self.response_summary else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_response_summary(self, data: dict[str, Any]):
        """Set response_summary as JSON."""
        self.response_summary = json.dumps(data) if data else None
    
    def __repr__(self):
        return f'<ActivityLog {self.action} {self.status} {self.created_at}>'


class RegistrationRequest(db.Model):
    """
    Pending registration (before email verification).
    
    Records are deleted after successful verification (account is created).
    """
    __tablename__ = 'registration_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    
    verification_code = db.Column(db.String(6), nullable=False)
    verification_expires_at = db.Column(db.DateTime, nullable=False)
    verification_attempts = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        CheckConstraint('verification_attempts <= 5', name='check_max_verification_attempts'),
    )
    
    def set_password(self, password: str):
        """Hash and set password."""
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    def is_expired(self) -> bool:
        """Check if verification code has expired."""
        return self.verification_expires_at < datetime.utcnow()
    
    def is_locked(self) -> bool:
        """Check if too many verification attempts."""
        return self.verification_attempts >= 5
    
    def __repr__(self):
        return f'<RegistrationRequest {self.username}>'


class Settings(db.Model):
    """
    System settings key-value store.
    
    Stores configuration like Netcup API credentials, SMTP settings, etc.
    """
    __tablename__ = 'settings'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text)  # JSON
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def get_value(self) -> Any:
        """Parse value from JSON."""
        try:
            return json.loads(self.value) if self.value else None
        except (json.JSONDecodeError, TypeError):
            return None
    
    def set_value(self, data: Any):
        """Set value as JSON."""
        self.value = json.dumps(data) if data is not None else None
    
    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        """Get a settings value by key."""
        setting = cls.query.filter_by(key=key).first()
        if setting:
            return setting.get_value()
        return default
    
    @classmethod
    def set(cls, key: str, value: Any) -> 'Settings':
        """Set a settings value by key (creates or updates)."""
        setting = cls.query.filter_by(key=key).first()
        if setting:
            setting.set_value(value)
        else:
            setting = cls(key=key)
            setting.set_value(value)
            db.session.add(setting)
        db.session.commit()
        return setting
    
    @classmethod
    def delete(cls, key: str) -> bool:
        """Delete a settings key. Returns True if deleted."""
        setting = cls.query.filter_by(key=key).first()
        if setting:
            db.session.delete(setting)
            db.session.commit()
            return True
        return False
    
    def __repr__(self):
        return f'<Settings {self.key}>'


# Compatibility aliases for migration
SystemConfig = Settings
