# UI Testing Suite

Automated UI coverage using a multi-layer testing strategy:

## Test Files Overview

### Journey Tests (Fresh Deployment)

**`test_journey_master.py`** - End-to-end workflows on fresh database
- Bootstrap system from default credentials
- Complete account registration lifecycle  
- Populate comprehensive test states (clients, tokens, domains)
- Generate journey report (journey_report.json)
- **Run first** on new deployments to establish baseline

### User Journeys (Existing System)

**`test_user_journeys.py`** - Workflows on populated system
- Account management (CRUD operations)
- Configuration reviews (Netcup API, Email, System Info)
- Audit log workflows (filtering, export, auto-refresh)
- Password changes and theme customization
- Dashboard statistics and quick actions
- **Run after** journey tests when data exists

### Core UI Validation

**`test_ui_interactive.py`** - Interactive elements and CSS
- JavaScript behavior (password toggle, entropy, generate button)
- CSS variable validation (themes, density)
- Navigation consistency matrix (navbar, footer, logout)
- No stale breadcrumbs or H1 icons

**`test_ui_comprehensive.py`** - Complete admin workflows
- Full CRUD operations on all admin pages
- Form validation and error handling
- Multi-step processes (approval, bulk operations)

**`test_ui_functional.py`** - JavaScript and CSS integration
- Theme switching without reload
- Dynamic form validation
- Client-side password strength checks

**`test_ui_ux_validation.py`** - Page structure validation
- Required elements present on all pages
- Consistent navigation structure
- Proper heading hierarchy

**`test_ui_regression.py`** - Visual regression testing
- Screenshot comparison against baselines
- Detect unintended layout changes

### Admin Feature Tests

**`test_admin_ui.py`** - Admin-specific functionality
- Dashboard statistics and quick actions
- Account management workflows
- System configuration pages

**`test_config_pages.py`** - Configuration management
- Netcup API settings
- Email/SMTP configuration
- System information display

**`test_audit_logs.py`** - Audit log functionality
- Filtering by time, status, action
- Pagination and auto-refresh

**`test_audit_export.py`** - ODS export workflow
- Export audit logs to spreadsheet format

**`test_bulk_operations.py`** - Bulk actions on accounts/clients
- Multi-select and bulk approve/delete

### API and Security

**`test_api_proxy.py`** - DNS update API endpoints
- Token authentication
- Rate limiting enforcement
- Request validation

**`test_api_security.py`** - Security hardening
- CSRF protection
- SQL injection prevention
- XSS protection

**`test_security.py`** - Authentication and authorization
- Login workflows (admin + client)
- 2FA enforcement
- Session management

**`test_recovery_codes.py`** - 2FA recovery codes
- Generation, download, regeneration

### Registration Flows

**`test_registration_e2e.py`** - Complete registration workflow
- Form submission with email verification
- 2FA setup on first login

**`test_registration_negative.py`** - Registration error cases
- Invalid email formats
- Password validation failures
- Duplicate username detection

**`test_email_notifications.py`** - Email sending verification
- 2FA codes delivered
- Registration confirmation emails

### Mock Service Tests

**`test_mock_api_standalone.py`** - Netcup API mock server
- Domain listing, record CRUD
- Error simulation

**`test_mock_smtp.py`** - Mailpit SMTP mock
- Email delivery to test inbox
- 2FA code extraction

**`test_mock_geoip.py`** - GeoIP API mock
- IP geolocation lookups

### Quick Update Tests

**`test_ddns_quick_update.py`** - Rapid DNS update workflow
- Single-hostname IP updates (DDNS use case)
- Minimal latency validation

### Performance and Accessibility

**`test_performance.py`** - Load time and responsiveness
- Page load under 2s
- API response times

**`test_accessibility.py`** - WCAG compliance
- ARIA labels, keyboard navigation
- Screen reader compatibility

**`test_mobile_responsive.py`** - Mobile viewport testing
- Layout adapts to small screens
- Touch-friendly controls

**`test_console_errors.py`** - JavaScript error detection
- No console errors on page load
- No unhandled promise rejections

### Integration Verification

**`test_live_dns_verification.py`** - Real DNS record updates (requires live credentials)
**`test_live_email_verification.py`** - Real email sending (requires SMTP credentials)
**`test_holistic_coverage.py`** - System-wide integration smoke test

## Running Tests

### Full Deployment Test Suite

```bash
# Complete build, deploy, test cycle (recommended)
./deploy.sh local

# Skip build if deploy-local already exists
./deploy.sh local --tests-only
```

**Test Execution Order:**
1. **Journey Tests** (`test_journey_master.py`) - Establish fresh deployment baseline
2. **Validation Tests** (all others) - Verify all features on populated system
3. **Screenshot Capture** - Document all UI states for regression testing

### Individual Test Files

```bash
# Journey tests (fresh deployment)
docker exec naf-playwright pytest ui_tests/tests/test_journey_master.py -v

# User journeys (existing system)
docker exec naf-playwright pytest ui_tests/tests/test_user_journeys.py -v

# UI interactive tests
docker exec naf-playwright pytest ui_tests/tests/test_ui_interactive.py -v

# All validation tests
docker exec naf-playwright pytest ui_tests/tests -v --ignore=ui_tests/tests/test_journey_master.py
```

## Prerequisites

1. Start the Playwright container:
   ```bash
   cd tooling/playwright
   docker compose up -d
   ```
2. Install the test dependencies (this intentionally lives in a standalone file
   so production dependencies are untouched):
   ```bash
   pip install -r ui_tests/requirements.txt
   ```
3. Export any environment overrides before running the suite. Defaults cover
   the current deployment documented in `AGENTS.md`.

## One-command local validation

When you need to spin up the seeded backend, TLS proxy, Playwright container,
and the pytest suite in one go, run `tooling/run-ui-validation.sh` from the
repository root. The script will:

- Render/stage the nginx config and cert bundle under `/tmp/netcup-local-proxy`.
- Start gunicorn on port `LOCAL_APP_PORT` (default 5100) with a seeded SQLite
   database inside `tmp/local-netcup.db`.
- Launch the nginx proxy + Playwright container via docker compose.
- Install `ui_tests/requirements.txt` (skip via `SKIP_UI_TEST_DEPS=1`).
- Export sensible defaults for `UI_BASE_URL` (`https://<host-gateway>:443`).
- Execute `pytest ui_tests/tests -vv` inside the Playwright container and tear everything down afterwards.

Override `UI_BASE_URL`, `PLAYWRIGHT_HEADLESS`, `UI_ADMIN_PASSWORD`, and similar
variables before running the helper if you need to target a different host or
credentials.

| Variable | Default | Purpose |
| --- | --- | --- |
| `UI_BASE_URL` | `https://naf.vxxu.de` | Target deployment root |
| `UI_ADMIN_USERNAME` | `admin` | Admin login |
| `UI_ADMIN_PASSWORD` | `admin` | Current admin password |
| `UI_ADMIN_NEW_PASSWORD` | _(unset)_ | Provide if the server still forces password rotation |
| `UI_CLIENT_ID` | `test_qweqweqwe_vi` | Expected client row in the admin UI |
| `UI_CLIENT_TOKEN` | `qweqweqwe-vi-readonly` | Token for the client portal |
| `UI_CLIENT_DOMAIN` | `qweqweqwe.vi` | Domain shown for the seeded token |
| `UI_SCREENSHOT_PREFIX` | `ui-regression` | Prefix when capturing screenshots |
| `UI_ALLOW_WRITES` | `1` | Set to `0` to skip destructive admin flows |
| `UI_SMOKE_BASE_URL` | _(unset)_ | Optional second target (e.g., production host) |
| `UI_SMOKE_ALLOW_WRITES` | `0` | Controls whether smoke profile may perform writes |
| `UI_SMOKE_ADMIN_*` etc. | inherit primary | Override credentials/domain for smoke profile |

When `UI_SMOKE_BASE_URL` is provided, each test parametrizes over both the
primary (usually local) environment and the smoke target, automatically
reusing credentials unless the `UI_SMOKE_*` overrides are supplied. Write-heavy
flows (client creation, Netcup config saves, etc.) automatically skip any
profile that sets `*_ALLOW_WRITES=0`, allowing safe read-only validation
against production.

## Running the suite

```bash
# All tests
docker exec playwright pytest /workspaces/netcup-api-filter/ui_tests/tests -q

# Specific test file
docker exec playwright pytest /workspaces/netcup-api-filter/ui_tests/tests/test_ui_functional.py -v

# Specific test class
docker exec playwright pytest /workspaces/netcup-api-filter/ui_tests/tests/test_ui_functional.py::TestThemeAndCSS -v
```

Screenshots stay inside the Playwright container under `/screenshots`; copy any
artifacts out with `docker cp playwright:/screenshots/<file> ./screenshots/`
if you need to attach them to an issue or PR.

## Test Organization

```
ui_tests/
├── browser.py                        # Playwright browser wrapper
├── config.py                         # Test configuration from environment
├── conftest.py                       # Pytest fixtures (browser, auth)
├── workflows.py                      # Reusable test workflows
├── deployment_state.py               # Track deployment credentials
├── mailpit_client.py                 # Email verification helper
├── parallel_session_manager.py       # Multi-browser orchestration
├── playwright_client.py              # MCP server client
├── capture_ui_screenshots.py         # Automated screenshot capture
├── analyze_ui_screenshots.py         # Screenshot diff analysis
├── mock_netcup_api.py                # Netcup CCP API mock server
├── mock_smtp_server.py               # SMTP testing server
├── mock_geoip_server.py              # GeoIP lookup mock
├── tests/
│   ├── journeys/
│   │   └── (journey test modules)    # Imported by test_journey_master.py
│   ├── test_journey_master.py        # Fresh deployment workflows
│   ├── test_user_journeys.py         # Existing system workflows
│   ├── test_ui_interactive.py        # JS/CSS/Navigation
│   ├── test_ui_comprehensive.py      # Full admin workflows
│   ├── test_ui_functional.py         # Theme/form validation
│   ├── test_ui_ux_validation.py      # Page structure
│   ├── test_ui_regression.py         # Visual regression
│   ├── test_admin_ui.py              # Admin features
│   ├── test_config_pages.py          # Configuration management
│   ├── test_audit_logs.py            # Audit functionality
│   ├── test_audit_export.py          # ODS export
│   ├── test_bulk_operations.py       # Bulk actions
│   ├── test_api_proxy.py             # DNS update API
│   ├── test_api_security.py          # API security
│   ├── test_security.py              # Auth/session management
│   ├── test_recovery_codes.py        # 2FA recovery
│   ├── test_registration_e2e.py      # Registration workflow
│   ├── test_registration_negative.py # Registration errors
│   ├── test_email_notifications.py   # Email delivery
│   ├── test_ddns_quick_update.py     # Rapid DNS updates
│   ├── test_performance.py           # Load times
│   ├── test_accessibility.py         # WCAG compliance
│   ├── test_mobile_responsive.py     # Mobile layouts
│   ├── test_console_errors.py        # JavaScript errors
│   ├── test_mock_api_standalone.py   # Mock API verification
│   ├── test_mock_smtp.py             # Mock SMTP verification
│   ├── test_mock_geoip.py            # Mock GeoIP verification
│   ├── test_live_dns_verification.py # Real DNS (requires creds)
│   ├── test_live_email_verification.py # Real email (requires creds)
│   └── test_holistic_coverage.py     # Integration smoke test
└── requirements.txt                  # Test dependencies
```
