# Deployment Workflow Documentation

## Overview

The deployment system now provides a seamless, zero-configuration workflow for both local and webhosting deployments.

## Key Improvements

### 1. Automatic FQDN Detection

**No manual setup required!** The system automatically detects your public FQDN via reverse DNS.

```bash
# Just run deploy.sh - FQDN detection is automatic
./deploy.sh local
```

**How it works:**
1. When starting TLS proxy, checks if `PUBLIC_FQDN` exists in `.env.workspace`
2. If missing, automatically runs `detect-fqdn.sh --update-workspace`
3. Detects public IP via multiple endpoints (ipify, icanhazip, ifconfig.me)
4. Performs reverse DNS lookup to get FQDN
5. Saves results to `.env.workspace` for future runs
6. Configures TLS proxy with detected FQDN

**Files updated automatically:**
- `.env.workspace` - Adds `PUBLIC_FQDN` and `PUBLIC_IP`
- `tooling/reverse-proxy/.env` - Uses `${PUBLIC_FQDN}` variable
- Certificate paths - Constructed as `/etc/letsencrypt/live/${PUBLIC_FQDN}/`

### 2. Unified Service Naming (`.env.services`)

All container/service names are now centralized in `.env.services`:

```bash
# Service names follow pattern: ${PROJECT_TAG}-${ENV_TAG}-{service}
SERVICE_PLAYWRIGHT="naf-dev-playwright"
SERVICE_REVERSE_PROXY="naf-dev-reverse-proxy"
SERVICE_MAILPIT="naf-dev-mailpit"
# ... etc
```

**Benefits:**
- Single source of truth for all service names
- Easy to change environment tags (dev/staging/prod)
- Consistent across Docker Compose, nginx configs, Python code, shell scripts

### 3. Clean Stop/Start Workflow

#### Stop All Services

```bash
./deploy.sh --stop
```

**What it stops:**
1. Flask/gunicorn backend
2. TLS reverse proxy (nginx)
3. Mailpit (SMTP testing)
4. Mock Netcup API
5. Mock GeoIP service
6. Playwright container

**Output:**
```
╔═══════════════════════════════════════════════════════════╗
║  Stopping All Deployment Services
╚═══════════════════════════════════════════════════════════╝

→ Stopping Flask backend...
✓ Flask stopped
→ Stopping TLS reverse proxy...
✓ TLS proxy stopped
→ Stopping Mailpit...
✓ Mailpit stopped
→ Stopping Mock Netcup API...
✓ Mock Netcup API stopped
→ Stopping Mock GeoIP...
✓ Mock GeoIP stopped
→ Stopping Playwright container...
✓ Playwright stopped

✓ All naf- containers stopped
```

#### Fresh Start (From Scratch)

```bash
./deploy.sh local
```

**What it does automatically:**
1. **Phase 0: Infrastructure**
   - Auto-detects PUBLIC_FQDN if missing
   - Starts Playwright container
   - Starts mock services (Mailpit, Mock Netcup API, Mock GeoIP)
   - Starts TLS reverse proxy with Let's Encrypt certificates

2. **Phase 1: Build**
   - Creates fresh `deploy.zip` with vendored dependencies
   - Includes fresh database with default credentials

3. **Phase 2: Deploy**
   - Extracts to `deploy-local/`
   - Preserves screenshots directory

4. **Phase 3: Start**
   - Starts Flask/gunicorn backend

5. **Phase 4: Journey Tests**
   - Documents fresh deployment experience
   - Performs initial password change
   - Captures authentication screenshots

6. **Phase 5: Validation Tests**
   - Runs comprehensive test suite (90+ tests)
   - Adapts to deployment mode (mock vs live)

7. **Phase 6: Screenshots**
   - Captures all UI pages for documentation

## Usage Examples

### Quick Development Iteration

```bash
# Full deployment with all tests (default)
./deploy.sh local

# Skip tests for faster iteration
./deploy.sh local --skip-tests

# Run tests only (no rebuild)
./deploy.sh local --tests-only

# Plain HTTP (no TLS proxy)
./deploy.sh local --http
```

### Production Deployment

```bash
# Deploy to webhosting (uses live services by default)
./deploy.sh webhosting

# Skip tests on production
./deploy.sh webhosting --skip-tests
```

### Service Management

```bash
# Stop everything
./deploy.sh --stop

# Start fresh with HTTPS (default)
./deploy.sh local

# Start with HTTP only
./deploy.sh local --http

# Start with live services (real Netcup API)
./deploy.sh local --mode live
```

## Configuration Files

### `.env.workspace` (Auto-generated)

Created by `post-create.sh` and updated by `detect-fqdn.sh`:

```bash
export PUBLIC_FQDN="gstammtisch.dchive.de"
export PUBLIC_IP="152.53.179.117"
export REPO_ROOT="/workspaces/netcup-api-filter"
export PHYSICAL_REPO_ROOT="/home/vb/volkb79-2/netcup-api-filter"
export DOCKER_NETWORK_INTERNAL="naf-dev-network"
export DEVCONTAINER_NAME="netcup-api-filter-devcontainer-vb"
```

### `.env.services` (Service Names)

Central registry of all service/container names:

```bash
SERVICE_PLAYWRIGHT="naf-dev-playwright"
SERVICE_REVERSE_PROXY="naf-dev-reverse-proxy"
SERVICE_MAILPIT="naf-dev-mailpit"
SERVICE_MOCK_NETCUP_API="naf-dev-mock-netcup-api"
SERVICE_MOCK_GEOIP="naf-dev-mock-geoip"

# URLs for inter-service communication
MAILPIT_URL="http://naf-dev-mailpit:8025/mailpit"
MOCK_NETCUP_API_URL="http://naf-dev-mock-netcup-api"
```

### `tooling/reverse-proxy/.env`

TLS proxy configuration (uses variables from `.env.workspace`):

```bash
LOCAL_TLS_DOMAIN=${PUBLIC_FQDN:-gstammtisch.dchive.de}
LOCAL_APP_HOST=netcup-api-filter-devcontainer-vb
LOCAL_APP_PORT=5100
LOCAL_TLS_BIND_HTTPS=443
LOCAL_PROXY_NETWORK=naf-dev-network
```

## Deployment Modes

### Mock Mode (Default for Local)

Uses mock services for isolated testing:
- Mailpit for SMTP (web UI at `/mailpit`)
- Mock Netcup API (simulated DNS responses)
- Mock GeoIP (IP geolocation testing)

```bash
./deploy.sh local  # Implicit --mode mock
```

### Live Mode (Default for Webhosting)

Uses real external services:
- Real SMTP server (from config)
- Real Netcup CCP API
- Real GeoIP service

```bash
./deploy.sh local --mode live
./deploy.sh webhosting  # Always live mode
```

## HTTPS vs HTTP

### HTTPS (Default for Local)

Provides production parity with real Let's Encrypt certificates:

```bash
./deploy.sh local  # HTTPS via TLS proxy
```

**Requirements:**
- Public FQDN with reverse DNS configured
- Let's Encrypt certificates at `/etc/letsencrypt/live/${PUBLIC_FQDN}/`
- Certificates readable by nginx container (docker group access)

**Benefits:**
- 100% production parity
- Secure cookies work correctly
- Tests HTTPS-specific features
- Mailpit accessible at `https://${PUBLIC_FQDN}/mailpit`

### HTTP (Opt-in)

Simplified setup without TLS:

```bash
./deploy.sh local --http
```

**When to use:**
- No Let's Encrypt certificates available
- Quick local testing without HTTPS requirements
- Debugging TLS-independent issues

## Troubleshooting

### FQDN Detection Failed

If reverse DNS is not configured:

```bash
# Manual override
FORCE_FQDN=my-domain.com ./detect-fqdn.sh --update-workspace

# Or use HTTP mode
./deploy.sh local --http
```

### Certificates Not Found

```bash
# Check if certificates exist on host
ls -la /etc/letsencrypt/live/${PUBLIC_FQDN}/

# If missing, obtain Let's Encrypt certificate
sudo certbot certonly --standalone -d ${PUBLIC_FQDN}

# Or use HTTP mode
./deploy.sh local --http
```

### Services Won't Stop

```bash
# Force stop all naf- containers
docker ps --filter "name=naf-" -q | xargs -r docker stop

# Verify all stopped
docker ps --filter "name=naf-"
```

### Flask Import Errors

Check that all dependencies are in `requirements.webhosting.txt`:

```bash
# List vendored packages
ls deploy-local/vendor/

# Check for missing package
grep -i httpx requirements.webhosting.txt
```

## Advanced Usage

### Skip Infrastructure Setup

If services are already running:

```bash
./deploy.sh local --skip-infra --skip-tests
```

### Run Specific Test Suite

```bash
# Set environment and run pytest directly
DEPLOYMENT_TARGET=local \
UI_BASE_URL="https://gstammtisch.dchive.de" \
pytest ui_tests/tests/test_admin_ui.py -v
```

### Debug TLS Proxy

```bash
# Check proxy logs
docker logs naf-dev-reverse-proxy

# Test backend directly (bypass proxy)
curl http://localhost:5100/admin/login

# Test HTTPS through proxy
curl -sk https://gstammtisch.dchive.de/admin/login
```

## Migration from Old Workflow

### Before (Manual Steps)

```bash
# 1. Manual FQDN detection
./detect-fqdn.sh --update-workspace

# 2. Manual proxy configuration
cd tooling/reverse-proxy
./render-nginx-conf.sh
./stage-proxy-inputs.sh
docker compose up -d

# 3. Build and deploy
cd ../..
./build-and-deploy-local.sh

# 4. Manual cleanup
pkill gunicorn
docker stop naf-playwright
docker stop naf-reverse-proxy
```

### After (Automated)

```bash
# Start everything
./deploy.sh local

# Stop everything
./deploy.sh --stop
```

**Improvements:**
- ✅ FQDN detection automatic
- ✅ Single command for full deployment
- ✅ Clean stop/start workflow
- ✅ Centralized service naming
- ✅ Automatic proxy configuration

## See Also

- [FQDN Detection](FQDN_DETECTION.md) - Reverse DNS and certificate paths
- [Local Testing Guide](LOCAL_TESTING_GUIDE.md) - HTTP testing without TLS
- [HTTPS Local Testing](HTTPS_LOCAL_TESTING.md) - TLS proxy setup
- [Deploy Architecture](DEPLOY_ARCHITECTURE.md) - System architecture
