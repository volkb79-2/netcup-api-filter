# CONFIG_DRIVEN_ARCHITECTURE (Retired)

Use `CONFIGURATION_GUIDE.md` for the authoritative description of our config-driven and fail-fast policies. Update that guide (and `.env.defaults`) whenever you add or change configuration values.
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
