# Deep Dive Review: Multi-Backend TOML Configuration Feature

## Context

We recently redesigned the TOML configuration architecture to support:
- **Multiple backends** of the same provider type (multiple Netcup accounts, PowerDNS instances)
- **User preseeding** with their own backend credentials (BYOD - Bring Your Own Domain)
- **Explicit backend-to-domain mapping** via `[[domain_roots]]` arrays
- **Environment variable substitution** (`${POWERDNS_API_KEY}`)
- **Auto-detection** (`"auto"` for PowerDNS URL)

## Review Objective

Perform a comprehensive, layer-by-layer verification that this feature is:
1. **Completely implemented** - No missing pieces or half-finished code
2. **Correctly integrated** - All layers work together properly
3. **Production-ready** - Error handling, logging, validation in place
4. **Well-tested** - Can be validated end-to-end

## Review Checklist

### 1. TOML Structure & Parsing

**Files:** `app-config.toml`

- [ ] **Array syntax correct**: Verify `[[backends]]`, `[[domain_roots]]`, `[[users]]` parse with Python `tomllib`
- [ ] **All required fields present**: Check each array has all mandatory fields documented in `docs/TOML_CONFIGURATION.md`
- [ ] **Optional fields handled**: Verify defaults applied when optional fields omitted
- [ ] **Comment blocks clear**: Inline documentation matches behavior
- [ ] **Examples valid**: Commented examples are syntactically correct
- [ ] **Legacy sections removed**: Old `[netcup]`, `[platform_backends]`, `[free_domains]` removed or clearly deprecated

**Test:**
```bash
cd /workspaces/netcup-api-filter
python3 -c "
import tomllib
with open('app-config.toml', 'rb') as f:
    config = tomllib.load(f)
    assert 'backends' in config, 'Missing [[backends]]'
    assert 'domain_roots' in config, 'Missing [[domain_roots]]'
    print(f'✓ TOML parses: {len(config[\"backends\"])} backends, {len(config[\"domain_roots\"])} domains')
"
```

### 2. Database Schema Compatibility

**Files:** `src/netcup_api_filter/models.py`

- [ ] **Settings table**: Verify can store `backends_config`, `domain_roots_config`, `users_config` as JSON strings
- [ ] **BackendService model**: Check fields match TOML `[[backends]]` structure
  - [ ] `service_name` (unique)
  - [ ] `provider` (references BackendProvider)
  - [ ] `owner_type` (OwnerTypeEnum: PLATFORM/USER)
  - [ ] `owner_account_id` (nullable, references Account)
  - [ ] `config` (JSON blob for provider-specific settings)
  - [ ] `display_name`, `is_active`
- [ ] **ManagedDomainRoot model**: Check fields match TOML `[[domain_roots]]` structure
  - [ ] `backend_service_id` (references BackendService)
  - [ ] `root_domain`, `dns_zone`
  - [ ] `visibility` (VisibilityEnum: PUBLIC/PRIVATE/INVITE)
  - [ ] `display_name`, `description`
  - [ ] `allow_apex_access`, `min_subdomain_depth`, `max_subdomain_depth`
  - [ ] `allowed_record_types`, `allowed_operations` (JSON arrays or null)
  - [ ] `user_quotas` (JSON blob with `max_hosts_per_user`)
  - [ ] `require_email_verification`
- [ ] **Account model**: Check supports user preseeding
  - [ ] `username`, `email`, `password_hash`
  - [ ] `is_approved`, `must_change_password`
- [ ] **Foreign key relationships**: Verify cascades and nullability correct

**Test:**
```python
# Check model fields exist
from netcup_api_filter.models import BackendService, ManagedDomainRoot, Account
assert hasattr(BackendService, 'service_name')
assert hasattr(BackendService, 'owner_type')
assert hasattr(ManagedDomainRoot, 'visibility')
assert hasattr(ManagedDomainRoot, 'user_quotas')
```

### 3. TOML Import Logic (passenger_wsgi.py)

**Files:** `src/netcup_api_filter/passenger_wsgi.py` (lines ~180-330)

- [ ] **Array iteration**: Verify loops correctly over `config['backends']`, `config['domain_roots']`, `config['users']`
- [ ] **JSON serialization**: Check arrays stored as JSON in database
- [ ] **Field extraction**: All fields from TOML extracted and stored
- [ ] **Logging comprehensive**: Each array processed with clear log messages
- [ ] **Error handling**: Try/except around JSON parsing
- [ ] **Legacy support**: Falls back to old `[netcup]` section if arrays missing
- [ ] **Deprecation warnings**: Logs warnings for legacy sections
- [ ] **Bootstrap called**: `initialize_platform_backends()` invoked after commit
- [ ] **File deletion**: `app-config.toml` deleted after successful import

**Critical checks:**
```python
# Verify JSON structure stored correctly
import json
from netcup_api_filter.database import get_setting

backends_str = get_setting('backends_config')
backends = json.loads(backends_str)
assert isinstance(backends, list), "backends_config must be array"
assert all('service_name' in b for b in backends), "Missing service_name"
```

### 4. Bootstrap Logic (platform_backends.py)

**Files:** `src/netcup_api_filter/bootstrap/platform_backends.py`

**Step 1: User Preseeding**
- [ ] **Users created first**: `[[users]]` processed before `[[backends]]` (user-owned backends need existing users)
- [ ] **Duplicate check**: Existing usernames skipped
- [ ] **Password generation**: `password = "generate"` creates random password via `generate_token(32)`
- [ ] **Password logging**: Generated passwords logged once with clear "SAVE THIS" warning
- [ ] **Password hashing**: Uses `hash_password()` not plaintext
- [ ] **Fields mapped**: All TOML fields (`is_approved`, `must_change_password`) applied to Account model
- [ ] **Commit timing**: `db.session.commit()` after all users created

**Step 2: Backend Creation**
- [ ] **Environment variable substitution**: `${POWERDNS_API_KEY}` replaced with `os.environ.get()`
- [ ] **Auto-detection**: `api_url = "auto"` calls `get_powerdns_api_url()`
- [ ] **URL detection logic**: Checks (1) explicit config → (2) HOSTNAME_POWERDNS → (3) PUBLIC_FQDN → (4) localhost
- [ ] **Owner type handling**: `owner = "platform"` vs `owner = "username"` correctly resolved
- [ ] **User lookup**: Finds user from `users_created` dict or database query
- [ ] **Duplicate check**: Existing `service_name` skipped
- [ ] **Provider validation**: Provider exists (calls `seed_backend_providers()` if missing)
- [ ] **Config processing**: Nested dict values handled (inline tables in TOML)
- [ ] **Error handling**: Logs errors if user not found for user-owned backend
- [ ] **Commit timing**: `db.session.commit()` after all backends created

**Step 3: Domain Root Creation**
- [ ] **Backend reference resolution**: Finds backend by `service_name` from previous step or database
- [ ] **Duplicate check**: Existing `(backend_service_id, root_domain)` tuple skipped
- [ ] **Visibility mapping**: String `"public"` → `VisibilityEnum.PUBLIC`
- [ ] **Quota handling**: `max_hosts_per_user` stored in `user_quotas` JSON field
- [ ] **Array fields**: `allowed_record_types` and `allowed_operations` stored correctly
- [ ] **Null handling**: `null` in TOML (omitted fields) → `None` in database
- [ ] **Error handling**: Logs error if backend not found
- [ ] **Commit timing**: `db.session.commit()` after all domain roots created

**Step 4: Legacy Fallback**
- [ ] **Detection**: Falls back to old structure if `backends_config` / `domain_roots_config` not found
- [ ] **Old functions called**: `setup_platform_powerdns()`, `setup_platform_netcup()`, `setup_free_domains()`
- [ ] **Log messages**: Clear indication of legacy vs new path

**Critical checks:**
```python
# Verify bootstrap creates database entries
from netcup_api_filter.models import BackendService, ManagedDomainRoot, Account

# Check backends created
backends = BackendService.query.all()
assert len(backends) > 0, "No backends created"
assert any(b.service_name == 'platform-powerdns' for b in backends), "PowerDNS backend missing"

# Check domain roots created
roots = ManagedDomainRoot.query.all()
assert len(roots) > 0, "No domain roots created"
assert any(r.root_domain == 'powerdomains.vxxu.de' for r in roots), "Free domain missing"

# Check backend-domain link
root = ManagedDomainRoot.query.filter_by(root_domain='powerdomains.vxxu.de').first()
assert root.backend_service is not None, "Domain not linked to backend"
assert root.backend_service.provider.provider_code == 'powerdns', "Wrong backend type"
```

### 5. Integration with Existing Architecture

**Files:** `src/netcup_api_filter/bootstrap/seeding.py`

- [ ] **create_backend_service()**: Called correctly with all parameters
  - [ ] `provider_code` matches BackendProvider.provider_code
  - [ ] `service_name` unique constraint honored
  - [ ] `config` parameter is dict (not JSON string)
  - [ ] `owner_type` is string `"platform"` or `"user"`
  - [ ] `owner_account_id` set for user-owned, None for platform
- [ ] **create_domain_root()**: Called correctly with all parameters
  - [ ] `backend_service` is BackendService instance (not name)
  - [ ] `visibility` is string `"public"`, `"private"`, `"invite"`
  - [ ] `allowed_record_types` is Python list or None
  - [ ] `allowed_operations` is Python list or None
- [ ] **seed_backend_providers()**: Called before creating backends
- [ ] **Return values**: Functions return created instances

### 6. Environment Variable Handling

**Files:** `src/netcup_api_filter/bootstrap/platform_backends.py` (lines ~120-140)

- [ ] **Substitution pattern**: Detects `${...}` syntax correctly
- [ ] **Variable extraction**: Strips `${` and `}` to get variable name
- [ ] **Environment lookup**: Uses `os.environ.get(var_name, '')` with empty string default
- [ ] **Missing variable logging**: Warns if environment variable not set
- [ ] **Non-string values**: Skips substitution for integers, booleans
- [ ] **Nested configs**: Handles dict values recursively

**Test:**
```bash
# Set test env var
export TEST_API_KEY="test-key-12345"

# Create test TOML
cat > /tmp/test-env-vars.toml <<'EOF'
[[backends]]
service_name = "test"
provider = "powerdns"
owner = "platform"
config = { api_key = "${TEST_API_KEY}", api_url = "http://localhost" }
EOF

# Parse and check substitution
python3 -c "
import tomllib, os
with open('/tmp/test-env-vars.toml', 'rb') as f:
    config = tomllib.load(f)
    api_key = config['backends'][0]['config']['api_key']
    assert api_key == '\${TEST_API_KEY}', 'TOML should preserve literal'
    
    # Simulate bootstrap substitution
    if api_key.startswith('\${') and api_key.endswith('}'):
        env_var = api_key[2:-1]
        api_key = os.environ.get(env_var, '')
    assert api_key == 'test-key-12345', 'Substitution failed'
    print('✓ Environment variable substitution works')
"
```

### 7. Auto-Detection Features

**Files:** `src/netcup_api_filter/bootstrap/platform_backends.py::get_powerdns_api_url()`

- [ ] **"auto" trigger**: Detects `api_url = "auto"` in config
- [ ] **Priority order**: (1) Explicit config → (2) HOSTNAME_POWERDNS → (3) PUBLIC_FQDN → (4) localhost
- [ ] **Environment variables**: Reads `HOSTNAME_POWERDNS`, `PUBLIC_FQDN`
- [ ] **URL construction**: Formats correctly (http:// vs https://, ports, paths)
- [ ] **Logging**: Each detection step logged
- [ ] **Fallback warning**: Warns if localhost used (likely wrong)

**Test:**
```bash
# Test auto-detection
export HOSTNAME_POWERDNS="naf-dev-powerdns"
export PUBLIC_FQDN="test.example.com"

python3 -c "
import os, sys
sys.path.insert(0, '/workspaces/netcup-api-filter/src')
from netcup_api_filter.bootstrap.platform_backends import get_powerdns_api_url

url = get_powerdns_api_url()
print(f'Detected URL: {url}')
assert 'naf-dev-powerdns' in url or 'test.example.com' in url, 'Auto-detection failed'
"
```

### 8. Error Handling & Validation

**Cross-cutting concerns**

- [ ] **JSON parse errors**: Try/except around all `json.loads()` calls
- [ ] **Missing required fields**: Checks before accessing TOML keys
- [ ] **Foreign key violations**: User/backend existence validated before foreign key assignment
- [ ] **Duplicate entries**: Checks existing before `db.session.add()`
- [ ] **Database errors**: Try/except around commits with rollback
- [ ] **Logging comprehensive**: All errors logged with context (which backend/domain failed)
- [ ] **Partial success**: Continues processing remaining items after error
- [ ] **No crashes**: App starts even if bootstrap partially fails

### 9. Idempotency & Safety

**Re-import behavior**

- [ ] **Duplicate user**: Existing username skipped, logged, continues
- [ ] **Duplicate backend**: Existing service_name skipped, logged, continues
- [ ] **Duplicate domain**: Existing (backend_service_id, root_domain) skipped
- [ ] **No overwrites**: Existing entries NOT modified (safe to re-run)
- [ ] **Logging clear**: "already exists" messages distinguish from creation
- [ ] **Return values**: Functions return existing instance when found

**Test:**
```python
# Simulate double import
from netcup_api_filter.bootstrap.platform_backends import initialize_platform_backends

# First import
initialize_platform_backends()
backends_count_1 = BackendService.query.count()

# Second import (should skip duplicates)
initialize_platform_backends()
backends_count_2 = BackendService.query.count()

assert backends_count_1 == backends_count_2, "Not idempotent - duplicates created"
```

### 10. Logging & Observability

**Log message quality**

- [ ] **Structured logging**: Uses module logger (`logger = logging.getLogger(__name__)`)
- [ ] **Log levels correct**: INFO for normal, WARNING for issues, ERROR for failures
- [ ] **Context included**: Service names, usernames, domains in messages
- [ ] **Progress tracking**: `[1/3]`, `[2/3]` style counters for arrays
- [ ] **Success indicators**: `✓` checkmarks for completed steps
- [ ] **Error details**: Exception info included (`exc_info=True`)
- [ ] **Secrets redacted**: No full API keys/passwords in logs (use `[:8]...` truncation)
- [ ] **Generated passwords**: Shown once with "SAVE THIS" warning

**Log review:**
```bash
# Check logs during import
grep -E "(backends|domain_roots|users)" netcup_filter.log
# Should see structured messages like:
# [INFO] Processing [[backends]] arrays: 2 backend(s) defined
# [INFO]   [1] platform-powerdns (provider: powerdns, owner: platform)
# [INFO] Created backend: platform-powerdns
```

### 11. Documentation Completeness

**Files:** `docs/TOML_CONFIGURATION.md`

- [ ] **All fields documented**: Every `[[backends]]`, `[[domain_roots]]`, `[[users]]` field explained
- [ ] **Types clear**: String, int, bool, array, object types specified
- [ ] **Required vs optional**: Clearly marked
- [ ] **Special values**: `"auto"`, `"generate"`, `"${...}"` explained
- [ ] **Examples realistic**: Working configs, not placeholders
- [ ] **Use cases covered**: Free DDNS, multiple accounts, BYOD, mixed scenarios
- [ ] **Migration guide**: Legacy → new structure conversion path
- [ ] **Troubleshooting**: Common errors and solutions
- [ ] **Cross-references**: Links to related docs (ENV_WORKSPACE.md, FQDN_DETECTION.md)

### 12. End-to-End Integration Test

**Full workflow verification**

1. **Setup test TOML:**
```bash
cat > /tmp/test-config.toml <<'EOF'
[[backends]]
service_name = "test-powerdns"
provider = "powerdns"
owner = "platform"
config = { api_url = "http://localhost:8081", api_key = "test-key", server_id = "localhost" }

[[domain_roots]]
backend = "test-powerdns"
domain = "test.local"
visibility = "public"
max_hosts_per_user = 3

[[users]]
username = "testuser"
email = "test@test.local"
password = "generate"
is_approved = true
EOF
```

2. **Run import:**
```python
import os, sys, json
sys.path.insert(0, '/workspaces/netcup-api-filter/src')
os.environ['DATABASE_URL'] = 'sqlite:////tmp/test.db'

from netcup_api_filter.database import init_db, get_setting, set_setting
from netcup_api_filter.bootstrap.platform_backends import initialize_platform_backends
import tomllib

# Initialize database
init_db()

# Simulate passenger_wsgi.py import
with open('/tmp/test-config.toml', 'rb') as f:
    config = tomllib.load(f)
    
# Store configs
set_setting('backends_config', json.dumps(config.get('backends', [])))
set_setting('domain_roots_config', json.dumps(config.get('domain_roots', [])))
set_setting('users_config', json.dumps(config.get('users', [])))

# Run bootstrap
initialize_platform_backends()
```

3. **Verify results:**
```python
from netcup_api_filter.models import BackendService, ManagedDomainRoot, Account

# Check user created
user = Account.query.filter_by(username='testuser').first()
assert user is not None, "User not created"
assert user.is_approved == True, "User not approved"

# Check backend created
backend = BackendService.query.filter_by(service_name='test-powerdns').first()
assert backend is not None, "Backend not created"
assert backend.provider.provider_code == 'powerdns', "Wrong provider"
assert backend.owner_type.value == 'platform', "Wrong owner type"

# Check domain created
domain = ManagedDomainRoot.query.filter_by(root_domain='test.local').first()
assert domain is not None, "Domain not created"
assert domain.backend_service_id == backend.id, "Domain not linked to backend"
assert domain.visibility.value == 'public', "Wrong visibility"

# Check quota
import json
quotas = json.loads(domain.user_quotas)
assert quotas['max_hosts_per_user'] == 3, "Quota not set"

print("✓ End-to-end test PASSED")
```

### 13. Production Readiness Checks

**Deployment considerations**

- [ ] **No hardcoded values**: All config from TOML/environment
- [ ] **Fail-fast on missing vars**: Clear errors if required env vars missing
- [ ] **Secrets handling**: No secrets in logs, only in database encrypted fields
- [ ] **Performance**: Bulk operations where possible (not N+1 queries)
- [ ] **Transaction safety**: Database operations in transactions
- [ ] **Rollback on error**: Partial imports don't corrupt database
- [ ] **Monitoring hooks**: Logs structured enough for monitoring tools
- [ ] **Documentation current**: README, AGENTS.md reference new structure

## Review Execution Plan

1. **Read code files** in order:
   - `app-config.toml` → Understand structure
   - `src/netcup_api_filter/passenger_wsgi.py` → Import logic
   - `src/netcup_api_filter/bootstrap/platform_backends.py` → Bootstrap logic
   - `src/netcup_api_filter/models.py` → Database schema
   - `docs/TOML_CONFIGURATION.md` → Documentation

2. **Run validation tests** from checklist sections above

3. **Trace execution path** through code:
   - TOML → passenger_wsgi.py → database → platform_backends.py → models
   - Identify any broken links or missing steps

4. **Test error paths**:
   - Missing required fields
   - Invalid references (backend not found)
   - Duplicate entries
   - Environment variables not set

5. **Verify integration points**:
   - Backend providers seeded
   - Foreign keys resolve correctly
   - Enums convert properly (string → enum)
   - JSON serialization round-trips

6. **Check documentation accuracy**:
   - Examples actually work
   - Field descriptions match code behavior
   - Special values implemented as documented

## Expected Deliverable

**Comprehensive report structured as:**

```markdown
# Multi-Backend TOML Configuration - Implementation Review

## Executive Summary
- Overall status: ✅ Complete | ⚠️ Incomplete | ❌ Broken
- Critical issues: [count]
- Blockers for production: [list]

## Layer-by-Layer Analysis

### 1. TOML Structure & Parsing
- Status: [✅/⚠️/❌]
- Issues found: [list or "None"]
- Evidence: [test output, code references]

### 2. Database Schema Compatibility
...

[Continue for all 13 sections]

## Critical Issues (P0 - Must Fix)
1. [Issue description] - Location: [file:line] - Impact: [description]

## Important Issues (P1 - Should Fix)
...

## Recommendations
1. [Specific actionable item]
2. ...

## Code References
- [File:line] - [Finding description]
```

---

## Usage

Copy this prompt and provide it to a Copilot agent or use it as a review guide:

```
Please perform a comprehensive deep-dive review of the multi-backend TOML configuration feature using the checklist and methodology defined in .vscode/REVIEW_PROMPT_MULTI_BACKEND_TOML.md. 

Focus on:
1. Verifying complete implementation across all layers
2. Testing critical integration points
3. Identifying any gaps or bugs
4. Validating production readiness

Provide a structured report with findings, evidence, and specific recommendations.
```
