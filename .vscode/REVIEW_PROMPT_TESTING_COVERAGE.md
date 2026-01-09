# Deep Dive Review: Testing Architecture & Coverage

## Context

The project implements a comprehensive multi-layer testing strategy:
- **Unit tests**: Model validation, business logic, utilities
- **Integration tests**: Database interactions, API endpoints
- **UI tests**: Playwright browser automation (28 interactive + 15 journey tests)
- **Journey tests**: End-to-end user workflows with contracts
- **Local deployment tests**: Production parity testing
- **HTTPS tests**: Real Let's Encrypt certificates with TLS proxy
- **Screenshot tests**: Visual regression and UI validation

## Review Objective

Verify that the testing strategy is:
1. **Comprehensive** - All critical paths covered
2. **Reliable** - Tests pass consistently, no flakiness
3. **Maintainable** - Clear contracts, well-documented
4. **Production-equivalent** - Tests match real deployment
5. **Fast** - Can run frequently during development

## Review Checklist

### 1. Test Coverage Analysis

**Files:** `pytest.ini`, `ui_tests/`, `tooling/`

#### Code Coverage
- [ ] **Coverage measurement**: pytest-cov configured
- [ ] **Target coverage**: 80%+ code coverage
- [ ] **Critical paths**: 100% coverage for auth, token validation
- [ ] **Exclusions**: Test files, migrations excluded from coverage
- [ ] **Reports**: HTML coverage reports generated

**Test:**
```bash
# Run with coverage
pytest --cov=src/netcup_api_filter --cov-report=html
# Check coverage report
open htmlcov/index.html
```

#### Route Coverage
- [ ] **All endpoints tested**: Every Flask route has test
- [ ] **HTTP methods**: GET, POST, PUT, DELETE all tested
- [ ] **Auth paths**: Authenticated and unauthenticated tested
- [ ] **Error paths**: 4xx and 5xx responses tested

**Verify against:** `docs/ROUTE_COVERAGE.md`

#### UI Coverage
- [ ] **Admin pages**: All admin UI pages tested (dashboard, accounts, realms, tokens, settings, audit logs)
- [ ] **Account portal**: Registration, login, 2FA, password change
- [ ] **Interactive elements**: Forms, buttons, dropdowns, modals
- [ ] **CSS validation**: Theme variables, dark mode tested
- [ ] **JavaScript**: Password toggle, entropy, form validation

### 2. Test Organization & Structure

**Directory structure**

```
ui_tests/
├── tests/
│   ├── test_ui_interactive.py    # 28 tests - JS, CSS, navigation
│   ├── test_user_journeys.py     # 15 tests - end-to-end workflows
│   ├── test_api_security.py      # API auth tests
│   ├── test_ddns_protocols.py    # DDNS endpoint tests
│   └── conftest.py               # Shared fixtures
├── journeys/
│   ├── test_01_admin_setup.py    # Admin initial setup
│   ├── test_02_backend_config.py # Backend configuration
│   ├── test_03_user_registration.py
│   ├── test_04_realm_management.py
│   ├── test_05_api_usage.py      # API testing
│   └── conftest.py
└── capture_ui_screenshots.py     # Screenshot automation
```

- [ ] **Logical grouping**: Tests grouped by feature area
- [ ] **Naming conventions**: `test_*.py` files, `test_*()` functions
- [ ] **Fixtures**: Shared setup in `conftest.py`
- [ ] **Markers**: pytest markers for test categories (smoke, integration, e2e)
- [ ] **Parallel execution**: Tests can run in parallel (pytest-xdist)

### 3. Test Fixtures & Setup

**Files:** `ui_tests/tests/conftest.py`, `ui_tests/journeys/conftest.py`

#### Playwright Fixtures
- [ ] **Browser fixture**: Shared browser instance
- [ ] **Page fixture**: New page per test (isolation)
- [ ] **Context fixture**: Handles cookies, storage
- [ ] **Base URL fixture**: Configurable via UI_BASE_URL
- [ ] **Timeout fixture**: Configurable test timeouts
- [ ] **Screenshot on failure**: Automatic screenshot capture

#### Database Fixtures
- [ ] **Fresh database**: Each test suite gets clean DB
- [ ] **Seeded data**: Admin account, test client preseeded
- [ ] **Transaction rollback**: Tests rollback changes (or use fresh DB)
- [ ] **Isolation**: Tests don't interfere with each other

#### Authentication Fixtures
- [ ] **Admin login**: Reusable admin session fixture
- [ ] **Account login**: Reusable account session fixture
- [ ] **API token**: Bearer token fixture for API tests
- [ ] **2FA handling**: TOTP generation for 2FA tests

**Example fixture:**
```python
@pytest.fixture
async def admin_session(page, base_url):
    """Authenticated admin session."""
    await page.goto(f"{base_url}/admin/login")
    await page.fill('input[name="username"]', "admin")
    await page.fill('input[name="password"]', "admin")
    await page.click('button[type="submit"]')
    await page.wait_for_url(f"{base_url}/admin/dashboard")
    yield page
```

### 4. Journey Test Contracts

**Files:** `docs/JOURNEY_CONTRACTS.md`, `ui_tests/journeys/test_*.py`

- [ ] **Contract definition**: Each journey has documented contract
- [ ] **Prerequisites**: Required state before journey starts
- [ ] **Postconditions**: Expected state after journey completes
- [ ] **Error scenarios**: Failure paths tested
- [ ] **State verification**: Database state checked at end
- [ ] **Idempotency**: Journeys can run multiple times
- [ ] **Dependency chain**: Journey dependencies documented

**Journey workflow:**
1. Admin Setup (creates admin, changes password)
2. Backend Config (configures Netcup/PowerDNS)
3. User Registration (creates account, verifies email)
4. Realm Management (creates realm, generates token)
5. API Usage (uses token to update DNS)

- [ ] **Each journey verifies previous**: Journey 2 assumes Journey 1 completed

### 5. Playwright Test Patterns

**Files:** `ui_tests/tests/test_ui_interactive.py`, `ui_tests/tests/test_user_journeys.py`

#### Best Practices (from TESTING_LESSONS_LEARNED.md)
- [ ] **Live URL detection**: Always use `page.url` (not cached `current_url`)
- [ ] **2FA form submission**: Use JavaScript `form.submit()` to avoid race conditions
- [ ] **Session detection**: Check for active session before attempting login
- [ ] **Wait strategies**: Use `page.wait_for_selector()`, not fixed sleeps
- [ ] **Error screenshots**: Capture screenshot before assertion fails
- [ ] **Explicit waits**: Wait for network idle, load state

#### Anti-Patterns to Avoid
- [ ] **No `time.sleep()`**: Use proper waits instead
- [ ] **No cached URLs**: Always get current URL from page
- [ ] **No auto-submit reliance**: Explicit form submission
- [ ] **No brittle selectors**: Use stable selectors (IDs, data attributes)

**Example pattern:**
```python
async def test_login_with_2fa(page, base_url):
    """Test login with 2FA enforcement."""
    
    # Navigate and fill form
    await page.goto(f"{base_url}/admin/login")
    await page.fill('input[name="username"]', "admin")
    await page.fill('input[name="password"]', "admin")
    await page.click('button[type="submit"]')
    
    # Wait for 2FA page (explicit wait)
    await page.wait_for_selector('input[name="totp_code"]', timeout=5000)
    
    # Generate TOTP
    totp_code = generate_totp(totp_secret)
    await page.fill('input[name="totp_code"]', totp_code)
    
    # Submit via JavaScript (avoid race condition)
    await page.evaluate('document.querySelector("form").submit()')
    
    # Verify redirect (use live URL)
    await page.wait_for_url(f"{base_url}/admin/dashboard", timeout=5000)
    assert "/admin/dashboard" in page.url
```

### 6. Local Deployment Testing

**Files:** `run-local-tests.sh`, `build-and-deploy-local.sh`

#### Production Parity
- [ ] **Same deployment package**: Uses `build_deployment.py`
- [ ] **Same directory structure**: `deploy-local/` mirrors production
- [ ] **Same entry point**: `passenger_wsgi.py:application`
- [ ] **Same database**: SQLite with preseeded data
- [ ] **Same config**: `.env.defaults` applied

#### Test Workflow
- [ ] **Build**: Runs `build_deployment.py --local`
- [ ] **Extract**: Unpacks `deploy.zip` to `deploy-local/`
- [ ] **Start Flask**: Runs Flask on port 5100
- [ ] **Run tests**: Executes 90-test suite
- [ ] **Cleanup**: Kills Flask automatically

**Test:**
```bash
# Full test run (build + deploy + test + cleanup)
./run-local-tests.sh

# Expected output:
# - Build phase: Creates deploy.zip
# - Deploy phase: Extracts to deploy-local/
# - Flask starts on port 5100
# - 90 tests run (27 UI + 10 admin + 4 client + 8 API + ...)
# - All pass
# - Flask killed, cleanup done
```

### 7. HTTPS Testing with Let's Encrypt

**Files:** `tooling/reverse-proxy/`, `test-https-deployment.sh`

#### TLS Proxy Setup
- [ ] **nginx container**: Configured with Let's Encrypt certs
- [ ] **Certificate mounting**: Certs from `/etc/letsencrypt/` mounted
- [ ] **TLS termination**: nginx terminates TLS, forwards to Flask
- [ ] **X-Forwarded-Proto**: Flask sees HTTPS protocol
- [ ] **Secure cookies**: Session cookies work with Secure=True

#### HTTPS Test Coverage
- [ ] **Certificate validation**: Browsers accept cert without warnings
- [ ] **TLS version**: Only TLS 1.2+ accepted
- [ ] **Cipher suites**: Strong ciphers only
- [ ] **HSTS headers**: Strict-Transport-Security present
- [ ] **Secure cookies**: Cookies set with Secure flag

**Test:**
```bash
# Start HTTPS proxy
cd tooling/reverse-proxy
./render-nginx-conf.sh && ./stage-proxy-inputs.sh
docker compose --env-file proxy.env up -d

# Run tests against HTTPS endpoint
FQDN=$(grep LOCAL_TLS_DOMAIN proxy.env | cut -d= -f2)
UI_BASE_URL="https://$FQDN" pytest ui_tests/tests -v

# Verify TLS
curl -v https://$FQDN/ 2>&1 | grep "SSL certificate verify ok"
```

### 8. API Testing

**Files:** `ui_tests/tests/test_api_security.py`, `ui_tests/journeys/test_05_api_usage.py`

#### Authentication Tests
- [ ] **Bearer token validation**: Valid tokens accepted
- [ ] **Invalid tokens rejected**: Malformed tokens return 401
- [ ] **Expired tokens rejected**: Past expiration returns 401
- [ ] **Missing tokens rejected**: No Authorization header returns 401
- [ ] **Disabled tokens rejected**: Inactive tokens return 401

#### Authorization Tests
- [ ] **Realm enforcement**: Out-of-realm requests denied
- [ ] **Record type filtering**: Disallowed types denied
- [ ] **Operation filtering**: Disallowed operations denied
- [ ] **IP whitelisting**: Out-of-range IPs denied

#### Error Response Tests
- [ ] **Consistent error format**: All errors use same JSON structure
- [ ] **Appropriate status codes**: 401/403/404/429/500 correctly used
- [ ] **No information leakage**: Error messages don't expose internals

**Test pattern:**
```python
async def test_api_auth_invalid_token():
    """Invalid token returns 401."""
    response = await client.get(
        "/api/dns/test.com/records",
        headers={"Authorization": "Bearer invalid-token"}
    )
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"
```

### 9. DDNS Protocol Tests

**Files:** `ui_tests/tests/test_ddns_protocols.py`

#### DynDNS2 Protocol
- [ ] **Update endpoint**: `/api/ddns/dyndns2/update` works
- [ ] **Response codes**: good, nochg, badauth, !yours, notfqdn, dnserr, 911
- [ ] **IP detection**: Auto-detects client IP
- [ ] **IPv6 support**: Handles AAAA records
- [ ] **Bearer auth**: Only bearer token (no Basic auth)

#### No-IP Protocol
- [ ] **Update endpoint**: `/api/ddns/noip/update` works
- [ ] **Response codes**: good, nochg, nohost, abuse, dnserr, 911
- [ ] **Protocol compliance**: Matches No-IP spec

#### Security Tests
- [ ] **No username/password**: Query params ignored
- [ ] **Realm authorization**: Domain access enforced
- [ ] **Rate limiting**: Rapid requests rate limited
- [ ] **Activity logging**: All updates logged

### 10. Screenshot Testing

**Files:** `ui_tests/capture_ui_screenshots.py`, `deploy-local/screenshots/`

#### Screenshot Coverage
- [ ] **All admin pages**: Dashboard, accounts, realms, tokens, settings, audit logs
- [ ] **Account portal**: Login, registration, dashboard, profile
- [ ] **Dark mode**: All pages in dark theme
- [ ] **Light mode**: All pages in light theme
- [ ] **Error pages**: 404, 500 error pages
- [ ] **Modals**: Dialogs, confirmations captured

#### Visual Regression
- [ ] **Baseline images**: Reference screenshots stored
- [ ] **Comparison**: New screenshots compared to baseline
- [ ] **Diff detection**: Pixel differences highlighted
- [ ] **Threshold**: Acceptable difference threshold configured
- [ ] **Font rendering**: Consistent fonts (fonts-noto-color-emoji)

**Test:**
```bash
# Capture screenshots
./tooling/playwright/playwright-exec.sh python3 ui_tests/capture_ui_screenshots.py

# Screenshots saved to deploy-local/screenshots/
ls -l deploy-local/screenshots/
# Should show: admin_dashboard.png, admin_accounts.png, ...
```

### 11. Test Isolation & Parallel Execution

**Parallelization strategy**

- [ ] **pytest-xdist**: Tests can run in parallel
- [ ] **Database isolation**: Each worker gets own DB or uses transactions
- [ ] **Port allocation**: Dynamic port allocation for parallel Flask instances
- [ ] **No shared state**: Tests don't depend on global state
- [ ] **Cleanup**: Each test cleans up after itself

**Test:**
```bash
# Run tests in parallel (4 workers)
pytest ui_tests/tests -n 4

# Should complete faster, all pass
```

### 12. Mock Services

**Files:** `tooling/netcup-api-mock/`, `tooling/geoip-mock/`, `tooling/mailpit/`

#### Netcup API Mock
- [ ] **API operations**: infoDnsZone, infoDnsRecords, updateDnsRecords
- [ ] **Response format**: Matches real Netcup API
- [ ] **Error simulation**: Can simulate API errors
- [ ] **Latency simulation**: Can add artificial delays
- [ ] **Session handling**: Handles sessionId correctly

#### GeoIP Mock
- [ ] **IP lookups**: Returns mock location data
- [ ] **ASN lookups**: Returns mock ASN info
- [ ] **Fallback**: Falls back to "Unknown" when needed

#### Mailpit (SMTP Mock)
- [ ] **SMTP capture**: Captures all outbound emails
- [ ] **Web UI**: Browse captured emails
- [ ] **API**: Query emails via API
- [ ] **No actual delivery**: Emails never actually sent

### 13. Test Data Management

**Seeded data strategy**

- [ ] **Preseeded accounts**: Admin, test user accounts created
- [ ] **Preseeded clients**: Test client with token ready
- [ ] **Preseeded realms**: Example realms configured
- [ ] **Preseeded backends**: Netcup, PowerDNS backends configured
- [ ] **Reset strategy**: Database can be reset to fresh state

**Test data files:**
- `deployment_state_local.json` - Local deployment credentials
- `deployment_state_webhosting.json` - Production credentials
- `.env.defaults` - Default test credentials

### 14. Continuous Integration Readiness

**CI/CD considerations**

- [ ] **Headless mode**: Playwright runs in headless mode
- [ ] **No manual steps**: All tests fully automated
- [ ] **Exit codes**: Tests exit 0 (success) or 1 (failure)
- [ ] **Parallel execution**: Tests can run in parallel
- [ ] **Fast feedback**: Core tests run in < 5 minutes
- [ ] **Artifacts**: Screenshots, logs, coverage reports saved

**CI workflow:**
```yaml
name: Test Suite
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Build deployment
        run: ./build-and-deploy-local.sh
      - name: Run tests
        run: pytest ui_tests/tests -v --junit-xml=junit.xml
      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

### 15. Test Documentation

**Documentation completeness**

- [ ] **README files**: Each test directory has README
- [ ] **Test contracts**: Journey contracts documented
- [ ] **Lessons learned**: TESTING_LESSONS_LEARNED.md exists
- [ ] **Playwright guide**: PLAYWRIGHT_CONTAINER.md complete
- [ ] **Local testing guide**: LOCAL_TESTING_GUIDE.md complete
- [ ] **HTTPS testing guide**: HTTPS_LOCAL_TESTING.md complete

## Test Quality Metrics

### Reliability Metrics

- [ ] **Pass rate**: 95%+ pass rate over last 100 runs
- [ ] **Flakiness**: < 1% flaky tests (pass/fail inconsistently)
- [ ] **Execution time**: Full suite runs in < 10 minutes
- [ ] **Parallelization**: 2x speedup with 4 workers

### Coverage Metrics

- [ ] **Code coverage**: 80%+ overall, 100% for critical paths
- [ ] **Route coverage**: 100% of Flask routes tested
- [ ] **UI coverage**: All admin pages, account portal tested
- [ ] **Error path coverage**: 4xx, 5xx responses tested

### Maintainability Metrics

- [ ] **Test clarity**: Tests are self-documenting
- [ ] **DRY principle**: Shared logic in fixtures
- [ ] **Stable selectors**: Use IDs, data attributes (not fragile CSS)
- [ ] **Error messages**: Clear assertion messages

## End-to-End Test Scenarios

### Scenario 1: Complete User Journey

```python
async def test_complete_user_journey():
    """Test full user journey from registration to API usage."""
    
    # 1. Admin creates account
    await admin_page.goto(f"{base_url}/admin/accounts/create")
    await admin_page.fill('input[name="username"]', "testuser")
    await admin_page.fill('input[name="email"]', "test@example.com")
    await admin_page.click('button[type="submit"]')
    
    # 2. Admin creates realm for user
    await admin_page.goto(f"{base_url}/admin/realms/create")
    await admin_page.select_option('select[name="account_id"]', label="testuser")
    await admin_page.fill('input[name="realm_value"]', "test.example.com")
    await admin_page.click('button[type="submit"]')
    
    # 3. User logs in
    await user_page.goto(f"{base_url}/account/login")
    await user_page.fill('input[name="username"]', "testuser")
    await user_page.fill('input[name="password"]', "generated_password")
    await user_page.click('button[type="submit"]')
    
    # 4. User generates token
    await user_page.goto(f"{base_url}/account/tokens/create")
    await user_page.fill('input[name="alias"]', "my-ddns")
    await user_page.click('button[type="submit"]')
    token = await user_page.text_content('.token-display')
    
    # 5. Use token via API
    response = await client.get(
        "/api/dns/test.example.com/records",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    
    # 6. Verify activity logged
    await admin_page.goto(f"{base_url}/admin/audit-log")
    await admin_page.fill('input[name="search"]', "testuser")
    logs = await admin_page.query_selector_all('.activity-log-row')
    assert len(logs) > 0
```

### Scenario 2: Security Hardening

```python
async def test_security_controls():
    """Test all security controls are enforced."""
    
    # 1. Rate limiting
    for _ in range(100):
        response = await client.get("/api/dns/test.com/records")
    assert response.status_code == 429  # Too Many Requests
    
    # 2. CSRF protection
    response = await client.post(
        "/admin/accounts/create",
        data={"username": "test"},
        # Missing CSRF token
    )
    assert response.status_code in [400, 403]
    
    # 3. Session security
    cookies = await page.context.cookies()
    session_cookie = [c for c in cookies if c['name'] == 'session'][0]
    assert session_cookie['secure'] is True
    assert session_cookie['httpOnly'] is True
    
    # 4. Password policy
    response = await client.post(
        "/account/password-change",
        data={"new_password": "weak"}  # Too weak
    )
    assert "password strength" in response.text.lower()
```

## Expected Deliverable

**Comprehensive testing review report:**

```markdown
# Testing Architecture & Coverage - Quality Review

## Executive Summary
- Test quality: ✅ Excellent | ⚠️ Good | ❌ Needs Work
- Coverage: [percentage]% code, [percentage]% routes
- Pass rate: [percentage]% over last 100 runs
- Critical gaps: [list]

## Coverage Analysis

### Code Coverage
- Overall: [percentage]%
- Critical paths: [percentage]%
- Uncovered areas: [list]

### Route Coverage
- Tested routes: [count]/[total]
- Missing tests: [list]

### UI Coverage
- Admin pages: [count]/[total]
- Account portal: [count]/[total]
- Interactive elements: [list]

## Test Quality Metrics

### Reliability
- Pass rate: [percentage]%
- Flaky tests: [count] ([percentage]%)
- Execution time: [minutes]

### Maintainability
- DRY violations: [count]
- Brittle selectors: [count]
- Missing fixtures: [count]

## Critical Gaps (P0)
1. [Gap] - Area: [feature] - Risk: [description]

## Recommendations

### Immediate Actions
1. [Action item with priority]

### Quality Improvements
...

## Test Examples

### Well-Written Test
```python
[Example of good test]
```

### Needs Improvement
```python
[Example with issues, suggested fix]
```

## Code References
- [File:line] - [Finding]
```

---

## Usage

```
Please perform a comprehensive testing architecture review using the checklist defined in .vscode/REVIEW_PROMPT_TESTING_COVERAGE.md.

Focus on:
1. Analyzing test coverage gaps
2. Evaluating test quality and reliability
3. Identifying flaky or brittle tests
4. Recommending improvements

Provide a structured report with coverage metrics, quality analysis, and actionable recommendations.
```
