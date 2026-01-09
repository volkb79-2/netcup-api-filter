# Deep Dive Review: Authentication & Security Architecture

## Context

The application implements a multi-layered security model:
- **Admin Portal**: Session-based auth with password policies, 2FA enforcement
- **Account Portal**: Session-based auth for account holders
- **API Endpoints**: Bearer token authentication with realm-based authorization
- **DDNS Protocols**: DynDNS2/No-IP compatibility with bearer token auth
- **Rate Limiting**: Per-endpoint, per-IP rate limits
- **IP Whitelisting**: Network/CIDR-based access control
- **Audit Logging**: Comprehensive security event tracking

## Review Objective

Verify that the security architecture is:
1. **Defense-in-depth** - Multiple layers of security controls
2. **Correctly implemented** - No bypasses or gaps
3. **Production-hardened** - Handles attacks, rate limits, edge cases
4. **Auditable** - All security events properly logged

## Review Checklist

### 1. Password Security

**Files:** `src/netcup_api_filter/models.py`, `src/netcup_api_filter/api/admin.py`

- [ ] **Hash algorithm**: bcrypt with proper work factor (10-12 rounds)
- [ ] **Password validation**: Enforces strength requirements
  - [ ] Minimum length (12+ characters)
  - [ ] Complexity requirements (uppercase, lowercase, digit, special)
  - [ ] No common passwords (dictionary check)
  - [ ] No username/email substring
- [ ] **Password change enforcement**: `must_change_password` flag honored
- [ ] **Old password verification**: Required for password changes
- [ ] **Password history**: Prevents reuse of recent passwords
- [ ] **Plaintext never stored**: Only bcrypt hashes in database
- [ ] **Timing-safe comparison**: Uses constant-time comparison for tokens

**Test:**
```python
from netcup_api_filter.models import Account
from netcup_api_filter.utils import hash_password, verify_password

# Test bcrypt hashing
password = "TestPassword123!"
hashed = hash_password(password)
assert hashed.startswith('$2b$'), "Not bcrypt hash"
assert verify_password(password, hashed), "Verification failed"
assert not verify_password("wrong", hashed), "Accepted wrong password"
```

### 2. Session Management

**Files:** `src/netcup_api_filter/app.py`, session handling in routes

- [ ] **Session security flags**:
  - [ ] `SESSION_COOKIE_SECURE` = auto (True in production, False in local_test)
  - [ ] `SESSION_COOKIE_HTTPONLY` = True (XSS protection)
  - [ ] `SESSION_COOKIE_SAMESITE` = Lax (CSRF protection)
- [ ] **Session lifetime**: Configurable timeout (default 1 hour)
- [ ] **Session invalidation**: Logout clears session completely
- [ ] **Session regeneration**: New session ID after login (prevents fixation)
- [ ] **Concurrent sessions**: Multiple sessions per user allowed
- [ ] **Session storage**: Server-side storage (not client cookies)

**Test:**
```bash
# Verify session cookies secure in production
curl -I https://$PUBLIC_FQDN/ | grep -i "Set-Cookie"
# Should show: Secure; HttpOnly; SameSite=Lax
```

### 3. Bearer Token Authentication

**Files:** `src/netcup_api_filter/token_auth.py`, `src/netcup_api_filter/models.py`

- [ ] **Token format**: `naf_<alias>_<random64>` correctly validated
- [ ] **Token storage**: bcrypt hashed in database (not plaintext)
- [ ] **Token generation**: Cryptographically random (32 bytes from secrets module)
- [ ] **Prefix extraction**: Correct extraction of token prefix for lookups
- [ ] **Expiration checking**: Expired tokens rejected
- [ ] **Disabled token check**: Inactive tokens rejected
- [ ] **Alias validation**: Alphanumeric + hyphens only (prevents injection)
- [ ] **Token shown once**: Only displayed at creation, never retrieved
- [ ] **Authorization header**: `Authorization: Bearer <token>` properly parsed
- [ ] **Error responses**: 401 for all auth failures (no timing leaks)

**Test:**
```python
from netcup_api_filter.token_auth import authenticate_token

# Test valid token
result = authenticate_token("naf_test_" + "a"*64)
assert result.authenticated, "Valid token rejected"

# Test invalid format
result = authenticate_token("invalid-token")
assert not result.authenticated, "Invalid format accepted"

# Test expired token
# (Create token with past expiration, verify rejected)
```

### 4. Realm-Based Authorization

**Files:** `src/netcup_api_filter/token_auth.py::check_permission()`

- [ ] **Realm matching**: Host, subdomain, wildcard correctly enforced
- [ ] **Record type filtering**: Only allowed types permitted
- [ ] **Operation filtering**: read/create/update/delete correctly enforced
- [ ] **Domain validation**: Ensures domain within realm scope
- [ ] **Subdomain depth**: Min/max depth limits enforced
- [ ] **Apex access**: `allow_apex_access` honored
- [ ] **Wildcard handling**: Wildcards only match subdomains (not apex)
- [ ] **Case insensitivity**: Domain comparisons case-insensitive

**Test:**
```python
from netcup_api_filter.token_auth import check_permission

# Test subdomain realm
realm_value = "sub.example.com"
realm_type = "subdomain"

# Should allow sub.example.com, a.sub.example.com
assert check_permission(realm_value, realm_type, "sub.example.com", ["A"], ["update"])
assert check_permission(realm_value, realm_type, "a.sub.example.com", ["A"], ["update"])

# Should deny example.com (apex), other.example.com (outside realm)
assert not check_permission(realm_value, realm_type, "example.com", ["A"], ["update"])
assert not check_permission(realm_value, realm_type, "other.example.com", ["A"], ["update"])
```

### 5. IP Whitelisting

**Files:** `src/netcup_api_filter/token_auth.py::validate_dns_records_update()`

- [ ] **CIDR parsing**: Correctly parses IPv4/IPv6 CIDR notation
- [ ] **Network matching**: Source IP checked against allowed networks
- [ ] **X-Forwarded-For handling**: Reads real IP from proxy headers
- [ ] **Null whitelist**: Empty whitelist = allow all (not deny all)
- [ ] **Invalid CIDR handling**: Logs errors, fails safe (denies access)
- [ ] **IPv6 support**: Handles both IPv4 and IPv6 addresses
- [ ] **Network size limits**: Prevents /0 (entire internet)

**Test:**
```python
from netcup_api_filter.token_auth import validate_dns_records_update
from netcup_api_filter.models import AuthToken, Realm

# Create realm with IP whitelist
realm = Realm(allowed_ip_ranges=['192.168.1.0/24'])

# Test within range
result, error, code = validate_dns_records_update(
    auth_result, "example.com", records, "192.168.1.100"
)
assert result, "Allowed IP rejected"

# Test outside range
result, error, code = validate_dns_records_update(
    auth_result, "example.com", records, "10.0.0.1"
)
assert not result, "Blocked IP accepted"
```

### 6. Rate Limiting

**Files:** `src/netcup_api_filter/app.py`, rate limit decorators

- [ ] **Global limits**: Default limits applied to all routes
- [ ] **Per-endpoint limits**: Specific limits for sensitive endpoints
- [ ] **Key function**: Uses `get_remote_address()` for per-IP limits
- [ ] **Storage**: In-memory storage (Redis for production)
- [ ] **Response codes**: 429 Too Many Requests with Retry-After header
- [ ] **Health check exemption**: `/` endpoint exempt from limits
- [ ] **API endpoint limits**: Stricter limits on auth endpoints
- [ ] **Configuration**: Limits configurable via `.env.defaults`
- [ ] **Testing override**: Disabled via `FLASK_ENV=local_test`

**Test:**
```bash
# Test rate limiting (should hit 429 after limit)
for i in {1..100}; do
  curl -w "%{http_code}\n" -o /dev/null \
    -H "Authorization: Bearer invalid-token" \
    https://$PUBLIC_FQDN/api/dns/test.com/records
done
# Expect 401 responses initially, then 429 after exceeding limit
```

### 7. CSRF Protection

**Files:** `src/netcup_api_filter/app.py`, form templates

- [ ] **Flask-WTF CSRF**: Enabled for all forms
- [ ] **Token in forms**: `{{ csrf_token() }}` in all form templates
- [ ] **API exemption**: DNS API and DDNS endpoints exempt (use Bearer auth)
- [ ] **Token validation**: Invalid CSRF token rejects form submission
- [ ] **Token expiration**: CSRF tokens expire with session
- [ ] **Double-submit cookie**: CSRF token in cookie + form field

**Test:**
```bash
# Test CSRF protection (should reject without token)
curl -X POST https://$PUBLIC_FQDN/admin/accounts/create \
  -d "username=test&password=test" \
  -b "session=..." \
  -w "%{http_code}\n"
# Expect 400 or 403 (CSRF token missing)
```

### 8. 2FA Enforcement (TOTP)

**Files:** `src/netcup_api_filter/api/admin.py`, 2FA views

- [ ] **TOTP generation**: Generates valid TOTP secrets
- [ ] **QR code display**: Shows scannable QR code for enrollment
- [ ] **Verification**: Validates 6-digit TOTP codes
- [ ] **Time window**: Accepts codes within ±1 time window (30 seconds)
- [ ] **Rate limiting**: Prevents brute force of TOTP codes
- [ ] **Mandatory flag**: `totp_enabled_mandatory` enforced at login
- [ ] **Backup codes**: Optional backup codes for recovery
- [ ] **Secret storage**: TOTP secret encrypted in database

**Test:**
```python
import pyotp
from netcup_api_filter.models import Account

# Test TOTP generation
account = Account.query.filter_by(username='admin').first()
totp = pyotp.TOTP(account.totp_secret)
code = totp.now()

# Verify code acceptance
assert account.verify_totp(code), "Valid TOTP rejected"
assert not account.verify_totp("000000"), "Invalid TOTP accepted"
```

### 9. Audit Logging

**Files:** `src/netcup_api_filter/token_auth.py::log_activity()`, `src/netcup_api_filter/models.py::ActivityLog`

- [ ] **Activity types**: All security events logged (login, failed_auth, token_create, dns_update)
- [ ] **Context capture**: IP, user agent, account, realm, token captured
- [ ] **Request data**: Sanitized request details stored
- [ ] **Response summary**: Success/failure status recorded
- [ ] **Severity levels**: info, warning, error, critical properly assigned
- [ ] **Error codes**: Standardized error codes (unauthorized, forbidden, rate_limit_exceeded)
- [ ] **Timestamp accuracy**: UTC timestamps with timezone
- [ ] **Log retention**: Configurable retention policy
- [ ] **Secret redaction**: No passwords, full tokens, API keys in logs

**Test:**
```python
from netcup_api_filter.models import ActivityLog

# Test activity logging
log_activity(
    account=account,
    realm=realm,
    token=token,
    activity_type="dns_update",
    source_ip="192.168.1.1",
    status="success"
)

# Verify log created
log = ActivityLog.query.order_by(ActivityLog.created_at.desc()).first()
assert log.activity_type == "dns_update"
assert log.source_ip == "192.168.1.1"
assert log.status == "success"
```

### 10. Error Handling & Information Disclosure

**Cross-cutting security concerns**

- [ ] **Generic error messages**: No stack traces in production
- [ ] **Timing attacks**: Constant-time comparison for secrets
- [ ] **Enumeration protection**: Same error for "user not found" and "wrong password"
- [ ] **Debug mode**: Debug disabled in production (`FLASK_ENV` != 'development')
- [ ] **Error logging**: Errors logged server-side, not shown to client
- [ ] **404 handling**: Custom 404 page (no Flask debug)
- [ ] **Exception handling**: Try/except around all external calls
- [ ] **SQL injection**: Use parameterized queries (ORM)
- [ ] **XSS prevention**: Template auto-escaping enabled
- [ ] **Path traversal**: No user input in file paths

### 11. DDNS Protocol Security

**Files:** `src/netcup_api_filter/api/ddns_protocols.py`

- [ ] **No username/password**: Only bearer token auth (no Basic auth fallback)
- [ ] **Protocol compliance**: Correct response codes (good, nochg, badauth, etc.)
- [ ] **IP validation**: Validates myip parameter format
- [ ] **Auto IP detection**: Safe extraction of client IP
- [ ] **Realm authorization**: Enforces realm permissions
- [ ] **Rate limiting**: Applies rate limits to DDNS endpoints
- [ ] **Activity logging**: All updates logged
- [ ] **Error responses**: Protocol-compliant text responses (not JSON leaks)

**Test:**
```bash
# Test DDNS auth (should reject without bearer token)
curl "https://$PUBLIC_FQDN/api/ddns/dyndns2/update?hostname=test.com&myip=1.2.3.4"
# Expect: badauth

# Test with valid bearer token
curl "https://$PUBLIC_FQDN/api/ddns/dyndns2/update?hostname=test.com&myip=1.2.3.4" \
  -H "Authorization: Bearer naf_test_..."
# Expect: good 1.2.3.4 or nochg 1.2.3.4
```

### 12. Environment Variable Security

**Files:** `.env.defaults`, config loading

- [ ] **No secrets in defaults**: `.env.defaults` has no sensitive values
- [ ] **Secret keys random**: `SECRET_KEY` generated per deployment
- [ ] **Environment override**: Secrets loaded from environment, not hardcoded
- [ ] **Config validation**: Fail-fast if required secrets missing
- [ ] **Dotenv loading**: `.env` files not committed to git
- [ ] **Deployment state**: Secrets stored securely in deployment state files

### 13. Database Security

**Files:** `src/netcup_api_filter/models.py`, database configuration

- [ ] **Password hashing**: All passwords bcrypt hashed
- [ ] **Token hashing**: API tokens bcrypt hashed
- [ ] **SQL injection**: ORM prevents SQL injection
- [ ] **Foreign key constraints**: Enforced at database level
- [ ] **Indexes on sensitive fields**: Efficient lookups without full scans
- [ ] **Unique constraints**: Prevent duplicate users/tokens
- [ ] **Connection pooling**: Database connections properly managed
- [ ] **Transaction isolation**: Proper transaction boundaries

### 14. Security Headers

**Files:** `src/netcup_api_filter/app.py`

- [ ] **X-Frame-Options**: DENY or SAMEORIGIN (clickjacking protection)
- [ ] **X-Content-Type-Options**: nosniff (MIME sniffing protection)
- [ ] **X-XSS-Protection**: 1; mode=block (XSS filter)
- [ ] **Strict-Transport-Security**: HTTPS enforcement
- [ ] **Content-Security-Policy**: Restricts resource loading
- [ ] **Referrer-Policy**: Controls referrer information

**Test:**
```bash
curl -I https://$PUBLIC_FQDN/ | grep -E "(X-Frame-Options|X-Content-Type-Options|Strict-Transport-Security)"
```

### 15. Production Hardening

**Deployment security checks**

- [ ] **TLS certificates**: Valid Let's Encrypt certificates
- [ ] **TLS version**: TLS 1.2+ only (no SSLv3, TLS 1.0/1.1)
- [ ] **Cipher suites**: Strong ciphers only (no RC4, DES, MD5)
- [ ] **HTTP → HTTPS redirect**: All HTTP redirects to HTTPS
- [ ] **Port exposure**: Only 443 externally exposed
- [ ] **File permissions**: Config files not world-readable
- [ ] **Log permissions**: Log files protected
- [ ] **Database permissions**: Database file not world-readable
- [ ] **Process user**: App runs as non-root user
- [ ] **Dependency updates**: Regular security updates

## Security Testing Scenarios

### 1. Authentication Bypass Attempts

```python
# Test token authentication bypass attempts
test_cases = [
    ("", "Empty token"),
    ("Bearer", "Bearer without token"),
    ("naf_test_" + "a"*63, "Token too short"),
    ("naf_test_" + "a"*65, "Token too long"),
    ("naf_<script>_" + "a"*64, "XSS attempt in alias"),
    ("naf_test_../../../etc/passwd", "Path traversal attempt"),
    ("naf_test_' OR '1'='1", "SQL injection attempt"),
]

for token, description in test_cases:
    result = authenticate_token(token)
    assert not result.authenticated, f"Bypass via {description}"
```

### 2. Authorization Bypass Attempts

```python
# Test realm authorization bypass attempts
test_cases = [
    ("example.com", "sub.example.com", "Access parent from subdomain realm"),
    ("a.example.com", "b.example.com", "Access sibling subdomain"),
    ("example.com", "../evil.com", "Path traversal in domain"),
    ("example.com", "example.com.evil.com", "Suffix matching bypass"),
]

for realm, domain, description in test_cases:
    result = check_permission(realm, "subdomain", domain, ["A"], ["update"])
    assert not result, f"Bypass via {description}"
```

### 3. Rate Limit Bypass Attempts

```bash
# Test rate limit bypass attempts
# 1. Different source IPs (requires IP spoofing - should fail)
# 2. Different User-Agents (should not bypass - same IP)
# 3. Multiple tokens (should still hit per-IP limit)
# 4. Randomized paths (should hit global limit)
```

### 4. Session Security Tests

```python
# Test session security
# 1. Session fixation (should generate new session ID after login)
# 2. Session hijacking (should require CSRF token)
# 3. Concurrent sessions (should allow multiple sessions)
# 4. Session expiration (should logout after timeout)
```

## Expected Deliverable

**Comprehensive security report structured as:**

```markdown
# Authentication & Security Architecture - Security Review

## Executive Summary
- Security posture: ✅ Strong | ⚠️ Moderate | ❌ Weak
- Critical vulnerabilities: [count]
- Security issues requiring immediate attention: [list]

## Security Controls Analysis

### 1. Password Security
- Status: [✅/⚠️/❌]
- Findings: [list]
- Evidence: [test results]

### 2. Session Management
...

[Continue for all 15 sections]

## Vulnerability Summary

### Critical (P0 - Immediate Fix Required)
1. [Vulnerability] - Location: [file:line] - CVSS Score: [score]

### High (P1 - Fix Within 7 Days)
...

### Medium (P2 - Fix Within 30 Days)
...

### Low (P3 - Fix When Possible)
...

## Security Recommendations

### Immediate Actions
1. [Specific action item with code reference]

### Short-term Improvements
...

### Long-term Enhancements
...

## Compliance Status

- [ ] OWASP Top 10 coverage
- [ ] CWE/SANS Top 25 coverage
- [ ] PCI DSS requirements (if applicable)
- [ ] GDPR requirements (if applicable)

## Code References
- [File:line] - [Security finding]
```

---

## Usage

```
Please perform a comprehensive security review of the authentication and authorization architecture using the checklist and methodology defined in .vscode/REVIEW_PROMPT_AUTH_SECURITY.md.

Focus on:
1. Verifying all security controls are properly implemented
2. Testing for common vulnerabilities (OWASP Top 10)
3. Validating defense-in-depth approach
4. Identifying any security gaps or weaknesses

Provide a structured security report with findings, CVSS scores, and remediation recommendations.
```
