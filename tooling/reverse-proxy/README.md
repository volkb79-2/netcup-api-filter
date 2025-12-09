# Local TLS Reverse Proxy

This folder contains the tooling required to run a local reverse proxy that
terminates TLS for the host's public Fully Qualified Domain Name (FQDN) while
forwarding traffic to a locally running instance of the Netcup API Filter.
Use this when you need production-like HTTPS behaviour (real hostname,
Let's Encrypt certificates, secure cookies) but also want full observability that is not
available on the shared webhosting setup.

## Certificate Access Pattern (CRITICAL)

**Problem**: In devcontainer scenarios, the devcontainer user cannot access `/etc/letsencrypt` on the host.

**Solution**: Docker daemon mounts host filesystem directly to nginx container, which runs with docker group membership.

```
HOST filesystem:
  /etc/letsencrypt/
    drwxr-x--- root:docker  (perms: 750)
    ├── live/${PUBLIC_FQDN}/fullchain.pem
    └── live/${PUBLIC_FQDN}/privkey.pem

Devcontainer:
  Cannot access /etc/letsencrypt (isolated)
  ❌ ls /etc/letsencrypt/live/  # "No such file or directory"

nginx container:
  user: "0:${DOCKER_GID}"  # UID=0 (root), GID=994 (docker)
  volumes:
    - /etc/letsencrypt:/etc/letsencrypt:ro  # HOST path mounted by Docker daemon
  ✅ Can read certs via docker group membership
```

**Verification**: Never check certificate existence from devcontainer. Let nginx container start and fail with clear error if certs are missing/unreadable.

## When to use this project

- **Debugging complex flows**: run the Flask stack locally, capture logs and
  traces, yet continue driving the UI via `https://<public-fqdn>/...` so the
  Playwright MCP harness and browsers behave exactly as in production.
- **Pre-deployment validation**: exercise password rotations or token
  provisioning locally before publishing to the live webhoster.
- **TLS parity**: confirm that modern browsers, MCP tools or API clients accept
  the same certificate chain that production uses (no self-signed certs).

If the shared hosting target already provides the telemetry you need, keep
using the `## deploy to live server via webhosting` flow from `AGENTS.md`.
Otherwise, spin up this local proxy and point clients at it.

## Files in this folder

| File | Purpose | Status |
| ---- | ------- | ------ |
| `docker-compose.yml` | Defines the `reverse-proxy` service (nginx) with direct mounts via `PHYSICAL_REPO_ROOT`. | ✅ Active |
| `.env` | Configuration variables consumed by Docker Compose (sourced from `.env.workspace`). | ✅ Active |
| `nginx.conf.template` | Parametrised nginx config; rendered with `envsubst` using values from `.env`. | ✅ Active |
| `nginx.conf` | Base nginx.conf (mounted as `/etc/nginx/nginx.conf`, includes `conf.d/*.conf`). | ✅ Active |
| `conf.d/default.conf` | Generated site config (regenerated from template on each deployment). | 🔄 Generated |
| `render-nginx-conf.sh` | Renders `nginx.conf.template` → `conf.d/default.conf` using `.env` variables. | ✅ Active |
| `_proxy_lib.sh` | Shared bash functions for config rendering and validation. | ✅ Active |
| `README.md` | You are here. | ✅ Active |

**Obsolete files removed:**
- ❌ `stage-proxy-inputs.sh` - No longer needed with `PHYSICAL_REPO_ROOT` direct mounts
- ❌ `auto-detect-fqdn.sh` - Duplicate of root `detect-fqdn.sh`
- ❌ `proxy.env` - Renamed to `.env` for consistency
- ❌ `local_app.py` - Never implemented, backend managed separately

## Architecture (Updated December 2024)

**Key Changes from Previous Version:**
- ✅ **Direct mounts** - Uses `PHYSICAL_REPO_ROOT` instead of `/tmp` staging
- ✅ **Simplified workflow** - No more `stage-proxy-inputs.sh` needed
- ✅ **Centralized FQDN** - Uses root `detect-fqdn.sh` → `.env.workspace`
- ✅ **Consistent naming** - `proxy.env` → `.env` to match other services

### How It Works

```
Root Repository
├── .env.workspace                    # PUBLIC_FQDN, PHYSICAL_REPO_ROOT, DOCKER_GID
├── detect-fqdn.sh                    # Detects FQDN via reverse DNS
└── tooling/reverse-proxy/
    ├── .env                          # Proxy config (sources .env.workspace)
    ├── nginx.conf.template           # Template with ${variables}
    ├── render-nginx-conf.sh          # envsubst → conf.d/default.conf
    ├── conf.d/default.conf           # Generated config (git-ignored)
    └── docker-compose.yml            # Direct mounts via PHYSICAL_REPO_ROOT
```

**Docker Compose Mounts:**
```yaml
volumes:
  # Config files (direct mount via PHYSICAL_REPO_ROOT)
  - ${PHYSICAL_REPO_ROOT}/tooling/reverse-proxy/conf.d:/etc/nginx/conf.d:ro
  # Let's Encrypt certificates (direct mount from host)
  - /etc/letsencrypt:/etc/letsencrypt:ro
```

**Why PHYSICAL_REPO_ROOT?**
- Docker daemon on host can't access `/workspaces/` inside devcontainer
- `PHYSICAL_REPO_ROOT` points to host-side path (e.g., `/home/vb/volkb79-2/netcup-api-filter`)
- Set automatically by devcontainer, available in `.env.workspace`

## Quick Start

### One-Command Deployment

```bash
# Start everything (mock services, Flask, proxy, Playwright)
./start-local-https.sh

# Access deployment
echo "Admin UI: https://${PUBLIC_FQDN}/admin/login"
echo "Mailpit: https://${PUBLIC_FQDN}/mailpit/"
echo "Credentials: admin / admin"
```

### Manual Setup (Step-by-Step)

```bash
# 1. Detect public FQDN (populates .env.workspace)
./detect-fqdn.sh --update-workspace [--verify-certs]

# 2. Build deployment
python3 build_deployment.py --local

# 3. Generate nginx config
cd tooling/reverse-proxy
./render-nginx-conf.sh  # Reads .env, writes conf.d/default.conf

# 4. Start proxy
docker compose --env-file .env up -d

# 5. Start Flask backend (separate terminal)
cd deploy-local
gunicorn passenger_wsgi:application -b 0.0.0.0:5100
```

## Configuration Variables (`.env`)

All configuration is sourced from `.env.workspace` at the repository root. Variables:

| Variable | Source | Description |
|----------|--------|-------------|
| `PUBLIC_FQDN` | `.env.workspace` | Auto-detected via reverse DNS (e.g., `gstammtisch.dchive.de`) |
| `PHYSICAL_REPO_ROOT` | `.env.workspace` | Host-side path to repository (for Docker mounts) |
| `DOCKER_GID` | `.env.workspace` | Docker group GID (for certificate access) |
| `LOCAL_TLS_DOMAIN` | `.env` | Set to `${PUBLIC_FQDN}` (constructs cert paths) |
| `LOCAL_APP_HOST` | `.env` | Flask backend hostname (e.g., `netcup-api-filter-devcontainer-vb`) |
| `LOCAL_APP_PORT` | `.env` | Flask backend port (default: `5100`) |
| `LOCAL_PROXY_NETWORK` | `.env` | Docker network for proxy↔backend (default: `naf-dev-network`) |
| `LOCAL_TLS_BIND_HTTPS` | `.env` | Host HTTPS port binding (default: `443`) |
| `LOCAL_TLS_BIND_HTTP` | `.env` | Host HTTP port binding (default: `80`) |
| `LE_CERT_BASE` | `.env` | Let's Encrypt base path (default: `/etc/letsencrypt`) |

**Certificate Paths (Constructed):**
```bash
# Fullchain certificate
/etc/letsencrypt/live/${PUBLIC_FQDN}/fullchain.pem

# Private key
/etc/letsencrypt/live/${PUBLIC_FQDN}/privkey.pem
```

**Template Substitution:**
The `render-nginx-conf.sh` script uses `envsubst` to replace template variables:
```nginx
# nginx.conf.template → conf.d/default.conf
server_name ${LOCAL_TLS_DOMAIN} _;
ssl_certificate /etc/letsencrypt/live/${LOCAL_TLS_DOMAIN}/fullchain.pem;
proxy_pass http://${LOCAL_APP_HOST}:${LOCAL_APP_PORT};
```

## Safety Notes

- ✅ Let's Encrypt tree mounted **read-only** (proxy cannot alter certificates)
- ✅ Container runs as `root:docker` (GID access to certificates owned by `docker` group)
- ✅ `disable_symlinks off` allows following Let's Encrypt `live/ → archive/` symlinks
- ✅ `.env` and `conf.d/default.conf` are git-ignored (machine-specific, regenerated)
- ✅ Proxy and devcontainer share Docker network (`naf-dev-network`)

## Testing

### Verify Mailpit UI (Sub-filter Test)

```bash
# Test asset loading after sub_filter rewrite
curl -sk -u admin:MailpitDev123! https://${PUBLIC_FQDN}/mailpit/ | grep -E 'href="/mailpit/'
curl -sk -u admin:MailpitDev123! https://${PUBLIC_FQDN}/mailpit/dist/app.css | head -5
```

### Full Test Suite

```bash
# Complete test suite (90 tests)
./run-local-tests.sh

# UI tests only (28 interactive + 15 journey)
docker exec -e UI_BASE_URL="https://${PUBLIC_FQDN}" \
  naf-playwright pytest /workspaces/netcup-api-filter/ui_tests/tests -v
```

## Troubleshooting

**Config changes not applied?**
```bash
# Always regenerate config + restart container
cd tooling/reverse-proxy
./render-nginx-conf.sh
docker compose restart
```

**404 errors for Mailpit assets?**
```bash
# Verify sub_filter directives in config
grep -A3 "location /mailpit/" conf.d/default.conf
# Should show: sub_filter 'href="/' 'href="/mailpit/';
```

**Certificate errors?**
```bash
# Verify certificates exist on host
ls -l /etc/letsencrypt/live/${PUBLIC_FQDN}/
# Should show: fullchain.pem, privkey.pem (symlinks)

# Check certificate ownership/permissions
ls -l /etc/letsencrypt/archive/${PUBLIC_FQDN}/
# Should be readable by docker group
```

**Container can't start?**
```bash
# Check if PHYSICAL_REPO_ROOT is set
echo $PHYSICAL_REPO_ROOT
# If empty: source .env.workspace

# Verify Docker network exists
docker network ls | grep naf-dev-network
# If missing: devcontainer creates it automatically
```

## Related Documentation

- [`AGENTS.md`](../../AGENTS.md) - Complete deployment workflows
- [`docs/HTTPS_LOCAL_TESTING.md`](../../docs/HTTPS_LOCAL_TESTING.md) - HTTPS testing guide
- [`docs/MAILPIT_CONFIGURATION.md`](../../docs/MAILPIT_CONFIGURATION.md) - Mailpit setup
- [`detect-fqdn.sh`](../../detect-fqdn.sh) - FQDN detection script
