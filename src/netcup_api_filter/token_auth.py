"""
Token authentication service for the Account → Realms → Tokens model.

Handles:
- Token parsing (extract username and random part)
- Token lookup (find by username + prefix)
- Token verification (bcrypt hash check)
- Permission checking (account → realm → token chain)
- IP whitelist enforcement
- Usage tracking and activity logging

Token Format: naf_<username>_<random64>
  Authorization: Bearer naf_johndoe_a1B2c3D4e5F6...
"""
import ipaddress
import logging
from datetime import datetime
from functools import wraps
from typing import Any, NamedTuple, Optional

from flask import g, request

from .models import (
    Account,
    AccountRealm,
    ActivityLog,
    APIToken,
    db,
    parse_token,
)

logger = logging.getLogger(__name__)


class AuthResult(NamedTuple):
    """Result of authentication attempt."""
    success: bool
    token: Optional[APIToken] = None
    realm: Optional[AccountRealm] = None
    account: Optional[Account] = None
    error: Optional[str] = None
    error_code: Optional[str] = None  # 'invalid_token', 'expired', 'disabled', etc.


class PermissionResult(NamedTuple):
    """Result of permission check."""
    granted: bool
    reason: Optional[str] = None


def extract_bearer_token(authorization_header: str | None) -> str | None:
    """
    Extract token from Authorization header.
    
    Expected format: "Bearer naf_username_randompart"
    """
    if not authorization_header:
        return None
    
    parts = authorization_header.split(' ', 1)
    if len(parts) != 2:
        return None
    
    scheme, token = parts
    if scheme.lower() != 'bearer':
        return None
    
    return token.strip()


def authenticate_token(token: str) -> AuthResult:
    """
    Authenticate a Bearer token.
    
    Steps:
    1. Parse token to extract username and random part
    2. Find account by username
    3. Find token by prefix within account's tokens
    4. Verify full token against bcrypt hash
    5. Check token is active and not expired
    6. Check account is active
    7. Check realm is approved
    
    Returns:
        AuthResult with token, realm, account if successful
    """
    # Parse token format
    parsed = parse_token(token)
    if not parsed:
        logger.debug("Token format invalid")
        return AuthResult(
            success=False,
            error="Invalid token format",
            error_code="invalid_format"
        )
    
    username, random_part = parsed
    token_prefix = random_part[:8]
    
    logger.debug(f"Token lookup: username={username}, prefix={token_prefix}")
    
    # Find account by username
    account = Account.query.filter_by(username=username).first()
    if not account:
        logger.debug(f"Account not found: {username}")
        return AuthResult(
            success=False,
            error="Invalid token",
            error_code="invalid_token"
        )
    
    # Check account is active
    if not account.is_active:
        logger.warning(f"Account disabled: {username}")
        return AuthResult(
            success=False,
            error="Account is disabled",
            error_code="account_disabled"
        )
    
    # Find tokens matching prefix across all account's realms
    # Join through realms to filter by account
    api_token = (
        APIToken.query
        .join(AccountRealm)
        .filter(
            AccountRealm.account_id == account.id,
            APIToken.token_prefix == token_prefix
        )
        .first()
    )
    
    if not api_token:
        logger.debug(f"Token not found for account {username} with prefix {token_prefix}")
        return AuthResult(
            success=False,
            error="Invalid token",
            error_code="invalid_token"
        )
    
    # Verify full token against hash
    if not api_token.verify(token):
        logger.warning(f"Token hash mismatch for {username}")
        return AuthResult(
            success=False,
            error="Invalid token",
            error_code="invalid_token"
        )
    
    # Check token is active
    if not api_token.is_active:
        logger.warning(f"Token revoked: {api_token.token_name}")
        return AuthResult(
            success=False,
            error="Token has been revoked",
            error_code="token_revoked"
        )
    
    # Check token expiration
    if api_token.is_expired():
        logger.warning(f"Token expired: {api_token.token_name}")
        return AuthResult(
            success=False,
            error="Token has expired",
            error_code="token_expired"
        )
    
    # Get realm and check approval status
    realm = api_token.realm
    if realm.status != 'approved':
        logger.warning(f"Realm not approved: {realm.realm_type}:{realm.realm_value}")
        return AuthResult(
            success=False,
            error="Realm access has not been approved",
            error_code="realm_not_approved"
        )
    
    logger.info(f"Token authenticated: {username}/{api_token.token_name}")
    return AuthResult(
        success=True,
        token=api_token,
        realm=realm,
        account=account
    )


def check_ip_allowed(token: APIToken, client_ip: str) -> bool:
    """
    Check if client IP is allowed for this token.
    
    Returns True if:
    - No IP restrictions configured (empty list), OR
    - Client IP matches one of the allowed ranges/addresses
    """
    allowed_ranges = token.get_allowed_ip_ranges()
    if not allowed_ranges:
        return True  # No restrictions
    
    try:
        ip_obj = ipaddress.ip_address(client_ip)
    except ValueError:
        logger.warning(f"Invalid client IP format: {client_ip}")
        return False
    
    for allowed in allowed_ranges:
        try:
            if '/' in allowed:
                # CIDR notation
                network = ipaddress.ip_network(allowed, strict=False)
                if ip_obj in network:
                    return True
            else:
                # Single IP
                if ip_obj == ipaddress.ip_address(allowed):
                    return True
        except ValueError:
            logger.warning(f"Invalid IP range in whitelist: {allowed}")
            continue
    
    return False


def check_permission(
    auth: AuthResult,
    operation: str,
    domain: str,
    record_type: str | None = None,
    record_name: str | None = None,
    client_ip: str | None = None
) -> PermissionResult:
    """
    Check if authenticated token has permission for operation.
    
    Permission chain:
    1. Account must be active (already checked in auth)
    2. Realm must be approved (already checked in auth)
    3. Token must be active and not expired (already checked in auth)
    4. IP must be in whitelist (if configured)
    5. Domain must match realm scope
    6. Operation must be allowed (token-level or realm-level)
    7. Record type must be allowed (token-level or realm-level)
    """
    if not auth.success:
        return PermissionResult(granted=False, reason=auth.error)
    
    token = auth.token
    realm = auth.realm
    
    # Check IP whitelist
    if client_ip and not check_ip_allowed(token, client_ip):
        logger.warning(f"IP not whitelisted: {client_ip} for token {token.token_name}")
        return PermissionResult(granted=False, reason="IP address not in whitelist")
    
    # Check domain matches realm
    if not realm.matches_domain(domain):
        logger.warning(f"Domain {domain} not in realm {realm.realm_type}:{realm.realm_value}")
        return PermissionResult(granted=False, reason="Domain not in authorized scope")
    
    # Check operation allowed
    allowed_ops = token.get_effective_operations()
    if operation not in allowed_ops:
        logger.warning(f"Operation {operation} not allowed (allowed: {allowed_ops})")
        return PermissionResult(granted=False, reason=f"Operation '{operation}' not permitted")
    
    # Check record type allowed (if specified)
    if record_type:
        allowed_types = token.get_effective_record_types()
        if record_type not in allowed_types:
            logger.warning(f"Record type {record_type} not allowed (allowed: {allowed_types})")
            return PermissionResult(granted=False, reason=f"Record type '{record_type}' not permitted")
    
    logger.info(f"Permission granted: {operation} on {domain} for token {token.token_name}")
    return PermissionResult(granted=True)


def log_activity(
    auth: AuthResult,
    action: str,
    operation: str | None = None,
    domain: str | None = None,
    record_type: str | None = None,
    record_name: str | None = None,
    source_ip: str | None = None,
    user_agent: str | None = None,
    status: str = 'success',
    status_reason: str | None = None,
    request_data: dict[str, Any] | None = None,
    response_summary: dict[str, Any] | None = None
):
    """
    Log activity for auditing.
    
    Called after every API operation (success or failure).
    """
    log_entry = ActivityLog(
        token_id=auth.token.id if auth.token else None,
        account_id=auth.account.id if auth.account else None,
        action=action,
        operation=operation,
        realm_type=auth.realm.realm_type if auth.realm else None,
        realm_value=auth.realm.realm_value if auth.realm else domain,
        record_type=record_type,
        record_name=record_name,
        source_ip=source_ip or request.remote_addr,
        user_agent=user_agent or request.headers.get('User-Agent'),
        status=status,
        status_reason=status_reason,
    )
    
    if request_data:
        log_entry.set_request_data(request_data)
    if response_summary:
        log_entry.set_response_summary(response_summary)
    
    db.session.add(log_entry)
    
    # Update token usage if authenticated
    if auth.success and auth.token:
        auth.token.record_usage(source_ip or request.remote_addr)
    
    db.session.commit()


def require_auth(f):
    """
    Decorator for API endpoints requiring Bearer token authentication.
    
    Sets g.auth with AuthResult on success.
    Returns 401 Unauthorized on failure.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import jsonify
        
        # Extract token from Authorization header
        auth_header = request.headers.get('Authorization')
        token = extract_bearer_token(auth_header)
        
        if not token:
            return jsonify({
                'error': 'Authorization required',
                'message': 'Missing or invalid Authorization header. Use: Authorization: Bearer <token>'
            }), 401
        
        # Authenticate
        auth = authenticate_token(token)
        
        if not auth.success:
            # Log failed auth attempt
            log_activity(
                auth=auth,
                action='api_auth',
                status='denied',
                status_reason=auth.error,
                source_ip=request.remote_addr
            )
            
            return jsonify({
                'error': auth.error_code or 'unauthorized',
                'message': auth.error
            }), 401
        
        # Store auth result in Flask g object for use in endpoint
        g.auth = auth
        
        return f(*args, **kwargs)
    
    return decorated_function


def filter_dns_records(auth: AuthResult, domain: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Filter DNS records based on token permissions.
    
    Only returns records whose type is in the token's allowed record types.
    """
    if not auth.success:
        return []
    
    allowed_types = auth.token.get_effective_record_types()
    
    filtered = [
        record for record in records
        if record.get('type') in allowed_types
    ]
    
    logger.info(f"Filtered {len(records)} records to {len(filtered)} for token {auth.token.token_name}")
    return filtered


def validate_dns_records_update(
    auth: AuthResult,
    domain: str,
    records: list[dict[str, Any]],
    client_ip: str
) -> tuple[bool, str | None]:
    """
    Validate if token can update the specified DNS records.
    
    Checks each record's operation and type against permissions.
    
    Returns:
        (is_valid, error_message)
    """
    if not auth.success:
        return False, auth.error
    
    for record in records:
        record_name = record.get('hostname', '')
        record_type = record.get('type', '')
        delete_record = record.get('deleterecord', False)
        record_id = record.get('id')
        
        # Determine operation
        if delete_record:
            operation = 'delete'
        elif record_id:
            operation = 'update'
        else:
            operation = 'create'
        
        # Check permission
        perm = check_permission(
            auth=auth,
            operation=operation,
            domain=domain,
            record_type=record_type,
            record_name=record_name,
            client_ip=client_ip
        )
        
        if not perm.granted:
            return False, f"No permission to {operation} record {record_name} ({record_type}): {perm.reason}"
    
    return True, None
