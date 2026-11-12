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

**Bulk actions, API security, registration negatives, DDNS protocols/quick update** - moved to the hermetic `tests/test_*_http.py` modules (S8).

### API and Security

**`test_api_proxy.py`** - DNS update API endpoints
- Token authentication
- Rate limiting enforcement
- Request validation

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

**`test_email_notifications.py`** - Email sending verification
- 2FA codes delivered
- Registration confirmation emails

### Mock Service Tests

**`test_mock_api_standalone.py`** - Netcup API mock server
- Domain listing, record CRUD
- Error simulation

Mailpit is the SMTP mock: delivery and 2FA-code extraction are covered by the feature and security
suites through `mailpit_client.py`.

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
# Complete production-parity local build and test cycle (recommended)
run-gate local-build (see run-gate.toml)

# Reuse deploy-local if it already exists
run-gate local-build (see run-gate.toml)
```

**Test Execution Order:**
1. **Journey Tests** (`test_journey_master.py`) - Establish fresh deployment baseline
2. **Validation Tests** (all others) - Verify all features on populated system
3. **Screenshot Capture** - Document all UI states for regression testing

### Individual Test Files

```bash
# Journey tests (fresh deployment)
pytest ui_tests/tests/test_journey_master.py -v

# User journeys (existing system)
pytest ui_tests/tests/test_user_journeys.py -v

# UI interactive tests
pytest ui_tests/tests/test_ui_interactive.py -v

# All validation tests
pytest ui_tests/tests -v --ignore=ui_tests/tests/test_journey_master.py
```

## Prerequisites

1. Install the test dependencies (this intentionally lives in a standalone file
   so production dependencies are untouched):
   ```bash
   pip install -r ui_tests/requirements.txt
   ```
2. Install Playwright browser binaries (in-process mode, the default):
   ```bash
   playwright install --with-deps chromium
   ```
   Skip this step if using a remote Playwright-as-a-Service container
   (`PLAYWRIGHT_SERVER_WS=ws://<service>:3000/`).
3. Export any environment overrides before running the suite. Defaults cover
   the current deployment documented in `AGENTS.md`.

## Local validation

The app, mocks and browser all run as ciu stacks; the lanes run inside the 3.11 test-runner.
The sequence is documented at the top of `run-gate.toml` (`run-gate local-build`, then
`run-gate e2e`). Point a remote Playwright service with `PLAYWRIGHT_SERVER_WS=ws://<service-name>:3000/`.

## Running the suite

```bash
# All tests (in-process browser, default)
pytest ui_tests/tests -q

# Specific test file
pytest ui_tests/tests/test_ui_functional.py -v

# Specific test class
pytest ui_tests/tests/test_ui_functional.py::TestThemeAndCSS -v

# Remote browser (Playwright-as-a-Service)
PLAYWRIGHT_SERVER_WS=ws://pwmcp:3000/ pytest ui_tests/tests -q   # the estate pwmcp on PWMCP_NETWORK
```

Screenshots are saved to `SCREENSHOT_DIR` (default: `E2E_SCREENSHOT_DIR` in `.env.defaults`, `tmp/e2e-screenshots`). Every session starts its own app on a copy of the golden DB with random personas; see `docs/TESTING_INFRASTRUCTURE.md`.

## Test Organization

```
ui_tests/
├── browser.py                        # Playwright browser wrapper
├── config.py                         # settings, bound per session to the instance + personas
├── conftest.py                       # Pytest fixtures (session app instance, browser, auth)
├── e2e_env.py                        # Per-session throwaway app on a copy of the golden DB
├── personas.py                       # Random per-session admin/user/read-only personas
├── workflows.py                      # Reusable test workflows
├── mailpit_client.py                 # Email verification helper
├── parallel_session_manager.py       # Multi-browser orchestration
├── playwright_client.py              # MCP server client
├── capture_ui_screenshots.py         # Automated screenshot capture
├── mock_netcup_api.py                # Netcup CCP API mock server
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
│   ├── test_api_proxy.py             # DNS update API
│   ├── test_security.py              # Auth/session management
│   ├── test_recovery_codes.py        # 2FA recovery
│   ├── test_registration_e2e.py      # Registration workflow
│   ├── test_email_notifications.py   # Email delivery
│   ├── test_performance.py           # Load times
│   ├── test_accessibility.py         # WCAG compliance
│   ├── test_mobile_responsive.py     # Mobile layouts
│   ├── test_console_errors.py        # JavaScript errors
│   ├── test_mock_api_standalone.py   # Mock API verification
│   ├── test_live_dns_verification.py # Real DNS (requires creds)
│   ├── test_live_email_verification.py # Real email (requires creds)
│   └── test_holistic_coverage.py     # Integration smoke test
└── requirements.txt                  # Test dependencies
```

## asyncio.sleep - Replacement Patterns

### Pattern 1: Navigation Waits

**❌ Before:**
```python
await browser.goto(url)
await asyncio.sleep(0.3)
await browser.fill("#field", "value")
```

**✅ After:**
```python
await browser.goto(url)
await browser._page.wait_for_load_state('domcontentloaded')
await browser.fill("#field", "value")
```

### Pattern 2: Form Submission Waits

**❌ Before:**
```python
await browser.click("button[type='submit']")
await asyncio.sleep(1.0)
# Check result
```

**✅ After:**
```python
async with browser._page.expect_navigation(wait_until="networkidle", timeout=10000):
    await browser.click("button[type='submit']")
# Check result
```

### Pattern 3: Client-Side Validation Waits

**❌ Before:**
```python
await browser.fill("#password", password)
await browser.evaluate("document.getElementById('password').dispatchEvent(new Event('input'))")
await asyncio.sleep(0.5)
await browser.click("#submit")
```

**✅ After:**
```python
await browser.fill("#password", password)
await browser.evaluate("document.getElementById('password').dispatchEvent(new Event('input'))")
await browser._page.wait_for_function(
    "document.getElementById('submit') && !document.getElementById('submit').disabled",
    timeout=5000
)
await browser.click("#submit")
```

### Pattern 4: Polling for URL Change

**❌ Before:**
```python
for _ in range(20):
    await asyncio.sleep(0.5)
    if browser._page.url != original_url:
        break
else:
    raise AssertionError("Navigation timeout")
```

**✅ After:**
```python
try:
    await browser._page.wait_for_url(
        lambda url: url != original_url,
        timeout=10000
    )
except Exception as e:
    raise AssertionError("Navigation timeout") from e
```

### Pattern 5: Dropdown/Menu Opens

**❌ Before:**
```python
await dropdown.click()
await asyncio.sleep(0.3)
# Check dropdown is open
```

**✅ After:**
```python
await dropdown.click()
await browser._page.wait_for_selector('.dropdown-menu.show', timeout=5000)
# Dropdown is now open
```

### Pattern 6: Element Appears After Action

**❌ Before:**
```python
await browser.click("#trigger")
await asyncio.sleep(0.5)
element = await browser.query_selector("#result")
```

**✅ After:**
```python
await browser.click("#trigger")
element = await browser._page.wait_for_selector("#result", timeout=5000)
```

## Why This Matters

### Benefits of Proper Waits

1. **Speed**: Tests run faster (no arbitrary waits)
2. **Reliability**: No race conditions or flakiness
3. **Clarity**: Intent is explicit (waiting for specific condition)
4. **Debugging**: Failures provide actionable information

### Problems with asyncio.sleep()

1. **Arbitrary**: 0.5 seconds might be too short on slow systems, too long on fast ones
2. **Masks Issues**: Hides race conditions and timing bugs
3. **Slow**: Wastes time waiting even when condition is already met
4. **Flaky**: Tests pass/fail randomly based on system load
