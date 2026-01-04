# API Reference

Complete API reference for netcup-api-filter.

## Table of Contents

1. [Authentication](#authentication)
2. [DNS Record Operations](#dns-record-operations)
3. [DDNS Protocol Endpoints](#ddns-protocol-endpoints)
4. [Utility Endpoints](#utility-endpoints)

---

## Authentication

All API endpoints require bearer token authentication.

### Token Format
```
Authorization: Bearer naf_<user_alias>_<random64>
```

**Example:**
```
Authorization: Bearer naf_Ab3xYz9KmNpQrStU_a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8s9T0u1V2w3X4y5Z6
```

### Error Responses

All authentication failures return 401:
```json
{
  "error": "unauthorized",
  "message": "Invalid or expired token"
}
```

---

## DNS Record Operations

RESTful API for DNS record management.

### List Records

**Endpoint:** `GET /api/dns/<domain>/records`

**Description:** Retrieve all DNS records for a domain (filtered by token permissions).

**Example Request:**
```bash
curl "https://naf.example.com/api/dns/example.com/records" \
  -H "Authorization: Bearer naf_..."
```

**Example Response:**
```json
{
  "domain": "example.com",
  "records": [
    {
      "id": "12345",
      "hostname": "www",
      "type": "A",
      "destination": "203.0.113.1",
      "priority": null
    },
    {
      "id": "12346",
      "hostname": "mail",
      "type": "MX",
      "destination": "mail.example.com",
      "priority": 10
    }
  ],
  "total": 2
}
```

### Create Record

**Endpoint:** `POST /api/dns/<domain>/records`

**Description:** Create a new DNS record.

**Request Body:**
```json
{
  "hostname": "device",
  "type": "A",
  "destination": "203.0.113.42",
  "priority": null
}
```

**Example Request:**
```bash
curl -X POST "https://naf.example.com/api/dns/example.com/records" \
  -H "Authorization: Bearer naf_..." \
  -H "Content-Type: application/json" \
  -d '{"hostname":"device","type":"A","destination":"203.0.113.42"}'
```

**Example Response:**
```json
{
  "status": "created",
  "record": {
    "hostname": "device",
    "type": "A",
    "destination": "203.0.113.42"
  }
}
```

### Update Record

**Endpoint:** `PUT /api/dns/<domain>/records/<record_id>`

**Description:** Update an existing DNS record.

**Request Body:**
```json
{
  "hostname": "device",
  "type": "A",
  "destination": "203.0.113.43",
  "priority": null
}
```

**Example Request:**
```bash
curl -X PUT "https://naf.example.com/api/dns/example.com/records/12345" \
  -H "Authorization: Bearer naf_..." \
  -H "Content-Type: application/json" \
  -d '{"hostname":"device","type":"A","destination":"203.0.113.43"}'
```

### Delete Record

**Endpoint:** `DELETE /api/dns/<domain>/records/<record_id>`

**Description:** Delete a DNS record.

**Example Request:**
```bash
curl -X DELETE "https://naf.example.com/api/dns/example.com/records/12345" \
  -H "Authorization: Bearer naf_..."
```

---

## DDNS Protocol Endpoints

DDNS-compatible endpoints for dynamic IP updates. These return **plain text responses** (not JSON) following DynDNS2/No-IP protocol specifications.

For complete documentation, see [DDNS_PROTOCOLS.md](DDNS_PROTOCOLS.md).

### DynDNS2 Update

**Endpoint:** `GET /api/ddns/dyndns2/update` or `POST /api/ddns/dyndns2/update`

**Description:** Update DNS record using DynDNS2 protocol.

**Query Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `hostname` | Yes | FQDN to update (e.g., `device.example.com`) |
| `myip` | No | IP address or `auto`/`public`/`detect` for auto-detection |
| `username` | No | Ignored (legacy compatibility) |
| `password` | No | Ignored (legacy compatibility) |

**Authentication:** Bearer token in `Authorization` header.

**Example Request:**
```bash
curl "https://naf.example.com/api/ddns/dyndns2/update?hostname=device.example.com&myip=auto" \
  -H "Authorization: Bearer naf_..."
```

**Example Response:**
```
good 203.0.113.42
```

**Response Codes:**

| Code | Status | Meaning |
|------|--------|---------|
| `good <ip>` | 200 | Update successful |
| `nochg <ip>` | 200 | No change needed |
| `badauth` | 401 | Authentication failed |
| `!yours` | 403 | Permission denied |
| `notfqdn` | 400 | Invalid hostname |
| `dnserr` | 502 | DNS error |
| `911` | 500 | Server error |

### No-IP Update

**Endpoint:** `GET /api/ddns/noip/update` or `POST /api/ddns/noip/update`

**Description:** Update DNS record using No-IP protocol.

**Query Parameters:** Same as DynDNS2.

**Authentication:** Same as DynDNS2.

**Example Request:**
```bash
curl "https://naf.example.com/api/ddns/noip/update?hostname=vpn.example.com&myip=public" \
  -H "Authorization: Bearer naf_..."
```

**Example Response:**
```
good 198.51.100.5
```

**Response Codes:**

| Code | Status | Meaning |
|------|--------|---------|
| `good <ip>` | 200 | Update successful |
| `nochg <ip>` | 200 | No change needed |
| `nohost` | 401/400 | Auth failed or invalid hostname |
| `abuse` | 403 | Permission denied |
| `dnserr` | 502 | DNS error |
| `911` | 500 | Server error |

**Note:** No-IP uses `nohost` for both authentication and hostname errors.

### Auto IP Detection

Both endpoints support automatic IP detection:

**Triggers:**
- `myip` parameter missing
- `myip` parameter empty (`myip=`)
- `myip=auto`
- `myip=public`
- `myip=detect`

**Behavior:**
- Uses client IP from request
- Respects `X-Forwarded-For` header (first IP)
- Automatically detects IPv4/IPv6 (creates A/AAAA record accordingly)

**Example with IPv6:**
```bash
curl "https://naf.example.com/api/ddns/dyndns2/update?hostname=device.example.com&myip=2001:db8::1" \
  -H "Authorization: Bearer naf_..."
```

Response:
```
good 2001:db8::1
```

---

## Utility Endpoints

### Get My IP

**Endpoint:** `GET /api/myip`

**Description:** Returns caller's public IP address (no authentication required).

**Example Request:**
```bash
curl "https://naf.example.com/api/myip"
```

**Example Response:**
```json
{
  "ip": "203.0.113.42",
  "headers": {
    "x-forwarded-for": "203.0.113.42, 198.51.100.1",
    "x-real-ip": "203.0.113.42"
  }
}
```

### GeoIP Lookup

**Endpoint:** `GET /api/geoip/<ip>`

**Description:** Look up geolocation for an IP address (no authentication required).

**Example Request:**
```bash
curl "https://naf.example.com/api/geoip/8.8.8.8"
```

**Example Response:**
```json
{
  "ip": "8.8.8.8",
  "country": "US",
  "country_name": "United States",
  "city": "Mountain View",
  "latitude": 37.386,
  "longitude": -122.0838
}
```

### Health Check

**Endpoint:** `GET /health`

**Description:** Health check endpoint (no authentication required).

**Example Response:**
```json
{
  "status": "ok"
}
```

---

## Error Responses

### Standard Error Format

All JSON error responses follow this format:
```json
{
  "error": "error_code",
  "message": "Human-readable error message"
}
```

### Common HTTP Status Codes

| Code | Meaning | Example |
|------|---------|---------|
| 200 | Success | Request completed successfully |
| 201 | Created | Resource created |
| 400 | Bad Request | Invalid parameters or malformed request |
| 401 | Unauthorized | Missing or invalid authentication |
| 403 | Forbidden | Valid auth but insufficient permissions |
| 404 | Not Found | Endpoint or resource not found |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Server error |
| 502 | Bad Gateway | Backend (Netcup API) error |

---

## Rate Limiting

API endpoints are subject to rate limiting:
- **Default:** 200 requests per hour, 50 per minute
- **Auth endpoints:** 10 requests per minute
- **Response Header:** `Retry-After` (seconds to wait)

**Rate Limit Response:**
```json
{
  "error": "rate_limited",
  "message": "Too many requests",
  "retry_after": 60
}
```

---

## Client Configuration Examples

### curl
```bash
# Set token as variable
TOKEN="naf_Ab3xYz9KmNpQrStU_..."

# List records
curl "https://naf.example.com/api/dns/example.com/records" \
  -H "Authorization: Bearer $TOKEN"

# DDNS update
curl "https://naf.example.com/api/ddns/dyndns2/update?hostname=device.example.com&myip=auto" \
  -H "Authorization: Bearer $TOKEN"
```

### Python (requests)
```python
import requests

TOKEN = "naf_Ab3xYz9KmNpQrStU_..."
BASE_URL = "https://naf.example.com"

headers = {
    "Authorization": f"Bearer {TOKEN}"
}

# List records
response = requests.get(
    f"{BASE_URL}/api/dns/example.com/records",
    headers=headers
)
print(response.json())

# DDNS update
response = requests.get(
    f"{BASE_URL}/api/ddns/dyndns2/update",
    headers=headers,
    params={"hostname": "device.example.com", "myip": "auto"}
)
print(response.text)  # Plain text response
```

### JavaScript (fetch)
```javascript
const TOKEN = "naf_Ab3xYz9KmNpQrStU_...";
const BASE_URL = "https://naf.example.com";

const headers = {
    "Authorization": `Bearer ${TOKEN}`
};

// List records
fetch(`${BASE_URL}/api/dns/example.com/records`, { headers })
    .then(response => response.json())
    .then(data => console.log(data));

// DDNS update
fetch(`${BASE_URL}/api/ddns/dyndns2/update?hostname=device.example.com&myip=auto`, { headers })
    .then(response => response.text())
    .then(text => console.log(text));  // Plain text response
```

---

## Related Documentation

- **[DDNS Protocols](DDNS_PROTOCOLS.md)** - Complete DDNS protocol documentation with client configs
- **[Client Templates](../CLIENT_TEMPLATES.md)** - Pre-configured token templates for common use cases
- **[README](../README.md)** - Project overview and getting started guide

---

## Support

For issues or questions:
1. Check the [DDNS Troubleshooting Guide](DDNS_PROTOCOLS.md#troubleshooting)
2. Review server logs and activity logs
3. Test with curl to isolate issues
4. Contact support with error codes and log excerpts (never include full tokens!)
