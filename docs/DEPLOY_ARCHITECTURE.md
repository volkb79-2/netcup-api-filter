# Deploy Script Architecture

## Overview

The deployment system supports two targets and two modes:

### Targets
- **local** - Deploy to `deploy-local/` directory
- **webhosting** - Deploy to production webhosting server

### Modes (NEW)
- **mock** - Uses mocked external services (default for local)
  - Mock Netcup API server
  - Mock SMTP server (Mailpit)
  - Mock GeoIP server
  - Runs full test suite including mock-dependent tests
  
- **live** - Uses real external services (default for webhosting)
  - Real Netcup API (from config)
  - Real SMTP server (from config)
  - Real GeoIP database
  - Runs only non-mock tests

## Infrastructure Requirements

Before deployment, the following services must be running:

### For Local Mock Mode
```bash
# Infrastructure starts automatically as Phase 0 (use --skip-infra to reuse running services)
./deploy.sh local --mode mock
```

This starts:
1. **Playwright container** - For browser automation tests
2. **TLS proxy** - nginx with Let's Encrypt certs for HTTPS testing
3. **Mock services** - Mailpit, Mock Netcup API, Mock GeoIP

### For Webhosting/Live Mode
```bash
# Just Playwright for screenshot capture
./deploy.sh webhosting
```

## Phase Order

```
┌─────────────────────────────────────────────────────────────┐
│ Phase 0: Infrastructure Setup (NEW)                         │
│   - Start Playwright container                               │
│   - Start TLS proxy (local mode with HTTPS)                  │
│   - Start mock services (mock mode only)                     │
│   - Wait for all services to be healthy                      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ Phase 1: Build                                              │
│   - Run build_deployment.py                                  │
│   - Create deploy.zip with fresh database                    │
│   - Generate deployment_state.json with client credentials   │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ Phase 2: Deploy                                             │
│   - Extract deploy.zip (local) or upload to server          │
│   - Mount SSHFS for webhosting access                        │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ Phase 3: Start Application                                  │
│   - Start Flask/gunicorn (local)                             │
│   - Or restart Passenger (webhosting)                        │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ Phase 4: Journey Tests (Fresh Deployment)                   │
│   - Run journey tests (test_journey_master.py) on fresh DB   │
│   - Authentication / mandatory password change is folded in  │
│   - Update deployment_state.json with new password           │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ Phase 5: Tests                                              │
│   - Run ALL applicable test suites via Playwright container  │
│   - Mock-only tests run only in mock mode                    │
│   - Tests use HTTPS via TLS proxy (production parity)        │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ Phase 6: Screenshots                                        │
│   - Capture ALL UI pages (admin + client portal)             │
│   - Read client credentials from deployment_state.json       │
│   - Save to deploy-local/screenshots/                        │
└─────────────────────────────────────────────────────────────┘
```

## Test Categorization

> **Note**: the authoritative suite list is maintained in `deploy.sh`. The snapshot below
> reflects the post-hardening (E1–E4, 2026-06-14) bucket layout. For the full current list,
> read `deploy.sh` directly.

### Always Run (both modes)

`ui_tests/tests/` is now organized into named bucket subdirectories. The `-m <marker>` flag
selects any bucket regardless of path.

- `smoke/test_route_smoke.py` — 86 route-smoke tests (auto-discovered from Flask URL map)
- `smoke/test_ui_widgets.py` — widget smoke
- `smoke/test_admin_ui.py` — admin UI smoke
- `smoke/test_backends_ui.py` — backends UI smoke
- `features/test_audit_logs.py`, `test_audit_export.py`, `test_config_pages.py`, `test_bulk_operations.py`
- `security/` — auth, 2FA, recovery codes, IP allowlist (all files)
- `roundtrip/test_cross_role_account_lifecycle.py`, `test_cross_role_realm_propagation.py`, `test_cross_role_token_lifecycle.py`
- `nonfunctional/test_accessibility.py`, `test_performance.py`

### Mock Mode Only
- `mocks/test_mock_api_standalone.py`
- `mocks/test_mock_smtp.py`
- `mocks/test_mock_geoip.py`
- `roundtrip/test_ddns_quick_update.py`
- `roundtrip/test_api_dns_crud_success_with_mock_backend.py`
- `roundtrip/test_admin_security_api_contracts.py`
- `features/test_ddns_protocols.py`

## Usage Examples

```bash
# Full local deployment with mocks (recommended for development)
./deploy.sh local --mode mock

# Local deployment without tests (manual testing)
./deploy.sh local --skip-tests

# Production deployment
./deploy.sh webhosting

# Re-run tests only (skip build/deploy)
./deploy.sh local --tests-only

# Reuse already-running infrastructure (skip Phase 0)
./deploy.sh local --skip-infra

# HTTPS is the default for local; opt out with --http
./deploy.sh local --mode mock --http

# Clean shutdown of all services
./deploy.sh --stop
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DEPLOYMENT_TARGET` | Target: local or webhosting | local |
| `DEPLOYMENT_MODE` | Mode: mock or live | mock (local), live (webhosting) |
| `USE_HTTPS` | Use TLS proxy for HTTPS (HTTPS is the default for local; `--http` sets this to false) | true |
| `SKIP_INFRA` | Don't start infrastructure | false |
| `SKIP_TESTS` | Don't run tests | false |
| `SKIP_SCREENSHOTS` | Don't capture screenshots | false |

## Files Modified

### deployment_state_{target}.json
Single source of truth for credentials, now includes full client data:
```json
{
  "target": "local",
  "admin": { "username": "admin", "password": "..." },
  "clients": [
    { "client_id": "demo-user", "secret_key": "naf_...", "description": "..." }
  ]
}
```

### build_info.json (CHANGED)
Now includes demo_clients array for screenshot capture:
```json
{
  "demo_clients": [
    { "client_id": "demo-user", "token": "demo-user:naf_...", "description": "..." }
  ]
}
```
