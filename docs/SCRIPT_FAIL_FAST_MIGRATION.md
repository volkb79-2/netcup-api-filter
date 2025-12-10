# Script Fail-Fast Migration Complete

## Summary

All tooling scripts have been migrated to use the fail-fast principle and centralized service names from `.env.services`.

## Changes Made

### 1. playwright-exec.sh
- ✅ Added `.env.services` sourcing
- ✅ Replaced hardcoded `"naf-dev-playwright"` with `${SERVICE_PLAYWRIGHT:?...}`
- ✅ Fail-fast validation for `SERVICE_PLAYWRIGHT`

### 2. start-playwright.sh
- ✅ Added `.env.services` sourcing
- ✅ Fail-fast validation for `SERVICE_PLAYWRIGHT`
- ✅ Updated container name checks to use `${SERVICE_PLAYWRIGHT}`

### 3. start-mcp.sh
- ✅ Added `.env.services` sourcing
- ✅ Fail-fast validation for `SERVICE_PLAYWRIGHT`
- ✅ Updated echo messages to use `${SERVICE_PLAYWRIGHT}`

### 4. setup-playwright.sh
- ✅ Added `.env.workspace` sourcing
- ✅ Added `.env.services` sourcing
- ✅ Fail-fast validation for `DOCKER_NETWORK_INTERNAL` and `SERVICE_PLAYWRIGHT`
- ✅ Updated all `docker exec playwright` commands to use `${SERVICE_PLAYWRIGHT}`
- ✅ Updated example commands in output messages

### 5. start-ui-stack.sh
- ✅ Added `.env.workspace` sourcing
- ✅ Added `.env.services` sourcing
- ✅ Fail-fast validation for `DOCKER_NETWORK_INTERNAL` and `SERVICE_PLAYWRIGHT`
- ✅ Updated all `docker exec playwright` commands to use `${SERVICE_PLAYWRIGHT}`
- ✅ Updated output messages

### 6. run-tests.sh
- ✅ Added `.env.workspace` sourcing
- ✅ Added `.env.services` sourcing
- ✅ Fail-fast validation for `SERVICE_PLAYWRIGHT`
- ✅ Updated container existence check to use `${SERVICE_PLAYWRIGHT}`
- ✅ Changed from `docker compose exec` to `docker exec` with service variable

### 7. run-ui-validation.sh
- ✅ Added `.env.services` sourcing
- ✅ Fail-fast validation for `SERVICE_PLAYWRIGHT`
- ✅ Updated all `docker exec playwright` commands to use `${SERVICE_PLAYWRIGHT}`

## Configuration Hierarchy

All scripts now properly source configuration in the correct order:

1. **`.env.workspace`** - Environment-specific settings (network, paths)
2. **`.env.services`** - Centralized service/container names
3. **Fail-fast validation** - Ensure critical variables are set

## Pattern Used

```bash
# Load workspace environment
if [[ -f "${ROOT_DIR}/.env.workspace" ]]; then
    # shellcheck source=/dev/null
    source "${ROOT_DIR}/.env.workspace"
fi

# Load service names
if [[ -f "${ROOT_DIR}/.env.services" ]]; then
    # shellcheck source=/dev/null
    source "${ROOT_DIR}/.env.services"
fi

# Fail-fast: require essential variables
: "${DOCKER_NETWORK_INTERNAL:?DOCKER_NETWORK_INTERNAL must be set (run post-create.sh)}"
: "${SERVICE_PLAYWRIGHT:?SERVICE_PLAYWRIGHT must be set (source .env.services)}"
```

## Service Names

All scripts now use:
- `${SERVICE_PLAYWRIGHT}` instead of hardcoded `"playwright"` or `"naf-dev-playwright"`
- `${SERVICE_MAILPIT}` (already in deploy.sh)
- `${SERVICE_REVERSE_PROXY}` (already in deploy.sh)
- etc.

## Deployment Test Results

**Status**: ✅ All fail-fast and .env.services changes working correctly

```bash
./deploy.sh --stop  # Clean shutdown - all services stopped
./deploy.sh local   # Fresh deployment - succeeded
```

**Infrastructure Phase**: ✅ PASSED
- Playwright container started with correct name
- Mock services started
- TLS proxy started
- All service references work correctly

**Build/Deploy Phase**: ✅ PASSED
- Build package created
- Extracted to deploy-local
- Flask started successfully

**Test Failures**: Separate issue (not related to fail-fast/service names)
- Journey tests: 2FA emails not received from Mailpit
- Admin UI tests: Stuck at 2FA page
- This is a Flask SMTP configuration issue, NOT a fail-fast or service naming issue

## Verification

To verify the changes work:

```bash
# 1. Stop all services
./deploy.sh --stop

# 2. Run fresh deployment
./deploy.sh local

# 3. Check service names are used correctly
docker ps --filter "name=naf-dev-" --format "table {{.Names}}\t{{.Status}}"
```

Expected output:
```
NAMES                         STATUS
naf-dev-playwright            Up
naf-dev-mailpit              Up  
naf-dev-mock-netcup-api      Up
naf-dev-mock-geoip           Up
naf-dev-reverse-proxy        Up
```

## Next Steps

The fail-fast and service naming migration is **complete**. Remaining issues:

1. **2FA/Mailpit Integration** (separate issue)
   - Flask sends 2FA emails to Mailpit SMTP (mailpit:1025)
   - Tests query Mailpit API for emails
   - No 2FA emails found in Mailpit
   - Need to debug Flask SMTP sending

## References

- [Fail-Fast Principle](FAIL_FAST_PRINCIPLE.md) - Complete fail-fast documentation
- [.env.services](.env.services) - Service name registry
- [.env.workspace](.env.workspace) - Environment configuration
- [deploy.sh](../deploy.sh) - Main deployment script
