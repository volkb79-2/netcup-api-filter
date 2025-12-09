# Certificate Mounting in Devcontainer

## Problem

When running inside a devcontainer, Docker containers need access to:
1. **Let's Encrypt certificates** from the host's `/etc/letsencrypt`
2. **nginx config files** from the workspace (which is inside the devcontainer)

The challenge: Docker daemon runs on the **host**, not in the devcontainer. Volume mounts must reference **host paths**, not devcontainer paths.

## Solution

### Architecture

```
Host Machine
├── /etc/letsencrypt/              # Let's Encrypt certificates
│   └── live/gstammtisch.dchive.de/
│       ├── fullchain.pem -> ../../archive/.../fullchain2.pem
│       └── privkey.pem -> ../../archive/.../privkey2.pem
│
└── /home/vb/volkb79-2/netcup-api-filter/  # Physical repo (PHYSICAL_REPO_ROOT)
    └── tooling/reverse-proxy/
        └── conf.d/default.conf    # nginx config
```

### Docker Compose Configuration

```yaml
services:
  reverse-proxy:
    image: nginx:stable-alpine
    # Run as root with docker group for certificate access
    user: "0:${DOCKER_GID}"
    volumes:
      # Config: Use PHYSICAL_REPO_ROOT (host path to workspace)
      - "${PHYSICAL_REPO_ROOT}/tooling/reverse-proxy/conf.d:/etc/nginx/conf.d:ro"
      
      # Certificates: Direct mount from host
      - /etc/letsencrypt:/etc/letsencrypt:ro
```

### Key Variables

| Variable | Source | Value | Purpose |
|----------|--------|-------|---------|
| `PHYSICAL_REPO_ROOT` | `.env.workspace` | `/home/vb/volkb79-2/netcup-api-filter` | Host path to workspace |
| `DOCKER_GID` | `.env.workspace` | `994` | Docker group ID (for cert access) |
| `PUBLIC_FQDN` | `.env.workspace` | `gstammtisch.dchive.de` | Auto-detected FQDN |

### User/Group Strategy

```yaml
user: "0:${DOCKER_GID}"
```

- **UID 0** (root): Required for nginx to bind to privileged ports (80, 443)
- **GID 994** (docker): Allows reading Let's Encrypt certs owned by docker group

Let's Encrypt directory permissions:
```bash
drwxr-x---    9 root     994           4096 Oct 29 01:56 /etc/letsencrypt/live
```

The `docker` group (GID 994) has read-execute access, allowing nginx running as `root:docker` to read certificate files.

## Why This Works

### 1. PHYSICAL_REPO_ROOT

**Problem**: Devcontainer path `/workspaces/netcup-api-filter` doesn't exist on host.

**Solution**: `PHYSICAL_REPO_ROOT` contains the **host-side path** to the workspace:
- Inside devcontainer: `/workspaces/netcup-api-filter`
- On host: `/home/vb/volkb79-2/netcup-api-filter`

Docker daemon (running on host) uses the host path to bind-mount config files.

### 2. Direct Certificate Mount

**Problem**: Staging certs to `/tmp` creates copies and breaks symlinks.

**Solution**: Mount `/etc/letsencrypt:ro` directly from host:
- No staging scripts needed
- Symlinks work correctly (nginx follows links with `disable_symlinks off`)
- Always up-to-date (no copy lag)

### 3. Group Membership

**Problem**: Certs are owned by `root:docker`, not readable by arbitrary users.

**Solution**: Run nginx as `root:docker` (UID 0, GID 994):
- Root can bind to ports 80/443
- Docker group membership allows reading certs

## Implementation

### docker-compose.yml

```yaml
services:
  reverse-proxy:
    user: "0:${DOCKER_GID:?DOCKER_GID must be set}"
    volumes:
      # Config from workspace (via PHYSICAL_REPO_ROOT)
      - "${PHYSICAL_REPO_ROOT:?PHYSICAL_REPO_ROOT must be set}/tooling/reverse-proxy/conf.d:/etc/nginx/conf.d:ro"
      
      # Certs from host (direct mount)
      - /etc/letsencrypt:/etc/letsencrypt:ro
    environment:
      - PUBLIC_FQDN=${PUBLIC_FQDN:?PUBLIC_FQDN must be set}
```

### start-local-https.sh

```bash
# Export required variables for docker-compose
export PHYSICAL_REPO_ROOT="${PHYSICAL_REPO_ROOT:?PHYSICAL_REPO_ROOT must be set}"
export DOCKER_GID="${DOCKER_GID:?DOCKER_GID must be set}"
export PUBLIC_FQDN="${PUBLIC_FQDN:?PUBLIC_FQDN must be set}"

# Start proxy
docker compose --env-file proxy.env up -d
```

### nginx.conf

```nginx
server {
    listen 443 ssl;
    server_name gstammtisch.dchive.de;
    
    # Certificates via direct host mount
    ssl_certificate     /etc/letsencrypt/live/gstammtisch.dchive.de/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/gstammtisch.dchive.de/privkey.pem;
    
    # Allow following Let's Encrypt symlinks
    disable_symlinks off;
}
```

## Benefits

1. **No Staging Scripts**: No `stage-proxy-inputs.sh` needed
2. **No Copies**: Direct mount avoids stale cert copies
3. **Symlinks Work**: nginx follows Let's Encrypt's archive symlinks
4. **Always Fresh**: Certificate renewals immediately available
5. **Secure**: Read-only mounts, group-based access control

## Verification

```bash
# Check variables
source .env.workspace
echo "PHYSICAL_REPO_ROOT: ${PHYSICAL_REPO_ROOT}"
echo "DOCKER_GID: ${DOCKER_GID}"
echo "PUBLIC_FQDN: ${PUBLIC_FQDN}"

# Verify certs accessible inside container
docker exec naf-reverse-proxy ls -la /etc/letsencrypt/live/gstammtisch.dchive.de/

# Test nginx config
docker exec naf-reverse-proxy nginx -t

# Test HTTPS endpoint
curl -sfk https://gstammtisch.dchive.de/admin/login
```

## Comparison: Old vs New

### Old Approach (Staging)

```yaml
volumes:
  - "${LE_CERT_BASE}:/etc/letsencrypt:ro"  # LE_CERT_BASE=/tmp/naf-proxy-certs
  - "${LOCAL_PROXY_CONFIG_PATH}:/etc/nginx/conf.d:ro"  # /tmp/naf-proxy-conf
```

**Required**:
1. Run `stage-proxy-inputs.sh` to copy certs to `/tmp`
2. Run `stage-proxy-inputs.sh` to copy configs to `/tmp`
3. Docker mounts from `/tmp` (accessible to daemon)

**Issues**:
- Extra staging step
- Stale copies (renewal doesn't auto-update)
- Breaks symlinks (copies resolve them)

### New Approach (Direct Mount)

```yaml
user: "0:${DOCKER_GID}"
volumes:
  - "${PHYSICAL_REPO_ROOT}/tooling/reverse-proxy/conf.d:/etc/nginx/conf.d:ro"
  - /etc/letsencrypt:/etc/letsencrypt:ro
```

**Required**:
1. Set `PHYSICAL_REPO_ROOT`, `DOCKER_GID`, `PUBLIC_FQDN`
2. Run `docker compose up`

**Benefits**:
- No staging
- Always fresh
- Symlinks work
- Simpler workflow

## Troubleshooting

### "Cannot load certificate"

```bash
# Check if certs exist on host
ls -la /etc/letsencrypt/live/gstammtisch.dchive.de/

# Check if nginx container can see them
docker exec naf-reverse-proxy ls -la /etc/letsencrypt/live/gstammtisch.dchive.de/

# Check user/group
docker exec naf-reverse-proxy id
# Should show: uid=0(root) gid=994(docker)
```

### "Config file not found"

```bash
# Check PHYSICAL_REPO_ROOT
echo $PHYSICAL_REPO_ROOT
# Should be host path, not /workspaces/...

# Verify config exists on host
ls -la "${PHYSICAL_REPO_ROOT}/tooling/reverse-proxy/conf.d/default.conf"
```

### "Permission denied"

```bash
# Check DOCKER_GID matches docker group
getent group docker
# Output: docker:x:994:vb

# Verify container runs with correct GID
docker exec naf-reverse-proxy id
# gid should match docker group GID
```

## Related Documentation

- **FQDN Detection**: `docs/FQDN_DETECTION.md`
- **Environment Setup**: `docs/ENV_WORKSPACE.md`
- **Deployment Guide**: `DEPLOYMENT_SUCCESS.md`

---

**Last Updated**: 2025-12-08  
**Status**: Production-ready with Let's Encrypt certificates
