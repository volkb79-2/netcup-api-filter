# Charset Validation Patterns

This document defines the canonical validation patterns for usernames, passwords, aliases, and tokens in the Netcup API Filter application.

## Overview

All validation is centralized in `src/netcup_api_filter/models.py` to ensure consistency between server-side validation and client-side form validation.

## Username Validation

**Pattern:** `^[a-zA-Z][a-zA-Z0-9-._]{7,31}$`

**Rules:**
- Minimum 8 characters, maximum 32 characters
- Must start with a letter (upper or lower case)
- May contain: letters (a-z, A-Z), digits (0-9), hyphens (-), dots (.), underscores (_)
- Case-insensitive for uniqueness (stored as-entered, compared lowercase)
- Reserved usernames are blocked: admin, root, system, api, naf, test, administrator, superuser, operator, support

**Examples:**
- ✅ `JohnDoe123`
- ✅ `my_user.name`
- ✅ `user-name-1`
- ❌ `123user` (must start with letter)
- ❌ `ab` (too short)
- ❌ `admin` (reserved)

**Implementation:** `models.validate_username()`

## Password Validation

**Pattern:** Safe printable ASCII, min 20 chars, min 100 bits entropy

**Rules:**
- Minimum 20 characters
- Minimum 100 bits of entropy
- Only safe printable ASCII characters allowed
- **Disallowed characters:** `!` (shell history), `` ` `` (command substitution), `'` `"` (quoting), `\` (escape)

**Allowed characters:**
```
a-z A-Z 0-9
- = _ + ; : , . | / ? @ # $ % ^ & * ( ) [ ] { } ~ < > <space>
```

**Entropy calculation:**
- Based on character class analysis (lowercase, uppercase, digits, special)
- Entropy = length × log₂(charset_size)
- Must achieve ≥100 bits for acceptance

**Password strength levels:**
| Entropy (bits) | Level | Description |
|----------------|-------|-------------|
| < 50 | Very Weak | Too easy to crack |
| 50-74 | Weak | Increase length or complexity |
| 75-99 | Moderate | Approaching minimum |
| 100-127 | Good | Secure for most uses |
| ≥ 128 | Excellent | Very secure |

**Implementation:** `models.validate_password()`, `models.calculate_entropy()`

## User Alias (Token Attribution)

**Pattern:** `^[a-zA-Z0-9]{16}$`

**Rules:**
- Exactly 16 characters
- Alphanumeric only (a-z, A-Z, 0-9)
- Server-side generated (cryptographically random)
- Used in tokens instead of username for security
- One alias per account (immutable after creation)

**Example:** `Ab3xYz9KmNpQrStU`

**Implementation:** `models.generate_user_alias()`

## API Token

**Pattern:** `^naf_[a-zA-Z0-9]{16}_[a-zA-Z0-9]{64}$`

**Format:** `naf_<user_alias>_<random64>`

**Components:**
- Prefix: `naf_` (Netcup API Filter)
- User alias: 16-char alphanumeric (identifies the account)
- Separator: `_`
- Random part: 64-char alphanumeric (the secret)

**Example:** `naf_Ab3xYz9KmNpQrStU_aB1cD2eF3gH4iJ5kL6mN7oP8qR9sT0uV1wX2yZ3aB4cD5eF6gH7iJ8kL9mN0`

**Security notes:**
- Only the SHA-256 hash of the token is stored
- Full token shown once to user at creation
- Token prefix (first 8 chars) logged for identification

**Implementation:** `models.generate_token()`, `models.parse_token()`

## Client-Side Validation

Templates should match server-side validation:

### Password Forms (admin/change_password.html, account/*)
```javascript
const MIN_ENTROPY_BITS = 100;
const MIN_PASSWORD_LENGTH = 20;
const ALLOWED_CHARSET = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-=_+;:,.|/?@#$%^&*()[]{}~<> ';
```

### Username Forms (account/register.html)
```javascript
const USERNAME_PATTERN = /^[a-zA-Z][a-zA-Z0-9-._]{7,31}$/;
const USERNAME_MIN_LENGTH = 8;
const USERNAME_MAX_LENGTH = 32;
```

## Migration Notes

**Previous patterns (deprecated):**
- Username: `^[a-z][a-z0-9-]{6,30}[a-z0-9]$` (lowercase only)
- Password: min 8-12 chars, no entropy requirement

**Current patterns:**
- Username: `^[a-zA-Z][a-zA-Z0-9-._]{7,31}$` (case-insensitive, more chars)
- Password: min 20 chars, min 100 bits entropy, safe ASCII only

Existing accounts with old-pattern credentials will continue to work for login, but password changes enforce the new requirements.

## Testing

Validation can be tested via the Python module:

```python
from netcup_api_filter.models import validate_username, validate_password, calculate_entropy

# Username
is_valid, error = validate_username("TestUser123")

# Password (note: ! is disallowed, use + instead)
is_valid, error = validate_password("MySecure+Password-2024+Secure")
entropy = calculate_entropy("MySecure+Password-2024+Secure")
```

## Configuration

While the patterns are defined in code, the minimum password entropy can be overridden via environment:

```bash
# .env (optional override)
PASSWORD_MIN_ENTROPY=120  # Default: 100
PASSWORD_MIN_LENGTH=24    # Default: 20
```

Note: These overrides require code changes to implement; the current implementation uses hardcoded defaults.
