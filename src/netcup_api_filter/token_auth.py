"""
Token authentication service for the Account → Realms → Tokens model.

Handles:
- Token parsing (extract user_alias and random part)
- Token lookup (find by user_alias + prefix)
- Token verification (bcrypt hash check)
- Permission checking (account → realm → token chain)
- IP whitelist enforcement
- Usage tracking and activity logging
- Granular error codes for security monitoring

Token Format: naf_<user_alias>_<random64>
  - user_alias: 16-char random identifier (NOT username for security)
  - random: 64 chars, [a-zA-Z0-9]
  Authorization: Bearer naf_Ab3xYz9KmNpQrStU_a1B2c3D4e5F6...

Security: user_alias protects username from exposure in API tokens.

Error Codes (for security analytics):
  Authentication failures:
    - invalid_format: Token doesn't match naf_<alias>_<random> pattern
    - missing_token: No Authorization header
    - alias_not_found: Valid format but user_alias doesn't exist
    - token_prefix_not_found: Alias exists but no token with prefix (attack detection!)
    - token_hash_mismatch: Prefix exists but hash fails (BRUTE FORCE!)
    - account_disabled: Account is_active=False
    - token_revoked: Token is_active=False
    - token_expired: Token past expires_at
    - realm_not_approved: Realm status != 'approved'
  
  Authorization failures (permission checks):
    - ip_denied: IP not in token whitelist
    - domain_denied: Domain outside realm scope
    - operation_denied: Operation not allowed
    - record_type_denied: Record type not allowed
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


# =============================================================================
# Error Severity Classification
# =============================================================================

ERROR_SEVERITY = {
    # Authentication errors
    'invalid_format': 'low',
    'missing_token': 'low',
    'alias_not_found': 'medium',  # Could be credential stuffing
    'token_prefix_not_found': 'high',  # User attributable, probing
    'token_hash_mismatch': 'critical',  # BRUTE FORCE - user + token known!
    'account_disabled': 'medium',
    'token_revoked': 'high',  # Could indicate stolen token still in use
    'token_expired': 'low',  # Expected behavior
    'realm_not_approved': 'low',
    
    # Authorization errors
    'ip_denied': 'critical',  # Unexpected location - possible compromise
    'domain_denied': 'high',  # Scope probing
    'operation_denied': 'medium',  # May be user error
    'record_type_denied': 'low',  # May be user error
}

NOTIFY_USER_ERRORS = {
    'token_prefix_not_found',  # Someone probing their tokens
    'token_hash_mismatch',  # Brute force against their token
    'token_revoked',  # Revoked token still in use
    'ip_denied',  # Access from unexpected location
    'domain_denied',  # Scope probing
}


class AuthResult(NamedTuple):
    """Result of authentication attempt."""
    success: bool
    token: Optional[APIToken] = None
    realm: Optional[AccountRealm] = None
    account: Optional[Account] = None
    error: Optional[str] = None  # Generic message for API response
    error_code: Optional[str] = None  # Structured code for logging
    severity: Optional[str] = None  # 'low', 'medium', 'high', 'critical'
    should_notify_user: bool = False  # Send security alert to user?
    # Additional context for logging (NOT returned to API caller)
    user_alias_attempted: Optional[str] = None  # Even on failure, for attribution
    token_prefix_attempted: Optional[str] = None  # For identifying which token was attacked


class PermissionResult(NamedTuple):
    """Result of permission check."""
    granted: bool
    reason: Optional[str] = None  # Human-readable
    error_code: Optional[str] = None  # Structured code


def extract_bearer_token(authorization_header: str | None) -> str | None:
    """
    Extract token from Authorization header.
    
    Expected format: "Bearer naf_<user_alias>_<randompart>"
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
    Authenticate a Bearer token with granular error tracking.
    
    Steps:
    1. Parse token to extract user_alias and random part
    2. Find account by user_alias (NOT username)
    3. Find token by prefix within account's tokens
    4. Verify full token against bcrypt hash
    5. Check token is active and not expired
    6. Check account is active
    7. Check realm is approved
    
    Returns:
        AuthResult with token, realm, account if successful.
        On failure, includes error_code, severity, and attribution info.
    """
    # Parse token format
    parsed = parse_token(token)
    if not parsed:
        logger.debug("Token format invalid")
        return AuthResult(
            success=False,
            error="Invalid token",
            error_code="invalid_format",
            severity=ERROR_SEVERITY['invalid_format'],
            should_notify_user=False
        )
    
    user_alias, random_part = parsed
    token_prefix = random_part[:8]
    
    logger.debug(f"Token lookup: alias={user_alias[:4]}..., prefix={token_prefix}")
    
    # Find account by user_alias (NOT username for security)
    account = Account.query.filter_by(user_alias=user_alias).first()
    if not account:
        logger.debug(f"User alias not found: {user_alias[:4]}...")
        return AuthResult(
            success=False,
            error="Invalid token",
            error_code="alias_not_found",
            severity=ERROR_SEVERITY['alias_not_found'],
            should_notify_user=False,
            user_alias_attempted=user_alias  # For credential stuffing detection
        )
    
    # Check account is active FIRST (before token lookup)
    if not account.is_active:
        logger.warning(f"Account disabled: {account.username}")
        return AuthResult(
            success=False,
            error="Account is disabled",
            error_code="account_disabled",
            severity=ERROR_SEVERITY['account_disabled'],
            should_notify_user=False,
            account=account,  # Attribution!
            user_alias_attempted=user_alias
        )
    
    # Find tokens matching prefix across all account's realms
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
        # Token prefix not found - someone may be probing this account's tokens
        logger.warning(f"Token prefix not found for account {account.username}: {token_prefix}")
        return AuthResult(
            success=False,
            error="Invalid token",
            error_code="token_prefix_not_found",
            severity=ERROR_SEVERITY['token_prefix_not_found'],
            should_notify_user='token_prefix_not_found' in NOTIFY_USER_ERRORS,
            account=account,  # ATTRIBUTION: We know who is being attacked!
            user_alias_attempted=user_alias,
            token_prefix_attempted=token_prefix
        )
    
    # Verify full token against hash - CRITICAL if this fails
    if not api_token.verify(token):
        logger.warning(
            f"Token hash mismatch for {account.username}, "
            f"token={api_token.token_name} - POSSIBLE BRUTE FORCE"
        )
        return AuthResult(
            success=False,
            error="Invalid token",
            error_code="token_hash_mismatch",
            severity=ERROR_SEVERITY['token_hash_mismatch'],
            should_notify_user='token_hash_mismatch' in NOTIFY_USER_ERRORS,
            account=account,  # ATTRIBUTION
            token=api_token,  # ATTRIBUTION: We know WHICH token!
            user_alias_attempted=user_alias,
            token_prefix_attempted=token_prefix
        )
    
    # Check token is active (revoked check)
    if not api_token.is_active:
        logger.warning(f"Revoked token still in use: {api_token.token_name}")
        return AuthResult(
            success=False,
            error="Token has been revoked",
            error_code="token_revoked",
            severity=ERROR_SEVERITY['token_revoked'],
            should_notify_user='token_revoked' in NOTIFY_USER_ERRORS,
            account=account,
            token=api_token,
            realm=api_token.realm
        )
    
    # Check token expiration
    if api_token.is_expired():
        logger.info(f"Expired token used: {api_token.token_name}")
        return AuthResult(
            success=False,
            error="Token has expired",
            error_code="token_expired",
            severity=ERROR_SEVERITY['token_expired'],
            should_notify_user=False,  # Expected behavior
            account=account,
            token=api_token,
            realm=api_token.realm
        )
    
    # Get realm and check approval status
    realm = api_token.realm
    if realm.status != 'approved':
        logger.warning(f"Realm not approved: {realm.realm_type}:{realm.realm_value}")
        return AuthResult(
            success=False,
            error="Realm access has not been approved",
            error_code="realm_not_approved",
            severity=ERROR_SEVERITY['realm_not_approved'],
            should_notify_user=False,
            account=account,
            token=api_token,
            realm=realm
        )
    
    # SUCCESS
    logger.info(f"Token authenticated: {account.username}/{api_token.token_name}")
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
    
    Returns PermissionResult with structured error_code for logging.
    """
    if not auth.success:
        return PermissionResult(granted=False, reason=auth.error, error_code=auth.error_code)
    
    # After checking auth.success, token and realm are guaranteed non-None
    token = auth.token
    realm = auth.realm
    assert token is not None, "token should be set when auth.success is True"
    assert realm is not None, "realm should be set when auth.success is True"
    
    # Check IP whitelist
    if client_ip and not check_ip_allowed(token, client_ip):
        logger.warning(f"IP not whitelisted: {client_ip} for token {token.token_name}")
        return PermissionResult(
            granted=False,
            reason="IP address not in whitelist",
            error_code="ip_denied"
        )
    
    # Check domain matches realm
    if not realm.matches_domain(domain):
        logger.warning(f"Domain {domain} not in realm {realm.realm_type}:{realm.realm_value}")
        return PermissionResult(
            granted=False,
            reason="Domain not in authorized scope",
            error_code="domain_denied"
        )
    
    # Check operation allowed
    allowed_ops = token.get_effective_operations()
    if operation not in allowed_ops:
        logger.warning(f"Operation {operation} not allowed (allowed: {allowed_ops})")
        return PermissionResult(
            granted=False,
            reason=f"Operation '{operation}' not permitted",
            error_code="operation_denied"
        )
    
    # Check record type allowed (if specified)
    if record_type:
        allowed_types = token.get_effective_record_types()
        if record_type not in allowed_types:
            logger.warning(f"Record type {record_type} not allowed (allowed: {allowed_types})")
            return PermissionResult(
                granted=False,
                reason=f"Record type '{record_type}' not permitted",
                error_code="record_type_denied"
            )
    
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
    error_code: str | None = None,
    status_reason: str | None = None,
    severity: str | None = None,
    request_data: dict[str, Any] | None = None,
    response_summary: dict[str, Any] | None = None
):
    """
    Log activity for auditing with security classification.
    
    Called after every API operation (success or failure).
    Includes error_code and severity for security analytics.
    """
    # Determine severity
    if severity is None:
        if error_code:
            severity = ERROR_SEVERITY.get(error_code, 'medium')
        elif status == 'success':
            severity = None  # No severity for successful operations
    
    # Determine source IP (required field)
    actual_source_ip = source_ip or request.remote_addr or 'unknown'
    actual_user_agent = user_agent or request.headers.get('User-Agent')
    
    log_entry = ActivityLog(  # type: ignore[call-arg]  # SQLAlchemy dynamic columns
        token_id=auth.token.id if auth.token else None,
        account_id=auth.account.id if auth.account else None,
        action=action,
        operation=operation,
        realm_type=auth.realm.realm_type if auth.realm else None,
        realm_value=auth.realm.realm_value if auth.realm else domain,
        record_type=record_type,
        record_name=record_name,
        source_ip=actual_source_ip,
        user_agent=actual_user_agent,
        status=status,
        error_code=error_code or auth.error_code,
        status_reason=status_reason or auth.error,
        severity=severity or auth.severity,
        is_attack=1 if (severity in ('high', 'critical') or (auth.severity in ('high', 'critical'))) else 0,
    )
    
    if request_data:
        log_entry.set_request_data(request_data)
    if response_summary:
        log_entry.set_response_summary(response_summary)
    
    db.session.add(log_entry)
    
    # Update token usage if authenticated
    if auth.success and auth.token:
        auth.token.record_usage(actual_source_ip)
    
    db.session.commit()
    
    # Trigger notification if needed
    if auth.should_notify_user and auth.account:
        _trigger_security_notification(auth, actual_source_ip)


def _trigger_security_notification(auth: AuthResult, source_ip: str):
    """
    Send security notification to account owner.
    
    Called when a high-severity security event is detected.
    TODO: Implement send_security_alert in notification_service.py
    """
    try:
        # TODO: Uncomment when send_security_alert is implemented
        # from .notification_service import send_security_alert
        # send_security_alert(
        #     account=auth.account,
        #     event_type=auth.error_code,
        #     severity=auth.severity,
        #     source_ip=source_ip,
        #     token_name=auth.token.token_name if auth.token else None,
        #     details=auth.error
        # )
        logger.info(
            f"Security notification triggered: event={auth.error_code}, "
            f"severity={auth.severity}, ip={source_ip}, account={auth.account.username if auth.account else 'unknown'}"
        )
    except Exception as e:
        logger.error(f"Failed to send security notification: {e}")


def require_auth(f):
    """
    Decorator for API endpoints requiring Bearer token authentication.
    
    Sets g.auth with AuthResult on success.
    Returns 401 Unauthorized on failure.
    
    Note: Error responses are generic to avoid leaking information.
    Detailed info is logged server-side for admin review.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import jsonify
        
        # Extract token from Authorization header
        auth_header = request.headers.get('Authorization')
        token = extract_bearer_token(auth_header)
        
        if not token:
            # Log without auth context
            log_entry = ActivityLog(  # type: ignore[call-arg]  # SQLAlchemy dynamic columns
                action='api_auth',
                source_ip=request.remote_addr or 'unknown',
                user_agent=request.headers.get('User-Agent'),
                status='denied',
                error_code='missing_token',
                status_reason='Missing Authorization header',
                severity=ERROR_SEVERITY['missing_token'],
            )
            db.session.add(log_entry)
            db.session.commit()
            
            return jsonify({
                'error': 'unauthorized',
                'message': 'Authorization required'
            }), 401
        
        # Authenticate
        auth = authenticate_token(token)
        
        if not auth.success:
            # Log failed auth attempt with full context
            log_activity(
                auth=auth,
                action='api_auth',
                status='denied',
                error_code=auth.error_code,
                status_reason=auth.error,
                severity=auth.severity,
                source_ip=request.remote_addr
            )
            
            # SECURITY: Return generic error to API caller
            # Detailed info is in the logs for admin
            return jsonify({
                'error': 'unauthorized',
                'message': 'Invalid or expired token'  # Generic message
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
    if not auth.success or auth.token is None:
        return []
    
    token = auth.token  # Now guaranteed non-None
    allowed_types = token.get_effective_record_types()
    
    filtered = [
        record for record in records
        if record.get('type') in allowed_types
    ]
    
    logger.info(f"Filtered {len(records)} records to {len(filtered)} for token {token.token_name}")
    return filtered


def validate_dns_records_update(
    auth: AuthResult,
    domain: str,
    records: list[dict[str, Any]],
    client_ip: str
) -> tuple[bool, str | None, str | None]:
    """
    Validate if token can update the specified DNS records.
    
    Checks each record's operation and type against permissions.
    
    Returns:
        (is_valid, error_message, error_code)
    """
    if not auth.success:
        return False, auth.error, auth.error_code
    
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
            return False, f"No permission to {operation} record {record_name} ({record_type}): {perm.reason}", perm.error_code
    
    return True, None, None


# =============================================================================
# Security Analytics Helpers
# =============================================================================

def get_security_stats(hours: int = 24) -> dict[str, Any]:
    """
    Get security statistics for dashboard.
    
    Returns counts by error code and severity for the given time window.
    """
    from datetime import timedelta
    from sqlalchemy import func
    
    since = datetime.utcnow() - timedelta(hours=hours)
    
    # Count by error code
    error_counts = (
        db.session.query(
            ActivityLog.error_code,
            func.count(ActivityLog.id).label('count')
        )
        .filter(
            ActivityLog.created_at >= since,
            ActivityLog.status == 'denied',
            ActivityLog.error_code.isnot(None)
        )
        .group_by(ActivityLog.error_code)
        .all()
    )
    
    # Count by severity
    severity_counts = (
        db.session.query(
            ActivityLog.severity,
            func.count(ActivityLog.id).label('count')
        )
        .filter(
            ActivityLog.created_at >= since,
            ActivityLog.status == 'denied',
            ActivityLog.severity.isnot(None)
        )
        .group_by(ActivityLog.severity)
        .all()
    )
    
    # Recent attack events
    attack_events = (
        ActivityLog.query
        .filter(
            ActivityLog.created_at >= since,
            ActivityLog.is_attack == 1
        )
        .order_by(ActivityLog.created_at.desc())
        .limit(50)
        .all()
    )
    
    return {
        'by_error_code': {r.error_code: r.count for r in error_counts},
        'by_severity': {r.severity: r.count for r in severity_counts if r.severity},
        'attack_events': [
            {
                'id': e.id,
                'error_code': e.error_code,
                'severity': e.severity,
                'source_ip': e.source_ip,
                'account_id': e.account_id,
                'created_at': e.created_at.isoformat()
            }
            for e in attack_events
        ],
        'total_denied': sum(r.count for r in error_counts),
        'window_hours': hours
    }


def get_security_timeline(hours: int = 24, bucket_minutes: int = 60) -> list[dict[str, Any]]:
    """
    Get security events over time for graphing.
    
    Returns hourly (or custom bucket) counts by error code.
    """
    from datetime import timedelta
    from sqlalchemy import func
    
    since = datetime.utcnow() - timedelta(hours=hours)
    
    # SQLite date truncation
    time_bucket = func.strftime('%Y-%m-%d %H:00:00', ActivityLog.created_at)
    
    results = (
        db.session.query(
            time_bucket.label('bucket'),
            ActivityLog.error_code,
            func.count(ActivityLog.id).label('count')
        )
        .filter(
            ActivityLog.created_at >= since,
            ActivityLog.status == 'denied',
            ActivityLog.error_code.isnot(None)
        )
        .group_by(time_bucket, ActivityLog.error_code)
        .order_by(time_bucket)
        .all()
    )
    
    # Organize by bucket
    timeline = {}
    for r in results:
        bucket = r.bucket
        if bucket not in timeline:
            timeline[bucket] = {'timestamp': bucket}
        timeline[bucket][r.error_code] = r.count
    
    return list(timeline.values())
