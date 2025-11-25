# Multi-Client Demonstration System

## Overview

The deployment now includes **5 different demo clients** that showcase the full range of API filtering capabilities. Each client demonstrates different permission configurations for real-world use cases.

## Demo Clients

### 1. Read-only Host (`readonly-1`)
- **Realm**: `host` → `example.com`
- **Record Types**: A, AAAA
- **Operations**: read
- **Use Case**: Basic monitoring and status checking of a single host
- **Screenshots**: Dashboard, activity log, domain detail (no record creation)

### 2. Full Control Host (`fullcontrol-2`)
- **Realm**: `host` → `api.example.com`
- **Record Types**: A, AAAA, CNAME
- **Operations**: read, update, create, delete
- **Use Case**: Complete DNS management for a specific host
- **Screenshots**: Dashboard, activity log, domain detail, record creation form

### 3. Subdomain Read-only (`subdomain-readonly-3`)
- **Realm**: `subdomain` → `*.example.com`
- **Record Types**: A, AAAA, CNAME
- **Operations**: read
- **Use Case**: Monitor all subdomains under a domain (infrastructure monitoring)
- **Screenshots**: Dashboard, activity log, domain detail (no record creation)

### 4. Subdomain with Update (`subdomain-write-4`)
- **Realm**: `subdomain` → `*.dyn.example.com`
- **Record Types**: A, AAAA
- **Operations**: read, update, create
- **Use Case**: Dynamic DNS service (clients can update IPs for their subdomains)
- **Screenshots**: Dashboard, activity log, domain detail, record creation form

### 5. Multi-record Full Control (`fullcontrol-5`)
- **Realm**: `host` → `services.example.com`
- **Record Types**: A, AAAA, CNAME, NS
- **Operations**: read, update, create, delete
- **Use Case**: DNS provider API integration with full record type support
- **Screenshots**: Dashboard, activity log, domain detail, record creation form

## Screenshot Naming Convention

Client portal screenshots use descriptive suffixes:
- `readonly-1` - Read-only host monitoring
- `fullcontrol-2` - Full DNS control for single host
- `subdomain-readonly-3` - Wildcard subdomain monitoring
- `subdomain-write-4` - Dynamic DNS with write permissions
- `fullcontrol-5` - Multi-record type DNS provider

### Screenshot Files

Each client gets 3-4 screenshots:
- `08-client-dashboard-{suffix}.png` - Main dashboard view
- `09-client-activity-{suffix}.png` - Activity/audit log
- `10-client-domain-{suffix}.png` - Domain detail page
- `11-client-record-create-{suffix}.png` - Record creation form (write clients only)

## Dynamic Credential Generation

All client credentials are **generated dynamically** during the build process:
- Client IDs: `test_<random_8chars>` (e.g., `test_VRPR4fHZ`)
- Secret keys: 32-byte random tokens (URL-safe base64)
- No hardcoded credentials in version control

### Credential Storage

Build system stores all credentials:
```json
{
  "demo_clients": [
    {
      "client_id": "test_VRPR4fHZ",
      "secret_key": "...",
      "description": "Read-only host",
      "token": "test_VRPR4fHZ:..."
    }
  ]
}
```

Deployment scripts extract and use these tokens for:
- Initial credential synchronization (`.env.local` / `.env.webhosting`)
- Screenshot capture (all client logins)
- Testing and validation

## Build Process Integration

### 1. Database Seeding
`bootstrap/seeding.py` creates 5 clients with varied permissions:
```python
def seed_demo_clients() -> list[Tuple[str, str, str]]:
    # Returns list of (client_id, secret_key, description) tuples
    clients = []
    clients.append((client_id_1, secret_1, "Read-only host"))
    clients.append((client_id_2, secret_2, "Full control host"))
    # ... etc
```

### 2. Build Metadata
`build_deployment.py` stores all credentials in `build_info.json`:
```python
"demo_clients": [
    {
        "client_id": cid,
        "secret_key": secret,
        "description": desc,
        "token": f"{cid}:{secret}"
    }
    for cid, secret, desc in all_demo_clients
]
```

### 3. Screenshot Capture
`capture_ui_screenshots.py` reads `build_info.json` and logs in as each client:
```python
async def capture_client_pages(browser):
    # Read demo clients from build_info.json
    demo_clients = build_info.get("demo_clients", [])
    
    # Capture screenshots for each client
    for client_data in demo_clients:
        client_token = client_data["token"]
        await capture_client_pages_for_token(browser, client_token, suffix)
```

## Real-World Use Cases Demonstrated

### Infrastructure Monitoring
**Client**: `subdomain-readonly-3` (Subdomain read-only)  
Monitor all services under `*.example.com` without write access. Perfect for monitoring tools like Prometheus, Grafana.

### API Server Management
**Client**: `fullcontrol-2` (Full control host)  
Complete DNS control for `api.example.com` including CNAMEs for load balancers, A records for direct access.

### Dynamic DNS Service
**Client**: `subdomain-write-4` (Subdomain with update)  
Clients can update their own subdomains under `*.dyn.example.com` (home servers, IoT devices).

### DNS Provider Integration
**Client**: `fullcontrol-5` (Multi-record full control)  
Full API access for DNS automation, supports all common record types (A, AAAA, CNAME, NS).

### Status Page Monitoring
**Client**: `readonly-1` (Read-only host)  
Basic read-only access for status pages to check DNS resolution without modification rights.

## Testing Multi-Client System

### Build and Deploy
```bash
# Local deployment (creates all 5 clients + screenshots)
./build-and-deploy-local.sh

# Verify clients created
sqlite3 deploy-local/netcup_filter.db "SELECT client_id, description FROM clients"

# Check build metadata
jq '.demo_clients' deploy/build_info.json
```

### Manual Client Testing
Each client token is in `deploy/build_info.json`:
```bash
# Test read-only client
TOKEN=$(jq -r '.demo_clients[0].token' deploy/build_info.json)
curl -H "Authorization: Bearer $TOKEN" http://localhost:5100/api/v1/domains

# Test full-control client
TOKEN=$(jq -r '.demo_clients[1].token' deploy/build_info.json)
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"hostname":"test.api.example.com","type":"A","destination":"1.2.3.4"}' \
  http://localhost:5100/api/v1/records
```

### Screenshot Review
All 28 screenshots demonstrate:
- 10 admin pages (user management, config, system info)
- 18 client pages (5 clients × 3-4 pages each)

```bash
ls -1 deploy-local/screenshots/ | wc -l  # Should show 28
ls -1 deploy-local/screenshots/11-client-record-create-*.png  # Only write clients
```

## Configuration Reference

### Client Permission Matrix

| Client Type | Realm Type | Operations | Record Types | Write Access |
|-------------|------------|------------|--------------|--------------|
| readonly-1 | host | read | A, AAAA | No |
| fullcontrol-2 | host | all | A, AAAA, CNAME | Yes |
| subdomain-readonly-3 | subdomain | read | A, AAAA, CNAME | No |
| subdomain-write-4 | subdomain | read, update, create | A, AAAA | Yes |
| fullcontrol-5 | host | all | A, AAAA, CNAME, NS | Yes |

### Suffix Generation Logic

Screenshot suffix determined by client description:
- Contains "subdomain" + "read-only" → `subdomain-readonly`
- Contains "subdomain" + "update/write/create" → `subdomain-write`
- Contains "full control" or "multi-record" → `fullcontrol`
- Contains "read-only" or "monitor" → `readonly`
- Default → `client-{idx}`

## Deployment Scripts Integration

### build-and-deploy-local.sh
```bash
# Extract all demo clients for screenshot capture
DEMO_CLIENTS_FILE="${DEPLOY_LOCAL_DIR}/demo_clients.json"
jq '.demo_clients' "$BUILD_INFO" > "$DEMO_CLIENTS_FILE"

# First client credentials sync to .env.local
GENERATED_CLIENT_ID=$(jq -r '.generated_client_id' "$BUILD_INFO")
GENERATED_SECRET_KEY=$(jq -r '.generated_secret_key' "$BUILD_INFO")
```

### capture_ui_screenshots.py
```python
# Read from build metadata (no database queries needed)
build_info_path = Path(repo_root) / "deploy" / "build_info.json"
with open(build_info_path, 'r') as f:
    build_info = json.load(f)
demo_clients = build_info.get("demo_clients", [])

# Each client has token readily available
for client_data in demo_clients:
    client_token = client_data["token"]  # Format: "client_id:secret_key"
```

## Benefits

1. **Complete Coverage**: Demonstrates all permission combinations
2. **Real-World Scenarios**: Each client maps to actual use case
3. **Dynamic Credentials**: No secrets in version control
4. **Automated Testing**: Screenshots verify all client types work
5. **Documentation**: Visual proof of capabilities for each permission level

## Future Enhancements

Potential additions:
- Multi-domain client (access to multiple domains)
- Time-based restrictions (temporary access tokens)
- Rate-limited clients (different quotas per client type)
- Geographic restrictions (IP-based access control)
- Client groups (shared permissions across multiple clients)
