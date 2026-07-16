

## Repository State Analysis & Multi-Backend Proposal

### Current State Assessment (Updated: 2026-01-10)

#### ✅ Strong Foundations
1. **Account → Realms → Tokens Architecture**: Well-designed 3-tier permission system
2. **Config-Driven Design**: .env.defaults + environment + database Settings model
3. **PowerDNS Infrastructure**: Init container pattern, Docker integration, API ready
4. **Comprehensive Testing**: 90+ tests (UI, E2E, journey contracts)
5. **Security**: ✅ **AUDITED** (Security Review Report complete - see `docs/SECURITY_REVIEW_REPORT.md`)
   - CSRF, 2FA, bcrypt, input validation, XSS protection
   - Security headers implemented (X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy)
   - 0 critical/high vulnerabilities
   - 1 medium (fixed), 4 low, 3 informational findings
   - OWASP Top 10 2021: 9/10 coverage (A05 security headers fixed in review)

#### ✅ Completed Reviews (6/7)

1. **Configuration & Environment** (`docs/CONFIG_ENVIRONMENT_REVIEW.md`)
   - Status: ✅ 100% config-driven, fail-fast compliant (95% compliance score)
   - Action needed: None (excellent state)

2. **Admin UI & UX** (`docs/ADMIN_UI_UX_REVIEW.md`)
   - Status: ✅ Production-ready (9/10 consistency, 86 templates, 19 themes)
   - Action needed: None

3. **Database Models** (`docs/DATABASE_MODELS_REVIEW.md`)
   - Status: ✅ Excellent schema design (0 critical issues, 3NF+, proper indexes)
   - Action needed: None

4. **Deployment & Operations** (`docs/DEPLOYMENT_OPS_REVIEW.md`)
   - Status: ✅ Fully automated (100% production parity, single-command deployment)
   - Action needed: None

5. **Testing Coverage** (`docs/TESTING_COVERAGE_REVIEW.md`)
   - Status: ✅ Comprehensive strategy (90+ tests, multi-layer approach)
   - Gap: Route coverage only 27% (21/77 routes)
   - Gap: Account portal authenticated pages not tested
   - Action: P2 - Expand test coverage (non-blocking)

6. **Authentication & Security** (`docs/SECURITY_REVIEW_REPORT.md`) ✅ **NEW**
   - Status: ✅ Strong security posture
   - Findings: 0 critical, 0 high, 1 medium (fixed), 4 low, 3 informational
   - Security headers: ✅ Implemented (X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy)
   - OWASP Top 10: 9/10 coverage (A05 security misconfiguration fixed)
   - Action needed: Low-priority improvements (password history, 2FA lockout, session regeneration)

#### ⚠️ Remaining Review (1/7)

**Multi-Backend TOML Configuration** (REVIEW_PROMPT_MULTI_BACKEND_TOML.md)
   - Status: ❌ No audit report found
   - Priority: **P1 (High)** - Recently implemented feature (app-config.example.toml refactoring)
   - Scope: TOML parsing, environment substitution, bootstrap logic, idempotency
   - Action: Complete end-to-end review with integration tests

#### ⚠️ Areas Needing Improvement (Post-Security Review)

**1. Test Coverage Expansion (P2 - Medium)**
   - ⚠️ Only 27% route coverage (21/77 routes)
   - ⚠️ Account portal authenticated pages untested
   - ⚠️ Admin token management routes untested
   - Target: Increase coverage from 27% to 60%+
   - Add pytest-cov configuration
   - Set coverage threshold (80%+)

**2. Backend Abstraction (COMPLETE - Multi-Backend Architecture)**
   - ✅ `backends/` module exists
   - ✅ Abstract `DNSBackend` interface
   - ✅ Netcup and PowerDNS implementations
   - ✅ Backend registry with provider discovery
   - ✅ 9 new database tables (BackendProvider, BackendService, ManagedDomainRoot, etc.)
   - ✅ Admin UI for backend management (10+ templates)
   - ✅ User backend management (BYOD)
   - ✅ 28 tests (14 journey, 14 UI)
   - 🔲 Cloudflare/Route53 backends (future)

**3. Security Enhancements (P3 - Low Priority)**
   - From Security Review Report:
     - ⚠️ Password history not implemented (users can reuse old passwords)
     - ⚠️ Session not regenerated on login (minor session fixation risk)
     - ⚠️ Recovery code rate limiting (potential brute force)
     - ⚠️ 2FA code rate limiting (account lockout after X failures)
   - These are low-priority improvements, not blockers

**4. Additional Documentation Needed**
   - ⚠️ Multi-Backend TOML review report (see Remaining Review above)
   - ⚠️ User guides for BYOD (Bring Your Own DNS)
   - ⚠️ Migration guide from single-backend to multi-backend

---

## Updated Recommended Action Plan (January 10, 2026)

### ✅ Completed Since Last Review

1. **Security Review** (`copilot/review-authentication-security` branch)
   - Full authentication/authorization audit completed
   - Security headers implemented
   - 3 new documentation files:
     - `docs/SECURITY_REVIEW_REPORT.md` - Comprehensive security audit
     - `docs/SECURITY.md` - Security hardening guide
     - `docs/SECURITY_ERROR_TAXONOMY.md` - Error classification system
   - Result: 0 critical/high vulnerabilities, ready for production

### 🎯 Immediate Priorities

#### Priority 1: Multi-Backend TOML Review (P1 - High) - 2-3 hours

**Why this is critical:**
- Recent major refactoring: `app-config.toml.example` → `app-config.example.toml`
- TOML import logic in `passenger_wsgi.py` is complex (environment substitution, auto-detection)
- Bootstrap logic (`platform_backends.py`) has many integration points
- No end-to-end validation since refactoring

**Specific tasks:**
1. Read REVIEW_PROMPT_MULTI_BACKEND_TOML.md checklist
2. Trace code path: TOML → passenger_wsgi.py → database → platform_backends.py
3. Write end-to-end integration test:
   - Create test TOML with backends, domain_roots, users
   - Verify database state after import
   - Test environment variable substitution edge cases
   - Test idempotency (double import should be safe)
   - Test error paths (missing user, invalid backend ref)
4. Document findings in `docs/MULTI_BACKEND_TOML_REVIEW.md`

**Expected outcome:** Confidence in TOML configuration system before production deployment.

#### Priority 2: Test Coverage Expansion (P2 - Medium) - 4-6 hours

**Current state:** 27% route coverage (21/77 routes)

**Focus areas:**
1. Account portal authenticated routes:
   - Dashboard (`/account/dashboard`)
   - Realms management (`/account/realms/*`)
   - Tokens management (`/account/tokens/*`)
   - DNS records (`/account/dns/*`)
   - 2FA setup (`/account/2fa/*`)
2. Admin token management routes (`/admin/tokens/*`)
3. Admin API routes (`/admin/api/*`)

**Target:** Increase coverage from 27% to 60%+

**Implementation:**
- Add pytest-cov configuration to `pytest.ini`
- Set coverage threshold (80%+)
- Write Playwright tests for missing routes
- Focus on authenticated journeys (avoid duplicating login tests)

#### Priority 3: Security Enhancements (P3 - Low) - 3-4 hours

**From Security Review Report (non-blocking improvements):**

1. **Password History** (1 hour)
   - Store hash of last 5 passwords
   - Prevent reuse during password change
   - Database: Add `password_history` table

2. **2FA Attempt Lockout** (1.5 hours)
   - Lock account after 5 failed 2FA attempts
   - Require email notification to unlock
   - Add to existing `_track_failed_login()` pattern

3. **Session Regeneration** (0.5 hour)
   - Explicitly regenerate session ID after login
   - Implement absolute session timeout

4. **Recovery Code Rate Limiting** (1 hour)
   - Add rate limiting to recovery code attempts
   - Leverage existing Flask-Limiter configuration

**Note:** These are quality-of-life improvements, not security blockers.

---

## Complete Multi-Backend Implementation Proposal

**STATUS UPDATE:** This entire proposal has been ✅ **IMPLEMENTED**. See "Implementation Status Summary" section at the end for details.

The multi-backend architecture is production-ready with:
- 9 new database tables
- Backend abstraction layer (Netcup + PowerDNS)
- Admin UI (10+ templates)
- User BYOD support
- 28 comprehensive tests

**Remaining work:**
- 🔲 Additional provider implementations (Cloudflare, Route53)
- 🔲 Encryption at rest for credentials (requires external KMS)
- 🔲 User documentation for BYOD workflows

### Phase 1: Database Schema (1 day)

**Add `backend_services` table:**
```sql
CREATE TABLE backend_services (
    id INTEGER PRIMARY KEY,
    service_name VARCHAR(64) UNIQUE NOT NULL,        -- 'netcup-global', 'powerdns-local'
    backend_type VARCHAR(32) NOT NULL,               -- 'netcup', 'powerdns'
    display_name VARCHAR(128) NOT NULL,              -- 'Netcup CCP API', 'Local PowerDNS'
    
    -- Configuration (JSON)
    config TEXT NOT NULL,                            -- {"api_url": "...", "api_key": "..."}
    
    -- Status
    is_active BOOLEAN DEFAULT 1,
    is_default BOOLEAN DEFAULT 0,                    -- Default for new realms
    
    -- Metadata
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    last_tested_at DATETIME,
    test_status VARCHAR(20),                         -- 'success', 'failed', NULL
    test_message TEXT,
    
    CHECK(backend_type IN ('netcup', 'powerdns'))
);

-- Modify account_realms table
ALTER TABLE account_realms ADD COLUMN backend_service_id INTEGER REFERENCES backend_services(id);
ALTER TABLE account_realms ADD COLUMN backend_config TEXT;  -- Optional: per-realm credential override

-- Default index
CREATE INDEX idx_backend_services_active ON backend_services(is_active, is_default);
```

**Migration script:**
```python
# migrations/add_backend_services.py
def upgrade():
    # Create table
    op.create_table('backend_services', ...)
    
    # Seed default Netcup backend from existing settings
    netcup_config = Settings.get('netcup_config')
    if netcup_config:
        op.execute("""
            INSERT INTO backend_services (service_name, backend_type, display_name, config, is_active, is_default)
            VALUES ('netcup-global', 'netcup', 'Netcup CCP API (Global)', ?, 1, 1)
        """, json.dumps(netcup_config))
    
    # Add PowerDNS backend if configured
    powerdns_key = os.environ.get('POWERDNS_API_KEY')
    if powerdns_key:
        op.execute("""
            INSERT INTO backend_services (service_name, backend_type, display_name, config, is_active, is_default)
            VALUES ('powerdns-local', 'powerdns', 'PowerDNS (Local)', ?, 1, 0)
        """, json.dumps({
            'api_url': 'http://naf-dev-powerdns:8081',
            'api_key': powerdns_key
        }))
```

### Phase 2: Backend Abstraction Layer (2 days)

**Create `src/netcup_api_filter/backends/` module:**

```
src/netcup_api_filter/backends/
├── __init__.py              # Public API
├── base.py                  # Abstract base class
├── netcup.py                # Netcup CCP implementation
├── powerdns.py              # PowerDNS implementation
└── registry.py              # Backend factory/registry
```

**`base.py` - Abstract Interface:**
```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class DNSBackend(ABC):
    """Abstract base class for DNS backends."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
    
    @abstractmethod
    def test_connection(self) -> tuple[bool, str]:
        """Test backend connectivity. Returns (success, message)."""
        pass
    
    @abstractmethod
    def list_records(self, domain: str) -> List[Dict[str, Any]]:
        """List all DNS records for a domain."""
        pass
    
    @abstractmethod
    def create_record(self, domain: str, record: Dict[str, Any]) -> Dict[str, Any]:
        """Create a DNS record. Returns created record."""
        pass
    
    @abstractmethod
    def update_record(self, domain: str, record_id: str, record: Dict[str, Any]) -> Dict[str, Any]:
        """Update a DNS record. Returns updated record."""
        pass
    
    @abstractmethod
    def delete_record(self, domain: str, record_id: str) -> bool:
        """Delete a DNS record. Returns success status."""
        pass
    
    @abstractmethod
    def get_zone_info(self, domain: str) -> Dict[str, Any]:
        """Get zone information."""
        pass
    
    def normalize_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize record format to common schema."""
        return {
            'id': record.get('id'),
            'hostname': record.get('hostname', '@'),
            'type': record.get('type'),
            'destination': record.get('destination') or record.get('content'),
            'priority': record.get('priority'),
            'ttl': record.get('ttl', 300)
        }
```

**`netcup.py` - Netcup Implementation:**
```python
from .base import DNSBackend
from ..netcup_client import NetcupClient

class NetcupBackend(DNSBackend):
    """Netcup CCP API backend."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.client = NetcupClient(
            customer_id=config['customer_id'],
            api_key=config['api_key'],
            api_password=config['api_password'],
            api_url=config.get('api_url', 'https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON'),
            timeout=config.get('timeout', 30)
        )
    
    def test_connection(self) -> tuple[bool, str]:
        try:
            self.client.login()
            self.client.logout()
            return True, "Connection successful"
        except Exception as e:
            return False, str(e)
    
    def list_records(self, domain: str) -> List[Dict[str, Any]]:
        records = self.client.info_dns_records(domain)
        return [self.normalize_record(r) for r in records]
    
    def create_record(self, domain: str, record: Dict[str, Any]) -> Dict[str, Any]:
        # Get existing records
        existing = self.client.info_dns_records(domain)
        # Add new record
        existing.append({
            'hostname': record['hostname'],
            'type': record['type'],
            'destination': record['destination'],
            'priority': record.get('priority', '')
        })
        # Update zone
        result = self.client.update_dns_records(domain, existing)
        return self.normalize_record(record)
    
    def update_record(self, domain: str, record_id: str, record: Dict[str, Any]) -> Dict[str, Any]:
        # Netcup doesn't have record IDs - update by matching hostname+type
        existing = self.client.info_dns_records(domain)
        for idx, rec in enumerate(existing):
            if rec['id'] == record_id or (rec['hostname'] == record['hostname'] and rec['type'] == record['type']):
                existing[idx] = {
                    'hostname': record['hostname'],
                    'type': record['type'],
                    'destination': record['destination'],
                    'priority': record.get('priority', '')
                }
                break
        self.client.update_dns_records(domain, existing)
        return self.normalize_record(record)
    
    def delete_record(self, domain: str, record_id: str) -> bool:
        existing = self.client.info_dns_records(domain)
        filtered = [r for r in existing if r.get('id') != record_id]
        self.client.update_dns_records(domain, filtered)
        return True
    
    def get_zone_info(self, domain: str) -> Dict[str, Any]:
        return self.client.info_dns_zone(domain)
```

**`powerdns.py` - PowerDNS Implementation:**
```python
import httpx
from .base import DNSBackend

class PowerDNSBackend(DNSBackend):
    """PowerDNS Authoritative Server backend."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_url = config['api_url'].rstrip('/')
        self.api_key = config['api_key']
        self.client = httpx.Client(
            base_url=self.api_url,
            headers={'X-API-Key': self.api_key},
            timeout=config.get('timeout', 30)
        )
    
    def test_connection(self) -> tuple[bool, str]:
        try:
            response = self.client.get('/api/v1/servers/localhost')
            response.raise_for_status()
            data = response.json()
            return True, f"Connected to PowerDNS {data.get('version')}"
        except Exception as e:
            return False, str(e)
    
    def list_records(self, domain: str) -> List[Dict[str, Any]]:
        zone = domain if domain.endswith('.') else f"{domain}."
        response = self.client.get(f'/api/v1/servers/localhost/zones/{zone}')
        response.raise_for_status()
        zone_data = response.json()
        
        records = []
        for rrset in zone_data.get('rrsets', []):
            for record in rrset.get('records', []):
                records.append(self.normalize_record({
                    'id': f"{rrset['name']}:{rrset['type']}",
                    'hostname': rrset['name'].rstrip('.'),
                    'type': rrset['type'],
                    'content': record['content'],
                    'ttl': rrset.get('ttl', 60)
                }))
        return records
    
    def create_record(self, domain: str, record: Dict[str, Any]) -> Dict[str, Any]:
        zone = domain if domain.endswith('.') else f"{domain}."
        name = record['hostname']
        if not name.endswith('.'):
            name = f"{name}.{zone}"
        
        rrset = {
            "name": name,
            "type": record['type'],
            "changetype": "REPLACE",
            "ttl": record.get('ttl', 60),
            "records": [{"content": record['destination'], "disabled": False}]
        }
        
        response = self.client.patch(
            f'/api/v1/servers/localhost/zones/{zone}',
            json={"rrsets": [rrset]}
        )
        response.raise_for_status()
        return self.normalize_record(record)
    
    def update_record(self, domain: str, record_id: str, record: Dict[str, Any]) -> Dict[str, Any]:
        # PowerDNS uses REPLACE changetype - same as create
        return self.create_record(domain, record)
    
    def delete_record(self, domain: str, record_id: str) -> bool:
        # record_id format: "hostname:type"
        name, rtype = record_id.split(':', 1)
        zone = domain if domain.endswith('.') else f"{domain}."
        
        rrset = {
            "name": name if name.endswith('.') else f"{name}.{zone}",
            "type": rtype,
            "changetype": "DELETE"
        }
        
        response = self.client.patch(
            f'/api/v1/servers/localhost/zones/{zone}',
            json={"rrsets": [rrset]}
        )
        response.raise_for_status()
        return True
    
    def get_zone_info(self, domain: str) -> Dict[str, Any]:
        zone = domain if domain.endswith('.') else f"{domain}."
        response = self.client.get(f'/api/v1/servers/localhost/zones/{zone}')
        response.raise_for_status()
        return response.json()
```

**`registry.py` - Backend Factory:**
```python
from typing import Dict, Type
from .base import DNSBackend
from .netcup import NetcupBackend
from .powerdns import PowerDNSBackend

BACKEND_REGISTRY: Dict[str, Type[DNSBackend]] = {
    'netcup': NetcupBackend,
    'powerdns': PowerDNSBackend,
}

def get_backend(backend_type: str, config: Dict[str, Any]) -> DNSBackend:
    """Get backend instance by type."""
    backend_class = BACKEND_REGISTRY.get(backend_type)
    if not backend_class:
        raise ValueError(f"Unknown backend type: {backend_type}")
    return backend_class(config)

def get_backend_for_realm(realm: 'AccountRealm') -> DNSBackend:
    """Get backend instance for a realm."""
    from ..models import db
    from ..models import BackendService
    
    # Get realm's backend service
    service = BackendService.query.get(realm.backend_service_id)
    if not service or not service.is_active:
        # Fallback to default
        service = BackendService.query.filter_by(is_default=True, is_active=True).first()
        if not service:
            raise ValueError("No active backend service configured")
    
    # Use per-realm config override if exists, otherwise service config
    config = realm.backend_config or service.config
    return get_backend(service.backend_type, config)
```

**__init__.py - Public API:**
```python
from .base import DNSBackend
from .registry import get_backend, get_backend_for_realm
from .netcup import NetcupBackend
from .powerdns import PowerDNSBackend

__all__ = [
    'DNSBackend',
    'get_backend',
    'get_backend_for_realm',
    'NetcupBackend',
    'PowerDNSBackend',
]
```

### Phase 3: Refactor Existing Code (1 day)

**Update dns_api.py:**
```python
from ..backends import get_backend_for_realm

@dns_api_bp.route('/dns/<domain>/records', methods=['GET'])
@require_auth
def list_records(domain):
    """List DNS records for a domain."""
    auth = g.auth
    realm = g.realm
    
    # Check permission
    perm = check_permission(auth, 'read', domain)
    if not perm.granted:
        return jsonify({'error': 'forbidden'}), 403
    
    try:
        # Get backend for realm
        backend = get_backend_for_realm(realm)
        
        # Fetch records
        records = backend.list_records(domain)
        
        # Filter by realm scope
        filtered = filter_records_by_realm(records, realm, domain)
        
        log_activity(auth, 'read', domain=domain, success=True)
        return jsonify({'records': filtered})
        
    except Exception as e:
        logger.error(f"Failed to list records: {e}", exc_info=True)
        return jsonify({'error': 'backend_error', 'message': str(e)}), 500
```

### Phase 4: Admin UI for Backend Management (2 days)

**New route: `/admin/backends`**

```html
<!-- admin/backend_services.html -->
<h1>DNS Backend Services</h1>

<table>
  <thead>
    <tr>
      <th>Service Name</th>
      <th>Backend Type</th>
      <th>Status</th>
      <th>Last Tested</th>
      <th>Actions</th>
    </tr>
  </thead>
  <tbody>
    {% for service in services %}
    <tr>
      <td>{{ service.display_name }}</td>
      <td><code>{{ service.backend_type }}</code></td>
      <td>
        {% if service.test_status == 'success' %}
        <span class="badge bg-success">✓ Connected</span>
        {% else %}
        <span class="badge bg-danger">✗ Failed</span>
        {% endif %}
      </td>
      <td>{{ service.last_tested_at }}</td>
      <td>
        <a href="{{ url_for('admin.backend_edit', id=service.id) }}">Edit</a>
        <a href="{{ url_for('admin.backend_test', id=service.id) }}">Test</a>
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>

<a href="{{ url_for('admin.backend_create') }}" class="btn btn-primary">
  <i class="bi bi-plus"></i>Add Backend Service
</a>
```

**New route: `/admin/backends/create`**
```html
<!-- Form to add Netcup or PowerDNS backend -->
<select name="backend_type">
  <option value="netcup">Netcup CCP API</option>
  <option value="powerdns">PowerDNS</option>
</select>

<!-- Dynamic form fields based on backend_type -->
<div id="netcup-fields" style="display:none">
  <input name="customer_id" placeholder="Customer ID">
  <input name="api_key" placeholder="API Key">
  <input name="api_password" type="password">
</div>

<div id="powerdns-fields" style="display:none">
  <input name="api_url" value="http://naf-dev-powerdns:8081">
  <input name="api_key" type="password">
</div>
```

**Update realm creation form:**
```html
<!-- admin/realm_create.html -->
<select name="backend_service_id" required>
  <option value="">Select DNS Backend...</option>
  {% for service in backend_services %}
  <option value="{{ service.id }}" {% if service.is_default %}selected{% endif %}>
    {{ service.display_name }}
  </option>
  {% endfor %}
</select>
```

### Phase 5: Testing & Documentation (1 day)

**Test matrix:**
- ✅ Backend abstraction (unit tests for each backend)
- ✅ Realm routing (integration tests)
- ✅ Admin UI (journey tests for backend management)
- ✅ Multi-backend scenarios (Netcup + PowerDNS simultaneously)

**Documentation:**
- `docs/BACKEND_ABSTRACTION.md` - Architecture guide
- `docs/MULTI_BACKEND_SETUP.md` - Admin setup guide
- Update README.md with multi-backend examples

---

## Holistic Multi-Backend Architecture Proposal (v2)

### Executive Summary

The original proposal in sections above is technically sound but incomplete. It addresses **backend abstraction** but doesn't address the **fundamental ownership and authorization model**. Specifically:

1. **Realms cannot be freely user-chosen** - The platform must control the DNS zones where it performs operations
2. **Two distinct use cases** need support:
   - **Platform-managed backends**: Admin provides credentials, users get subdomain access
   - **User-managed backends**: User provides their own DNS credentials (BYOD - Bring Your Own DNS)
3. **`backend_type` should be a foreign key** to a `backend_providers` table (plugins), not a text column
4. **Multiple backends per domain tree supported**: e.g., `vxxu.de` at Netcup AND `dyn.vxxu.de` delegated to PowerDNS

This section provides a comprehensive architectural redesign addressing all gaps.

**Design Principles**:
- Greenfield implementation (no legacy/migration considerations)
- No encryption at rest for now (external service dependency postponed)
- Strong typing: ENUMs and foreign keys instead of unconstrained text fields
- Realm uniqueness: Same subdomain cannot be claimed by multiple accounts

---

### Design Decisions & Rationale

#### ✅ Decision 1: `backend_type` as Foreign Key (AGREED)

**Issue**: Original proposal uses `backend_type VARCHAR(32)` with CHECK constraint. This is problematic:
- No extensibility without schema migration
- Can't track provider metadata (version, capabilities, documentation URL)
- Can't enable/disable providers dynamically

**Solution**: Create `backend_providers` table as registry of available backends:

```sql
CREATE TABLE backend_providers (
    id INTEGER PRIMARY KEY,
    provider_code VARCHAR(32) UNIQUE NOT NULL,     -- 'netcup', 'powerdns', 'cloudflare'
    display_name VARCHAR(128) NOT NULL,            -- 'Netcup CCP API'
    description TEXT,                              -- Provider description
    config_schema TEXT NOT NULL,                   -- JSON Schema for config validation
    documentation_url VARCHAR(512),                -- Link to provider docs
    icon_class VARCHAR(64),                        -- CSS class for UI icon
    
    -- Capabilities
    supports_zone_create BOOLEAN DEFAULT 0,        -- Can create new zones
    supports_zone_delete BOOLEAN DEFAULT 0,        -- Can delete zones
    supports_dnssec BOOLEAN DEFAULT 0,             -- DNSSEC support
    supports_record_types TEXT,                    -- JSON: ["A", "AAAA", "CNAME", ...]
    
    -- Status
    is_enabled BOOLEAN DEFAULT 1,                  -- Admin can disable providers
    is_builtin BOOLEAN DEFAULT 1,                  -- vs dynamically loaded plugin
    
    -- Timestamps
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

-- Seed built-in providers (using proper JSON Schema format for validation)
INSERT INTO backend_providers (provider_code, display_name, config_schema, is_builtin, is_enabled)
VALUES 
    ('netcup', 'Netcup CCP API', '{
        "type": "object",
        "properties": {
            "customer_id": {"type": "string", "minLength": 1},
            "api_key": {"type": "string", "minLength": 1},
            "api_password": {"type": "string", "minLength": 1},
            "api_url": {"type": "string", "format": "uri"},
            "timeout": {"type": "integer", "minimum": 5, "maximum": 120, "default": 30}
        },
        "required": ["customer_id", "api_key", "api_password"]
    }', 1, 1),
    ('powerdns', 'PowerDNS', '{
        "type": "object",
        "properties": {
            "api_url": {"type": "string", "format": "uri"},
            "api_key": {"type": "string", "minLength": 1},
            "timeout": {"type": "integer", "minimum": 5, "maximum": 120, "default": 30}
        },
        "required": ["api_url", "api_key"]
    }', 1, 1),
    ('cloudflare', 'Cloudflare DNS', '{
        "type": "object",
        "properties": {
            "api_token": {"type": "string", "minLength": 1},
            "zone_id": {"type": "string", "pattern": "^[a-f0-9]{32}$"}
        },
        "required": ["api_token"]
    }', 1, 0),
    ('route53', 'AWS Route 53', '{
        "type": "object",
        "properties": {
            "access_key_id": {"type": "string", "pattern": "^AKIA[0-9A-Z]{16}$"},
            "secret_access_key": {"type": "string", "minLength": 40},
            "region": {"type": "string", "default": "us-east-1"}
        },
        "required": ["access_key_id", "secret_access_key"]
    }', 1, 0);
```

Then `backend_services` references provider:
```sql
ALTER TABLE backend_services ADD COLUMN provider_id INTEGER REFERENCES backend_providers(id) NOT NULL;
```

#### ✅ Decision 2: DNS Abstraction Interface

**Current State**: `netcup_client.py` is directly used in `dns_api.py`

**Solution**: Create abstract interface as described in Phase 2 above. The implementation is correct. Key additions:

```python
# src/netcup_api_filter/backends/base.py

class DNSBackend(ABC):
    """Abstract base for DNS backends."""
    
    # Add zone enumeration capability
    @abstractmethod
    def list_zones(self) -> List[str]:
        """List all zones manageable by this backend.
        
        Used for admin UI to select available zones when
        creating managed domain roots.
        """
        pass
    
    # Add zone validation  
    @abstractmethod
    def validate_zone_access(self, zone: str) -> tuple[bool, str]:
        """Verify backend can manage this zone.
        
        Returns (can_manage, error_message).
        Used before allowing realm creation.
        """
        pass
```

#### ✅ Decision 3: Realm Ownership Model (CRITICAL)

**Problem Statement Analysis**:
> "the realm to be created... needs to be somehow under control of our platform"

This is correct. The original design allowed users to request ANY domain as a realm. This is fundamentally broken because:
1. NAF can't perform DNS operations on domains it has no credentials for
2. Users could claim authority over domains they don't own
3. No validation that the backend actually controls the claimed zone

**Solution**: Introduce **Managed Domain Roots** - admin-controlled DNS zones that users can request subdomains within.

---

### Revised Database Schema

```sql
-- ============================================================================
-- ENUM-like Status Tables (for type safety instead of VARCHAR with CHECK)
-- ============================================================================

-- Test status enumeration
CREATE TABLE test_status_enum (
    id INTEGER PRIMARY KEY,
    status_code VARCHAR(20) UNIQUE NOT NULL,
    display_name VARCHAR(64) NOT NULL
);
INSERT INTO test_status_enum (status_code, display_name) VALUES
    ('pending', 'Pending'),
    ('success', 'Success'),
    ('failed', 'Failed');

-- Visibility enumeration
CREATE TABLE visibility_enum (
    id INTEGER PRIMARY KEY,
    visibility_code VARCHAR(20) UNIQUE NOT NULL,
    display_name VARCHAR(64) NOT NULL,
    description TEXT
);
INSERT INTO visibility_enum (visibility_code, display_name, description) VALUES
    ('public', 'Public', 'Any authenticated user can request subdomains'),
    ('private', 'Private', 'Only explicitly granted users can request subdomains'),
    ('invite', 'Invite Only', 'Users need invitation code to request subdomains');

-- Owner type enumeration  
CREATE TABLE owner_type_enum (
    id INTEGER PRIMARY KEY,
    owner_code VARCHAR(20) UNIQUE NOT NULL,
    display_name VARCHAR(64) NOT NULL
);
INSERT INTO owner_type_enum (owner_code, display_name) VALUES
    ('platform', 'Platform'),
    ('user', 'User');

-- Grant type enumeration
CREATE TABLE grant_type_enum (
    id INTEGER PRIMARY KEY,
    grant_code VARCHAR(20) UNIQUE NOT NULL,
    display_name VARCHAR(64) NOT NULL
);
INSERT INTO grant_type_enum (grant_code, display_name) VALUES
    ('standard', 'Standard'),
    ('admin', 'Administrator'),
    ('invite_only', 'Invite Only');

-- ============================================================================
-- Provider Registry (plugin system foundation)
-- ============================================================================
CREATE TABLE backend_providers (
    id INTEGER PRIMARY KEY,
    provider_code VARCHAR(32) UNIQUE NOT NULL,     -- 'netcup', 'powerdns'
    display_name VARCHAR(128) NOT NULL,
    description TEXT,
    config_schema TEXT NOT NULL,                   -- JSON Schema
    supports_zone_list BOOLEAN DEFAULT 0,          -- Can enumerate zones
    supports_zone_create BOOLEAN DEFAULT 0,
    supports_dnssec BOOLEAN DEFAULT 0,
    supported_record_types TEXT,                   -- JSON array
    is_enabled BOOLEAN DEFAULT 1,
    is_builtin BOOLEAN DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- Backend Services (credential instances)
-- ============================================================================
CREATE TABLE backend_services (
    id INTEGER PRIMARY KEY,
    provider_id INTEGER NOT NULL REFERENCES backend_providers(id),
    service_name VARCHAR(64) UNIQUE NOT NULL,      -- 'netcup-production', 'powerdns-iot'
    display_name VARCHAR(128) NOT NULL,
    
    -- Ownership (FK to enum table for type safety)
    owner_type_id INTEGER NOT NULL REFERENCES owner_type_enum(id),
    owner_id INTEGER,                              -- NULL for platform, account.id for user
    
    -- Configuration (plaintext JSON for now, encryption postponed)
    config TEXT NOT NULL,
    
    -- Status
    is_active BOOLEAN DEFAULT 1,
    is_default_for_owner BOOLEAN DEFAULT 0,
    
    -- Health monitoring (FK to enum table for type safety)
    last_tested_at DATETIME,
    test_status_id INTEGER REFERENCES test_status_enum(id),
    test_message TEXT,
    
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (owner_id) REFERENCES accounts(id) ON DELETE CASCADE
);

-- Index for user-owned backends lookup
CREATE INDEX idx_backend_services_owner ON backend_services(owner_type_id, owner_id);

-- ============================================================================
-- Managed Domain Roots (admin-controlled zones)
-- ============================================================================
CREATE TABLE managed_domain_roots (
    id INTEGER PRIMARY KEY,
    backend_service_id INTEGER NOT NULL REFERENCES backend_services(id),
    
    -- Zone identification
    root_domain VARCHAR(255) NOT NULL,             -- 'vxxu.de' or 'dyn.vxxu.de'
    dns_zone VARCHAR(255) NOT NULL,                -- Actual zone in backend (may differ)
    
    -- Access control (FK to enum table for type safety)
    visibility_id INTEGER NOT NULL REFERENCES visibility_enum(id),
    
    -- Subdomain policy
    allow_apex_access BOOLEAN DEFAULT 0,           -- Can users get apex records?
    min_subdomain_depth INTEGER DEFAULT 1,         -- Minimum label depth below root
    max_subdomain_depth INTEGER DEFAULT 3,         -- Maximum label depth below root
    
    -- Record type restrictions (JSON array, NULL = all allowed)
    allowed_record_types TEXT,
    
    -- Operation restrictions (JSON array, NULL = all allowed)
    allowed_operations TEXT,
    
    -- Description for users
    display_name VARCHAR(128),
    description TEXT,
    
    -- Status
    is_active BOOLEAN DEFAULT 1,
    verified_at DATETIME,                          -- When admin verified backend access
    
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(backend_service_id, root_domain)
);

-- ============================================================================
-- User Access Grants (links users to domain roots they can use)
-- ============================================================================
CREATE TABLE domain_root_grants (
    id INTEGER PRIMARY KEY,
    domain_root_id INTEGER NOT NULL REFERENCES managed_domain_roots(id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    
    -- Grant type (FK to enum table for type safety)
    grant_type_id INTEGER NOT NULL REFERENCES grant_type_enum(id),
    
    -- Additional restrictions (tighter than root's defaults)
    allowed_record_types TEXT,                     -- JSON, NULL = inherit from root
    allowed_operations TEXT,                       -- JSON, NULL = inherit from root
    max_realms INTEGER DEFAULT 5,                  -- Max realms under this root
    
    -- Metadata
    granted_by_id INTEGER REFERENCES accounts(id),
    granted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,                           -- NULL = never
    revoked_at DATETIME,
    revoke_reason TEXT,
    
    UNIQUE(domain_root_id, account_id)
);

-- ============================================================================
-- Account Realms (MODIFIED - now links to domain roots)
-- ============================================================================
-- Add columns to existing account_realms table
ALTER TABLE account_realms ADD COLUMN domain_root_id INTEGER REFERENCES managed_domain_roots(id);
ALTER TABLE account_realms ADD COLUMN user_backend_id INTEGER REFERENCES backend_services(id);

-- Constraint: exactly one of domain_root_id or user_backend_id must be set
-- (realm is either under platform root OR uses user's own backend)
CREATE TRIGGER check_realm_backend_exclusive
    BEFORE INSERT ON account_realms
    WHEN NEW.domain_root_id IS NULL AND NEW.user_backend_id IS NULL
    BEGIN
        SELECT RAISE(ABORT, 'Realm must have either domain_root_id or user_backend_id');
    END;

CREATE TRIGGER check_realm_backend_exclusive_update
    BEFORE UPDATE ON account_realms
    WHEN NEW.domain_root_id IS NULL AND NEW.user_backend_id IS NULL
    BEGIN
        SELECT RAISE(ABORT, 'Realm must have either domain_root_id or user_backend_id');
    END;

-- ============================================================================
-- Realm Uniqueness Constraint (prevent duplicate subdomain claims)
-- ============================================================================
-- Ensure the same subdomain under a domain root can only be claimed by one account
-- This prevents user A from claiming 'myhost.dyn.vxxu.de' if user B already has it
CREATE UNIQUE INDEX idx_unique_realm_subdomain 
    ON account_realms(domain_root_id, realm_value) 
    WHERE domain_root_id IS NOT NULL;

-- For user backends, uniqueness is per-user (same user can't have duplicate realms)
CREATE UNIQUE INDEX idx_unique_user_realm 
    ON account_realms(user_backend_id, account_id, domain, realm_value) 
    WHERE user_backend_id IS NOT NULL;
```

---

### Use Case A: Platform-Managed Backends (Multi-Backend Example)

**Scenario**: Admin has multiple DNS backends:
- `vxxu.de` is hosted at Netcup (registrar DNS)
- `dyn.vxxu.de` is delegated via NS records to a self-hosted PowerDNS instance

Users can request realms under either zone, with different backends handling the DNS operations.

**Workflow**:

**Step 1: Admin creates TWO Backend Services**

```
Backend Service 1:
  Provider: netcup
  Service Name: netcup-vxxu  
  Config: {customer_id, api_key, api_password}
  Owner Type: platform

Backend Service 2:
  Provider: powerdns
  Service Name: powerdns-dyn  
  Config: {api_url: "http://powerdns:8081", api_key: "xxx"}
  Owner Type: platform
```

**Step 2: Admin creates TWO Managed Domain Roots**

```
Domain Root 1 (for direct vxxu.de records):
  Backend: netcup-vxxu
  Root Domain: vxxu.de
  DNS Zone: vxxu.de (same - managed at Netcup)
  Visibility: private (admin grants required)
  Min Subdomain Depth: 1
  Allowed Record Types: [A, AAAA, CNAME, TXT]
  Allowed Operations: [read, update]

Domain Root 2 (for delegated dyn.vxxu.de zone):
  Backend: powerdns-dyn
  Root Domain: dyn.vxxu.de
  DNS Zone: dyn.vxxu.de (delegated zone in PowerDNS)
  Visibility: public (any user can claim free subdomain)
  Min Subdomain Depth: 1
  Allowed Record Types: [A, AAAA, TXT]
  Allowed Operations: [read, update]
```

**Step 3: Different users create realms under different roots**

```
User A (granted access to vxxu.de):
  Available Roots: [vxxu.de (Private - Netcup), dyn.vxxu.de (Public - PowerDNS)]
  Selected: vxxu.de
  Requested Subdomain: host1 → host1.vxxu.de
  → Realm uses Netcup API

User B (public access):
  Available Roots: [dyn.vxxu.de (Public - PowerDNS)]
  Selected: dyn.vxxu.de
  Requested Subdomain: host2 → host2.dyn.vxxu.de
  → Realm uses PowerDNS API

User C (also public):
  Available Roots: [dyn.vxxu.de (Public - PowerDNS)]
  Selected: dyn.vxxu.de
  Requested Subdomain: host2 → ERROR: "host2.dyn.vxxu.de already claimed"
  → Uniqueness constraint prevents duplicate claims
```

**Step 4: API calls route to correct backend**

```
Token(host1.vxxu.de) → Realm → DomainRoot(vxxu.de) → BackendService(netcup-vxxu) → Netcup API
Token(host2.dyn.vxxu.de) → Realm → DomainRoot(dyn.vxxu.de) → BackendService(powerdns-dyn) → PowerDNS API
```

**Key Design Points**:
- Same domain tree can have multiple backends at different delegation points
- Each `managed_domain_root` points to exactly one `backend_service`
- Public roots allow any authenticated user to claim free subdomains
- Uniqueness index prevents multiple accounts from claiming the same subdomain
- Backend resolution is transparent to API clients (they just use their token)

**UI Changes for Realm Creation**:
```html
<!-- Instead of free-text domain input -->
<div class="form-group">
  <label>DNS Zone</label>
  <select name="domain_root_id" required>
    <option value="">Select available zone...</option>
    {% for root in available_roots %}
    <option value="{{ root.id }}">
      {{ root.root_domain }} ({{ root.backend_service.display_name }})
      {% if root.visibility.visibility_code == 'public' %} - Public{% endif %}
    </option>
    {% endfor %}
    {% if user_has_own_backends %}
    <option disabled>──────────────</option>
    <option value="user_backend">Use my own backend credentials</option>
    {% endif %}
  </select>
</div>

<div class="form-group">
  <label>Subdomain</label>
  <div class="input-group">
    <input type="text" name="subdomain" placeholder="myhost" pattern="[a-z0-9-]+">
    <span class="input-group-text">.{{ selected_root.root_domain }}</span>
  </div>
  <small>Your full hostname will be: <code id="preview">myhost.dyn.vxxu.de</code></small>
</div>
```

---

### Use Case B: User-Managed Backends (BYOD)

**Scenario**: User has their own Netcup account and wants to use NAF as a filter/proxy frontend.

**Workflow**:

1. **User navigates to "My Backends"** (new account page):
   ```
   /account/backends
   ```

2. **User adds their own Backend Service**:
   ```
   Provider: netcup
   Service Name: my-netcup
   Config: {customer_id, api_key, api_password}
   Owner Type: user
   Owner ID: <current_user_id>
   ```

3. **System validates credentials** (test connection)

4. **User can now enumerate their zones**:
   ```
   Available zones in my-netcup:
   - example.com
   - myproject.io
   ```

5. **User creates Realm against their backend**:
   ```
   Backend: my-netcup (User Backend)
   Zone: example.com
   Subdomain: ddns
   Full Realm: ddns.example.com
   ```

6. **No admin approval needed** (user owns the credentials)

7. **API calls route through user's backend**:
   ```
   Token → Realm(ddns.example.com) → UserBackend(my-netcup) → Netcup API
   ```

**New UI Pages**:
- `/account/backends` - List user's backend services
- `/account/backends/new` - Add new backend (select provider, enter credentials)
- `/account/backends/<id>` - View/edit backend, test connection
- `/account/backends/<id>/zones` - List available zones from backend

---

### Backend Resolution Logic

```python
# src/netcup_api_filter/backends/resolver.py

def get_backend_for_realm(realm: AccountRealm) -> DNSBackend:
    """Resolve the correct backend for a realm.
    
    Exactly one of domain_root_id or user_backend_id must be set
    (enforced by database trigger).
    """
    
    # Case B: User-provided backend (BYOD)
    if realm.user_backend_id:
        service = BackendService.query.get(realm.user_backend_id)
        if not service or not service.is_active:
            raise BackendError("User backend is disabled or deleted")
        if service.owner_id != realm.account_id:
            raise SecurityError("Backend ownership mismatch")
        return instantiate_backend(service)
    
    # Case A: Platform-managed via domain root
    if realm.domain_root_id:
        root = ManagedDomainRoot.query.get(realm.domain_root_id)
        if not root or not root.is_active:
            raise BackendError("Domain root is disabled")
        service = BackendService.query.get(root.backend_service_id)
        if not service or not service.is_active:
            raise BackendError("Backend service is disabled")
        return instantiate_backend(service)
    
    # Should never reach here due to database trigger constraint
    raise BackendError("No backend configured for realm (invalid state)")


def instantiate_backend(service: BackendService) -> DNSBackend:
    """Create backend instance from service configuration.
    
    Validates config against provider's JSON Schema before instantiation.
    """
    import jsonschema
    
    provider = BackendProvider.query.get(service.provider_id)
    if not provider or not provider.is_enabled:
        raise BackendError(f"Provider {service.provider_id} is not available")
    
    backend_class = BACKEND_REGISTRY.get(provider.provider_code)
    if not backend_class:
        raise BackendError(f"No implementation for provider: {provider.provider_code}")
    
    # Parse and validate config against provider schema
    try:
        config = json.loads(service.config)
        schema = json.loads(provider.config_schema)
        jsonschema.validate(instance=config, schema=schema)
    except json.JSONDecodeError as e:
        raise BackendError(f"Invalid config JSON: {e}")
    except jsonschema.ValidationError as e:
        raise BackendError(f"Config validation failed: {e.message}")
    
    return backend_class(config)
```

---

### Admin UI Additions

#### New Pages

| Route | Purpose |
|-------|---------|
| `/admin/backends` | List all platform backend services |
| `/admin/backends/new` | Add new platform backend |
| `/admin/backends/<id>` | Edit/test platform backend |
| `/admin/domain-roots` | List managed domain roots |
| `/admin/domain-roots/new` | Create new domain root |
| `/admin/domain-roots/<id>` | Edit root, manage user grants |
| `/admin/domain-roots/<id>/grants` | Manage user access to root |

#### User Account Pages

| Route | Purpose |
|-------|---------|
| `/account/backends` | List user's own backends |
| `/account/backends/new` | Add user backend |
| `/account/backends/<id>` | Edit/test user backend |
| `/account/backends/<id>/zones` | Browse zones from backend |

---

### Security Considerations

1. **Credential Storage**: Backend service configs are stored as plaintext JSON for now
   - Encryption at rest postponed (requires external key management service)
   - Database file should be protected at filesystem level
   - Future: Add Fernet encryption when external KMS is available

2. **User Backend Validation**: Before allowing user backends, require:
   - Email verification
   - Optional: Admin approval for user backend feature
   - Connection test must succeed

3. **Zone Ownership Validation**: 
   - Platform backends: Admin manually verifies zone access
   - User backends: Connection test + zone list enumeration

4. **Realm Uniqueness**: 
   - Database index prevents duplicate subdomain claims under same domain root
   - First user to claim a subdomain owns it exclusively
   - Audit log tracks all realm creation/deletion

5. **Audit Logging**: Log all backend credential changes with actor, timestamp, IP

---

### Implementation Priority

| Priority | Component | Effort | Dependencies | **Status** |
|----------|-----------|--------|--------------|------------|
| P0 | Database schema (all tables) | 1 day | None | ✅ Complete |
| P0 | Backend abstraction interface | 1 day | None | ✅ Complete |
| P0 | Netcup backend implementation | 0.5 day | P0 | ✅ Complete |
| P1 | Backend providers seeding | 0.5 day | P0 | ✅ Complete |
| P1 | Admin backend management UI | 2 days | P0 | ✅ Complete |
| P1 | Managed domain roots UI | 1.5 days | P0 | ✅ Complete |
| P2 | Realm creation with root selection | 1 day | P1 | ✅ Complete |
| P2 | Realm uniqueness enforcement | 0.5 day | P2 | ✅ Complete |
| P3 | User backend management (BYOD) | 2 days | P0 | ✅ Complete |
| P3 | PowerDNS backend implementation | 1 day | P0 | ✅ Complete |
| P4 | Cloudflare backend implementation | 1 day | P0 | 🔲 Not Started |
| P4 | Route53 backend implementation | 1 day | P0 | 🔲 Not Started |

---

### Summary of Architectural Changes

| Aspect | Implementation | **Status** |
|--------|---------------|------------|
| Realm selection | Dropdown of available domain roots (not free-text) | ✅ Complete |
| Backend configuration | Multiple `backend_services` with FK to `backend_providers` | ✅ Complete |
| DNS operations | Abstract `DNSBackend` interface with provider implementations | ✅ Complete |
| Status/type fields | ENUM tables with foreign keys (type-safe) | ✅ Complete |
| User backends | BYOD support via user-owned `backend_services` | ✅ Complete |
| Zone validation | Backend validates zone access before realm creation | ✅ Complete |
| Domain roots | Admin-controlled `managed_domain_roots` with visibility policies | ✅ Complete |
| Realm uniqueness | Database index prevents duplicate subdomain claims | ✅ Complete |
| Multi-backend trees | Same domain tree can have different backends at delegation points | ✅ Complete |

This is a greenfield implementation enabling multi-backend, multi-tenant architecture.

---

## Implementation Status Summary

### Completed Features

#### Backend Abstraction Layer
- ✅ `DNSBackend` abstract base class (`backends/base.py`)
- ✅ Netcup CCP API implementation (`backends/netcup.py`)
- ✅ PowerDNS HTTP API implementation (`backends/powerdns.py`)
- ✅ Backend registry with provider discovery (`backends/registry.py`)

#### Database Models (9 new tables)
- ✅ 4 ENUM tables: TestStatusEnum, VisibilityEnum, OwnerTypeEnum, GrantTypeEnum
- ✅ BackendProvider - Plugin registry with JSON Schema config
- ✅ BackendService - Credential instances (platform/user-owned)
- ✅ ManagedDomainRoot - Admin-controlled zones with visibility policies
- ✅ DomainRootGrant - User access grants
- ✅ Modified AccountRealm with domain_root_id and user_backend_id

#### Admin UI (10+ templates)
- ✅ `backends_list.html` - List all backend services with filters
- ✅ `backend_detail.html` - View backend with connection status
- ✅ `backend_form.html` - Create/edit with provider-specific config
- ✅ `backend_providers.html` - View available providers
- ✅ `domain_roots_list.html` - List domain roots with stats
- ✅ `domain_root_detail.html` - View root with realms and grants
- ✅ `domain_root_form.html` - Create/edit with policies
- ✅ `domain_root_grants.html` - Manage user grants
- ✅ Updated `base.html` with DNS dropdown menu

#### User Account UI (BYOD)
- ✅ `account/backends_list.html` - List user's own backends
- ✅ `account/backend_detail.html` - View backend with realms
- ✅ `account/backend_form.html` - Create/edit with provider-specific config
- ✅ `account/backend_zones.html` - Browse available zones
- ✅ Updated `account/base.html` with "My Backends" nav link
- ✅ Updated `account/request_realm.html` with domain root dropdown

#### Routes
- ✅ Admin backend CRUD: list, create, detail, edit, test, enable, disable, delete
- ✅ Admin domain root CRUD: list, create, detail, edit, enable, disable, delete
- ✅ Admin provider listing
- ✅ User backend CRUD: list, create, detail, edit, test, delete
- ✅ User backend zones browsing
- ✅ Updated realm request with domain root selection

#### Tests
- ✅ Journey test `test_09_multibackend.py` (14 test cases)
  - Admin views providers, backends, domain roots
  - Admin create forms accessibility
  - User realm request with dropdown
  - User backend management (BYOD)
  - State combinations (visibility, status)
  - Navigation tests
- ✅ UI tests `test_backends_ui.py` (14 test cases)
  - Admin backends list, providers, create
  - User backends list, create, providers info
  - Navigation tests
  - Stats display tests

#### Seeding
- ✅ Auto-seeding of enum tables and providers on database init
- ✅ Demo backend + public domain root at dyn.example.com

### Not Yet Implemented

- 🔲 Cloudflare backend implementation
- 🔲 Route53 backend implementation
- 🔲 Encryption at rest for credentials (requires external KMS)

