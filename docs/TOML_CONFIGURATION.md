# TOML Configuration Guide

**Version:** 2.0 (Array-Based Multi-Backend Architecture)

## Overview

The `app-config.toml` file enables automated platform configuration at deployment time. This document describes the **new array-based structure** that supports:

- **Multiple backends** of the same provider type (multiple Netcup accounts, PowerDNS instances)
- **User preseeding** with their own backend credentials (BYOD - Bring Your Own Domain)
- **Explicit backend-to-domain mapping** via `[[domain_roots]]` arrays
- **Environment variable substitution** (`${POWERDNS_API_KEY}`)
- **Auto-detection** (`"auto"` for PowerDNS URL)

## Configuration Hierarchy

1. **`app-config.toml`** - Initial deployment configuration (imported once, then deleted)
2. **Database settings table** - Runtime configuration (survives deployments)
3. **Admin UI** - Post-deployment management (CRUD backends, domains, users)

## File Structure

```toml
# =============================================================================
# SMTP CONFIGURATION
# =============================================================================
[smtp]
smtp_host = "mail.example.com"
smtp_port = 587
smtp_security = "starttls"  # "ssl", "starttls", or "none"
smtp_username = "noreply@example.com"
smtp_password = "password"
from_email = "noreply@example.com"
from_name = "Netcup API Filter"

# =============================================================================
# GEOIP CONFIGURATION (MaxMind)
# =============================================================================
[geoip]
account_id = "1234567"
license_key = "your-license-key"
api_url = "https://geoip.maxmind.com"
edition_ids = "GeoLite2-ASN GeoLite2-City GeoLite2-Country"

# =============================================================================
# BACKEND SERVICES - DNS Provider Credentials
# =============================================================================
# Define multiple backend services (platform and/or user-owned)

[[backends]]
service_name = "platform-netcup-primary"
provider = "netcup"
owner = "platform"  # "platform" or username
display_name = "Platform Netcup (Primary)"
config = { 
    customer_id = "221368", 
    api_key = "your-api-key", 
    api_password = "your-api-password",
    api_url = "https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON",
    timeout = 30
}

[[backends]]
service_name = "platform-powerdns"
provider = "powerdns"
owner = "platform"
display_name = "Platform PowerDNS"
# Special value "auto" triggers auto-detection
# Use "${ENV_VAR}" for environment variable substitution
config = { 
    api_url = "auto", 
    api_key = "${POWERDNS_API_KEY}", 
    server_id = "localhost"
}

# User-owned backend example (requires [[users]] section)
[[backends]]
service_name = "user-alice-netcup"
provider = "netcup"
owner = "alice"  # Must exist in [[users]] section or database
display_name = "Alice's Netcup Account"
config = { 
    customer_id = "999999", 
    api_key = "alice-key", 
    api_password = "alice-password"
}

# =============================================================================
# DOMAIN ROOTS - DNS Zones Managed by Backends
# =============================================================================
# Map domains to backends with visibility and quotas

[[domain_roots]]
backend = "platform-powerdns"  # References backends.service_name
domain = "powerdomains.vxxu.de"
dns_zone = "powerdomains.vxxu.de"
visibility = "public"  # "public", "private", "invite"
display_name = "Free PowerDNS DDNS"
description = "Public DDNS domain - users can create hosts without approval"
allow_apex_access = false
min_subdomain_depth = 1
max_subdomain_depth = 3
allowed_record_types = ["A", "AAAA", "CNAME", "TXT"]
allowed_operations = ["read", "create", "update", "delete"]
max_hosts_per_user = 5
require_email_verification = true

[[domain_roots]]
backend = "platform-netcup-primary"
domain = "internal.example.com"
visibility = "private"  # Admin-only
display_name = "Internal Zone"
description = "Admin-controlled DNS zone"

# =============================================================================
# USER PRESEEDING (Optional)
# =============================================================================
# Create users on first deployment (useful for user-owned backends)

[[users]]
username = "alice"
email = "alice@example.com"
password = "generate"  # Special value: generates random password (logged once)
# password = "SetMe123!"  # Or set explicit password
is_approved = true  # Auto-approve (skip admin workflow)
must_change_password = false
```

## Section Details

### `[[backends]]` (Required)

Defines DNS provider credentials. Each backend can be platform-owned or user-owned.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `service_name` | string | Yes | Unique identifier (e.g., `platform-powerdns`) |
| `provider` | string | Yes | Provider type: `netcup`, `powerdns`, `custom` |
| `owner` | string | Yes | `"platform"` or username (must exist) |
| `display_name` | string | No | Human-readable name |
| `config` | object | Yes | Provider-specific configuration (see below) |

#### Provider-Specific Config

**Netcup:**
```toml
config = {
    customer_id = "221368",
    api_key = "...",
    api_password = "...",
    api_url = "https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON",  # Optional
    timeout = 30  # Optional
}
```

**PowerDNS:**
```toml
config = {
    api_url = "auto",  # Auto-detect or explicit URL
    api_key = "${POWERDNS_API_KEY}",  # Environment variable substitution
    server_id = "localhost"
}
```

**Special Values:**
- `"auto"` (api_url): Auto-detects PowerDNS URL from container hostname or PUBLIC_FQDN
- `"${ENV_VAR}"`: Substitutes environment variable at import time

### `[[domain_roots]]` (Required)

Maps DNS zones to backends with access policies.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `backend` | string | Yes | Backend service name (from `[[backends]]`) |
| `domain` | string | Yes | Root domain (e.g., `powerdomains.vxxu.de`) |
| `dns_zone` | string | No | Actual zone name in backend (defaults to `domain`) |
| `visibility` | string | Yes | `"public"`, `"private"`, `"invite"` |
| `display_name` | string | No | Human-readable name |
| `description` | string | No | Purpose description |
| `allow_apex_access` | bool | No | Can users request access to apex? (default: false) |
| `min_subdomain_depth` | int | No | Minimum depth (1 = `host.domain`) (default: 1) |
| `max_subdomain_depth` | int | No | Maximum depth (3 = `a.b.c.domain`) (default: 3) |
| `allowed_record_types` | array | No | Allowed types (null = all) (e.g., `["A", "AAAA"]`) |
| `allowed_operations` | array | No | Allowed ops (null = all) (e.g., `["read", "create"]`) |
| `max_hosts_per_user` | int | No | User quota (public domains only) |
| `require_email_verification` | bool | No | Email verification required? (default: false) |

**Visibility Types:**
- `public`: Free DDNS - users create hosts without approval
- `private`: Admin-only - no user access
- `invite`: Invite-only - users request access, admin approves

### `[[users]]` (Optional)

Preseeds user accounts (useful for user-owned backends).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `username` | string | Yes | Unique username |
| `email` | string | Yes | User email |
| `password` | string | Yes | Password or `"generate"` for random |
| `is_approved` | bool | No | Auto-approve? (default: true) |
| `must_change_password` | bool | No | Force password change on first login? (default: false) |

**Special Values:**
- `password = "generate"`: Generates random password (logged once in startup logs - **SAVE IT!**)

## Environment Variable Substitution

Use `"${VARIABLE_NAME}"` syntax in TOML for runtime substitution:

```toml
[[backends]]
service_name = "platform-powerdns"
provider = "powerdns"
owner = "platform"
config = { 
    api_url = "auto", 
    api_key = "${POWERDNS_API_KEY}",  # Read from environment at import
    server_id = "localhost"
}
```

**How it works:**
1. `passenger_wsgi.py` parses TOML
2. Stores config in database with `${...}` intact
3. `platform_backends.py` replaces `${...}` with `os.environ.get(...)` at bootstrap time

**Common variables:**
- `POWERDNS_API_KEY` - PowerDNS authentication (from `.env.workspace`)
- `PUBLIC_FQDN` - Public hostname (auto-detected by `post-create.sh`)

## Auto-Detection

### PowerDNS URL (`api_url = "auto"`)

Uses first available:
1. Explicit `api_url` in config (if not "auto")
2. Internal container hostname: `http://naf-dev-powerdns:8081` (Docker network)
3. Public HTTPS URL: `https://${PUBLIC_FQDN}/backend-powerdns` (TLS proxy)
4. Fallback: `http://localhost:8081` (with warning)

**Implementation:** `platform_backends.py::get_powerdns_api_url()`

## Use Cases

### Case 1: Single PowerDNS Backend for Free DDNS

```toml
[[backends]]
service_name = "platform-powerdns"
provider = "powerdns"
owner = "platform"
config = { api_url = "auto", api_key = "${POWERDNS_API_KEY}", server_id = "localhost" }

[[domain_roots]]
backend = "platform-powerdns"
domain = "free.example.com"
visibility = "public"
max_hosts_per_user = 5
```

### Case 2: Multiple Netcup Accounts

```toml
# Primary account for public domains
[[backends]]
service_name = "netcup-public"
provider = "netcup"
owner = "platform"
config = { customer_id = "111111", api_key = "key1", api_password = "pass1" }

# Secondary account for internal services
[[backends]]
service_name = "netcup-internal"
provider = "netcup"
owner = "platform"
config = { customer_id = "222222", api_key = "key2", api_password = "pass2" }

[[domain_roots]]
backend = "netcup-public"
domain = "ddns.example.com"
visibility = "public"

[[domain_roots]]
backend = "netcup-internal"
domain = "internal.example.com"
visibility = "private"
```

### Case 3: User BYOD (Bring Your Own Domain)

```toml
# Preseed user account
[[users]]
username = "alice"
email = "alice@example.com"
password = "generate"
is_approved = true

# User's Netcup backend
[[backends]]
service_name = "alice-netcup"
provider = "netcup"
owner = "alice"  # Must match [[users]].username
config = { customer_id = "999999", api_key = "alice-key", api_password = "alice-pass" }

# User's private domain
[[domain_roots]]
backend = "alice-netcup"
domain = "alice.example.com"
visibility = "private"  # Only alice can manage
```

### Case 4: Mixed Platform + User Backends

```toml
# Platform PowerDNS for free domains
[[backends]]
service_name = "platform-powerdns"
provider = "powerdns"
owner = "platform"
config = { api_url = "auto", api_key = "${POWERDNS_API_KEY}", server_id = "localhost" }

# Platform Netcup for paid domains
[[backends]]
service_name = "platform-netcup"
provider = "netcup"
owner = "platform"
config = { customer_id = "111111", api_key = "key1", api_password = "pass1" }

# Alice's BYOD
[[users]]
username = "alice"
email = "alice@example.com"
password = "generate"

[[backends]]
service_name = "alice-netcup"
provider = "netcup"
owner = "alice"
config = { customer_id = "999999", api_key = "alice-key", api_password = "alice-pass" }

# Domains
[[domain_roots]]
backend = "platform-powerdns"
domain = "free.example.com"
visibility = "public"

[[domain_roots]]
backend = "platform-netcup"
domain = "premium.example.com"
visibility = "invite"

[[domain_roots]]
backend = "alice-netcup"
domain = "alice.example.com"
visibility = "private"
```

## Import Process

**When:**
- Deployment detects `app-config.toml` in working directory
- Only imported once per deployment

**Steps:**
1. `passenger_wsgi.py` parses TOML with `tomllib`
2. Stores configs in database as JSON:
   - `backends_config` - Array of backend definitions
   - `domain_roots_config` - Array of domain mappings
   - `users_config` - Array of user preseeds
3. Commits to database
4. Calls `platform_backends.initialize_platform_backends()`
5. Bootstrap module processes arrays:
   - Creates `Account` entries from `[[users]]`
   - Creates `BackendService` entries from `[[backends]]`
   - Creates `ManagedDomainRoot` entries from `[[domain_roots]]`
6. Deletes `app-config.toml`

**Safety:**
- Idempotent - safe to re-import
- Checks for existing entries (username, service_name, domain)
- Logs all created entries
- Generated passwords logged once (SAVE THEM!)

## Post-Deployment Management

After import, manage via **Admin UI** (not TOML):

- **Backends:** CRUD operations for `BackendService` (not yet implemented)
- **Domain Roots:** CRUD operations for `ManagedDomainRoot` (not yet implemented)
- **Users:** Standard account management
- **Realm Approvals:** Approve/reject user access requests (not yet implemented)

**Coming soon:**
- Admin UI for backend management
- Admin UI for domain root management
- Realm approval workflow UI
- User portal for BYOD

## Validation Rules

### Service Name Uniqueness
Each `[[backends]].service_name` must be unique across all backends.

### Owner Validation
- `owner = "platform"` - Always valid
- `owner = "username"` - User must exist (either in `[[users]]` or database)

### Backend Reference
Each `[[domain_roots]].backend` must reference an existing `[[backends]].service_name`.

### Visibility Quotas
`max_hosts_per_user` only applies to `visibility = "public"` domains.

## Logging

Bootstrap logs during initialization:

```
[INFO] Initializing platform backends...
[INFO] Processing NEW array-based TOML structure
[INFO]   [1] alice (alice@example.com)
[INFO]       - password: <generated>
[INFO] Generated password for alice: Rnd0m_P@ssw0rd_H3r3 (SAVE THIS - shown once)
[INFO] Created preseeded user: alice (alice@example.com)
[INFO]   [1] platform-powerdns
[INFO]       - provider: powerdns
[INFO]       - owner: platform
[INFO] Auto-detected PowerDNS URL: http://naf-dev-powerdns:8081
[INFO] Created backend: platform-powerdns (powerdns, owner=platform)
[INFO]   [1] powerdomains.vxxu.de (backend: platform-powerdns)
[INFO]       - visibility: public
[INFO]       - max_hosts_per_user: 5
[INFO] Created domain root: powerdomains.vxxu.de (backend=platform-powerdns, visibility=public)
[INFO] ✓ Platform backends initialized (NEW array-based structure)
```

## Legacy Structure (DEPRECATED)

The old single-instance structure is still supported but **deprecated**:

```toml
# DEPRECATED - Use [[backends]] arrays instead
[netcup]
customer_id = "221368"
api_key = "..."
api_password = "..."

# DEPRECATED - Use [[backends]] + [[domain_roots]] instead
[platform_backends]
powerdns_enabled = true
netcup_platform_backend = false

# DEPRECATED - Use [[domain_roots]] with visibility="public"
[free_domains]
enabled = true
domains = ["free.example.com"]
max_hosts_per_user = 5
```

**Migration path:**
1. Convert `[netcup]` → `[[backends]]` with `service_name = "platform-netcup-primary"`
2. Convert `[platform_backends]` → `[[backends]]` for PowerDNS
3. Convert `[free_domains]` → `[[domain_roots]]` with `visibility = "public"`

## Troubleshooting

### Backend Not Found
```
[ERROR] Backend platform-powerdns not found for domain powerdomains.vxxu.de, skipping
```
**Solution:** Ensure `[[domain_roots]].backend` matches `[[backends]].service_name`.

### User Not Found
```
[ERROR] User alice not found for backend alice-netcup, skipping
```
**Solution:** Define user in `[[users]]` section before referencing in `[[backends]].owner`.

### Environment Variable Not Set
```
[WARN] Environment variable POWERDNS_API_KEY not set for platform-powerdns.api_key
```
**Solution:** Set variable in `.env.workspace` or use explicit value.

### Service Already Exists
```
[INFO] Backend platform-powerdns already exists
```
**Not an error** - Bootstrap is idempotent. Existing entries are skipped.

## See Also

- [CONFIG_DRIVEN_ARCHITECTURE.md](CONFIG_DRIVEN_ARCHITECTURE.md) - Configuration philosophy
- [FQDN_DETECTION.md](FQDN_DETECTION.md) - PUBLIC_FQDN auto-detection
- [ENV_WORKSPACE.md](ENV_WORKSPACE.md) - Environment variables
- [DEPLOYMENT_WORKFLOW.md](DEPLOYMENT_WORKFLOW.md) - Deployment process
- [ADMIN_GUIDE.md](ADMIN_GUIDE.md) - Admin UI (when implemented)
