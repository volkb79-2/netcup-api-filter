

## Repository State Analysis & Multi-Backend Proposal

### Current State Assessment

#### ✅ Strong Foundations
1. **Account → Realms → Tokens Architecture**: Well-designed 3-tier permission system
2. **Config-Driven Design**: .env.defaults + environment + database Settings model
3. **PowerDNS Infrastructure**: Init container pattern, Docker integration, API ready
4. **Comprehensive Testing**: 90+ tests (UI, E2E, journey contracts)
5. **Security**: CSRF, 2FA, bcrypt, input validation, XSS protection

#### ⚠️ Areas Needing Improvement

**1. Backend Abstraction (MISSING - CRITICAL)**
   - ❌ No `backends/` module exists
   - ❌ Hardcoded Netcup API calls throughout codebase
   - ❌ No interface for pluggable DNS providers
   - ❌ Realm → Backend mapping not implemented

**2. Database Schema Gaps**
   - ❌ No `backend_services` table for service configuration
   - ❌ No `backend_type` column in `account_realms` for routing
   - ❌ No per-realm credential override support

**3. Admin UI Gaps**
   - ❌ No backend selection in realm creation
   - ❌ No backend service management page
   - ❌ No per-realm credential configuration

**4. Code Duplication**
   - ⚠️ Netcup client instantiation repeated in multiple files
   - ⚠️ DNS operation logic not abstracted

---

## Complete Multi-Backend Implementation Proposal

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

