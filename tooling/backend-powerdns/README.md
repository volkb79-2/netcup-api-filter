# PowerDNS Backend Tooling

Provides PowerDNS Authoritative Server as a self-managed DNS backend for netcup-api-filter.

## Overview

PowerDNS allows delegated DNS zones with full control:
- **Low TTL**: Set as low as 1 second (vs Netcup's 300s minimum)
- **No external risks**: Domain changes managed internally
- **HTTP API**: Direct integration without file parsing
- **Database-backed**: SQLite for persistent zone storage

## Architecture

**Init Container Pattern** - Proper separation of concerns:

```
Bind mount: tooling/backend-powerdns/data/ (host path, via PHYSICAL_REPO_ROOT)
  └── Persists across container restarts/recreation

naf-dev-powerdns-init (alpine:latest)
  ├── Runs once on startup (service_completed_successfully)
  ├── Mounts data/ at /data
  ├── Creates /data directory with 755 permissions
  ├── Initializes database if missing (sqlite3 + schema.sqlite3.sql)
  ├── Sets ownership to UID 953:docker (pdns user, host docker GID)
  └── Exits when complete

naf-dev-powerdns (powerdns/pdns-auth-48:latest)
  ├── Starts AFTER init container succeeds (depends_on)
  ├── Mounts same data/ at /var/lib/powerdns
  ├── Runs as pdns user (UID 953)
  ├── Reads database from the bind mount
  └── Serves DNS (port 53, published to the host) and the HTTP API (port 8081,
      internal-only — reachable from peers on the project network, and from
      outside via traefik at naf-pdns.<PUBLIC_FQDN> behind the basicauth guard)
```

**Why Init Container?**
- **Security**: Data directory owned by PowerDNS user only (770 perms)
- **Clean separation**: Deploy script doesn't need sudo/chmod/mkdir
- **Idempotent**: Safe to re-run, only initializes if missing
- **Fail-fast**: PowerDNS won't start if init fails

## ciu stack

This is a **ciu `.j2` stack** (`ciu.defaults.toml.j2` + `ciu.compose.yml.j2`),
not a hand-written `docker-compose.yml`. The rendered `ciu.toml` /
`ciu.compose.yml` are gitignored build artifacts — never edit or commit them.

The delegated DNS zone is **not** configured in this directory. It is a
GLOBAL topology fact (`[topology.dns] delegated_zone`, D-007 in
`nyxloom-trove/decisions.md`), sourced from `NAF_DELEGATED_DNS_ZONE` in the
environment. When it is set, a `post_compose` hook
(`post_compose_zone.py`) automatically creates the zone in PowerDNS — with an
SOA/NS derived from the zone itself (`ns1.<zone>`, `hostmaster.<zone>`) — the
first time this stack comes up. It is idempotent (no-op on rerun, no-op when
the zone is empty) and needs live validation on the next real redeploy.

## Quick Start

### 1. Generate API Key

```bash
cd /workspaces/netcup-api-filter

# Generate secure API key
openssl rand -hex 32

# Add to .env.defaults (or override in .env.workspace)
echo "POWERDNS_API_KEY=your-generated-key-here" >> .env.defaults
```

### 2. Start PowerDNS via ciu

```bash
cd /workspaces/netcup-api-filter

# ciu.env re-exports THIS repo's REPO_ROOT/PHYSICAL_REPO_ROOT — source it
# right before every ciu invocation (see ciu.global.defaults.toml.j2 header;
# a bare `ciu` call in this devcontainer can otherwise resolve to a sibling
# repo's checkout).
source ciu.env

# Single-stack bring-up
ciu up --dir tooling/backend-powerdns -y

# Check logs
docker logs naf-dev-powerdns
```

If `NAF_DELEGATED_DNS_ZONE` is set in the environment, the zone is created
automatically by the `post_compose` hook on this same `ciu up` — no separate
step needed. `POWERDNS_API_KEY` must be set (`.env` / `.env.defaults`) or the
render fails fast (`${POWERDNS_API_KEY:?...}` in ciu.compose.yml.j2).

### 3. Create an Additional Zone (optional)

`post_compose_zone.py` only bootstraps the ONE delegated zone from
`NAF_DELEGATED_DNS_ZONE`. For any other ad hoc zone, the old manual scripts
still work against a running stack:

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

## Volume Management

Data is a **bind mount** (`tooling/backend-powerdns/data/`, via
`PHYSICAL_REPO_ROOT`), not a Docker named volume — "resetting" means deleting
that directory on the host, not `docker volume rm`.

Stopping this single stack: `ciu down` only accepts `--profile` (whole-project
scope) — verified via `ciu down --help`; there is no supported `ciu down
--dir`. The working single-stack teardown is `docker compose` directly
against ciu's own rendered `ciu.compose.yml`, scoped to the same compose
project ciu used to bring it up (`<PROJECT_TAG>-<ENV_TAG>-backend-powerdns`,
i.e. `naf-dev-backend-powerdns`):

```bash
cd tooling/backend-powerdns
docker compose -p naf-dev-backend-powerdns -f ciu.compose.yml down
```

### Inspect Database

```bash
# Access database from container
docker exec naf-dev-powerdns sqlite3 /var/lib/powerdns/pdns.sqlite3 "SELECT * FROM domains;"
```

### Reset Database

```bash
# Stop the stack (see teardown command above)
cd tooling/backend-powerdns
docker compose -p naf-dev-backend-powerdns -f ciu.compose.yml down

# Delete the bind-mounted data directory
rm -rf data/

# Restart via ciu (init container recreates the database; the post_compose
# hook re-bootstraps the delegated zone if NAF_DELEGATED_DNS_ZONE is set)
cd /workspaces/netcup-api-filter
source ciu.env
ciu up --dir tooling/backend-powerdns -y
```

### Backup/Restore

```bash
# Backup
docker exec naf-dev-powerdns sqlite3 /var/lib/powerdns/pdns.sqlite3 .dump > backup.sql

# Restore (stop the stack first, see teardown command above)
cd tooling/backend-powerdns
docker compose -p naf-dev-backend-powerdns -f ciu.compose.yml down
rm -rf data/
cd /workspaces/netcup-api-filter && source ciu.env && ciu up --dir tooling/backend-powerdns -y
# Wait for init, then:
docker exec -i naf-dev-powerdns sqlite3 /var/lib/powerdns/pdns.sqlite3 < backup.sql
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
  http://naf-dev-powerdns:8081/api/v1/servers/localhost/zones/dyn.vxxu.de.
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
  http://naf-dev-powerdns:8081/api/v1/servers/localhost/zones/dyn.vxxu.de.
```

### List Zone Records

```bash
curl -X GET \
  -H "X-API-Key: $POWERDNS_API_KEY" \
  http://naf-dev-powerdns:8081/api/v1/servers/localhost/zones/dyn.vxxu.de. \
  | python3 -m json.tool
```

## Configuration

### Environment Variables

Only `POWERDNS_API_KEY` is a **required** operator-supplied secret (sourced
from `.env`/`.env.defaults`, fails render fast if unset — `${POWERDNS_API_KEY:?...}`
in `ciu.compose.yml.j2`). The DNS port (53), the API port (8081), and the
PowerDNS daemon knobs (`PDNS_AUTH_*`, `PDNS_LAUNCH`, logging, AXFR) are now
static config held in `ciu.defaults.toml.j2`'s `[backend_powerdns]` table, not
per-directory env vars:

| Variable | Source | Description |
|----------|--------|--------------|
| `POWERDNS_API_KEY` | `.env` / `.env.defaults` (required) | API authentication key (`openssl rand -hex 32`) |
| `[backend_powerdns].ports.dns` | ciu config, default `53` | Public DNS query port (UDP+TCP), published to the host |
| `[backend_powerdns].ports.api` | ciu config, default `8081` | Internal HTTP API port — never published to the host |
| `NAF_DELEGATED_DNS_ZONE` | root env (`ciu.env`/`.env`), default empty | The delegated zone (D-007) — read via `[topology.dns.delegated_zone]` |

There is no `PDNS_DEFAULT_SOA_NAME` / `PDNS_DEFAULT_SOA_MAIL` anymore. The
SOA is zone-specific and set automatically by `post_compose_zone.py` when the
zone is created (`ns1.<zone>.` / `hostmaster.<zone>.`), not a static default.

### Data Persistence

Zone data stored in `tooling/backend-powerdns/data/pdns.sqlite3` (SQLite database).

**Backup:**
```bash
cp data/pdns.sqlite3 data/pdns.sqlite3.backup
```

**Reset (delete all zones):**
```bash
rm -rf data/
# Recreate via ciu (see "Reset Database" above) — a bare `docker compose
# restart` will NOT recreate the schema; the init container only runs on `up`.
```

## Integration with Flask App

PowerDNS is accessed via internal Docker network (`naf-dev-network`):

```python
# src/netcup_api_filter/backends/powerdns.py
import httpx
import os

POWERDNS_API_URL = os.environ.get("POWERDNS_API_URL", "http://naf-dev-powerdns:8081")
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

## External Access (traefik)

naf no longer runs its own reverse proxy for this (superseded by host-traefik
exposure, naf-I04). The HTTP API is exposed by the host's `edge-traefik`
directly, at `naf-pdns.<PUBLIC_FQDN>`, behind the same basicauth guard as the
app (D-007) — see the `traefik.*` labels on the `{{ backend_powerdns.name }}`
service in `ciu.compose.yml.j2`. TLS/cert is inherited from traefik's
`websecure` entrypoint; nothing here holds cert material.

**External access:**
```bash
curl -X GET \
  -u "$NAF_GUARD_USER:$NAF_GUARD_PASSWORD" \
  -H "X-API-Key: $POWERDNS_API_KEY" \
  https://naf-pdns.<PUBLIC_FQDN>/api/v1/servers/localhost/zones
```

Internally (from another container on the project network), skip both
traefik and the guard and reach it by container name: `http://naf-dev-powerdns:8081/...`.

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

# Option 2: Change the DNS port — this is now static ciu config, not an env
# var (the real delegation always needs 53, so it isn't a per-developer
# override). Edit [backend_powerdns.ports].dns in ciu.defaults.toml.j2.
```

### API Not Reachable

```bash
# Verify container is running
docker ps | grep powerdns

# Check network connectivity
docker exec -it netcup-api-filter-devcontainer-vb curl http://naf-dev-powerdns:8081/api/v1/servers

# Verify API key
curl -H "X-API-Key: $POWERDNS_API_KEY" http://localhost:8081/api/v1/servers/localhost
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
├── ciu.defaults.toml.j2    # ciu stack marker — SOURCE. [backend_powerdns] config
│                            # (image, ports, UID, PDNS daemon knobs, health,
│                            # traefik toggle, zone flattened from
│                            # topology.dns.delegated_zone — D-007)
├── ciu.compose.yml.j2      # ciu compose template — SOURCE. Both services
│                            # (init + auth server), traefik/basicauth labels
├── post_compose_zone.py    # ciu post_compose hook — bootstraps the
│                            # delegated zone (SOA/NS derived from the zone,
│                            # idempotent, no-op when zone is empty)
├── ciu.toml                # rendered output of ciu.defaults.toml.j2 (GITIGNORED)
├── ciu.compose.yml         # rendered output of ciu.compose.yml.j2 (GITIGNORED)
├── ensure_zone.py          # manual/ops helper — idempotent zone-ensure via
│                            # the HTTP API, for zones OTHER than the delegated one
├── setup-zones.sh          # manual/ops helper — interactive zone creation
├── init-db.sh              # unreferenced by the current compose (the init
│                            # container's schema-load logic is inlined in
│                            # ciu.compose.yml.j2's `command:` instead)
├── schema.sqlite3.sql      # SQLite schema loaded by the init container
├── README.md               # This file
└── data/                   # SQLite database — bind mount (gitignored)
    └── pdns.sqlite3
```

## See Also

- [PowerDNS Documentation](https://doc.powerdns.com/authoritative/)
- [PowerDNS API Reference](https://doc.powerdns.com/authoritative/http-api/index.html)
- [DNS Delegation Guide](../../docs/DNS_DELEGATION.md) (TODO)
- [Backend Abstraction](../../docs/BACKEND_ABSTRACTION.md) (TODO)
