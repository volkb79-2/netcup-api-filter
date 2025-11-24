# Configuration-Driven Architecture

## Directive

**CRITICAL**: This project enforces a 100% config-driven approach. No values are hardcoded in scripts or code.

All configuration values MUST come from:
1. Environment variables (read from `.env` files)
2. TOML configuration files (`global-config.*.toml`)
3. Database-stored settings (admin UI configuration)

## Rationale

Hardcoded values create:
- **Deployment issues**: Different values needed for dev/staging/production
- **Maintenance burden**: Must search entire codebase to change a timeout
- **Security risks**: Secrets accidentally committed to version control
- **Testing complexity**: Cannot override values for different test scenarios

Config-driven approach provides:
- **Single source of truth**: All defaults in `.env.defaults`
- **Environment overrides**: Dev/staging/production can customize via environment
- **Audit trail**: All changes tracked via version control (defaults) or admin UI (runtime)
- **Testing flexibility**: Override any value for specific test scenarios

## Configuration Hierarchy

```
1. .env.defaults (version-controlled defaults)
   ↓
2. .env.local / .env.production (environment-specific overrides, not in git)
   ↓
3. Environment variables (deployment-specific overrides)
   ↓
4. Database settings (runtime configuration via admin UI)
```

Each layer can override the previous layer. Example:

```bash
# .env.defaults
FLASK_SESSION_LIFETIME=3600  # 1 hour default

# .env.production (not in git)
FLASK_SESSION_LIFETIME=7200  # 2 hours for production

# Environment override (CI/CD)
export FLASK_SESSION_LIFETIME=300  # 5 minutes for CI tests
```

## Current Configuration Audit

### ✅ Fully Config-Driven

#### Flask Session Settings (`passenger_wsgi.py`)

**Before** (hardcoded):
```python
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 3600
```

**After** (config-driven):
```python
# Read from environment (sourced from .env.defaults)
secure_cookie = os.environ.get('FLASK_SESSION_COOKIE_SECURE', 'auto')
if secure_cookie == 'auto':
    app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') != 'local_test'
else:
    app.config['SESSION_COOKIE_SECURE'] = secure_cookie.lower() in ('true', '1', 'yes')

app.config['SESSION_COOKIE_HTTPONLY'] = os.environ.get('FLASK_SESSION_COOKIE_HTTPONLY', 'True').lower() in ('true', '1', 'yes')
app.config['SESSION_COOKIE_SAMESITE'] = os.environ.get('FLASK_SESSION_COOKIE_SAMESITE', 'Lax')
app.config['PERMANENT_SESSION_LIFETIME'] = int(os.environ.get('FLASK_SESSION_LIFETIME', '3600'))
```

**Configuration** (`.env.defaults`):
```bash
# Flask session configuration (NO HARDCODED VALUES IN CODE!)
FLASK_SESSION_COOKIE_SECURE=auto
FLASK_SESSION_COOKIE_HTTPONLY=True
FLASK_SESSION_COOKIE_SAMESITE=Lax
FLASK_SESSION_LIFETIME=3600
```

#### Admin Credentials (`bootstrap/seeding.py`)

**Before**: Hardcoded `admin` / `admin` in code  
**After**: Read from `.env.defaults`:

```bash
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=admin
```

#### Test Client Credentials (`bootstrap/seeding.py`)

All values come from `.env.defaults`:

```bash
DEFAULT_TEST_CLIENT_ID=test_qweqweqwe_vi
DEFAULT_TEST_CLIENT_SECRET_KEY=qweqweqwe_vi_readonly_secret_key_12345
DEFAULT_TEST_CLIENT_DESCRIPTION=Sample read-only client for qweqweqwe.vi
DEFAULT_TEST_CLIENT_REALM_TYPE=host
DEFAULT_TEST_CLIENT_REALM_VALUE=qweqweqwe.vi
DEFAULT_TEST_CLIENT_RECORD_TYPES=A
DEFAULT_TEST_CLIENT_OPERATIONS=read
```

#### TLS Proxy Configuration (`tooling/local_proxy/proxy.env`)

All nginx and certificate paths from environment:

```bash
LOCAL_TLS_DOMAIN=gstammtisch.dchive.de  # Auto-detected via auto-detect-fqdn.sh
LOCAL_APP_HOST=__auto__
LOCAL_APP_PORT=5100
LOCAL_TLS_BIND_HTTPS=443
LOCAL_TLS_BIND_HTTP=80
LE_CERT_BASE=/etc/letsencrypt
LOCAL_PROXY_NETWORK=naf-local
LOCAL_PROXY_CONFIG_PATH=/tmp/netcup-local-proxy/conf.d
```

### ⚠️ Partial Config-Driven (Acceptable Defaults)

These have reasonable defaults but should be overridable:

#### Rate Limiting (`filter_proxy.py`)

**Current**:
```python
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per hour", "50 per minute"],
    storage_uri="memory://",
)
```

**Recommendation**: Add to `.env.defaults`:
```bash
# Rate limiting configuration
FLASK_MAX_CONTENT_LENGTH_MB=10
FLASK_RATE_LIMIT_HOURLY=200
FLASK_RATE_LIMIT_MINUTE=50
FLASK_RATE_LIMIT_STORAGE_URI=memory://
```

Then update code:
```python
max_content_mb = int(os.environ.get('FLASK_MAX_CONTENT_LENGTH_MB', '10'))
app.config['MAX_CONTENT_LENGTH'] = max_content_mb * 1024 * 1024

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=[
        f"{os.environ.get('FLASK_RATE_LIMIT_HOURLY', '200')} per hour",
        f"{os.environ.get('FLASK_RATE_LIMIT_MINUTE', '50')} per minute"
    ],
    storage_uri=os.environ.get('FLASK_RATE_LIMIT_STORAGE_URI', 'memory://'),
)
```

#### Request Timeouts (`netcup_client.py`, `example_client.py`)

**Current**:
```python
response = requests.post(self.api_url, json=payload, timeout=30)
response = requests.post(url, headers=headers, json=payload, timeout=10)
```

**Recommendation**: Add to `.env.defaults`:
```bash
# HTTP request timeouts (seconds)
NETCUP_API_TIMEOUT=30
CLIENT_REQUEST_TIMEOUT=10
```

Then update code:
```python
import os
timeout = int(os.environ.get('NETCUP_API_TIMEOUT', '30'))
response = requests.post(self.api_url, json=payload, timeout=timeout)
```

#### SMTP Timeouts (`email_notifier.py`)

**Current**:
```python
with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, timeout=30) as server:
```

**Recommendation**: Add to `.env.defaults`:
```bash
# Email configuration
SMTP_TIMEOUT=30
```

### ✅ Already Config-Driven

These are already properly configured:

#### Database Path

```python
db_path = os.environ.get('NETCUP_FILTER_DB_PATH', 'netcup_filter.db')
```

#### Secret Key

```python
secret_key = os.environ.get('SECRET_KEY')
if not secret_key:
    raise RuntimeError("SECRET_KEY environment variable must be set")
```

#### Netcup API Credentials

All stored in database, managed via admin UI:
- `customer_id`
- `api_key`
- `api_password`

#### Email Settings

All stored in database, managed via admin UI:
- `smtp_server`
- `smtp_port`
- `smtp_username`
- `smtp_password`
- `sender_email`
- `use_ssl`

## Implementation Checklist

When adding new configuration:

- [ ] Add default value to `.env.defaults` with descriptive comment
- [ ] Read from `os.environ.get('VAR_NAME', 'default')` in code
- [ ] Use appropriate type conversion (`int()`, `.lower() in ('true', '1', 'yes')`)
- [ ] Document in relevant guide (ADMIN_GUIDE.md, CLIENT_USAGE.md, etc.)
- [ ] Update tests to override value if needed
- [ ] Never commit actual secrets (use `.env.defaults` for placeholders)

## Testing Configuration

### Override for Tests

```python
# In test fixture
@pytest.fixture(autouse=True)
def override_config(monkeypatch):
    monkeypatch.setenv('FLASK_SESSION_LIFETIME', '300')  # 5 minutes for tests
    monkeypatch.setenv('NETCUP_API_TIMEOUT', '5')  # Faster timeout for tests
    yield
```

### Environment-Specific Config

```bash
# tests/.env.test
FLASK_SESSION_LIFETIME=300
FLASK_ENV=test
SECRET_KEY=test-secret-key-not-for-production
NETCUP_FILTER_DB_PATH=:memory:  # In-memory database for tests
```

Load in conftest.py:
```python
import pytest
from dotenv import load_dotenv

@pytest.fixture(scope='session', autouse=True)
def load_test_env():
    load_dotenv('tests/.env.test')
```

## Fail-Fast Policy

All required configuration MUST be validated at startup. Never use defaults for critical values.

**Good** (explicit validation):
```python
secret_key = os.environ.get('SECRET_KEY')
if not secret_key:
    raise RuntimeError("SECRET_KEY environment variable must be set")
```

**Bad** (silent default):
```python
secret_key = os.environ.get('SECRET_KEY', 'default-secret')  # ❌ NEVER DO THIS
```

See `FAIL_FAST_POLICY.md` for complete guidelines.

## Documentation Requirements

Each configuration variable must be documented with:

1. **Name**: Environment variable name (UPPER_SNAKE_CASE)
2. **Type**: String, integer, boolean, URL, path, etc.
3. **Default**: Value from `.env.defaults`
4. **Purpose**: What does this control?
5. **Impact**: What happens if changed?
6. **Constraints**: Valid ranges, formats, dependencies

Example:

```bash
# FLASK_SESSION_LIFETIME
# Type: Integer (seconds)
# Default: 3600
# Purpose: How long a user session remains valid without activity
# Impact: Lower = more frequent re-logins, Higher = longer security exposure
# Constraints: Must be > 0, recommended 300-7200 (5 min - 2 hours)
FLASK_SESSION_LIFETIME=3600
```

## Migration Guide

### For Existing Hardcoded Values

1. **Identify** hardcoded value in code:
   ```python
   timeout = 30  # ❌ Hardcoded
   ```

2. **Add to `.env.defaults`** with descriptive name:
   ```bash
   # Request timeout for external API calls (seconds)
   EXTERNAL_API_TIMEOUT=30
   ```

3. **Update code** to read from environment:
   ```python
   timeout = int(os.environ.get('EXTERNAL_API_TIMEOUT', '30'))
   ```

4. **Document** in appropriate guide (AGENTS.md section or dedicated guide)

5. **Test override** works:
   ```bash
   EXTERNAL_API_TIMEOUT=5 python test_api.py
   ```

### For New Features

1. **Design configuration first**: What values will users need to customize?
2. **Add to `.env.defaults`**: Set reasonable defaults
3. **Implement feature**: Read from environment everywhere
4. **Document**: Update guides with new configuration options
5. **Test**: Verify defaults work and overrides apply correctly

## Repository-Wide Compliance Plan

### Phase 1: Audit (Completed)

✅ Identified all hardcoded values via grep search  
✅ Categorized by priority (critical vs optional)  
✅ Documented in this guide

### Phase 2: Migration (In Progress)

✅ Flask session configuration → `.env.defaults`  
✅ Admin/client credentials → `.env.defaults`  
⚠️ Rate limiting → Pending (acceptable defaults exist)  
⚠️ Timeouts → Pending (acceptable defaults exist)

### Phase 3: Enforcement (Next)

- [ ] Add pre-commit hook to detect hardcoded values
- [ ] Create linter rule to flag hardcoded config
- [ ] Update CONTRIBUTING.md with config-driven requirements
- [ ] Add CI check to validate `.env.defaults` completeness

### Phase 4: Documentation (Next)

- [ ] Create CONFIGURATION_REFERENCE.md with all variables
- [ ] Update ADMIN_GUIDE.md with configuration section
- [ ] Add inline comments in `.env.defaults` for every value
- [ ] Generate environment variable documentation automatically

## Benefits Realized

### Before (Hardcoded)

```python
# To change session timeout:
# 1. Edit passenger_wsgi.py line 114
# 2. Rebuild deployment package
# 3. FTP upload to production
# 4. Restart Passenger
# 5. Hope you didn't break anything

app.config['PERMANENT_SESSION_LIFETIME'] = 3600
```

### After (Config-Driven)

```bash
# To change session timeout:
# 1. Set environment variable (no code change!)
# 2. Restart application

export FLASK_SESSION_LIFETIME=7200
gunicorn passenger_wsgi:application
```

### Development Workflow

```bash
# Local testing with debug settings
export FLASK_ENV=local_test
export FLASK_SESSION_LIFETIME=300  # 5 minutes
gunicorn passenger_wsgi:application

# Production with secure settings
export FLASK_ENV=production
export FLASK_SESSION_LIFETIME=3600  # 1 hour
gunicorn passenger_wsgi:application
```

### Testing Scenarios

```bash
# Test session timeout behavior
FLASK_SESSION_LIFETIME=10 pytest tests/test_session_timeout.py

# Test with strict rate limiting
FLASK_RATE_LIMIT_MINUTE=5 pytest tests/test_rate_limit.py

# Test with fast API timeouts
NETCUP_API_TIMEOUT=1 pytest tests/test_timeout_handling.py
```

## See Also

- `ENV_DEFAULTS.md` - Environment defaults system documentation
- `FAIL_FAST_POLICY.md` - Validation and error handling guidelines
- `.env.defaults` - Single source of truth for default values
- `HTTPS_LOCAL_TESTING.md` - TLS proxy auto-detection configuration
