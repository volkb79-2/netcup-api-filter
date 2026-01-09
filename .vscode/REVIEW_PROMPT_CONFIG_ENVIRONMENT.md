# Deep Dive Review: Configuration & Environment Management

## Context

The project implements a strict configuration hierarchy and fail-fast principle:
- **`.env.defaults`**: Single source of truth for all defaults (version-controlled)
- **Environment variables**: Override defaults per environment
- **Database settings**: Runtime configuration via admin UI
- **`app-config.toml`**: Initial deployment configuration (deleted after import)
- **Fail-fast validation**: No defaults, no fallbacks, explicit requirements

## Review Objective

Verify that the configuration system is:
1. **100% config-driven** - No hardcoded values in code
2. **Fail-fast compliant** - Missing config causes immediate failure with clear errors
3. **Environment-aware** - Correct behavior per environment (dev/local_test/production)
4. **Secure** - No secrets in version control, proper secret handling
5. **Documented** - All config options documented with examples

## Review Checklist

### 1. Configuration Hierarchy Validation

**Files:** `.env.defaults`, `src/netcup_api_filter/app.py`, documentation

#### Hierarchy Order (highest priority first)
1. **Environment variables** - Runtime overrides
2. **Settings table** - Admin UI changes (stored in database)
3. **`app-config.toml`** - Initial deployment config (deleted after import)
4. **`.env.defaults`** - Universal defaults (version-controlled)

- [ ] **Priority enforcement**: Higher priority sources override lower
- [ ] **Fallback chain**: Correct fallback order implemented
- [ ] **Documentation**: Hierarchy documented in comments
- [ ] **Consistency**: All config follows same pattern

**Test:**
```python
import os
from netcup_api_filter.database import get_setting

# Test hierarchy
# 1. Set in .env.defaults: FLASK_SESSION_LIFETIME=3600
# 2. Override in environment: os.environ['FLASK_SESSION_LIFETIME'] = '7200'
# 3. Verify environment wins
lifetime = int(os.environ.get('FLASK_SESSION_LIFETIME', '3600'))
assert lifetime == 7200, "Environment override failed"

# 4. Settings table should override environment (if set)
# (Tested via admin UI settings update)
```

### 2. `.env.defaults` Completeness

**File:** `.env.defaults`

#### Flask Configuration
- [ ] **SESSION_COOKIE_SECURE**: `auto` (True in prod, False in local_test)
- [ ] **SESSION_COOKIE_HTTPONLY**: `True`
- [ ] **SESSION_COOKIE_SAMESITE**: `Lax`
- [ ] **SESSION_LIFETIME**: `3600` (1 hour)
- [ ] **SECRET_KEY**: Generated per deployment (not in .env.defaults)

#### Admin Credentials (Defaults)
- [ ] **DEFAULT_ADMIN_USERNAME**: Default admin username
- [ ] **DEFAULT_ADMIN_PASSWORD**: Default admin password
- [ ] **Note**: Deployment generates random password, stored in deployment_state_*.json

#### Test Client Credentials
- [ ] **DEFAULT_TEST_CLIENT_ID**: Test client ID
- [ ] **DEFAULT_TEST_CLIENT_TOKEN**: Test client token
- [ ] **DEFAULT_TEST_CLIENT_REALM_***: Realm configuration
- [ ] **DEFAULT_TEST_CLIENT_RECORD_TYPES**: Allowed record types
- [ ] **DEFAULT_TEST_CLIENT_OPERATIONS**: Allowed operations

#### Rate Limiting
- [ ] **RATE_LIMIT_ADMIN**: Admin portal rate limit
- [ ] **RATE_LIMIT_ACCOUNT**: Account portal rate limit
- [ ] **RATE_LIMIT_API**: API endpoint rate limit

#### Timeouts
- [ ] **HTTP_TIMEOUT**: HTTP request timeout
- [ ] **SMTP_TIMEOUT**: SMTP connection timeout
- [ ] **API_TIMEOUT**: External API timeout

#### Local TLS Proxy (for HTTPS testing)
- [ ] **LOCAL_TLS_DOMAIN**: Public FQDN for local testing
- [ ] **LOCAL_TLS_CERT_PATH**: Certificate path
- [ ] **LOCAL_TLS_KEY_PATH**: Private key path
- [ ] **LOCAL_FLASK_PORT**: Flask backend port
- [ ] **LOCAL_PROXY_NETWORK**: Docker network name
- [ ] **LOCAL_PROXY_PORT_HTTP**: HTTP port
- [ ] **LOCAL_PROXY_PORT_HTTPS**: HTTPS port

#### Validation
- [ ] **All values have comments**: Purpose explained
- [ ] **No secrets**: No sensitive values in .env.defaults
- [ ] **Type hints**: Expected type in comments (string, integer, boolean)
- [ ] **Examples**: Example values provided

**Test:**
```bash
# Verify all expected variables present
grep -E "^[A-Z_]+=" .env.defaults | wc -l
# Should be 20+ variables

# Verify no secrets (no "password", "key", "token" actual values)
grep -iE "(password|api_key|token)=.{10,}" .env.defaults
# Should show empty values or references like "${POWERDNS_API_KEY}"
```

### 3. Fail-Fast Validation

**Files:** All shell scripts, Python initialization code

#### Shell Script Pattern
```bash
# ✅ GOOD: Explicit requirement with helpful error
PORT="${PORT:?PORT not set (check .env.defaults)}"
NETWORK="${NETWORK:?NETWORK must be set (source .env.workspace)}"

# ❌ BAD: Silent fallback hides configuration issues
PORT="${PORT:-8000}"
NETWORK="${NETWORK:-mynetwork}"
```

- [ ] **All critical variables**: Use `:?` syntax (fail if unset)
- [ ] **Error messages**: Include hint where to find variable
- [ ] **No defaults**: No `:-` fallbacks for required config
- [ ] **Early validation**: Check at script start, not during execution

#### Python Pattern
```python
# ✅ GOOD: Explicit requirement
config_value = os.environ['REQUIRED_CONFIG']  # Raises KeyError if missing

# or with better error message
def get_required_config(key: str) -> str:
    if key not in os.environ:
        raise ConfigurationError(f"{key} not set - check .env.defaults")
    return os.environ[key]

# ❌ BAD: Silent fallback
config_value = os.environ.get('REQUIRED_CONFIG', 'default')
```

- [ ] **Required config**: Raises exception if missing
- [ ] **Clear errors**: Error message explains what's missing and where to fix
- [ ] **Early validation**: Check at app startup, not on first use

**Test:**
```bash
# Test shell script fail-fast
unset REQUIRED_VAR
./script.sh
# Should fail with: "bash: REQUIRED_VAR: REQUIRED_VAR not set (check .env.defaults)"

# Test Python fail-fast
python3 -c "
import os
import sys
sys.path.insert(0, 'src')
os.environ.pop('SECRET_KEY', None)
from netcup_api_filter.app import create_app
try:
    app = create_app()
    print('ERROR: Should have failed')
except Exception as e:
    print(f'✓ Failed as expected: {e}')
"
```

### 4. Environment-Specific Behavior

**Files:** `.env.workspace`, environment detection code

#### Environment Detection
- [ ] **`FLASK_ENV` variable**: Determines environment
  - [ ] `production` (default): Full security, rate limiting
  - [ ] `local_test`: Security relaxed, rate limiting disabled
  - [ ] `development`: Debug mode enabled
- [ ] **Auto-detection**: Detects container environment correctly
- [ ] **Manual override**: Can set FLASK_ENV explicitly

#### Environment-Specific Settings

##### Production Environment
- [ ] **SESSION_COOKIE_SECURE**: True (HTTPS only)
- [ ] **DEBUG**: False
- [ ] **TESTING**: False
- [ ] **Rate limiting**: Enabled with configured limits
- [ ] **Logging**: INFO level, structured logs
- [ ] **Error pages**: Generic error messages (no stack traces)

##### Local Test Environment (`FLASK_ENV=local_test`)
- [ ] **SESSION_COOKIE_SECURE**: False (HTTP allowed)
- [ ] **DEBUG**: False (but more logging)
- [ ] **TESTING**: True
- [ ] **Rate limiting**: Disabled
- [ ] **Logging**: DEBUG level
- [ ] **Error pages**: Detailed errors for debugging

##### Development Environment
- [ ] **SESSION_COOKIE_SECURE**: False
- [ ] **DEBUG**: True (Flask debugger enabled)
- [ ] **TESTING**: False
- [ ] **Rate limiting**: Enabled but relaxed
- [ ] **Logging**: DEBUG level
- [ ] **Error pages**: Full stack traces

**Test:**
```python
# Test environment-specific behavior
import os
from netcup_api_filter.app import create_app

# Test production
os.environ['FLASK_ENV'] = 'production'
app_prod = create_app()
assert app_prod.config['SESSION_COOKIE_SECURE'] is True
assert app_prod.config['DEBUG'] is False

# Test local_test
os.environ['FLASK_ENV'] = 'local_test'
app_test = create_app()
assert app_test.config['SESSION_COOKIE_SECURE'] is False
assert app_test.config['TESTING'] is True
```

### 5. Secret Management

**Security requirements**

#### Never in Version Control
- [ ] **`.env`**: Git-ignored (for local secrets)
- [ ] **`.env.local`**: Git-ignored (local overrides)
- [ ] **`.env.production`**: Git-ignored (production secrets)
- [ ] **`deployment_state_*.json`**: Git-ignored (contains passwords)

#### Secret Sources
- [ ] **Environment variables**: Primary source for production
- [ ] **Deployment state files**: Generated passwords stored here
- [ ] **Database**: Some secrets encrypted in database (TOTP secrets)
- [ ] **External**: Option to use external secret managers

#### Secret Handling Patterns
```python
# ✅ GOOD: Read from environment, no default
api_key = os.environ['NETCUP_API_KEY']

# ✅ GOOD: Read from secure store
api_key = get_setting('netcup_api_key')  # From database

# ✅ GOOD: Environment variable substitution
# In TOML: api_key = "${NETCUP_API_KEY}"
# Bootstrap resolves to actual value

# ❌ BAD: Hardcoded secret
api_key = "abc123def456"
```

- [ ] **No hardcoded secrets**: Grep confirms no secrets in code
- [ ] **No secrets in logs**: Only log prefixes (first 8 chars)
- [ ] **No secrets in URLs**: No secrets in query params
- [ ] **Encrypted storage**: Secrets encrypted in database

**Test:**
```bash
# Grep for potential secrets in code
rg -i "(password|api_key|token|secret)\s*=\s*['\"][a-zA-Z0-9]{16,}" src/
# Should return no results (or only test fixtures)

# Verify .gitignore
cat .gitignore | grep -E "\.env$|deployment_state_.*\.json"
# Should be present
```

### 6. `app-config.toml` Import Process

**Files:** `src/netcup_api_filter/passenger_wsgi.py`, `app-config.toml.example`

#### Import Workflow
1. **Check existence**: Does `app-config.toml` exist?
2. **Parse TOML**: Use `tomllib` to parse
3. **Store in database**: Serialize arrays to JSON, store in Settings table
4. **Delete file**: Remove `app-config.toml` after successful import
5. **Bootstrap**: Call `initialize_platform_backends()` to process config

- [ ] **One-time only**: File deleted after first import
- [ ] **Idempotent**: Can run bootstrap multiple times safely
- [ ] **Error handling**: Parse errors logged, file not deleted
- [ ] **Transaction safety**: Database operations in transaction
- [ ] **Logging**: Clear log messages for each step

**Test:**
```bash
# Test import process
cp app-config.toml.example app-config.toml
# Edit app-config.toml with test data

# Start app (triggers import)
python3 -m netcup_api_filter

# Verify import
sqlite3 deploy-local/netcup_filter.db "SELECT key FROM settings WHERE key LIKE '%_config';"
# Should show: backends_config, domain_roots_config, users_config

# Verify file deleted
ls -l app-config.toml
# Should not exist
```

### 7. Database Settings Management

**Files:** `src/netcup_api_filter/database.py`, admin UI settings pages

#### Settings Table Usage
- [ ] **Key-value storage**: Simple key-value pairs in Settings table
- [ ] **JSON serialization**: Complex values stored as JSON strings
- [ ] **Helper functions**: `get_setting()`, `set_setting()`, `delete_setting()`
- [ ] **Type coercion**: Strings converted to correct types (int, bool, etc.)
- [ ] **Admin UI**: All settings editable via admin UI

#### Settings Categories
- [ ] **Rate limits**: admin_rate_limit, account_rate_limit, api_rate_limit
- [ ] **Security**: password_reset_expiry_hours, invite_expiry_hours
- [ ] **Email**: SMTP settings (host, port, username, password, etc.)
- [ ] **GeoIP**: MaxMind credentials (account_id, license_key)
- [ ] **Backend configs**: Stored as JSON blobs

**Test:**
```python
from netcup_api_filter.database import get_setting, set_setting

# Test setting storage and retrieval
set_setting('test_key', 'test_value')
assert get_setting('test_key') == 'test_value'

# Test JSON serialization
set_setting('test_json', json.dumps({'key': 'value'}))
data = json.loads(get_setting('test_json'))
assert data['key'] == 'value'
```

### 8. FQDN Auto-Detection

**Files:** `docs/FQDN_DETECTION.md`, `.env.workspace`

#### Detection Process
1. **Get external IP**: Queries ipify.org or similar
2. **Reverse DNS**: Performs PTR lookup on external IP
3. **Validate FQDN**: Checks if FQDN resolves back to IP
4. **Store in `.env.workspace`**: Writes PUBLIC_FQDN variable
5. **Used by scripts**: All scripts source `.env.workspace`

- [ ] **Auto-detection**: Runs during devcontainer post-create
- [ ] **Manual override**: Can set PUBLIC_FQDN manually in .env.workspace
- [ ] **Certificate paths**: Derived from FQDN automatically
- [ ] **Script usage**: All scripts that need FQDN source .env.workspace

**Test:**
```bash
# Test FQDN detection
source .env.workspace
echo "Detected FQDN: $PUBLIC_FQDN"

# Verify FQDN resolves
dig +short "$PUBLIC_FQDN"
# Should return an IP address

# Verify certificates exist
ls -l /etc/letsencrypt/live/"$PUBLIC_FQDN"/
# Should show fullchain.pem, privkey.pem
```

### 9. Configuration Documentation

**Files:** Documentation in `docs/`, comments in config files

#### Documentation Completeness
- [ ] **`docs/CONFIGURATION_GUIDE.md`**: Complete configuration guide exists
- [ ] **`docs/ENV_WORKSPACE.md`**: .env.workspace usage documented
- [ ] **`docs/FQDN_DETECTION.md`**: FQDN detection process documented
- [ ] **`docs/FAIL_FAST_PRINCIPLE.md`**: Fail-fast pattern documented
- [ ] **`CONFIG_DRIVEN_ARCHITECTURE.md`**: Architecture documented
- [ ] **Inline comments**: All config files have explanatory comments
- [ ] **Examples**: `app-config.toml.example` is complete and correct

#### Documentation Quality
- [ ] **Clear examples**: Working examples for all config options
- [ ] **Type information**: Expected types documented
- [ ] **Validation rules**: Constraints explained
- [ ] **Default values**: Defaults documented
- [ ] **Cross-references**: Related docs linked

### 10. Migration from Hardcoded Values

**Verify no hardcoded values remain**

#### Audit for Hardcoded Values
```bash
# Flask session settings
rg "SESSION_COOKIE_(SECURE|HTTPONLY|SAMESITE)\s*=\s*['\"]" src/
# Should have os.environ.get() not hardcoded

# Credentials
rg "(username|password)\s*=\s*['\"][a-zA-Z]+" src/
# Should reference env vars or database

# Rate limits
rg "limiter\.limit\(['\"][0-9]+ per" src/
# Should reference get_setting() not hardcoded numbers

# Ports
rg "port\s*=\s*[0-9]{4,}" src/
# Should reference env vars not hardcoded ports
```

- [ ] **No hardcoded session settings**: All from environment
- [ ] **No hardcoded credentials**: All from env/database
- [ ] **No hardcoded rate limits**: All from settings
- [ ] **No hardcoded timeouts**: All from environment
- [ ] **No hardcoded ports**: All from environment

### 11. Testing Configuration

**Test-specific configuration**

#### Playwright Container
- [ ] **UI_BASE_URL**: Configurable test target
- [ ] **UI_MCP_URL**: MCP endpoint URL
- [ ] **UI_ADMIN_PASSWORD**: Test admin password
- [ ] **Timeout settings**: Test timeouts configurable

#### Mock Services
- [ ] **Netcup API mock**: Mock endpoint configurable
- [ ] **GeoIP mock**: Mock endpoint configurable
- [ ] **Mailpit**: SMTP test server configurable

#### Test Isolation
- [ ] **Fresh database**: Each test run gets clean DB
- [ ] **Environment override**: Tests can override config
- [ ] **No side effects**: Tests don't affect production config

### 12. Deployment State Files

**Files:** `deployment_state_local.json`, `deployment_state_webhosting.json`

#### State File Structure
```json
{
  "target": "local|webhosting",
  "admin": {
    "username": "admin",
    "password": "current-actual-password",
    "must_change_password": false
  },
  "last_updated_at": "ISO-8601-timestamp",
  "updated_by": "agent|ui_test|manual"
}
```

- [ ] **Gitignored**: Deployment state files not in git
- [ ] **Per-target**: Separate file for local vs webhosting
- [ ] **Password tracking**: Tracks current admin password
- [ ] **Update tracking**: Last updated timestamp and source
- [ ] **Test usage**: Tests read from state file for credentials

**Test:**
```bash
# Verify state file structure
cat deployment_state_local.json | jq '.'
# Should be valid JSON with expected structure

# Verify gitignore
git check-ignore deployment_state_local.json
# Should return: deployment_state_local.json (is ignored)
```

### 13. Environment Variable Substitution

**Files:** `src/netcup_api_filter/bootstrap/platform_backends.py`

#### Substitution Pattern
```toml
# In app-config.toml
[[backends]]
service_name = "platform-powerdns"
config = { api_key = "${POWERDNS_API_KEY}", api_url = "auto" }
```

```python
# In bootstrap code
if value.startswith('${') and value.endswith('}'):
    env_var = value[2:-1]
    value = os.environ.get(env_var, '')
    if not value:
        logger.warning(f"Environment variable {env_var} not set")
```

- [ ] **Syntax detection**: Detects `${VAR_NAME}` pattern
- [ ] **Environment lookup**: Uses `os.environ.get()`
- [ ] **Missing variable handling**: Logs warning if not set
- [ ] **Nested objects**: Handles substitution in nested dicts
- [ ] **Type preservation**: Only substitutes strings (not ints, bools)

**Test:**
```python
# Test environment variable substitution
os.environ['TEST_VAR'] = 'test_value'

config = {
    'api_key': '${TEST_VAR}',
    'timeout': 30,  # Should not be substituted
}

# After substitution
assert config['api_key'] == 'test_value'
assert config['timeout'] == 30
```

### 14. Configuration Validation

**Runtime validation**

#### Validation Rules
- [ ] **Required fields**: Check all required fields present
- [ ] **Type validation**: Verify types (int, bool, string, etc.)
- [ ] **Format validation**: Validate formats (email, URL, CIDR)
- [ ] **Range validation**: Check value ranges (ports, timeouts)
- [ ] **Enum validation**: Check against allowed values
- [ ] **Cross-field validation**: Validate relationships between fields

#### Validation Timing
- [ ] **Startup validation**: Basic validation at app startup
- [ ] **Runtime validation**: Detailed validation on use
- [ ] **Admin UI validation**: Form validation before save
- [ ] **API validation**: Request validation before processing

**Example validation:**
```python
def validate_config():
    """Validate configuration at startup."""
    errors = []
    
    # Required fields
    if not os.environ.get('SECRET_KEY'):
        errors.append("SECRET_KEY not set")
    
    # Format validation
    smtp_port = os.environ.get('SMTP_PORT', '25')
    if not smtp_port.isdigit() or not (1 <= int(smtp_port) <= 65535):
        errors.append(f"Invalid SMTP_PORT: {smtp_port}")
    
    # Raise if errors
    if errors:
        raise ConfigurationError(f"Configuration errors: {', '.join(errors)}")
```

### 15. Production Deployment Configuration

**Webhosting-specific configuration**

#### Passenger Configuration
- [ ] **`passenger_wsgi.py`**: Entry point configured
- [ ] **Python version**: Python 3.11 specified
- [ ] **Document root**: Correct directory structure
- [ ] **Environment variables**: Set via hoster control panel

#### Production Settings
- [ ] **SECRET_KEY**: Unique per deployment
- [ ] **DEBUG**: False
- [ ] **SESSION_COOKIE_SECURE**: True
- [ ] **Rate limiting**: Enabled with production limits
- [ ] **Logging**: Appropriate log level (INFO)
- [ ] **Database**: Production database path

#### Secrets Management
- [ ] **Netcup credentials**: From database (admin UI)
- [ ] **SMTP credentials**: From database (admin UI)
- [ ] **Admin password**: From deployment_state_webhosting.json
- [ ] **No secrets in files**: All secrets in env/database

## Expected Deliverable

**Comprehensive configuration review report:**

```markdown
# Configuration & Environment Management - Audit Report

## Executive Summary
- Config quality: ✅ 100% Config-Driven | ⚠️ Mostly Config-Driven | ❌ Hardcoded Values Remain
- Fail-fast compliance: [percentage]%
- Security issues: [count]
- Missing documentation: [count]

## Configuration Audit

### Hardcoded Values
- Found: [count]
- Critical: [list]
- Recommendations: [actions]

### Fail-Fast Compliance
- Shell scripts: [pass/fail count]
- Python code: [pass/fail count]
- Missing error messages: [list]

### Secret Management
- Secrets in version control: [count] (should be 0)
- Secrets in logs: [count] (should be 0)
- Unencrypted secrets: [count]

## Environment-Specific Behavior

### Production
- Correct behavior: ✅/❌
- Issues: [list]

### Local Test
- Correct behavior: ✅/❌
- Issues: [list]

## Documentation Completeness

- Configuration guide: ✅/⚠️/❌
- Environment docs: ✅/⚠️/❌
- Inline comments: [percentage]%
- Examples: ✅/⚠️/❌

## Critical Issues (P0)
1. [Issue] - Location: [file:line] - Risk: [description]

## Recommendations

### Immediate Actions
1. [Action with priority]

### Improvements
...

## Code Examples

### ✅ Good Configuration Pattern
```python
[Example of correct config-driven code]
```

### ❌ Needs Fix
```python
[Example of hardcoded value, with suggested fix]
```

## Code References
- [File:line] - [Finding]
```

---

## Usage

```
Please perform a comprehensive configuration management review using the checklist defined in .vscode/REVIEW_PROMPT_CONFIG_ENVIRONMENT.md.

Focus on:
1. Identifying hardcoded values that should be config-driven
2. Verifying fail-fast compliance
3. Checking secret management practices
4. Validating environment-specific behavior

Provide a structured report with findings, code examples, and remediation steps.
```
