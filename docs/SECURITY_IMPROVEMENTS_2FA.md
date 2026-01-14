# 2FA Security Improvements

## Overview

This document describes the security enhancements implemented for the 2FA authentication system to prevent brute-force attacks and improve session security.

## Changes Implemented

### 1. Session Regeneration on Login ✅

**Purpose**: Prevent session fixation attacks

**Implementation**:
- Session ID is regenerated after successful authentication
- Old session data is preserved, then cleared and recreated
- Applied to both account and admin authentication

**Code Location**:
- `src/netcup_api_filter/account_auth.py` - `create_session()` function
- `src/netcup_api_filter/api/admin.py` - `_complete_admin_login()` function

**Example**:
```python
def create_session(account: Account):
    """Create authenticated session for account."""
    # Regenerate session ID to prevent session fixation attacks
    old_session_data = dict(session)
    session.clear()
    session.update(old_session_data)
    session.modified = True
    
    session[SESSION_KEY_USER_ID] = account.id
    session[SESSION_KEY_USERNAME] = account.username
    session.permanent = True
```

### 2. 2FA Failure Tracking with Account Lockout ✅

**Purpose**: Prevent brute-force attacks on 2FA codes

**Features**:
- Tracks failed 2FA attempts per account
- Locks account after configurable threshold (default: 5 attempts)
- Lockout duration configurable (default: 30 minutes)
- Automatic lockout expiry
- Failure counters reset on successful login
- Applies to both email and TOTP 2FA methods

**Configuration** (`.env.defaults`):
```bash
# Maximum failed 2FA attempts before account lockout
TFA_MAX_ATTEMPTS=5
# Account lockout duration after max failed 2FA attempts (minutes)
TFA_LOCKOUT_MINUTES=30
```

**Implementation Details**:
- Failure count stored in Settings table with key `2fa_failures:{account_id}`
- Includes timestamp of last failure for automatic expiry
- User sees remaining attempts on failure (e.g., "3 attempts remaining")
- After max attempts: "Too many failed attempts. Account locked for 30 minutes."

**Functions Added**:
```python
# In account_auth.py
get_2fa_failure_count(account)      # Get current failure count
increment_2fa_failures(account)      # Track failed attempt
reset_2fa_failures(account)          # Clear on success
is_2fa_locked(account)               # Check if locked
```

### 3. Recovery Code Rate Limiting ✅

**Purpose**: Prevent brute-force attacks on recovery codes

**Features**:
- Separate rate limiting for recovery code attempts
- Lower threshold than 2FA (default: 3 attempts)
- Lockout duration configurable (default: 30 minutes)
- Independent from 2FA failure tracking
- More strict because recovery codes are last resort

**Configuration** (`.env.defaults`):
```bash
# Maximum failed recovery code attempts before lockout
RECOVERY_CODE_MAX_ATTEMPTS=3
# Recovery code lockout duration (minutes)
RECOVERY_CODE_LOCKOUT_MINUTES=30
```

**Implementation**:
- Checked before verifying recovery code
- Invalid recovery code increments failure counter
- User sees clear error: "Too many failed recovery code attempts. Locked for 30 minutes."
- Failure tracking stored in Settings table with key `recovery_failures:{account_id}`

**Functions Added**:
```python
# In account_auth.py
get_recovery_code_failure_count(account)
increment_recovery_code_failures(account)
reset_recovery_code_failures(account)
is_recovery_code_locked(account)
```

### 4. Reduced Recovery Code Count ✅

**Purpose**: Limit brute-force attack surface

**Change**:
- **Before**: 10 recovery codes per account
- **After**: 3 recovery codes per account

**Configuration** (`.env.defaults`):
```bash
# Number of recovery codes generated per account
RECOVERY_CODE_COUNT=3
```

**Rationale**:
- 10 codes = 80 bits entropy (8 chars each, 32-char alphabet)
- 3 codes = 24 bits entropy - still sufficient with rate limiting
- With 3 attempt limit before lockout, effective protection against brute force
- Encourages users to regenerate codes after use (best practice)

**Code Location**:
- `src/netcup_api_filter/recovery_codes.py` - `RECOVERY_CODE_COUNT` constant

## Security Architecture

### Threat Model

**Threats Mitigated**:
1. **Session Fixation**: Attacker pre-sets session ID, victim authenticates with it
2. **2FA Brute Force**: Attacker tries to guess 6-digit codes (1M possibilities)
3. **Recovery Code Brute Force**: Attacker tries to guess recovery codes
4. **Credential Stuffing**: Automated tools trying leaked credentials

**Attack Scenarios Prevented**:
- **Before**: Attacker could try 1,000,000 2FA codes (6 digits) without limit
- **After**: Attacker gets max 5 attempts, then 30-minute lockout
- **Before**: 10 recovery codes provided multiple brute-force targets
- **After**: 3 recovery codes with 3-attempt limit = max 9 total attempts

### Defense in Depth

```
Authentication Flow:
1. Username + Password (bcrypt hashed)
   └─> Failed: Track per-username (separate system)
   
2. 2FA Code (Email/TOTP) OR Recovery Code
   └─> 2FA Failed: Track per-account (5 attempts, 30 min lockout)
   └─> Recovery Failed: Track separately (3 attempts, 30 min lockout)
   
3. Session Creation
   └─> Regenerate Session ID (prevent fixation)
   └─> Reset all failure counters
```

### Storage

Failure tracking uses the Settings table for persistence across workers:

```python
# Settings table entries
{
  "2fa_failures:{account_id}": {
    "count": 3,
    "last_failure": "2026-01-10T12:30:00Z"
  },
  "recovery_failures:{account_id}": {
    "count": 1,
    "last_failure": "2026-01-10T12:35:00Z"
  }
}
```

**Benefits**:
- Survives application restart
- Works in multi-worker deployments (shared database)
- Automatic cleanup via expiry check
- No separate cache infrastructure needed

## User Experience

### Normal Flow (Success)
1. Enter username + password → Success
2. Receive 2FA code via email/TOTP → Success
3. Enter code → **Login successful**
4. (Behind the scenes: Session ID regenerated, failure counters reset)

### Failed 2FA Attempts
1. Enter wrong 2FA code → "Invalid code. 4 attempts remaining."
2. Enter wrong code again → "Invalid code. 3 attempts remaining."
3. Continue until 5 failures → "Too many failed attempts. Account locked for 30 minutes."
4. User must wait or use recovery code (if not also locked)

### Recovery Code Usage
1. Click "Use recovery code" on 2FA page
2. Enter recovery code (format: XXXX-XXXX)
3. If valid → **Login successful**, code is consumed (one-time use)
4. If invalid → Failure tracked separately (max 3 attempts)

### Lockout Expiry
- Automatic: Lockout expires after configured minutes
- No admin intervention required
- User can retry login after expiry
- Failure counters automatically reset

## Configuration Reference

All settings are in `.env.defaults`:

```bash
# ========================================
# 2FA Security Settings
# ========================================

# Maximum failed 2FA attempts before account lockout
TFA_MAX_ATTEMPTS=5

# Account lockout duration after max failed 2FA attempts (minutes)
TFA_LOCKOUT_MINUTES=30

# Recovery Code Security
# Maximum failed recovery code attempts before lockout
RECOVERY_CODE_MAX_ATTEMPTS=3

# Recovery code lockout duration (minutes)
RECOVERY_CODE_LOCKOUT_MINUTES=30

# Number of recovery codes generated per account
RECOVERY_CODE_COUNT=3
```

## Testing

### Manual Testing Steps

1. **Test 2FA Lockout**:
   ```
   - Login with correct credentials
   - Enter wrong 2FA code 5 times
   - Verify account locked message
   - Wait 30 minutes or clear Settings table entry
   - Verify can login again
   ```

2. **Test Recovery Code Lockout**:
   ```
   - Login with correct credentials
   - Request recovery code
   - Enter wrong recovery code 3 times
   - Verify locked message
   - Verify 2FA still works (separate tracking)
   ```

3. **Test Session Regeneration**:
   ```
   - Login successfully
   - Check session cookie value before/after login
   - Verify session ID changed
   - Verify authenticated session works
   ```

### Automated Tests

**To be implemented** (see `SECURITY_ISSUE_2FA_LOCKOUT_NOTIFICATIONS.md`):
- Playwright UI tests for lockout flows
- Unit tests for failure tracking functions
- Integration tests for session regeneration

## Admin Operations

### Unlock Account Manually

If an admin needs to unlock a locked account:

```python
# Via Flask shell or admin script
from src.netcup_api_filter.account_auth import reset_2fa_failures, reset_recovery_code_failures
from src.netcup_api_filter.models import Account

account = Account.query.filter_by(username='user123').first()
reset_2fa_failures(account)
reset_recovery_code_failures(account)
```

Or directly in database:
```sql
-- Clear 2FA lockout
DELETE FROM settings WHERE key = '2fa_failures:123';

-- Clear recovery code lockout
DELETE FROM settings WHERE key = 'recovery_failures:123';
```

### Monitor Lockouts

Check activity log for patterns:
```sql
SELECT 
    account_id,
    COUNT(*) as failed_attempts,
    MIN(created_at) as first_attempt,
    MAX(created_at) as last_attempt
FROM activity_log
WHERE 
    action = 'login' 
    AND status = 'denied'
    AND status_reason LIKE '%2FA%'
    AND created_at > datetime('now', '-1 hour')
GROUP BY account_id
ORDER BY failed_attempts DESC;
```

## Future Enhancements

See `docs/SECURITY_ISSUE_2FA_LOCKOUT_NOTIFICATIONS.md` for planned improvements:

1. **Email Notifications**: Notify user and admin on lockout
2. **Suspicious Activity Detection**: Pattern analysis (geolocation, device fingerprinting)
3. **Self-Service Unlock**: Allow user to unlock via email verification
4. **Adaptive Lockout**: Increase lockout duration for repeated violations
5. **IP-Based Rate Limiting**: Additional layer beyond per-account tracking

## References

- **Session Fixation**: OWASP - https://owasp.org/www-community/attacks/Session_fixation
- **Brute Force Protection**: NIST SP 800-63B (Digital Identity Guidelines)
- **Recovery Codes**: RFC 8628 (OAuth 2.0 Device Flow) - recovery code patterns

## Changelog

**2026-01-10**:
- ✅ Implemented session regeneration on login
- ✅ Added 2FA failure tracking with lockout
- ✅ Added recovery code rate limiting
- ✅ Reduced recovery codes from 10 to 3
- ✅ Added configuration defaults to .env.defaults
- ✅ Applied same features to admin authentication
- 📝 Created security issue for email notifications

## Compliance

These improvements help meet security requirements for:
- **OWASP ASVS** (Application Security Verification Standard) Level 2
- **PCI DSS** (if handling payment data) - 8.2.3-8.2.5 (Account Lockout)
- **GDPR** (data protection by design) - Article 25
- **SOC 2** (if applicable) - CC6.1 (Logical and Physical Access Controls)
