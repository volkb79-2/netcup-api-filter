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
# Start all infrastructure
./deploy.sh local --mode mock --start-infra
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
│ Phase 4: Authentication                                     │
│   - Run auth test to change default password                 │
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

### Always Run (both modes)
- test_admin_ui.py
- test_api_proxy.py
- test_client_ui.py
- test_audit_logs.py
- test_config_pages.py
- test_ui_comprehensive.py
- test_ui_regression.py
- test_ui_ux_validation.py
- test_console_errors.py
- test_create_and_login.py
- test_isolated_sessions.py
- test_accessibility.py
- test_mobile_responsive.py
- test_performance.py
- test_security.py
- test_visual_regression.py
- test_user_journeys.py
- test_ui_functional.py
- test_ui_interactive.py
- test_bulk_operations.py
- test_audit_export.py
- test_recovery_codes.py
- test_registration_e2e.py

### Mock Mode Only
- test_mock_api_standalone.py
- test_e2e_with_mock_api.py
- test_client_scenarios_mock.py
- test_mock_smtp.py
- test_mock_geoip.py
- test_e2e_email.py
- test_ddns_quick_update.py

### Skip (broken/deprecated)
- test_ui_visual_regression.py.broken
- test_ui_ux_validation.py.broken
- test_e2e_dns.py.backup
- test_ui_comprehensive.py.backup

### Live API Required (run only with real Netcup API)
- test_e2e_dns.py
- test_end_to_end.py
- test_ui_flow_e2e.py
- test_api_security.py

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

# Start infrastructure without deploying
./deploy.sh local --infra-only

# Use HTTPS for local testing
./deploy.sh local --mode mock --https

# Clean shutdown of all services
./deploy.sh local --cleanup
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DEPLOYMENT_TARGET` | Target: local or webhosting | local |
| `DEPLOYMENT_MODE` | Mode: mock or live | mock (local), live (webhosting) |
| `USE_HTTPS` | Use TLS proxy for HTTPS | false |
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
