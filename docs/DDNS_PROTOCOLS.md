# DDNS Protocol Support

This document describes the DynDNS2 and No-IP compatible DDNS endpoints provided by netcup-api-filter.

## Table of Contents

1. [Overview](#overview)
2. [Protocol Details](#protocol-details)
3. [Security Model](#security-model)
4. [Client Configuration Examples](#client-configuration-examples)
5. [Troubleshooting](#troubleshooting)

---

## Overview

netcup-api-filter provides DDNS (Dynamic DNS) protocol endpoints compatible with major DDNS client tools including:
- **ddclient** - Popular Linux/Unix DDNS client
- **inadyn** - Lightweight DDNS client
- **Routers** - Many home routers support DynDNS2 or No-IP protocols

These endpoints allow automated DNS record updates for dynamic IP addresses (home connections, VPNs, mobile devices) while maintaining strict security through bearer token authentication.

### Supported Protocols

| Protocol | Endpoint | Compatible With |
|----------|----------|-----------------|
| **DynDNS2** | `/api/ddns/dyndns2/update` | ddclient, inadyn, most routers |
| **No-IP** | `/api/ddns/noip/update` | ddclient, inadyn, No-IP clients |

### Key Features

- ✅ **Standard Protocol Compliance** - Works with existing DDNS clients
- ✅ **Bearer Token Security** - No username/password in URLs
- ✅ **Realm-Based Authorization** - Fine-grained domain access control
- ✅ **Auto IP Detection** - Automatic client IP detection
- ✅ **IPv6 Support** - Automatic AAAA record handling
- ✅ **Activity Logging** - Full audit trail of all updates
- ✅ **IP Whitelisting** - Optional source IP restrictions

---

## Protocol Details

### DynDNS2 Protocol

#### Endpoint
```
GET /api/ddns/dyndns2/update
POST /api/ddns/dyndns2/update
```

#### Request Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `hostname` | Yes | FQDN to update (e.g., `device.iot.example.com`) |
| `myip` | No | IP address to set. If empty, `auto`, `public`, or `detect`, uses client IP |
| `username` | No | Ignored (legacy compatibility) |
| `password` | No | Ignored (legacy compatibility) |

#### Authentication
Bearer token in `Authorization` header (REQUIRED):
```
Authorization: Bearer naf_<user_alias>_<random64>
```

#### Response Codes

| Code | Status | Meaning |
|------|--------|---------|
| `good <ip>` | 200 OK | Update successful, IP changed |
| `nochg <ip>` | 200 OK | No change needed, IP already set |
| `badauth` | 401 Unauthorized | Authentication failed (missing/invalid token) |
| `!yours` | 403 Forbidden | Permission denied (domain not in token scope) |
| `notfqdn` | 400 Bad Request | Invalid hostname format |
| `dnserr` | 502 Bad Gateway | DNS backend error |
| `911` | 500 Internal Server Error | Server error |

#### Example Request (GET)
```bash
curl "https://naf.example.com/api/ddns/dyndns2/update?hostname=device.example.com&myip=auto" \
  -H "Authorization: Bearer naf_Ab3xYz9KmNpQrStU_a1B2c3D4e5F6..."
```

#### Example Response
```
good 203.0.113.42
```

---

### No-IP Protocol

#### Endpoint
```
GET /api/ddns/noip/update
POST /api/ddns/noip/update
```

#### Request Parameters

Same as DynDNS2 (see above).

#### Authentication

Same bearer token authentication as DynDNS2.

#### Response Codes

| Code | Status | Meaning |
|------|--------|---------|
| `good <ip>` | 200 OK | Update successful, IP changed |
| `nochg <ip>` | 200 OK | No change needed, IP already set |
| `nohost` | 401 Unauthorized | Authentication failed OR invalid hostname |
| `abuse` | 403 Forbidden | Permission denied (domain not in token scope) |
| `dnserr` | 502 Bad Gateway | DNS backend error |
| `911` | 500 Internal Server Error | Server error |

**Note:** No-IP protocol uses `nohost` for both authentication and hostname errors (protocol limitation).

#### Example Request (POST)
```bash
curl -X POST "https://naf.example.com/api/ddns/noip/update" \
  -H "Authorization: Bearer naf_Ab3xYz9KmNpQrStU_a1B2c3D4e5F6..." \
  -d "hostname=vpn.example.com" \
  -d "myip=public"
```

#### Example Response
```
good 198.51.100.5
```

---

### Protocol Differences

| Feature | DynDNS2 | No-IP |
|---------|---------|-------|
| Auth error response | `badauth` | `nohost` |
| Permission denied | `!yours` | `abuse` |
| Invalid hostname | `notfqdn` | `nohost` |
| Otherwise | Identical | Identical |

**Recommendation:** Use **DynDNS2** for better error distinction. Use **No-IP** only if your client requires it.

---

## Security Model

### Bearer Token Authentication

**CRITICAL:** These endpoints require bearer token authentication. Username/password parameters are **ignored** for security.

1. **Create API Token** via admin UI:
   - Log into admin portal
   - Create account realm (domain scope)
   - Generate API token with `update` operation and `A`/`AAAA` record types

2. **Use Token in Authorization Header**:
   ```
   Authorization: Bearer naf_<your_token>
   ```

3. **Never** put tokens in URLs (query parameters) - always use headers.

### Realm-Based Authorization

Tokens are scoped to specific domains/subdomains via realms:

| Realm Type | Scope | Example Token Access |
|------------|-------|---------------------|
| **host** | Exact hostname | Can update `vpn.example.com` only |
| **subdomain** | Wildcard (apex + children) | Can update `*.iot.example.com` and `iot.example.com` |
| **subdomain_only** | Children only (not apex) | Can update `*.devices.example.com` but NOT `devices.example.com` |

**Example:**
- Token realm: `subdomain` for `iot.example.com`
- **Allowed:** `device1.iot.example.com`, `sensor.iot.example.com`, `iot.example.com`
- **Denied:** `device.other.example.com`, `example.com`

### IP Whitelisting

Optionally restrict tokens to specific source IPs:
- Configure allowed IPs/CIDRs in token settings
- Empty list = allow all IPs
- Example: `192.168.1.0/24,203.0.113.5`

**Note:** The system respects `X-Forwarded-For` headers for reverse proxy deployments.

### Auto IP Detection

The `myip` parameter supports auto-detection:

| Value | Behavior |
|-------|----------|
| `auto` | Detect client IP |
| `public` | Detect client IP |
| `detect` | Detect client IP |
| `<empty>` | Detect client IP |
| `<valid IP>` | Use explicit IP |

**Keywords are configurable** via `DDNS_AUTO_IP_KEYWORDS` environment variable.

**X-Forwarded-For Handling:**
- If present: Uses first IP in chain (original client)
- If absent: Uses `request.remote_addr`

**IPv6 Support:**
- IPv6 addresses automatically create/update AAAA records
- IPv4 addresses create/update A records
- Detection is automatic based on IP format

---

## Client Configuration Examples

### ddclient (DynDNS2)

**File:** `/etc/ddclient.conf`

```conf
# netcup-api-filter with DynDNS2 protocol
protocol=dyndns2
use=web, web=https://naf.example.com/api/myip
server=naf.example.com
login=unused
password='naf_Ab3xYz9KmNpQrStU_a1B2c3D4e5F6...'
device.iot.example.com
```

**Notes:**
- `login` is ignored but required by ddclient config syntax
- `password` field contains your full bearer token
- Token is sent as HTTP Basic Auth password (ddclient limitation)
- Server endpoint: `https://naf.example.com/dyndns2/update` (ddclient adds path)

**Alternative (header-based auth):**

For true bearer token support, use ddclient's `web` protocol with custom update URL:

```conf
protocol=dyndns2
use=web, web=https://naf.example.com/api/myip
server=naf.example.com
login=unused
password='naf_Ab3xYz9KmNpQrStU_a1B2c3D4e5F6...'
web-header='Authorization: Bearer naf_Ab3xYz9KmNpQrStU_a1B2c3D4e5F6...'
device.iot.example.com
```

### inadyn (DynDNS2)

**File:** `/etc/inadyn.conf`

```conf
custom naf-dyndns2 {
    hostname = device.iot.example.com
    username = unused
    password = naf_Ab3xYz9KmNpQrStU_a1B2c3D4e5F6...
    ddns-server = naf.example.com
    ddns-path = "/api/ddns/dyndns2/update?hostname=%h&myip=%i"
    ssl = true
}
```

**Notes:**
- `username` is ignored
- `password` contains bearer token
- Token sent as HTTP Basic Auth (inadyn limitation)
- Update path includes full query string

### curl (Manual Testing)

#### DynDNS2 - Auto IP Detection
```bash
curl -i "https://naf.example.com/api/ddns/dyndns2/update?hostname=device.example.com&myip=auto" \
  -H "Authorization: Bearer naf_Ab3xYz9KmNpQrStU_a1B2c3D4e5F6..."
```

#### DynDNS2 - Explicit IP
```bash
curl -i "https://naf.example.com/api/ddns/dyndns2/update?hostname=device.example.com&myip=203.0.113.42" \
  -H "Authorization: Bearer naf_Ab3xYz9KmNpQrStU_a1B2c3D4e5F6..."
```

#### No-IP - POST with Form Data
```bash
curl -i -X POST "https://naf.example.com/api/ddns/noip/update" \
  -H "Authorization: Bearer naf_Ab3xYz9KmNpQrStU_a1B2c3D4e5F6..." \
  -d "hostname=vpn.example.com" \
  -d "myip=public"
```

#### IPv6 Update
```bash
curl -i "https://naf.example.com/api/ddns/dyndns2/update?hostname=device.example.com&myip=2001:db8::1" \
  -H "Authorization: Bearer naf_Ab3xYz9KmNpQrStU_a1B2c3D4e5F6..."
```

### Router Configuration

Many routers support DynDNS2 or No-IP protocols. Example configuration:

**Router Settings:**
- **Service:** Custom or DynDNS
- **Server:** `naf.example.com`
- **Protocol:** HTTPS (port 443)
- **Hostname:** `router.home.example.com`
- **Username:** `unused` (leave empty or any value)
- **Password:** `naf_Ab3xYz9KmNpQrStU_a1B2c3D4e5F6...` (your bearer token)
- **Update URL:** `/api/ddns/dyndns2/update` (or `/api/ddns/noip/update`)

**Note:** Some routers may not support bearer token headers. Check router documentation for custom DDNS provider support.

### Python Script

```python
import requests

def update_ddns(hostname, token, server="https://naf.example.com"):
    """Update DDNS record via DynDNS2 protocol."""
    url = f"{server}/api/ddns/dyndns2/update"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    params = {
        "hostname": hostname,
        "myip": "auto"
    }
    
    response = requests.get(url, headers=headers, params=params)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
    
    return response.status_code == 200

# Usage
token = "naf_Ab3xYz9KmNpQrStU_a1B2c3D4e5F6..."
update_ddns("device.iot.example.com", token)
```

---

## Troubleshooting

### Common Issues

#### 1. `badauth` / `nohost` (401 Unauthorized)

**Symptoms:**
```
badauth
```

**Causes:**
- Missing `Authorization` header
- Invalid bearer token format
- Token doesn't exist in database
- Token is revoked or expired
- Account is disabled

**Solutions:**
- Verify token format: `naf_<16chars>_<64chars>`
- Check token is active in admin UI
- Regenerate token if compromised
- Verify account is active

**Testing:**
```bash
# Test authentication
curl -i "https://naf.example.com/api/ddns/dyndns2/update?hostname=test.example.com&myip=auto" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

#### 2. `!yours` / `abuse` (403 Forbidden)

**Symptoms:**
```
!yours
```

**Causes:**
- Hostname not in token's realm scope
- Token realm not approved
- Operation not allowed (token lacks `update` permission)
- Record type not allowed (token doesn't permit `A`/`AAAA`)
- IP whitelist violation

**Solutions:**
- Verify realm scope matches hostname domain
- Check realm status is "approved" in admin UI
- Ensure token has `update` operation enabled
- Ensure token allows `A` and/or `AAAA` record types
- Verify source IP is in token's whitelist (if configured)

**Testing:**
```bash
# Check realm scope
# Token realm: iot.example.com (subdomain)
# ✅ Allowed: device.iot.example.com
# ❌ Denied: device.other.example.com

# Verify in admin UI:
# 1. Navigate to token details
# 2. Check "Realm" section - verify domain matches
# 3. Check "Operations" - must include "update"
# 4. Check "Record Types" - must include "A" or "AAAA"
```

#### 3. `notfqdn` / `nohost` (400 Bad Request)

**Symptoms:**
```
notfqdn
```

**Causes:**
- Invalid hostname format
- Hostname missing from request
- No dots in hostname
- Consecutive dots in hostname

**Solutions:**
- Use valid FQDN format: `device.subdomain.example.com`
- Include at least one dot: `device.example.com`
- No trailing dot: use `example.com` not `example.com.`

**Valid Examples:**
- ✅ `device.example.com`
- ✅ `vpn.iot.example.com`
- ✅ `example.com` (apex)

**Invalid Examples:**
- ❌ `device` (no dots)
- ❌ `device..example.com` (double dots)
- ❌ `` (empty)

#### 4. `dnserr` (502 Bad Gateway)

**Symptoms:**
```
dnserr
```

**Causes:**
- Netcup API not configured
- Netcup API credentials invalid
- Netcup API timeout
- Netcup API returned error
- Invalid IP address format
- Network connectivity issue

**Solutions:**
- Verify Netcup API configuration in admin UI
- Test Netcup API credentials
- Check server logs for detailed error
- Ensure IP address is valid format
- Verify network connectivity to Netcup API

**Testing:**
```bash
# Test with valid IP explicitly
curl -i "https://naf.example.com/api/ddns/dyndns2/update?hostname=device.example.com&myip=192.0.2.1" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"

# Check server logs
tail -f /var/log/netcup-api-filter/app.log
```

#### 5. `911` (500 Internal Server Error)

**Symptoms:**
```
911
```

**Causes:**
- Server configuration error
- DDNS protocols disabled
- Unexpected server error
- Database connection error

**Solutions:**
- Check DDNS is enabled: `DDNS_PROTOCOLS_ENABLED=true`
- Review server logs for stack traces
- Verify database connectivity
- Contact administrator

**Testing:**
```bash
# Check if DDNS is enabled
curl -i "https://naf.example.com/api/ddns/dyndns2/update?hostname=test.example.com&myip=auto" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"

# Response should be 200/401/403, NOT 500
```

### Debugging Tips

#### 1. Test Authentication First
```bash
# Test token against read-only endpoint
curl -i "https://naf.example.com/api/dns/DOMAIN/records" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"

# 200 = token valid
# 401 = token invalid
# 403 = token valid but wrong domain
```

#### 2. Test with curl Before Configuring Clients
```bash
# Start simple - auto IP detection
curl -i "https://naf.example.com/api/ddns/dyndns2/update?hostname=device.example.com&myip=auto" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"

# Then test explicit IP
curl -i "https://naf.example.com/api/ddns/dyndns2/update?hostname=device.example.com&myip=203.0.113.1" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"

# Test POST method
curl -i -X POST "https://naf.example.com/api/ddns/dyndns2/update" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -d "hostname=device.example.com" \
  -d "myip=auto"
```

#### 3. Check Activity Logs
The admin UI provides detailed activity logs:
1. Log into admin portal
2. Navigate to "Activity Logs"
3. Filter by your token or domain
4. Review `status`, `error_code`, and `status_reason` fields

**Look for:**
- `action=ddns_update`
- `status=denied` (permission errors)
- `status=error` (backend errors)
- `error_code` field for specific issue

#### 4. Verify DNS Updates
After successful update, verify DNS:
```bash
# Query DNS directly
dig device.example.com A +short
dig device.example.com AAAA +short

# Or use host command
host device.example.com

# Check against Netcup nameservers
dig @ns1.netcup.net device.example.com A +short
```

#### 5. Test IP Detection
```bash
# Check your public IP
curl https://naf.example.com/api/myip

# Test auto-detection with X-Forwarded-For
curl -i "https://naf.example.com/api/ddns/dyndns2/update?hostname=device.example.com&myip=auto" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "X-Forwarded-For: 203.0.113.1"
```

### Client-Specific Issues

#### ddclient
- **Issue:** Token not sent correctly
- **Solution:** Use `password` field, not `login`
- **Verify:** Check `/var/log/ddclient.log` for request details

#### inadyn
- **Issue:** SSL certificate verification fails
- **Solution:** Add `ssl = true` and verify certificate is valid
- **Verify:** Run inadyn in foreground: `inadyn -n -f /etc/inadyn.conf`

#### Routers
- **Issue:** Router doesn't support bearer tokens
- **Solution:** Some routers only support HTTP Basic Auth
  - May need to use legacy endpoint or proxy
  - Check router documentation for "custom DDNS provider"

### Getting Help

If issues persist:
1. **Check server logs** - Look for detailed error messages
2. **Review activity logs** - Admin UI → Activity Logs
3. **Test with curl** - Isolate issue from client configuration
4. **Verify token permissions** - Admin UI → Tokens → Details
5. **Contact support** - Include error codes and log excerpts (no tokens!)

---

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DDNS_PROTOCOLS_ENABLED` | `true` | Enable/disable DDNS endpoints |
| `DDNS_AUTO_IP_KEYWORDS` | `auto,public,detect` | Keywords for auto IP detection |

### Token Requirements

For DDNS to work, tokens must have:
- ✅ **Status:** Approved
- ✅ **Operations:** `update` (or `*`)
- ✅ **Record Types:** `A` and/or `AAAA`
- ✅ **Realm:** Covering target hostname domain

**Example Token Configuration:**
- **Realm Type:** `subdomain`
- **Realm Domain:** `example.com`
- **Realm Value:** `iot`
- **Operations:** `read`, `update`
- **Record Types:** `A`, `AAAA`
- **Result:** Can update `*.iot.example.com` A/AAAA records

---

## Security Best Practices

1. **Never log full tokens** - Only log token prefixes (first 8 chars of random part)
2. **Use HTTPS only** - Never send tokens over unencrypted HTTP
3. **Rotate tokens regularly** - Generate new tokens periodically
4. **Use IP whitelisting** - Restrict tokens to known source IPs when possible
5. **Monitor activity logs** - Review for suspicious access patterns
6. **Use minimal permissions** - Grant only required operations and record types
7. **Separate tokens per use case** - Don't reuse same token for different purposes

---

## Performance Considerations

- **Rate Limiting:** DDNS endpoints respect global rate limits (if configured)
- **Caching:** DNS updates are NOT cached - each request hits Netcup API
- **Update Frequency:** Recommended minimum 5 minutes between updates
- **No-Change Detection:** If IP unchanged, only reads DNS (no write API call)

---

## Related Documentation

- [API Reference](API_REFERENCE.md) - Complete API documentation
- [Client Templates](../CLIENT_TEMPLATES.md) - Pre-configured token templates
- [Security Model](../README.md#security) - Overall security architecture
- [Token Management](../README.md#tokens) - Creating and managing API tokens

---

## Version History

- **v1.0** (2026-01-04) - Initial implementation
  - DynDNS2 protocol support
  - No-IP protocol support
  - Auto IP detection
  - Bearer token authentication
  - IPv6 support
  - Activity logging
