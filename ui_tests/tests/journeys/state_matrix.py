"""
Comprehensive State Matrix for Journey Testing

This module defines ALL the states we need to test, creating a systematic
combinatorial coverage of the application's state space.

State Dimensions:
================

ACCOUNTS (4 states):
  1. Pending (awaiting admin approval)
  2. Approved (active, can login)
  3. Rejected (denied by admin) 
  4. Locked (too many failed logins)

REALMS (3 types × 2 approval states × 3 token counts = 18 combinations):
  Types:
    - host: single hostname only
    - subdomain: apex + children
    - subdomain_only: children only, not apex
  
  Approval:
    - pending: awaiting admin approval
    - approved: active, can create tokens
  
  Token counts:
    - 0 tokens: realm approved but no tokens yet
    - 1 token: single token created
    - 3+ tokens: multiple tokens with different scopes

TOKENS (for each realm, multiple types):
  - Read-only: ["read"]
  - Update-only: ["read", "update"]  
  - Full access: ["read", "update", "create", "delete"]
  - Record-type restricted: A records only, TXT only, etc.
  - IP-restricted: only from specific CIDR
  - Expired: expires_at in past
  - Revoked: is_active=0, revoked_at set

API TESTS (for each token type):
  - Authorized operation: should succeed
  - Unauthorized operation: should 403
  - Wrong realm: should 403
  - Invalid token: should 401
  - Expired token: should 401
  - Revoked token: should 401
  - IP not in range: should 403

Total systematic coverage: ~50-100 distinct states × API validations
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timedelta


@dataclass
class AccountSpec:
    """Specification for creating a test account."""
    name: str
    status: str  # "pending", "approved", "rejected", "locked"
    email_verified: bool = True
    is_admin: bool = False
    description: str = ""


@dataclass 
class RealmSpec:
    """Specification for creating a test realm."""
    name: str
    account_name: str  # Which account owns this realm
    realm_type: str  # "host", "subdomain", "subdomain_only"
    domain: str
    realm_value: str  # subdomain prefix (empty for apex)
    status: str  # "pending", "approved"
    allowed_record_types: list[str] = field(default_factory=lambda: ["A", "AAAA", "TXT", "CNAME"])
    allowed_operations: list[str] = field(default_factory=lambda: ["read", "update"])
    description: str = ""


@dataclass
class TokenSpec:
    """Specification for creating a test token."""
    name: str
    realm_name: str  # Which realm this token belongs to
    allowed_record_types: Optional[list[str]] = None  # None = inherit from realm
    allowed_operations: Optional[list[str]] = None  # None = inherit from realm
    allowed_ip_ranges: Optional[list[str]] = None  # None = no restriction
    expires_in_hours: Optional[float] = None  # None = never expires
    is_revoked: bool = False
    description: str = ""


@dataclass
class APITestSpec:
    """Specification for an API test against a token."""
    token_name: str
    operation: str  # "read", "update", "create", "delete"
    record_type: str  # "A", "AAAA", "TXT", etc.
    hostname: str  # What hostname to target
    expected_status: int  # 200, 401, 403, etc.
    description: str = ""


# =============================================================================
# ACCOUNT STATE MATRIX
# =============================================================================

ACCOUNTS = [
    AccountSpec(
        name="account-pending",
        status="pending",
        email_verified=True,
        description="Account awaiting admin approval"
    ),
    AccountSpec(
        name="account-approved",
        status="approved",
        email_verified=True,
        description="Approved account, can login and create realms"
    ),
    AccountSpec(
        name="account-rejected",
        status="rejected",
        email_verified=True,
        description="Account rejected by admin"
    ),
    AccountSpec(
        name="account-unverified",
        status="pending",
        email_verified=False,
        description="Account with unverified email"
    ),
]


# =============================================================================
# REALM STATE MATRIX  
# =============================================================================

REALMS = [
    # Host type realms
    RealmSpec(
        name="realm-host-pending",
        account_name="account-approved",
        realm_type="host",
        domain="example.com",
        realm_value="host1",
        status="pending",
        description="Host realm pending approval"
    ),
    RealmSpec(
        name="realm-host-approved",
        account_name="account-approved",
        realm_type="host",
        domain="example.com",
        realm_value="host2",
        status="approved",
        description="Host realm approved, ready for tokens"
    ),
    
    # Subdomain type realms (apex + children)
    RealmSpec(
        name="realm-subdomain-pending",
        account_name="account-approved",
        realm_type="subdomain",
        domain="example.com",
        realm_value="iot",
        status="pending",
        description="Subdomain realm (iot.example.com + children) pending"
    ),
    RealmSpec(
        name="realm-subdomain-approved",
        account_name="account-approved",
        realm_type="subdomain",
        domain="example.com",
        realm_value="k8s",
        status="approved",
        description="Subdomain realm (k8s.example.com + children) approved"
    ),
    
    # Subdomain-only type realms (children only, not apex)
    RealmSpec(
        name="realm-subonly-approved",
        account_name="account-approved",
        realm_type="subdomain_only",
        domain="example.com",
        realm_value="dynamic",
        status="approved",
        description="Subdomain-only realm (*.dynamic.example.com, NOT dynamic.example.com)"
    ),
    
    # Realm with restricted record types
    RealmSpec(
        name="realm-txt-only",
        account_name="account-approved",
        realm_type="subdomain",
        domain="example.com",
        realm_value="acme",
        status="approved",
        allowed_record_types=["TXT"],
        allowed_operations=["read", "create", "delete"],
        description="TXT-only realm for ACME/Let's Encrypt challenges"
    ),
    
    # Full control realm
    RealmSpec(
        name="realm-full-control",
        account_name="account-approved",
        realm_type="subdomain",
        domain="example.com",
        realm_value="managed",
        status="approved",
        allowed_record_types=["A", "AAAA", "TXT", "CNAME", "MX", "SRV"],
        allowed_operations=["read", "update", "create", "delete"],
        description="Full control realm for automation"
    ),
]


# =============================================================================
# TOKEN STATE MATRIX
# =============================================================================

TOKENS = [
    # Read-only token
    TokenSpec(
        name="token-readonly",
        realm_name="realm-subdomain-approved",
        allowed_operations=["read"],
        description="Read-only monitoring token"
    ),
    
    # Update-only token (DDNS use case)
    TokenSpec(
        name="token-ddns",
        realm_name="realm-host-approved",
        allowed_record_types=["A", "AAAA"],
        allowed_operations=["read", "update"],
        description="DDNS updater token"
    ),
    
    # Full access token
    TokenSpec(
        name="token-full",
        realm_name="realm-full-control",
        allowed_operations=["read", "update", "create", "delete"],
        description="Full control automation token"
    ),
    
    # TXT-only token for Let's Encrypt
    TokenSpec(
        name="token-acme",
        realm_name="realm-txt-only",
        allowed_record_types=["TXT"],
        allowed_operations=["read", "create", "delete"],
        description="ACME DNS-01 challenge token"
    ),
    
    # IP-restricted token
    TokenSpec(
        name="token-ip-restricted",
        realm_name="realm-subdomain-approved",
        allowed_ip_ranges=["192.168.1.0/24", "10.0.0.0/8"],
        description="Token only valid from internal networks"
    ),
    
    # Expiring token (expires in 1 hour for testing)
    TokenSpec(
        name="token-expiring",
        realm_name="realm-subdomain-approved",
        expires_in_hours=1.0,
        description="Short-lived token (1 hour)"
    ),
    
    # Already expired token
    TokenSpec(
        name="token-expired",
        realm_name="realm-subdomain-approved",
        expires_in_hours=-1.0,  # Negative = already expired
        description="Already expired token"
    ),
    
    # Revoked token
    TokenSpec(
        name="token-revoked",
        realm_name="realm-subdomain-approved",
        is_revoked=True,
        description="Revoked token (should fail auth)"
    ),
    
    # Multiple tokens for same realm (to test token list UI)
    TokenSpec(
        name="token-full-control-1",
        realm_name="realm-full-control",
        allowed_operations=["read", "update", "create", "delete"],
        description="First full control token"
    ),
    TokenSpec(
        name="token-full-control-2",
        realm_name="realm-full-control",
        allowed_operations=["read", "update"],
        description="Second token with fewer permissions"
    ),
    TokenSpec(
        name="token-full-control-3",
        realm_name="realm-full-control",
        allowed_record_types=["A"],
        allowed_operations=["read", "update"],
        description="Third token - A records only"
    ),
]


# =============================================================================
# API TEST MATRIX
# =============================================================================

@dataclass
class SecurityTestSpec:
    """
    Specification for a security-focused API test.
    
    Tests authentication/authorization failures with specific error codes.
    See docs/SECURITY_ERROR_TAXONOMY.md for error code definitions.
    """
    name: str
    description: str
    
    # Token manipulation
    token_name: Optional[str] = None  # Use this token (None = construct from token_format)
    token_format: Optional[str] = None  # e.g., "naf_unknown_user_abc123" for crafted tokens
    
    # Request details
    operation: str = "read"
    domain: str = "example.com"
    hostname: str = "test"
    record_type: str = "A"
    
    # Simulated source
    source_ip: Optional[str] = None  # None = actual client IP
    
    # Expected outcome
    expected_status: int = 401  # HTTP status code
    expected_error_code: str = ""  # e.g., "token_expired", "ip_denied"
    
    # Attribution check
    should_be_attributable: bool = False  # Is the account/token identifiable from the failure?
    should_notify_user: bool = False  # Should this trigger a user notification?
    
    # Severity level
    severity: str = "low"  # low, medium, high, critical


API_TESTS = [
    # =========================================================================
    # SUCCESSFUL OPERATIONS (baseline)
    # =========================================================================
    APITestSpec(
        token_name="token-readonly",
        operation="read",
        record_type="A",
        hostname="k8s.example.com",
        expected_status=200,
        description="Read-only token can read records"
    ),
    APITestSpec(
        token_name="token-ddns",
        operation="update",
        record_type="A",
        hostname="host2.example.com",
        expected_status=200,
        description="DDNS token can update A records"
    ),
    APITestSpec(
        token_name="token-full",
        operation="create",
        record_type="TXT",
        hostname="test.managed.example.com",
        expected_status=200,
        description="Full token can create TXT records"
    ),
    APITestSpec(
        token_name="token-acme",
        operation="create",
        record_type="TXT",
        hostname="_acme-challenge.acme.example.com",
        expected_status=200,
        description="ACME token can create TXT challenges"
    ),
    
    # =========================================================================
    # AUTHORIZATION FAILURES (permission denied - 403)
    # =========================================================================
    APITestSpec(
        token_name="token-readonly",
        operation="update",
        record_type="A",
        hostname="k8s.example.com",
        expected_status=403,
        description="Read-only token cannot update"
    ),
    APITestSpec(
        token_name="token-ddns",
        operation="delete",
        record_type="A",
        hostname="host2.example.com",
        expected_status=403,
        description="DDNS token cannot delete"
    ),
    APITestSpec(
        token_name="token-acme",
        operation="create",
        record_type="A",
        hostname="acme.example.com",
        expected_status=403,
        description="ACME token cannot create A records"
    ),
    
    # Wrong realm scenarios
    APITestSpec(
        token_name="token-ddns",
        operation="read",
        record_type="A",
        hostname="other.example.com",  # Not in host2 realm
        expected_status=403,
        description="Token cannot access outside its realm"
    ),
    
    # =========================================================================
    # AUTHENTICATION FAILURES (token invalid - 401)
    # =========================================================================
    APITestSpec(
        token_name="token-expired",
        operation="read",
        record_type="A",
        hostname="k8s.example.com",
        expected_status=401,
        description="Expired token gets 401"
    ),
    APITestSpec(
        token_name="token-revoked",
        operation="read",
        record_type="A",
        hostname="k8s.example.com",
        expected_status=401,
        description="Revoked token gets 401"
    ),
]


# =============================================================================
# SECURITY-FOCUSED TEST MATRIX (Extended)
# =============================================================================

SECURITY_TESTS = [
    # =========================================================================
    # AUTHENTICATION ERRORS (Token Validation)
    # =========================================================================
    
    # invalid_format: Token doesn't match naf_*_* pattern
    SecurityTestSpec(
        name="auth-invalid-format-random",
        description="Random string instead of token",
        token_format="this-is-not-a-valid-token",
        expected_status=401,
        expected_error_code="invalid_format",
        should_be_attributable=False,  # Can't identify user
        severity="low",
    ),
    SecurityTestSpec(
        name="auth-invalid-format-bearer-only",
        description="Empty bearer token",
        token_format="",
        expected_status=401,
        expected_error_code="missing_token",  # Or could be validation error
        should_be_attributable=False,
        severity="low",
    ),
    SecurityTestSpec(
        name="auth-invalid-format-sql-injection",
        description="SQL injection attempt in token",
        token_format="naf_admin'; DROP TABLE accounts; --_abc123",
        expected_status=401,
        expected_error_code="invalid_format",
        should_be_attributable=False,
        severity="low",  # Low because no attribution possible
    ),
    
    # alias_not_found: Valid format but user_alias doesn't exist
    SecurityTestSpec(
        name="auth-alias-not-found",
        description="Token with non-existent user_alias",
        token_format="naf_abcd1234efgh5678_abcdef12345678901234567890123456789012345678901234567890123456",
        expected_status=401,
        expected_error_code="alias_not_found",
        should_be_attributable=False,  # Alias doesn't exist
        severity="medium",  # Could be credential stuffing
    ),
    
    # token_prefix_not_found: Alias exists but no token with this prefix
    SecurityTestSpec(
        name="auth-token-prefix-not-found",
        description="Valid user_alias but wrong token prefix",
        token_format="naf_VALID_ALIAS_HERE_wrongpreabcdef12345678901234567890123456789012345678901234",
        expected_status=401,
        expected_error_code="token_prefix_not_found",
        should_be_attributable=True,  # We know which account is targeted!
        should_notify_user=True,  # Notify account owner
        severity="high",
    ),
    
    # token_hash_mismatch: Correct user+prefix, wrong hash (BRUTE FORCE!)
    SecurityTestSpec(
        name="auth-hash-mismatch-brute-force",
        description="Correct prefix but wrong token body - potential brute force",
        # Note: test needs to use actual account-approved's token prefix but wrong body
        token_format="DYNAMIC:account-approved:wrongbody",  # Special marker for test
        expected_status=401,
        expected_error_code="token_hash_mismatch",
        should_be_attributable=True,  # We know WHICH token is under attack
        should_notify_user=True,  # CRITICAL: Notify user immediately
        severity="critical",
    ),
    
    # account_disabled: Account is_active=False
    SecurityTestSpec(
        name="auth-account-disabled",
        description="Token for disabled account",
        token_name="token-for-disabled-account",  # Created in test setup
        expected_status=401,
        expected_error_code="account_disabled",
        should_be_attributable=True,
        should_notify_user=False,  # Admin should know, not user
        severity="medium",
    ),
    
    # token_expired: Past expires_at
    SecurityTestSpec(
        name="auth-token-expired",
        description="Expired token still being used",
        token_name="token-expired",
        expected_status=401,
        expected_error_code="token_expired",
        should_be_attributable=True,
        should_notify_user=False,  # Expected behavior, maybe reminder
        severity="low",
    ),
    
    # token_revoked: is_active=False
    SecurityTestSpec(
        name="auth-token-revoked",
        description="Revoked token still in use - possible credential theft",
        token_name="token-revoked",
        expected_status=401,
        expected_error_code="token_revoked",
        should_be_attributable=True,
        should_notify_user=True,  # Token may have been stolen before revocation
        severity="high",
    ),
    
    # realm_not_approved: Realm status != 'approved'
    SecurityTestSpec(
        name="auth-realm-not-approved",
        description="Token for unapproved realm",
        token_name="token-for-pending-realm",  # Created in test setup
        expected_status=401,
        expected_error_code="realm_not_approved",
        should_be_attributable=True,
        should_notify_user=False,
        severity="low",
    ),
    
    # =========================================================================
    # AUTHORIZATION ERRORS (Permission Checks)
    # =========================================================================
    
    # ip_denied: IP not in whitelist
    SecurityTestSpec(
        name="authz-ip-denied",
        description="Request from IP not in token whitelist",
        token_name="token-ip-restricted",
        source_ip="203.0.113.42",  # Not in 192.168.1.0/24 or 10.0.0.0/8
        expected_status=403,
        expected_error_code="ip_denied",
        should_be_attributable=True,
        should_notify_user=True,  # Unexpected location - potential compromise
        severity="critical",
    ),
    
    # domain_denied: Domain outside realm scope
    SecurityTestSpec(
        name="authz-domain-denied",
        description="Trying to access domain outside realm",
        token_name="token-ddns",
        domain="different-domain.com",
        expected_status=403,
        expected_error_code="domain_denied",
        should_be_attributable=True,
        should_notify_user=True,  # Scope probing attempt
        severity="high",
    ),
    
    # operation_denied: Operation not in allowed list
    SecurityTestSpec(
        name="authz-operation-denied-delete",
        description="Trying to delete with update-only token",
        token_name="token-ddns",
        operation="delete",
        expected_status=403,
        expected_error_code="operation_denied",
        should_be_attributable=True,
        should_notify_user=False,  # May be user error
        severity="medium",
    ),
    SecurityTestSpec(
        name="authz-operation-denied-create",
        description="Trying to create with read-only token",
        token_name="token-readonly",
        operation="create",
        expected_status=403,
        expected_error_code="operation_denied",
        should_be_attributable=True,
        should_notify_user=False,
        severity="medium",
    ),
    
    # record_type_denied: Record type not in allowed list
    SecurityTestSpec(
        name="authz-record-type-denied",
        description="TXT-only token trying A record",
        token_name="token-acme",
        operation="create",
        record_type="A",
        expected_status=403,
        expected_error_code="record_type_denied",
        should_be_attributable=True,
        should_notify_user=False,
        severity="low",
    ),
    
    # =========================================================================
    # ATTACK PATTERN TESTS (sequences)
    # =========================================================================
    
    SecurityTestSpec(
        name="pattern-brute-force-simulation",
        description="Multiple failed hash attempts (simulated brute force)",
        token_format="BRUTE_FORCE:account-approved:5",  # 5 attempts
        expected_status=401,
        expected_error_code="token_hash_mismatch",
        should_be_attributable=True,
        should_notify_user=True,
        severity="critical",
    ),
    
    SecurityTestSpec(
        name="pattern-credential-stuffing",
        description="Multiple non-existent aliases from same IP",
        token_format="CREDENTIAL_STUFFING:5",  # 5 different fake aliases
        expected_status=401,
        expected_error_code="alias_not_found",
        should_be_attributable=False,
        should_notify_user=False,  # No specific user to notify
        severity="medium",
    ),
    
    SecurityTestSpec(
        name="pattern-scope-probing",
        description="Sequential domain tests to find accessible resources",
        token_name="token-ddns",
        domain="SCOPE_PROBE:5",  # Try 5 different domains
        expected_status=403,
        expected_error_code="domain_denied",
        should_be_attributable=True,
        should_notify_user=True,
        severity="high",
    ),
]


# =============================================================================
# NOTIFICATION TRIGGER MATRIX
# =============================================================================

@dataclass
class NotificationTrigger:
    """Defines when to send notifications based on error patterns."""
    name: str
    description: str
    error_codes: list[str]  # Which error codes trigger this
    threshold: int = 1  # How many occurrences before triggering
    window_minutes: int = 60  # Time window for threshold
    notify_user: bool = False
    notify_admin: bool = False
    severity: str = "medium"


NOTIFICATION_TRIGGERS = [
    NotificationTrigger(
        name="brute-force-detected",
        description="Multiple hash mismatches for same token/user",
        error_codes=["token_hash_mismatch"],
        threshold=3,
        window_minutes=5,
        notify_user=True,
        notify_admin=True,
        severity="critical",
    ),
    NotificationTrigger(
        name="ip-access-blocked",
        description="Access from non-whitelisted IP",
        error_codes=["ip_denied"],
        threshold=1,
        window_minutes=1,
        notify_user=True,
        notify_admin=False,
        severity="high",
    ),
    NotificationTrigger(
        name="revoked-token-use",
        description="Revoked token still being used",
        error_codes=["token_revoked"],
        threshold=1,
        window_minutes=1,
        notify_user=True,
        notify_admin=True,
        severity="high",
    ),
    NotificationTrigger(
        name="credential-stuffing",
        description="Many non-existent aliases from same IP",
        error_codes=["alias_not_found"],
        threshold=10,
        window_minutes=10,
        notify_user=False,
        notify_admin=True,
        severity="medium",
    ),
    NotificationTrigger(
        name="scope-escalation",
        description="Attempts to access unauthorized domains",
        error_codes=["domain_denied"],
        threshold=3,
        window_minutes=10,
        notify_user=True,
        notify_admin=True,
        severity="high",
    ),
    NotificationTrigger(
        name="expired-token-reminder",
        description="Expired token used multiple times",
        error_codes=["token_expired"],
        threshold=5,
        window_minutes=1440,  # 24 hours
        notify_user=True,
        notify_admin=False,
        severity="low",
    ),
]


# =============================================================================
# UI SCREENSHOT MATRIX
# =============================================================================

UI_SCREENSHOTS = [
    # Account states in admin view
    ("admin-accounts-list", "Admin view: All account states visible"),
    ("admin-accounts-pending", "Admin view: Pending accounts for approval"),
    ("admin-account-detail-approved", "Admin view: Approved account detail"),
    ("admin-account-detail-pending", "Admin view: Pending account detail"),
    
    # Realm states in admin view
    ("admin-realms-list", "Admin view: All realm types and states"),
    ("admin-realms-pending", "Admin view: Pending realms for approval"),
    ("admin-realm-detail-host", "Admin view: Host realm detail"),
    ("admin-realm-detail-subdomain", "Admin view: Subdomain realm detail"),
    ("admin-realm-detail-subonly", "Admin view: Subdomain-only realm detail"),
    
    # Token states
    ("admin-tokens-list", "Admin view: Tokens with various states"),
    ("admin-token-detail-active", "Admin view: Active token detail"),
    ("admin-token-detail-expired", "Admin view: Expired token detail"),
    ("admin-token-detail-revoked", "Admin view: Revoked token detail"),
    
    # User account view
    ("account-dashboard", "User: Dashboard with realms and tokens"),
    ("account-realms-list", "User: Realm list (approved + pending)"),
    ("account-realm-detail", "User: Realm detail with tokens"),
    ("account-tokens-list", "User: Token list with status indicators"),
    ("account-token-create", "User: Token creation form"),
    
    # Audit log
    ("audit-log-api-calls", "Audit: API call history"),
    ("audit-log-filtered", "Audit: Filtered by token/action"),
    
    # Security dashboard
    ("security-dashboard-empty", "Security: Dashboard before any events"),
    ("security-dashboard-with-events", "Security: Dashboard with security events"),
    ("security-dashboard-attack-detected", "Security: Attack pattern detected"),
    ("security-events-filtered", "Security: Events filtered by severity"),
    
    # Account security operations (Journey 7)
    ("alias-rotation-modal", "Security: Credential rotation confirmation modal"),
    ("alias-rotation-success", "Security: Credential rotation success message"),
    ("alias-rotation-audit-log", "Security: Rotation logged in audit"),
    ("email-change-modal", "Security: Email change modal"),
    ("email-change-invalid-format", "Security: Invalid email format error"),
    ("email-change-duplicate", "Security: Duplicate email error"),
    ("email-change-success", "Security: Email change success"),
    ("email-change-audit-log", "Security: Email change logged in audit"),
    ("security-actions-card", "Security: Security actions card on account detail"),
]


# =============================================================================
# ROUTE CLASSIFICATION FOR AUTH ENFORCEMENT
# =============================================================================

# Public routes (no auth required)
PUBLIC_ROUTES = {
    '/',
    '/health',
    '/component-demo',
    '/component-demo-bs5',
    '/admin/login',
    '/account/login',
    '/account/register',
    '/account/forgot-password',
    '/account/reset-password/<token>',
    '/account/register/verify',
    '/account/register/pending',
}

# Admin routes requiring admin session
ADMIN_ROUTES = [
    '/admin/',
    '/admin/accounts',
    '/admin/accounts/pending',
    '/admin/accounts/<id>',
    '/admin/accounts/new',
    '/admin/accounts/<id>/approve',
    '/admin/accounts/<id>/delete',
    '/admin/accounts/<id>/disable',
    '/admin/accounts/<id>/reset-password',
    '/admin/accounts/<id>/regenerate-alias',  # Rotate API credentials
    '/admin/accounts/<id>/change-email',       # Change email address
    '/admin/accounts/<id>/realms/new',
    '/admin/realms',
    '/admin/realms/<id>',
    '/admin/realms/pending',
    '/admin/realms/<id>/approve',
    '/admin/realms/<id>/reject',
    '/admin/tokens/<id>',
    '/admin/tokens/<id>/revoke',
    '/admin/audit',
    '/admin/audit/export',
    '/admin/security',
    '/admin/config/netcup',
    '/admin/config/email',
    '/admin/config/email/test',
    '/admin/system',
    '/admin/system/security',
    '/admin/change-password',
    '/admin/logout',
    '/admin/api/accounts',
    '/admin/api/stats',
    '/admin/api/security/stats',
    '/admin/api/security/timeline',
    '/admin/api/security/events',
    '/admin/api/bulk/accounts',
    '/admin/api/bulk/realms',
]

# Account routes requiring account session
ACCOUNT_ROUTES = [
    '/account/dashboard',
    '/account/realms',
    '/account/realms/<id>',
    '/account/tokens',
    '/account/settings',
    '/account/change-password',
]

# API routes requiring Bearer token
API_ROUTES = [
    '/api/dns/<domain>/records',
    '/api/ddns/<domain>/<hostname>',
    '/filter-proxy/api/dns/<domain>/records',
]


def get_all_specs():
    """Get all test specifications for journey execution."""
    return {
        "accounts": ACCOUNTS,
        "realms": REALMS,
        "tokens": TOKENS,
        "api_tests": API_TESTS,
        "security_tests": SECURITY_TESTS,
        "notification_triggers": NOTIFICATION_TRIGGERS,
        "screenshots": UI_SCREENSHOTS,
        "routes": {
            "public": PUBLIC_ROUTES,
            "admin": ADMIN_ROUTES,
            "account": ACCOUNT_ROUTES,
            "api": API_ROUTES,
        },
    }
