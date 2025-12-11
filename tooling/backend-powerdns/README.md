# PowerDNS Backend Tooling

Provides PowerDNS Authoritative Server as a self-managed DNS backend for netcup-api-filter.

## Overview

PowerDNS allows delegated DNS zones with full control:
- **Low TTL**: Set as low as 1 second (vs Netcup's 300s minimum)
- **No external risks**: Domain changes managed internally
- **HTTP API**: Direct integration without file parsing
- **Database-backed**: SQLite for persistent zone storage

## Quick Start

### 1. Generate API Key

```bash
cd /workspaces/netcup-api-filter

# Generate secure API key
openssl rand -hex 32

# Add to .env.defaults (or override in .env.workspace)
echo "POWERDNS_API_KEY=your-generated-key-here" >> .env.defaults
```

### 2. Start PowerDNS Container

```bash
cd tooling/backend-powerdns

# Source environment
source ../../.env.workspace
source ../../.env.services
source .env

# Start container
docker compose up -d

# Check logs
docker logs naf-dev-powerdns
```

### 3. Create Test Zone

```bash
# Create dyn.vxxu.de zone
./setup-zones.sh dyn.vxxu.de

# Or use defaults (dyn.vxxu.de)
./setup-zones.sh
```

### 4. Add DNS Delegation at Parent Zone

In your Netcup DNS panel for `vxxu.de`, add:

```dns
dyn.vxxu.de.  IN  NS  ns1.vxxu.de.
ns1.vxxu.de.  IN  A   <your-powerdns-server-public-ip>
```

Replace `<your-powerdns-server-public-ip>` with the public IP of the server running PowerDNS.

### 5. Test DNS Resolution

```bash
# Query PowerDNS directly (localhost)
dig @localhost -p 53 dyn.vxxu.de SOA

# Query via public DNS (after delegation propagates)
dig dyn.vxxu.de SOA
```

## API Examples

### Create/Update A Record

```bash
curl -X PATCH \
  -H "X-API-Key: $POWERDNS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "rrsets": [{
      "name": "test.dyn.vxxu.de.",
      "type": "A",
      "changetype": "REPLACE",
      "ttl": 60,
      "records": [{"content": "192.0.2.1", "disabled": false}]
    }]
  }' \
  http://naf-dev-powerdns:80/api/v1/servers/localhost/zones/dyn.vxxu.de.
```

### Delete Record

```bash
curl -X PATCH \
  -H "X-API-Key: $POWERDNS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "rrsets": [{
      "name": "test.dyn.vxxu.de.",
      "type": "A",
      "changetype": "DELETE"
    }]
  }' \
  http://naf-dev-powerdns:80/api/v1/servers/localhost/zones/dyn.vxxu.de.
```

### List Zone Records

```bash
curl -X GET \
  -H "X-API-Key: $POWERDNS_API_KEY" \
  http://naf-dev-powerdns:80/api/v1/servers/localhost/zones/dyn.vxxu.de. \
  | python3 -m json.tool
```

## Configuration

### Environment Variables

Defined in `.env` (sourced from `.env.workspace`, `.env.services`, `.env.defaults`):

| Variable | Default | Description |
|----------|---------|-------------|
| `POWERDNS_API_KEY` | (required) | API authentication key |
| `POWERDNS_DNS_PORT_UDP` | 53 | Public DNS query port (UDP) |
| `POWERDNS_DNS_PORT_TCP` | 53 | Public DNS query port (TCP) |
| `POWERDNS_API_PORT` | 80 | Internal API port |
| `POWERDNS_DEFAULT_TTL` | 60 | Default TTL for records |
| `PDNS_DEFAULT_SOA_NAME` | ns1.vxxu.de | SOA nameserver |
| `PDNS_DEFAULT_SOA_MAIL` | hostmaster.vxxu.de | SOA email |

### Data Persistence

Zone data stored in `tooling/backend-powerdns/data/pdns.sqlite3` (SQLite database).

**Backup:**
```bash
cp data/pdns.sqlite3 data/pdns.sqlite3.backup
```

**Reset (delete all zones):**
```bash
rm -rf data/
docker compose restart
```

## Integration with Flask App

PowerDNS is accessed via internal Docker network (`naf-dev-network`):

```python
# src/netcup_api_filter/backends/powerdns.py
import httpx
import os

POWERDNS_API_URL = os.environ.get("POWERDNS_API_URL", "http://naf-dev-powerdns:80")
POWERDNS_API_KEY = os.environ["POWERDNS_API_KEY"]

client = httpx.Client(
    base_url=POWERDNS_API_URL,
    headers={"X-API-Key": POWERDNS_API_KEY}
)

# Update record
response = client.patch(
    f"/api/v1/servers/localhost/zones/dyn.vxxu.de.",
    json={"rrsets": [{
        "name": "test.dyn.vxxu.de.",
        "type": "A",
        "changetype": "REPLACE",
        "ttl": 60,
        "records": [{"content": "192.0.2.1", "disabled": false}]
    }]}
)
```

## Reverse Proxy Route

PowerDNS API exposed via reverse proxy at `/backend-powerdns`:

```nginx
# Secured by PowerDNS API key (no additional auth needed)
location /backend-powerdns/ {
    proxy_pass http://naf-dev-powerdns:80/;
    proxy_set_header X-API-Key $http_x_api_key;
}
```

**External access:**
```bash
curl -X GET \
  -H "X-API-Key: $POWERDNS_API_KEY" \
  https://naf.vxxu.de/backend-powerdns/api/v1/servers/localhost/zones
```

## Troubleshooting

### Container Not Starting

```bash
# Check logs
docker logs naf-dev-powerdns

# Common issues:
# - Port 53 already in use (systemd-resolved)
# - Missing API key (check .env.defaults)
# - Database permissions (data/ directory)
```

### Port 53 Conflict (systemd-resolved)

If port 53 is already bound by systemd-resolved:

```bash
# Check what's using port 53
sudo lsof -i :53

# Option 1: Stop systemd-resolved (temporary)
sudo systemctl stop systemd-resolved

# Option 2: Change PowerDNS port in .env
POWERDNS_DNS_PORT_UDP=5353
POWERDNS_DNS_PORT_TCP=5353
```

### API Not Reachable

```bash
# Verify container is running
docker ps | grep powerdns

# Check network connectivity
docker exec -it netcup-api-filter-devcontainer-vb curl http://naf-dev-powerdns:80/api/v1/servers

# Verify API key
curl -H "X-API-Key: $POWERDNS_API_KEY" http://localhost:80/api/v1/servers/localhost
```

### Zone Not Resolving

```bash
# Test direct query to container
dig @localhost -p 53 dyn.vxxu.de SOA

# If works locally but not externally:
# 1. Check firewall rules (port 53 UDP/TCP)
# 2. Verify parent zone delegation (NS records)
# 3. Wait for DNS propagation (up to 24h)

# Check PowerDNS logs
docker logs naf-dev-powerdns | grep dyn.vxxu.de
```

## Files

```
tooling/backend-powerdns/
├── .env                    # Environment configuration (fail-fast)
├── docker-compose.yml      # PowerDNS container definition
├── setup-zones.sh          # Zone creation script
├── README.md               # This file
└── data/                   # SQLite database (gitignored)
    └── pdns.sqlite3
```

## See Also

- [PowerDNS Documentation](https://doc.powerdns.com/authoritative/)
- [PowerDNS API Reference](https://doc.powerdns.com/authoritative/http-api/index.html)
- [DNS Delegation Guide](../../docs/DNS_DELEGATION.md) (TODO)
- [Backend Abstraction](../../docs/BACKEND_ABSTRACTION.md) (TODO)
