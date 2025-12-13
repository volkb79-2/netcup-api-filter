"""
Database models for netcup-api-filter (Account → Realms → Tokens architecture)

This module defines the three-tier permission hierarchy:
- Account: Human users who log into the UI
- AccountRealm: What domains/subdomains an account can access
- APIToken: Machine credentials scoped to a realm

Token Format: naf_<user_alias>_<random64>
  - user_alias: 16-char random identifier (NOT username for security)
  - random: 64 chars, [a-zA-Z0-9]
  - Total: 85 characters
  - Entropy: ~381 bits

Security: user_alias protects username from exposure in API tokens.
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
USER_ALIAS_LENGTH = 16  # Random user identifier in tokens
RANDOM_PART_LENGTH = 64
TOKEN_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

# Username validation (for UI login, NOT for tokens)
# Pattern: ^[a-zA-Z][a-zA-Z0-9-._]{7,31}$
# - 8-32 characters total
# - Must start with a letter (upper or lower)
# - Can contain letters, numbers, hyphens, dots, underscores
# - Case-insensitive for uniqueness checks
USERNAME_MIN_LENGTH = 8
USERNAME_MAX_LENGTH = 32
USERNAME_PATTERN = re.compile(r'^[a-zA-Z][a-zA-Z0-9\-._]{7,31}$')

# User alias pattern (for tokens)
USER_ALIAS_PATTERN = re.compile(rf'^[a-zA-Z0-9]{{{USER_ALIAS_LENGTH}}}$')

# Token parsing pattern: naf_<user_alias>_<random64>
TOKEN_PATTERN = re.compile(
    rf'^{TOKEN_PREFIX}([a-zA-Z0-9]{{{USER_ALIAS_LENGTH}}})_([a-zA-Z0-9]{{{RANDOM_PART_LENGTH}}})$'
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
    - Must start with a letter (upper or lower)
    - Can contain letters, numbers, hyphens, dots, underscores
    - Case-insensitive for uniqueness (stored as-entered, compared lowercase)
    - Cannot be reserved
    
    Pattern: ^[a-zA-Z][a-zA-Z0-9-._]{7,31}$
    
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
        return False, "Username must start with a letter and contain only letters, numbers, hyphens, dots, or underscores"
    
    return True, None


# Password validation
# Pattern: printable ASCII (32-126), min 20 chars, min 100 bits entropy
PASSWORD_MIN_LENGTH = 20
PASSWORD_MIN_ENTROPY = 100  # bits

# Safe printable ASCII: excludes characters that cause shell escaping issues
# Excludes: ! (shell history), ` (command substitution), ' " (quoting), \ (escape)
PASSWORD_ALLOWED_CHARS = set(
    'abcdefghijklmnopqrstuvwxyz'
    'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    '0123456789'
    '-=_+;:,.|/?@#$%^&*()'  # Safe special chars
    ' '  # Space allowed
    '[]{}~'  # More safe chars
    '<>'  # Comparison chars
)


def calculate_entropy(password: str) -> float:
    """
    Calculate password entropy in bits.
    
    Uses actual character class analysis:
    - lowercase (26), uppercase (26), digits (10), special (~30)
    - Entropy = log2(charset_size^length)
    
    Returns:
        Estimated entropy in bits
    """
    import math
    
    if not password:
        return 0.0
    
    has_lower = any(c.islower() for c in password)
    has_upper = any(c.isupper() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in '-=_+;:,.|/?@#$%^&*()[]{}~<> ' for c in password)
    
    charset_size = 0
    if has_lower:
        charset_size += 26
    if has_upper:
        charset_size += 26
    if has_digit:
        charset_size += 10
    if has_special:
        charset_size += 30  # Approximate for allowed specials
    
    if charset_size == 0:
        return 0.0
    
    return len(password) * math.log2(charset_size)


def validate_password(password: str) -> tuple[bool, str | None]:
    """
    Validate password format and entropy.
    
    Rules:
    - Minimum 20 characters
    - Minimum 100 bits of entropy
    - Only safe printable ASCII (no !, `, ', ", \\)
    
    Returns:
        (is_valid, error_message)
    """
    if not password:
        return False, "Password is required"
    
    if len(password) < PASSWORD_MIN_LENGTH:
        return False, f"Password must be at least {PASSWORD_MIN_LENGTH} characters"
    
    # Check for disallowed characters
    disallowed = set(password) - PASSWORD_ALLOWED_CHARS
    if disallowed:
        disallowed_str = ''.join(sorted(disallowed))
        return False, f"Password contains disallowed characters: {disallowed_str}"
    
    # Check entropy
    entropy = calculate_entropy(password)
    if entropy < PASSWORD_MIN_ENTROPY:
        return False, f"Password entropy too low ({entropy:.0f} bits). Need at least {PASSWORD_MIN_ENTROPY} bits. Use a longer password with mixed character types."
    
    return True, None


def generate_user_alias() -> str:
    """
    Generate a random user alias for token attribution.
    
    Format: 16 random alphanumeric characters
    Used in tokens instead of username for security.
    
    Returns:
        Random 16-char string like "Ab3xYz9KmNpQrStU"
    """
    return ''.join(secrets.choice(TOKEN_ALPHABET) for _ in range(USER_ALIAS_LENGTH))


def generate_token(user_alias: str) -> str:
    """
    Generate a new API token for the given user alias.
    
    Format: naf_<user_alias>_<random64>
    
    Args:
        user_alias: 16-char user identifier (NOT username)
    
    Returns:
        Full token string (store hash, show once to user)
    """
    random_part = ''.join(secrets.choice(TOKEN_ALPHABET) for _ in range(RANDOM_PART_LENGTH))
    return f"{TOKEN_PREFIX}{user_alias}_{random_part}"


def parse_token(token: str) -> tuple[str, str] | None:
    """
    Parse token into (user_alias, random_part) or None if invalid format.
    
    This allows routing/logging before database lookup.
    Note: Returns user_alias, NOT username (for security).
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
    
    Security: user_alias is used in tokens instead of username to avoid
    exposing login credentials in API tokens.
    """
    __tablename__ = 'accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), unique=True, nullable=False, index=True)
    user_alias = db.Column(db.String(16), unique=True, nullable=False, index=True)  # For tokens, NOT username
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
    
    # Password reset (temporary storage for reset flow)
    password_reset_code = db.Column(db.String(6))  # 6-digit reset code
    password_reset_expires = db.Column(db.DateTime)  # Code expiration time
    
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
    
    def regenerate_user_alias(self) -> tuple[str, int]:
        """
        Regenerate user_alias, invalidating ALL tokens.
        
        This is a security operation that should:
        1. Generate a new unique alias
        2. Delete all tokens (they become invalid anyway)
        3. Log the action
        
        Returns:
            (new_alias, tokens_deleted_count)
        """
        old_alias = self.user_alias
        tokens_deleted = 0
        
        # Delete all tokens for this account (cascade through realms)
        for realm in self.realms:
            tokens_deleted += len(realm.tokens)
            for token in realm.tokens:
                db.session.delete(token)
        
        # Generate new unique alias
        for _ in range(10):  # Max 10 attempts
            new_alias = generate_user_alias()
            existing = Account.query.filter_by(user_alias=new_alias).first()
            if not existing:
                self.user_alias = new_alias
                break
        else:
            raise RuntimeError("Failed to generate unique user_alias after 10 attempts")
        
        logger.info(
            f"User alias regenerated for {self.username}: "
            f"{old_alias[:4]}... → {new_alias[:4]}..., {tokens_deleted} tokens invalidated"
        )
        
        return new_alias, tokens_deleted
    
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
    
    Backend Resolution:
    - domain_root_id: Link to platform-managed domain root (Case A)
    - user_backend_id: Link to user's own backend service (Case B / BYOD)
    - Exactly one must be set (enforced by application logic)
    """
    __tablename__ = 'account_realms'
    
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False, index=True)
    
    domain = db.Column(db.String(255), nullable=False, index=True)  # Base domain (e.g., example.com)
    realm_type = db.Column(db.String(20), nullable=False)  # 'host', 'subdomain', 'subdomain_only'
    realm_value = db.Column(db.String(255), nullable=False)  # Prefix/host portion (e.g., 'iot', 'vpn', '')
    
    allowed_record_types = db.Column(db.Text, nullable=False)  # JSON array
    allowed_operations = db.Column(db.Text, nullable=False)  # JSON array
    
    # Backend resolution (exactly one should be set)
    domain_root_id = db.Column(db.Integer, db.ForeignKey('managed_domain_roots.id'), index=True)
    user_backend_id = db.Column(db.Integer, db.ForeignKey('backend_services.id'), index=True)
    
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
    domain_root = db.relationship('ManagedDomainRoot', foreign_keys=[domain_root_id])
    user_backend = db.relationship('BackendService', foreign_keys=[user_backend_id])
    
    __table_args__ = (
        db.UniqueConstraint('account_id', 'domain', 'realm_type', 'realm_value', name='uq_account_realm'),
        CheckConstraint("realm_type IN ('host', 'subdomain', 'subdomain_only')", name='check_realm_type'),
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name='check_realm_status'),
        # Unique subdomain per domain root (prevent duplicate claims)
        db.Index('idx_unique_realm_subdomain', 'domain_root_id', 'realm_value', unique=True,
                 postgresql_where=db.text('domain_root_id IS NOT NULL')),
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
    error_code = db.Column(db.String(30), index=True)  # Structured error code for analytics
    status_reason = db.Column(db.Text)  # Human-readable description
    
    # Security classification
    severity = db.Column(db.String(10))  # 'low', 'medium', 'high', 'critical'
    is_attack = db.Column(db.Integer, default=0)  # 1 if detected as attack pattern
    
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
    Includes realm_requests for unified registration + realm request workflow.
    """
    __tablename__ = 'registration_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    
    verification_code = db.Column(db.String(6), nullable=False)
    verification_expires_at = db.Column(db.DateTime, nullable=False)
    verification_attempts = db.Column(db.Integer, default=0)
    
    # Realm requests submitted during registration (JSON array)
    # Format: [{"realm_type": "host", "realm_value": "vpn", "domain": "example.com",
    #           "record_types": ["A", "AAAA"], "operations": ["read", "update"],
    #           "purpose": "Home router DDNS"}, ...]
    realm_requests = db.Column(db.Text)  # JSON array of realm requests
    
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
    
    def get_realm_requests(self) -> list[dict[str, Any]]:
        """Parse realm_requests from JSON."""
        try:
            return json.loads(self.realm_requests) if self.realm_requests else []
        except (json.JSONDecodeError, TypeError):
            return []
    
    def set_realm_requests(self, requests: list[dict[str, Any]]):
        """Set realm_requests as JSON."""
        self.realm_requests = json.dumps(requests) if requests else None
    
    def add_realm_request(self, realm_type: str, domain: str, realm_value: str,
                          record_types: list[str], operations: list[str],
                          purpose: str = ''):
        """Add a realm request to the list."""
        requests = self.get_realm_requests()
        requests.append({
            'realm_type': realm_type,
            'domain': domain,
            'realm_value': realm_value,
            'record_types': record_types,
            'operations': operations,
            'purpose': purpose
        })
        self.set_realm_requests(requests)
    
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


class ResetToken(db.Model):
    """
    Database-backed storage for password reset, invite, and verification tokens.
    
    Replaces in-memory _reset_tokens dict to support multi-worker deployments.
    Tokens are hashed (SHA256) for security - only the hash is stored.
    
    Token Types:
    - 'reset': Password reset tokens
    - 'invite': Account invite tokens (admin-created accounts)
    - 'verify': Email verification tokens for registration
    """
    __tablename__ = 'reset_tokens'
    
    id = db.Column(db.Integer, primary_key=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)  # SHA256 hash
    target_id = db.Column(db.Integer, nullable=False, index=True)  # Account.id or RegistrationRequest.id
    target_type = db.Column(db.String(20), nullable=False)  # 'account' or 'registration'
    token_type = db.Column(db.String(20), nullable=False)  # 'reset', 'invite', 'verify'
    
    expires_at = db.Column(db.DateTime, nullable=False)
    source_ip = db.Column(db.String(45))  # IP that requested the token (for binding)
    
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    used_at = db.Column(db.DateTime)  # Set when token is consumed
    
    __table_args__ = (
        CheckConstraint("token_type IN ('reset', 'invite', 'verify')", name='check_reset_token_type'),
        CheckConstraint("target_type IN ('account', 'registration')", name='check_reset_target_type'),
    )
    
    def is_expired(self) -> bool:
        """Check if token has expired."""
        return datetime.utcnow() > self.expires_at
    
    def is_used(self) -> bool:
        """Check if token has been used."""
        return self.used_at is not None
    
    def mark_used(self):
        """Mark token as used."""
        self.used_at = datetime.utcnow()
    
    @classmethod
    def cleanup_expired(cls):
        """Delete expired tokens (housekeeping)."""
        expired = cls.query.filter(cls.expires_at < datetime.utcnow()).all()
        for token in expired:
            db.session.delete(token)
        if expired:
            db.session.commit()
            logger.info(f"Cleaned up {len(expired)} expired reset tokens")
    
    def __repr__(self):
        return f'<ResetToken {self.token_type} target={self.target_type}:{self.target_id}>'


# ============================================================================
# Multi-Backend Architecture Models
# ============================================================================

class TestStatusEnum(db.Model):
    """Test status enumeration for type-safe status tracking."""
    __tablename__ = 'test_status_enum'
    
    id = db.Column(db.Integer, primary_key=True)
    status_code = db.Column(db.String(20), unique=True, nullable=False)
    display_name = db.Column(db.String(64), nullable=False)
    
    # Status codes
    PENDING = 'pending'
    SUCCESS = 'success'
    FAILED = 'failed'
    
    def __repr__(self):
        return f'<TestStatusEnum {self.status_code}>'


class VisibilityEnum(db.Model):
    """Visibility enumeration for domain root access control."""
    __tablename__ = 'visibility_enum'
    
    id = db.Column(db.Integer, primary_key=True)
    visibility_code = db.Column(db.String(20), unique=True, nullable=False)
    display_name = db.Column(db.String(64), nullable=False)
    description = db.Column(db.Text)
    
    # Visibility codes
    PUBLIC = 'public'
    PRIVATE = 'private'
    INVITE = 'invite'
    
    def __repr__(self):
        return f'<VisibilityEnum {self.visibility_code}>'


class OwnerTypeEnum(db.Model):
    """Owner type enumeration for backend service ownership."""
    __tablename__ = 'owner_type_enum'
    
    id = db.Column(db.Integer, primary_key=True)
    owner_code = db.Column(db.String(20), unique=True, nullable=False)
    display_name = db.Column(db.String(64), nullable=False)
    
    # Owner codes
    PLATFORM = 'platform'
    USER = 'user'
    
    def __repr__(self):
        return f'<OwnerTypeEnum {self.owner_code}>'


class GrantTypeEnum(db.Model):
    """Grant type enumeration for domain root access grants."""
    __tablename__ = 'grant_type_enum'
    
    id = db.Column(db.Integer, primary_key=True)
    grant_code = db.Column(db.String(20), unique=True, nullable=False)
    display_name = db.Column(db.String(64), nullable=False)
    
    # Grant codes
    STANDARD = 'standard'
    ADMIN = 'admin'
    INVITE_ONLY = 'invite_only'
    
    def __repr__(self):
        return f'<GrantTypeEnum {self.grant_code}>'


class BackendProvider(db.Model):
    """
    Backend provider registry (plugin system foundation).
    
    Each entry represents a DNS provider type (Netcup, PowerDNS, etc.)
    that can be used to create backend services.
    """
    __tablename__ = 'backend_providers'
    
    id = db.Column(db.Integer, primary_key=True)
    provider_code = db.Column(db.String(32), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text)
    config_schema = db.Column(db.Text, nullable=False)  # JSON Schema
    
    # Capabilities
    supports_zone_list = db.Column(db.Boolean, default=False)
    supports_zone_create = db.Column(db.Boolean, default=False)
    supports_dnssec = db.Column(db.Boolean, default=False)
    supported_record_types = db.Column(db.Text)  # JSON array
    
    # Status
    is_enabled = db.Column(db.Boolean, default=True)
    is_builtin = db.Column(db.Boolean, default=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    services = db.relationship('BackendService', back_populates='provider')
    
    def get_supported_record_types(self) -> list[str]:
        """Parse supported_record_types from JSON."""
        try:
            return json.loads(self.supported_record_types) if self.supported_record_types else []
        except (json.JSONDecodeError, TypeError):
            return []
    
    def set_supported_record_types(self, types: list[str]):
        """Set supported_record_types as JSON."""
        self.supported_record_types = json.dumps(types)
    
    def __repr__(self):
        return f'<BackendProvider {self.provider_code}>'


class BackendService(db.Model):
    """
    Backend service (credential instance).
    
    Each entry represents a configured connection to a DNS provider,
    either owned by the platform or by a specific user (BYOD).
    """
    __tablename__ = 'backend_services'
    
    id = db.Column(db.Integer, primary_key=True)
    provider_id = db.Column(db.Integer, db.ForeignKey('backend_providers.id'), nullable=False, index=True)
    service_name = db.Column(db.String(64), unique=True, nullable=False)
    display_name = db.Column(db.String(128), nullable=False)
    
    # Ownership (FK to enum table for type safety)
    owner_type_id = db.Column(db.Integer, db.ForeignKey('owner_type_enum.id'), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('accounts.id', ondelete='CASCADE'))
    
    # Configuration (plaintext JSON for now, encryption postponed)
    config = db.Column(db.Text, nullable=False)
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    is_default_for_owner = db.Column(db.Boolean, default=False)
    
    # Health monitoring (FK to enum table for type safety)
    last_tested_at = db.Column(db.DateTime)
    test_status_id = db.Column(db.Integer, db.ForeignKey('test_status_enum.id'))
    test_message = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    provider = db.relationship('BackendProvider', back_populates='services')
    owner_type = db.relationship('OwnerTypeEnum')
    owner = db.relationship('Account', foreign_keys=[owner_id])
    test_status = db.relationship('TestStatusEnum')
    domain_roots = db.relationship('ManagedDomainRoot', back_populates='backend_service')
    
    def get_config(self) -> dict[str, Any]:
        """Parse config from JSON."""
        try:
            return json.loads(self.config) if self.config else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_config(self, config: dict[str, Any]):
        """Set config as JSON."""
        self.config = json.dumps(config)
    
    def is_platform_owned(self) -> bool:
        """Check if this service is platform-owned."""
        return self.owner_type and self.owner_type.owner_code == OwnerTypeEnum.PLATFORM
    
    def __repr__(self):
        return f'<BackendService {self.service_name}>'


class ManagedDomainRoot(db.Model):
    """
    Managed domain root (admin-controlled zone).
    
    Represents a DNS zone that the platform manages and can offer
    to users for creating subdomains.
    """
    __tablename__ = 'managed_domain_roots'
    
    id = db.Column(db.Integer, primary_key=True)
    backend_service_id = db.Column(db.Integer, db.ForeignKey('backend_services.id'), nullable=False, index=True)
    
    # Zone identification
    root_domain = db.Column(db.String(255), nullable=False, index=True)
    dns_zone = db.Column(db.String(255), nullable=False)  # Actual zone in backend
    
    # Access control (FK to enum table for type safety)
    visibility_id = db.Column(db.Integer, db.ForeignKey('visibility_enum.id'), nullable=False)
    
    # Subdomain policy
    allow_apex_access = db.Column(db.Boolean, default=False)
    min_subdomain_depth = db.Column(db.Integer, default=1)
    max_subdomain_depth = db.Column(db.Integer, default=3)
    
    # Restrictions (JSON arrays, NULL = all allowed)
    allowed_record_types = db.Column(db.Text)
    allowed_operations = db.Column(db.Text)
    
    # Description for users
    display_name = db.Column(db.String(128))
    description = db.Column(db.Text)
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    verified_at = db.Column(db.DateTime)
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    backend_service = db.relationship('BackendService', back_populates='domain_roots')
    visibility = db.relationship('VisibilityEnum')
    grants = db.relationship('DomainRootGrant', back_populates='domain_root', cascade='all, delete-orphan')
    
    __table_args__ = (
        db.UniqueConstraint('backend_service_id', 'root_domain', name='uq_backend_root_domain'),
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
    
    def is_public(self) -> bool:
        """Check if this root is publicly accessible."""
        return self.visibility and self.visibility.visibility_code == VisibilityEnum.PUBLIC
    
    def __repr__(self):
        return f'<ManagedDomainRoot {self.root_domain}>'


class DomainRootGrant(db.Model):
    """
    Domain root access grant (links users to domain roots).
    
    Explicitly grants a user access to request realms under a domain root.
    Required for private/invite-only roots.
    """
    __tablename__ = 'domain_root_grants'
    
    id = db.Column(db.Integer, primary_key=True)
    domain_root_id = db.Column(db.Integer, db.ForeignKey('managed_domain_roots.id', ondelete='CASCADE'), nullable=False, index=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Grant type (FK to enum table for type safety)
    grant_type_id = db.Column(db.Integer, db.ForeignKey('grant_type_enum.id'), nullable=False)
    
    # Additional restrictions (tighter than root's defaults)
    allowed_record_types = db.Column(db.Text)  # JSON, NULL = inherit from root
    allowed_operations = db.Column(db.Text)  # JSON, NULL = inherit from root
    max_realms = db.Column(db.Integer, default=5)
    
    # Metadata
    granted_by_id = db.Column(db.Integer, db.ForeignKey('accounts.id'))
    granted_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)  # NULL = never
    revoked_at = db.Column(db.DateTime)
    revoke_reason = db.Column(db.Text)
    
    # Relationships
    domain_root = db.relationship('ManagedDomainRoot', back_populates='grants')
    account = db.relationship('Account', foreign_keys=[account_id])
    grant_type = db.relationship('GrantTypeEnum')
    granted_by = db.relationship('Account', foreign_keys=[granted_by_id])
    
    __table_args__ = (
        db.UniqueConstraint('domain_root_id', 'account_id', name='uq_grant_root_account'),
    )
    
    def is_active(self) -> bool:
        """Check if this grant is currently active."""
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None and self.expires_at < datetime.utcnow():
            return False
        return True
    
    def get_allowed_record_types(self) -> list[str] | None:
        """Parse allowed_record_types from JSON. Returns None if inheriting from root."""
        if self.allowed_record_types is None:
            return None
        try:
            return json.loads(self.allowed_record_types)
        except (json.JSONDecodeError, TypeError):
            return None
    
    def get_allowed_operations(self) -> list[str] | None:
        """Parse allowed_operations from JSON. Returns None if inheriting from root."""
        if self.allowed_operations is None:
            return None
        try:
            return json.loads(self.allowed_operations)
        except (json.JSONDecodeError, TypeError):
            return None
    
    def __repr__(self):
        return f'<DomainRootGrant root={self.domain_root_id} account={self.account_id}>'
