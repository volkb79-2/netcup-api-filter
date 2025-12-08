"""
Realm and Token management service.

Handles:
- Realm CRUD operations (create, read, update, delete)
- Realm approval workflow
- Token CRUD operations
- Token generation and hashing

Realm Types:
- host: Exact match only (vpn.example.com)
- subdomain: Apex + children (iot.example.com, *.iot.example.com)
- subdomain_only: Children only, NOT apex (*.client.vxxu.de)
"""
import logging
from datetime import datetime
from typing import Any, NamedTuple, Optional

from .models import (
    Account,
    AccountRealm,
    ActivityLog,
    APIToken,
    USER_ALIAS_LENGTH,
    db,
    generate_token,
    hash_token,
)

logger = logging.getLogger(__name__)

# Valid record types
VALID_RECORD_TYPES = frozenset({
    'A', 'AAAA', 'CNAME', 'TXT', 'MX', 'NS', 'SRV', 'SSHFP', 'CAA', 'TLSA'
})

# Valid operations
VALID_OPERATIONS = frozenset({'read', 'create', 'update', 'delete'})

# Realm types
VALID_REALM_TYPES = frozenset({'host', 'subdomain', 'subdomain_only'})


class RealmResult(NamedTuple):
    """Result of realm operation."""
    success: bool
    realm: Optional[AccountRealm] = None
    error: Optional[str] = None
    field: Optional[str] = None


class TokenResult(NamedTuple):
    """Result of token operation."""
    success: bool
    token_obj: Optional[APIToken] = None
    token_plain: Optional[str] = None  # Full token (only on create)
    error: Optional[str] = None
    field: Optional[str] = None


# ============================================================================
# Realm Validation
# ============================================================================

def validate_realm_type(realm_type: str) -> tuple[bool, str | None]:
    """Validate realm type."""
    if realm_type not in VALID_REALM_TYPES:
        return False, f"Invalid realm type. Must be one of: {', '.join(sorted(VALID_REALM_TYPES))}"
    return True, None


def validate_domain(domain: str) -> tuple[bool, str | None]:
    """
    Validate base domain format.
    
    Domain should be a valid domain (e.g., example.com).
    """
    if not domain:
        return False, "Domain is required"
    
    # Basic domain validation
    if len(domain) > 255:
        return False, "Domain too long (max 255 characters)"
    
    # Must have at least one dot for a proper domain
    if '.' not in domain:
        return False, "Invalid domain format (must contain at least one dot)"
    
    # No leading/trailing dots
    if domain.startswith('.') or domain.endswith('.'):
        return False, "Domain cannot start or end with a dot"
    
    # No double dots
    if '..' in domain:
        return False, "Domain cannot contain consecutive dots"
    
    # Each label must be valid
    labels = domain.split('.')
    for label in labels:
        if not label:
            return False, "Invalid domain format"
        if len(label) > 63:
            return False, f"Domain label '{label}' too long (max 63 characters)"
        if not all(c.isalnum() or c == '-' for c in label):
            return False, f"Invalid characters in domain label '{label}'"
        if label.startswith('-') or label.endswith('-'):
            return False, f"Domain label '{label}' cannot start or end with hyphen"
    
    return True, None


def validate_realm_value(realm_value: str, realm_type: str) -> tuple[bool, str | None]:
    """
    Validate realm value (subdomain prefix).
    
    For 'host' and 'subdomain' types, can be empty (meaning apex domain).
    For 'subdomain_only', must be non-empty.
    """
    # subdomain_only requires a non-empty prefix
    if realm_type == 'subdomain_only' and not realm_value:
        return False, "Realm value is required for subdomain_only type"
    
    # If empty, that's valid (apex domain)
    if not realm_value:
        return True, None
    
    # Validate prefix format
    if len(realm_value) > 63:
        return False, "Realm value too long (max 63 characters)"
    
    if not all(c.isalnum() or c == '-' for c in realm_value):
        return False, "Invalid characters in realm value (only alphanumeric and hyphen allowed)"
    
    if realm_value.startswith('-') or realm_value.endswith('-'):
        return False, "Realm value cannot start or end with hyphen"
    
    return True, None


def validate_record_types(record_types: list[str]) -> tuple[bool, str | None]:
    """Validate record types list."""
    if not record_types:
        return False, "At least one record type is required"
    
    for rt in record_types:
        if rt not in VALID_RECORD_TYPES:
            return False, f"Invalid record type: {rt}. Valid types: {', '.join(sorted(VALID_RECORD_TYPES))}"
    
    return True, None


def validate_operations(operations: list[str]) -> tuple[bool, str | None]:
    """Validate operations list."""
    if not operations:
        return False, "At least one operation is required"
    
    for op in operations:
        if op not in VALID_OPERATIONS:
            return False, f"Invalid operation: {op}. Valid operations: {', '.join(sorted(VALID_OPERATIONS))}"
    
    return True, None


# ============================================================================
# Realm CRUD
# ============================================================================

def request_realm(
    account: Account,
    domain: str,
    realm_type: str,
    realm_value: str,
    record_types: list[str],
    operations: list[str]
) -> RealmResult:
    """
    Request a new realm for an account.
    
    Creates realm in 'pending' status awaiting admin approval.
    
    Args:
        account: The account requesting the realm
        domain: Base domain (e.g., example.com)
        realm_type: 'host', 'subdomain', or 'subdomain_only'
        realm_value: Subdomain prefix (e.g., 'iot', 'vpn', or '' for apex)
        record_types: Allowed DNS record types
        operations: Allowed operations (read, create, update, delete)
    """
    # Validate realm type
    is_valid, error = validate_realm_type(realm_type)
    if not is_valid:
        return RealmResult(success=False, error=error, field='realm_type')
    
    # Validate domain
    is_valid, error = validate_domain(domain.lower())
    if not is_valid:
        return RealmResult(success=False, error=error, field='domain')
    
    # Validate realm value
    is_valid, error = validate_realm_value(realm_value.lower() if realm_value else '', realm_type)
    if not is_valid:
        return RealmResult(success=False, error=error, field='realm_value')
    
    # Validate record types
    is_valid, error = validate_record_types(record_types)
    if not is_valid:
        return RealmResult(success=False, error=error, field='record_types')
    
    # Validate operations
    is_valid, error = validate_operations(operations)
    if not is_valid:
        return RealmResult(success=False, error=error, field='operations')
    
    # Normalize values
    domain_normalized = domain.lower()
    realm_value_normalized = realm_value.lower() if realm_value else ''
    
    # Check for existing realm with same domain+type+value for this account
    existing = AccountRealm.query.filter_by(
        account_id=account.id,
        domain=domain_normalized,
        realm_type=realm_type,
        realm_value=realm_value_normalized
    ).first()
    
    if existing:
        if existing.status == 'rejected':
            # Allow re-request after rejection
            existing.status = 'pending'
            existing.rejection_reason = None
            existing.requested_at = datetime.utcnow()
            existing.set_allowed_record_types(record_types)
            existing.set_allowed_operations(operations)
            db.session.commit()
            logger.info(f"Realm re-requested: {domain_normalized}/{realm_type}:{realm_value_normalized} for {account.username}")
            return RealmResult(success=True, realm=existing)
        else:
            return RealmResult(
                success=False,
                error="Realm already exists for this account",
                field='realm_value'
            )
    
    # Create new realm request
    realm = AccountRealm(
        account_id=account.id,
        domain=domain_normalized,
        realm_type=realm_type,
        realm_value=realm_value_normalized,
        status='pending',
        requested_at=datetime.utcnow()
    )
    realm.set_allowed_record_types(record_types)
    realm.set_allowed_operations(operations)
    
    db.session.add(realm)
    db.session.commit()
    
    logger.info(f"Realm requested: {domain_normalized}/{realm_type}:{realm_value_normalized} for {account.username}")
    
    # Notify admin of pending realm request
    from .notification_service import notify_realm_pending
    notify_realm_pending(realm)
    
    return RealmResult(success=True, realm=realm)


def approve_realm(realm_id: int, approved_by: Account) -> RealmResult:
    """Approve a pending realm request."""
    realm = AccountRealm.query.get(realm_id)
    if not realm:
        return RealmResult(success=False, error="Realm not found")
    
    if realm.status != 'pending':
        return RealmResult(success=False, error=f"Realm is not pending (status: {realm.status})")
    
    realm.status = 'approved'
    realm.approved_by_id = approved_by.id
    realm.approved_at = datetime.utcnow()
    
    db.session.commit()
    
    logger.info(f"Realm approved: {realm.realm_type}:{realm.realm_value} by {approved_by.username}")
    
    # Notify user of approval
    from .notification_service import notify_realm_approved
    notify_realm_approved(realm)
    
    return RealmResult(success=True, realm=realm)


def reject_realm(realm_id: int, rejected_by: Account, reason: str) -> RealmResult:
    """Reject a pending realm request."""
    realm = AccountRealm.query.get(realm_id)
    if not realm:
        return RealmResult(success=False, error="Realm not found")
    
    if realm.status != 'pending':
        return RealmResult(success=False, error=f"Realm is not pending (status: {realm.status})")
    
    realm.status = 'rejected'
    realm.rejection_reason = reason
    
    db.session.commit()
    
    logger.info(f"Realm rejected: {realm.realm_type}:{realm.realm_value} by {rejected_by.username}")
    
    # Notify user of rejection
    from .notification_service import notify_realm_rejected
    notify_realm_rejected(realm, reason)
    
    return RealmResult(success=True, realm=realm)


def update_realm_permissions(
    realm_id: int,
    record_types: list[str],
    operations: list[str],
    updated_by: Account
) -> RealmResult:
    """
    Update realm permissions.
    
    Only admin can update approved realms.
    """
    realm = AccountRealm.query.get(realm_id)
    if not realm:
        return RealmResult(success=False, error="Realm not found")
    
    # Validate record types
    is_valid, error = validate_record_types(record_types)
    if not is_valid:
        return RealmResult(success=False, error=error, field='record_types')
    
    # Validate operations
    is_valid, error = validate_operations(operations)
    if not is_valid:
        return RealmResult(success=False, error=error, field='operations')
    
    realm.set_allowed_record_types(record_types)
    realm.set_allowed_operations(operations)
    
    db.session.commit()
    
    logger.info(f"Realm permissions updated: {realm.realm_type}:{realm.realm_value} by {updated_by.username}")
    
    return RealmResult(success=True, realm=realm)


def delete_realm(realm_id: int, deleted_by: Account) -> RealmResult:
    """
    Delete a realm and all its tokens.
    
    Only the account owner or admin can delete.
    """
    realm = AccountRealm.query.get(realm_id)
    if not realm:
        return RealmResult(success=False, error="Realm not found")
    
    # Check permission (owner or admin)
    if realm.account_id != deleted_by.id and not deleted_by.is_admin:
        return RealmResult(success=False, error="Permission denied")
    
    realm_info = f"{realm.realm_type}:{realm.realm_value}"
    
    db.session.delete(realm)
    db.session.commit()
    
    logger.info(f"Realm deleted: {realm_info} by {deleted_by.username}")
    
    return RealmResult(success=True)


def get_realms_for_account(account: Account) -> list[AccountRealm]:
    """Get all realms for an account."""
    return AccountRealm.query.filter_by(account_id=account.id).all()


def get_pending_realms() -> list[AccountRealm]:
    """Get all pending realm requests (for admin)."""
    return AccountRealm.query.filter_by(status='pending').all()


# ============================================================================
# Token CRUD
# ============================================================================

def create_token(
    realm: AccountRealm,
    token_name: str,
    description: str | None = None,
    record_types: list[str] | None = None,
    operations: list[str] | None = None,
    ip_ranges: list[str] | None = None,
    expires_at: datetime | None = None
) -> TokenResult:
    """
    Create a new API token for a realm.
    
    Returns the full token (only shown once) along with the token object.
    """
    # Validate realm is approved
    if realm.status != 'approved':
        return TokenResult(success=False, error="Cannot create token for unapproved realm")
    
    # Validate token name
    if not token_name or len(token_name) > 64:
        return TokenResult(success=False, error="Token name is required (max 64 characters)", field='token_name')
    
    # Check for duplicate name in this realm
    existing = APIToken.query.filter_by(realm_id=realm.id, token_name=token_name).first()
    if existing:
        return TokenResult(success=False, error="Token name already exists for this realm", field='token_name')
    
    # Validate record types (if restricted)
    if record_types:
        # Must be subset of realm's allowed types
        realm_types = set(realm.get_allowed_record_types())
        for rt in record_types:
            if rt not in realm_types:
                return TokenResult(
                    success=False,
                    error=f"Record type {rt} not allowed by realm",
                    field='record_types'
                )
    
    # Validate operations (if restricted)
    if operations:
        # Must be subset of realm's allowed operations
        realm_ops = set(realm.get_allowed_operations())
        for op in operations:
            if op not in realm_ops:
                return TokenResult(
                    success=False,
                    error=f"Operation {op} not allowed by realm",
                    field='operations'
                )
    
    # Get account for token generation
    account = realm.account
    
    # Generate full token using user_alias (not username, for security)
    full_token = generate_token(account.user_alias)
    
    # Extract prefix (first 8 chars of random part)
    # Token format: naf_<user_alias>_<random64> where user_alias is 16 chars
    random_part_start = 4 + USER_ALIAS_LENGTH + 1  # "naf_" + alias + "_"
    token_prefix = full_token[random_part_start:random_part_start + 8]
    
    # Hash full token for storage
    token_hash = hash_token(full_token)
    
    # Create token
    api_token = APIToken(
        realm_id=realm.id,
        token_name=token_name,
        token_description=description,
        token_prefix=token_prefix,
        token_hash=token_hash,
        expires_at=expires_at,
        is_active=1
    )
    
    if record_types:
        api_token.set_allowed_record_types(record_types)
    if operations:
        api_token.set_allowed_operations(operations)
    if ip_ranges:
        api_token.set_allowed_ip_ranges(ip_ranges)
    
    db.session.add(api_token)
    db.session.commit()
    
    logger.info(f"Token created: {token_name} for realm {realm.realm_type}:{realm.realm_value}")
    
    # Return both token object and plain token (shown once)
    return TokenResult(
        success=True,
        token_obj=api_token,
        token_plain=full_token
    )


def revoke_token(
    token_id: int,
    revoked_by: Account,
    reason: str | None = None
) -> TokenResult:
    """
    Revoke an API token.
    
    Token is not deleted, just marked as revoked for audit trail.
    Sends notification to token owner.
    """
    api_token = APIToken.query.get(token_id)
    if not api_token:
        return TokenResult(success=False, error="Token not found")
    
    # Check permission (realm owner or admin)
    realm = api_token.realm
    if realm.account_id != revoked_by.id and not revoked_by.is_admin:
        return TokenResult(success=False, error="Permission denied")
    
    if not api_token.is_active:
        return TokenResult(success=False, error="Token already revoked")
    
    api_token.is_active = 0
    api_token.revoked_at = datetime.utcnow()
    api_token.revoked_reason = reason
    
    db.session.commit()
    
    logger.info(f"Token revoked: {api_token.token_name} by {revoked_by.username}")
    
    # Send notification to token owner
    from .notification_service import notify_token_revoked
    notify_token_revoked(
        account=realm.account,
        token=api_token,
        revoked_by=revoked_by.username,
        reason=reason
    )
    
    return TokenResult(success=True, token_obj=api_token)


def regenerate_token(
    token_id: int,
    regenerated_by: Account
) -> TokenResult:
    """
    Regenerate an API token (new secret, same settings).
    
    Old token is revoked and a new one is created with same settings.
    """
    old_token = APIToken.query.get(token_id)
    if not old_token:
        return TokenResult(success=False, error="Token not found")
    
    # Check permission (realm owner or admin)
    realm = old_token.realm
    if realm.account_id != regenerated_by.id and not regenerated_by.is_admin:
        return TokenResult(success=False, error="Permission denied")
    
    # Revoke old token
    old_token.is_active = 0
    old_token.revoked_at = datetime.utcnow()
    old_token.revoked_reason = "Regenerated"
    
    # Create new token with same settings but new name
    new_name = f"{old_token.token_name}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    
    result = create_token(
        realm=realm,
        token_name=new_name,
        description=old_token.token_description,
        record_types=old_token.get_allowed_record_types(),
        operations=old_token.get_allowed_operations(),
        ip_ranges=old_token.get_allowed_ip_ranges() or None,
        expires_at=old_token.expires_at
    )
    
    if not result.success:
        # Rollback revocation
        db.session.rollback()
        return result
    
    db.session.commit()
    
    logger.info(f"Token regenerated: {old_token.token_name} -> {new_name} by {regenerated_by.username}")
    
    return result


def update_token(
    token_id: int,
    updated_by: Account,
    description: str | None = None,
    record_types: list[str] | None = None,
    operations: list[str] | None = None,
    ip_ranges: list[str] | None = None,
    expires_at: datetime | None = None
) -> TokenResult:
    """
    Update token settings (not the secret).
    """
    api_token = APIToken.query.get(token_id)
    if not api_token:
        return TokenResult(success=False, error="Token not found")
    
    # Check permission (realm owner or admin)
    realm = api_token.realm
    if realm.account_id != updated_by.id and not updated_by.is_admin:
        return TokenResult(success=False, error="Permission denied")
    
    # Validate record types (if specified)
    if record_types is not None:
        realm_types = set(realm.get_allowed_record_types())
        for rt in record_types:
            if rt not in realm_types:
                return TokenResult(
                    success=False,
                    error=f"Record type {rt} not allowed by realm",
                    field='record_types'
                )
        api_token.set_allowed_record_types(record_types)
    
    # Validate operations (if specified)
    if operations is not None:
        realm_ops = set(realm.get_allowed_operations())
        for op in operations:
            if op not in realm_ops:
                return TokenResult(
                    success=False,
                    error=f"Operation {op} not allowed by realm",
                    field='operations'
                )
        api_token.set_allowed_operations(operations)
    
    if description is not None:
        api_token.token_description = description
    
    if ip_ranges is not None:
        api_token.set_allowed_ip_ranges(ip_ranges or None)
    
    if expires_at is not None:
        api_token.expires_at = expires_at
    
    db.session.commit()
    
    logger.info(f"Token updated: {api_token.token_name} by {updated_by.username}")
    
    return TokenResult(success=True, token_obj=api_token)


def get_tokens_for_realm(realm: AccountRealm, include_revoked: bool = False) -> list[APIToken]:
    """Get all tokens for a realm."""
    query = APIToken.query.filter_by(realm_id=realm.id)
    if not include_revoked:
        query = query.filter_by(is_active=1)
    return query.all()


def get_token_activity(token: APIToken, limit: int = 50) -> list[ActivityLog]:
    """Get activity log for a specific token."""
    return (
        ActivityLog.query
        .filter_by(token_id=token.id)
        .order_by(ActivityLog.created_at.desc())
        .limit(limit)
        .all()
    )


# ============================================================================
# Admin Quick Actions
# ============================================================================

def create_realm_by_admin(
    account: Account,
    domain: str,
    realm_type: str,
    realm_value: str,
    record_types: list[str],
    operations: list[str],
    created_by: Account
) -> RealmResult:
    """
    Create and immediately approve a realm (admin action).
    
    Args:
        account: The account to create realm for
        domain: Base domain (e.g., example.com)
        realm_type: 'host', 'subdomain', or 'subdomain_only'
        realm_value: Subdomain prefix (e.g., 'iot', 'vpn', or '' for apex)
        record_types: Allowed DNS record types
        operations: Allowed operations (read, create, update, delete)
        created_by: Admin account creating the realm
    """
    # Use request_realm for validation
    result = request_realm(
        account=account,
        domain=domain,
        realm_type=realm_type,
        realm_value=realm_value,
        record_types=record_types,
        operations=operations
    )
    
    if not result.success:
        return result
    
    # Immediately approve
    realm = result.realm
    realm.status = 'approved'
    realm.approved_by_id = created_by.id
    realm.approved_at = datetime.utcnow()
    
    db.session.commit()
    
    logger.info(f"Realm created by admin: {domain}/{realm_type}:{realm_value} for {account.username}")
    
    return RealmResult(success=True, realm=realm)
