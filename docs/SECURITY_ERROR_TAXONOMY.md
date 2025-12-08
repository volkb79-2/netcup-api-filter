# Security Error Taxonomy

This document defines the classification of authentication/authorization errors,
their security implications, and notification policies.

## Token Format

```
naf_<user_alias>_<random64>
    │             └── 64-char random (first 8 = prefix, stored in DB)
    └── 16-char random alias (alphanumeric, unique per account)
```

**Security advantage**: The `user_alias` is a random 16-character identifier,
NOT the username. This prevents API tokens from disclosing login credentials.

**Key insight**: Even failed auth attempts can be attributed to specific accounts
if the user_alias is valid. This enables targeted security notifications.

---

## Error Categories

### 1. Authentication Errors (Token Validation)

| Error Code | Description | User Attributable? | Severity | Action |
|------------|-------------|-------------------|----------|--------|
| `invalid_format` | Token doesn't match `naf_*_*` pattern | ❌ No | Low | Log only |
| `alias_not_found` | Format valid but user_alias doesn't exist | ❌ No | Medium | Log + rate limit |
| `token_prefix_not_found` | Alias exists but no token with prefix | ✅ **Yes** | High | Log + **notify user** |
| `token_hash_mismatch` | Alias+prefix exist but hash fails | ✅ **Yes** | **Critical** | Log + **notify user** + block IP |
| `account_disabled` | Account `is_active=False` | ✅ Yes | Medium | Log + notify admin |
| `token_revoked` | Token `is_active=False` | ✅ Yes | High | Log + **notify user** |
| `token_expired` | Past `expires_at` | ✅ Yes | Low | Log (expected behavior) |
| `realm_not_approved` | Realm status != 'approved' | ✅ Yes | Low | Log only |

### 2. Authorization Errors (Permission Checks)

| Error Code | Description | User Attributable? | Severity | Action |
|------------|-------------|-------------------|----------|--------|
| `ip_denied` | IP not in token's whitelist | ✅ Yes | **High** | Log + **notify user** |
| `domain_denied` | Domain outside realm scope | ✅ Yes | High | Log + notify user |
| `operation_denied` | Operation (read/update/delete) not allowed | ✅ Yes | Medium | Log |
| `record_type_denied` | Record type (A/AAAA/TXT) not allowed | ✅ Yes | Low | Log |

### 3. Attack Patterns (Derived from Error Sequences)

| Pattern | Detection | Severity | Action |
|---------|-----------|----------|--------|
| **TOKEN_PROBE** | Many `invalid_format` from same IP | Low | Rate limit IP |
| **CREDENTIAL_STUFFING** | Many `user_not_found` from same IP | Medium | Block IP + notify admin |
| **BRUTE_FORCE** | Multiple `token_hash_mismatch` for same user | **Critical** | Block IP + **notify user** + lock account? |
| **COMPROMISED_TOKEN** | `ip_denied` from unexpected location/country | **Critical** | **Notify user** + consider revocation |
| **REPLAY_ATTACK** | `token_revoked` or `token_expired` repeated use | High | Log + notify user |
| **SCOPE_ESCALATION** | `domain_denied` or `operation_denied` after success | High | Log + notify user |

---

## Notification Triggers

### Immediate User Notifications (Email)

1. **Token under brute-force attack** (`token_hash_mismatch`)
   - Subject: "⚠️ Security Alert: Unauthorized access attempt on your account"
   - Include: Token name (prefix), IP address, time, GeoIP location

2. **Access from unexpected IP** (`ip_denied` when IP whitelist configured)
   - Subject: "🔒 Access blocked from unknown IP address"
   - Include: IP, location, token name, configured whitelist

3. **Revoked token still in use** (`token_revoked` repeated)
   - Subject: "⚠️ Warning: Revoked token still being used"
   - Include: Token name, IP, time (indicates token may have been stolen)

4. **Expired token repeated use** (`token_expired` > 3 times in 24h)
   - Subject: "ℹ️ Reminder: Your API token has expired"
   - Include: Token name, instructions to renew

### Admin Notifications

1. **High-volume attack pattern detected**
   - Multiple users targeted from same IP
   - Sudden spike in `denied` status logs

2. **Account-level lockout triggered**
   - Automatic or manual account disable

3. **Disabled account access attempts**
   - Someone trying to use a disabled account

---

## Database Schema Implications

### Current ActivityLog Fields (Sufficient)

```python
class ActivityLog:
    token_id       # ✅ Links to token (knows user)
    account_id     # ✅ Links to account directly
    source_ip      # ✅ For IP-based detection
    status         # 'success', 'denied', 'error'
    status_reason  # ✅ Free-text, but should be error_code
    user_agent     # ✅ For client fingerprinting
    created_at     # ✅ For temporal analysis
```

### Recommended Enhancement

Add `error_code` column for structured querying:

```python
error_code = db.Column(db.String(30), index=True)  # New column
# Values: 'invalid_format', 'user_not_found', 'token_hash_mismatch', etc.
```

This enables:
```sql
-- Find brute-force attacks against specific users
SELECT account_id, source_ip, COUNT(*)
FROM activity_log
WHERE error_code = 'token_hash_mismatch'
  AND created_at > datetime('now', '-1 hour')
GROUP BY account_id, source_ip
HAVING COUNT(*) >= 5;
```

---

## Token Lookup Security Enhancement

Current code lumps three failures into one `invalid_token`:

```python
# Current (insufficient granularity)
if not account:
    return AuthResult(success=False, error="Invalid token", error_code="invalid_token")
if not api_token:
    return AuthResult(success=False, error="Invalid token", error_code="invalid_token")
if not api_token.verify(token):
    return AuthResult(success=False, error="Invalid token", error_code="invalid_token")
```

**Security problem**: We lose attribution for brute-force detection!

### Recommended Change

```python
# Proposed (preserves attribution)
if not account:
    return AuthResult(
        success=False,
        error="Invalid token",
        error_code="user_not_found",
        account=None  # No attribution possible
    )

if not api_token:
    return AuthResult(
        success=False,
        error="Invalid token",
        error_code="token_prefix_not_found",
        account=account  # ✅ We know which account is targeted!
    )

if not api_token.verify(token):
    return AuthResult(
        success=False,
        error="Invalid token",
        error_code="token_hash_mismatch",
        account=account,
        token=api_token  # ✅ We know exactly which token!
    )
```

**Benefit**: When `token_hash_mismatch` occurs, we can:
1. Log `account_id` and `token_id` (even though auth failed)
2. Send notification to account owner
3. Implement per-token rate limiting

---

## UI Display Considerations

### Audit Log Enhancement

Add colored badges for error severity:

| Error Code | Badge Color | Icon |
|------------|-------------|------|
| `token_hash_mismatch` | 🔴 Red | ⚠️ |
| `ip_denied` | 🟠 Orange | 🌐 |
| `token_revoked` | 🟡 Yellow | 🚫 |
| `token_expired` | ⚪ Gray | ⏰ |
| `operation_denied` | 🔵 Blue | 🔒 |
| `invalid_format` | ⚪ Gray | 🤖 |

### Dashboard Security Widgets

1. **Failed Auth Attempts (24h)**
   - By error type (pie chart)
   - By IP (table with GeoIP)

2. **Accounts Under Attack**
   - List of accounts with recent `token_hash_mismatch` or `ip_denied`

3. **Suspicious IPs**
   - IPs with highest denial rate
   - GeoIP map visualization

---

## Test Matrix Requirements

The state matrix should include tests for:

### Authentication Failures (Attributable)
1. Token with valid format but wrong hash → `token_hash_mismatch`
2. Token with valid format but wrong prefix → `token_prefix_not_found`
3. Token for disabled account → `account_disabled`
4. Revoked token → `token_revoked`
5. Expired token → `token_expired`

### Authorization Failures (Attributable)
6. Valid token, wrong IP → `ip_denied`
7. Valid token, wrong domain → `domain_denied`
8. Valid token, forbidden operation → `operation_denied`
9. Valid token, forbidden record type → `record_type_denied`

### Attack Simulations
10. Brute-force: 5 `token_hash_mismatch` in 1 minute → rate limit
11. IP sweep: 10 different tokens from same IP → block IP
12. Scope probing: sequential domain tests → alert

---

## Implementation Priority

1. **High Priority**
   - Split `invalid_token` into `user_not_found`, `token_prefix_not_found`, `token_hash_mismatch`
   - Add `error_code` column to ActivityLog
   - Log `account_id` even on failed auth (when attributable)

2. **Medium Priority**
   - Email notifications for critical errors (hash mismatch, IP denied)
   - Dashboard security widgets
   - Rate limiting per IP and per token

3. **Lower Priority**
   - Attack pattern detection (requires time-series analysis)
   - GeoIP alerting (location anomaly detection)
   - Account lockout automation
