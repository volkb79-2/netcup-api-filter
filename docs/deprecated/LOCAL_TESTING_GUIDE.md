# Local Testing with Production Parity

> **Status:** Archived implementation notes. Follow `OPERATIONS_GUIDE.md` for the maintained testing workflow.

## Overview

This document describes how to run the complete test suite (47 tests: 26 functional + 21 E2E) against a local deployment that **exactly mirrors** the webhosting production environment.

## Key Principle

> **Production Parity**: Local testing uses the SAME deployment package, database, and configuration as production to ensure tests are valid.

## Quick Start

### Automated Testing (Recommended)

```bash
./run-local-tests.sh
```

This single command:
1. ✅ Uses existing `deploy-local/` or builds fresh deployment from `build_deployment.py`
2. ✅ Extracts the exact package that would be uploaded to production
3. ✅ Starts Flask from `deploy-local/` with preseeded database
4. ✅ Runs complete test suite (90 tests collected, 47 run locally, 43 skip on E2E markers)
5. ✅ Automatically cleans up Flask process on exit

### Manual Testing (Step-by-Step)

If you want more control or debugging:

```bash
# 1. Build deployment package (creates deploy.zip with preseeded database)
./build_deployment.py

# 2. Extract to local directory (mirrors webhosting FTP extraction)
rm -rf deploy-local
cp -r deploy deploy-local

# 3. Start Flask from deploy-local (same WSGI entry as production)
cd deploy-local
PYTHONPATH=vendor \
  NETCUP_FILTER_DB_PATH=netcup_filter.db \
  SECRET_KEY="local-test-secret-12345" \
  FLASK_ENV="local_test" \
  gunicorn -b 0.0.0.0:5100 --daemon passenger_wsgi:application

# 4. Run tests
export UI_BASE_URL=http://netcup-api-filter-devcontainer-vb:5100
export UI_ADMIN_USERNAME=admin
export UI_ADMIN_PASSWORD=admin
export UI_CLIENT_ID=test_qweqweqwe_vi
export UI_CLIENT_SECRET_KEY=qweqweqwe_vi_readonly_secret_key_12345

pytest ui_tests/tests -v

# 5. Cleanup
pkill gunicorn
```

## What Gets Tested

- **90 total tests** in test suite
- **47 tests run locally** (26 functional + 21 E2E)
- **43 tests skip** (database/unit tests run independently)

### Test Categories

| Category | Count | Runs Where | Requires |
|----------|-------|------------|----------|
| Functional (Admin UI) | 10 | Local + Production | Browser, HTTP access |
| Functional (Client Portal) | 8 | Local + Production | Browser, HTTP access |
| Functional (API) | 8 | Local + Production | HTTP client |
| E2E (DNS Operations) | 7 | **Local only** | Mock Netcup API (port 5555) |
| E2E (Email) | 6 | **Local only** | Mock SMTP (port 1025) |
| E2E (Full Workflow) | 8 | **Local only** | Both mocks |
| Database/Unit | 43 | Independent | None |

## Database Seeding

The deployment package includes a **preseeded SQLite database** (`netcup_filter.db`) with:

- **Admin User**: `admin` / `admin` (must change password on first login)
- **Test Client**: `test_qweqweqwe_vi:qweqweqwe_vi_readonly_secret_key_12345`
  - Read-only access to `qweqweqwe.vi` domain
  - A record type only

This matches the exact state that production gets after deployment.

## Production vs Local Differences

| Aspect | Production (Webhosting) | Local (deploy-local) | Impact |
|--------|------------------------|---------------------|---------|
| **Deployment Method** | FTP upload + unzip | `cp -r deploy deploy-local` | None - Same files |
| **WSGI Server** | Phusion Passenger | Gunicorn | None - Both use `passenger_wsgi:application` |
| **Protocol** | HTTPS (Let's Encrypt) | HTTP | Session cookies need `FLASK_ENV=local_test` |
| **Database** | `netcup_filter.db` (persistent) | `netcup_filter.db` (from package) | Tests reset DB each run |
| **Secret Key** | `.secret_key` file (persistent) | `SECRET_KEY` env var | Same security, different storage |
| **Dependencies** | `vendor/` directory | `vendor/` directory | ✅ Identical |
| **Application Code** | From deploy.zip | From deploy.zip | ✅ Identical |
| **Database Schema** | Same | Same | ✅ Identical |
| **Seeded Data** | Same | Same | ✅ Identical |
| **Default Credentials** | `admin` / `admin` (must change) | `admin` / `admin` (must change) | ✅ Identical |
| **Test Client** | `test_qweqweqwe_vi` | `test_qweqweqwe_vi` | ✅ Identical |

### Why HTTP vs HTTPS Matters

- **Production**: HTTPS enforces `SESSION_COOKIE_SECURE = True` (cookies only sent over encrypted connections)
- **Local**: HTTP requires `SESSION_COOKIE_SECURE = False` (set via `FLASK_ENV=local_test`)
- **Both**: Session cookies work correctly for their respective protocols

## Session Cookie Issue (RESOLVED ✅)

### Problem

**Symptom**: Playwright tests failed at login despite correct credentials:
- cURL login worked: `POST /admin/login` → 302 → `/admin/change-password` → 200 OK
- Playwright login failed: `POST /admin/login` → 302 → `/admin/change-password` → 302 → `/admin/login`

**Root Cause**: Flask session cookies were configured with `Secure` flag (`SESSION_COOKIE_SECURE = True`), which requires HTTPS. Local testing uses HTTP (`http://127.0.0.1:5100`), so browsers (including Playwright) correctly refused to send the cookie over insecure connections.

**Evidence from curl**:
```
< Set-Cookie: session=...; Secure; HttpOnly; Path=/; SameSite=Lax
```

The `Secure` flag meant the cookie was set after POST but never sent with subsequent GET requests over HTTP.

### Solution

Modified `passenger_wsgi.py` to conditionally disable the `Secure` flag for local testing:

```python
# Only require HTTPS in production (local testing over HTTP needs Secure=False)
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') != 'local_test'
```

**Local testing**: Set `FLASK_ENV=local_test` to disable Secure flag  
**Production (webhosting)**: No environment variable set, Secure flag enabled (HTTPS enforced)

### Why This Is Not a Playwright Limitation

Playwright was working correctly by following browser security standards. The `Secure` flag is defined by RFC 6265 and requires cookies to only be sent over HTTPS connections. This is a **security feature**, not a browser or Playwright limitation.

**What we learned**:
- Browsers (including Playwright's Chromium) enforce the `Secure` flag properly
- Local testing over HTTP requires `SESSION_COOKIE_SECURE = False`
- Production HTTPS requires `SESSION_COOKIE_SECURE = True`
- The fix allows both: conditional flag based on environment

## Test Coverage

- **90 total tests**
- **26 functional tests**: Run on both local and production
- **21 E2E tests**: Require mock services (Netcup API, SMTP), only run locally
- **43 database/unit tests**: Run independently

### Test Markers

```python
@pytest.mark.e2e_local  # Requires mock services, skip on production
```

Production URL detection:
```python
if settings.base_url and not any(host in settings.base_url for host in ['localhost', '127.0.0.1', '0.0.0.0']):
    pytest.skip("E2E tests require local mock services")
```

## Benefits of This Approach

✅ **True Production Parity**: Tests run against the exact deployment package production uses  
✅ **Same Database State**: Preseeded database matches production initial state  
✅ **Same Workflows**: Password change on first login, exactly like production  
✅ **Reusable Tests**: No special local-only test code in functional tests  
✅ **Protocol-Agnostic**: Tests work on both HTTP (local) and HTTPS (production)  
✅ **Fast Feedback**: Complete test suite runs in ~1 minute locally  
✅ **No Mocking**: Functional tests hit real Flask app, not mocks  
✅ **Confidence**: If tests pass locally, deployment **will** work on production  

## Troubleshooting

### Tests Fail with "Invalid username or password"

**Cause**: Flask using old deployment without session cookie fix  
**Fix**: Rebuild deploy-local:
```bash
rm -rf deploy-local
./build_deployment.py
cp -r deploy deploy-local
```

### Tests Fail with "Connection Refused"

**Cause**: Flask not running  
**Fix**: Check if gunicorn is running:
```bash
ps aux | grep gunicorn
# If not running:
cd deploy-local
FLASK_ENV=local_test gunicorn -b 0.0.0.0:5100 passenger_wsgi:application &
```

### E2E Tests Fail Locally

**Cause**: Mock services (Netcup API, SMTP) not running  
**Status**: E2E mock service setup documented separately  
**Workaround**: Run functional tests only:
```bash
pytest ui_tests/tests -v -m "not e2e_local"
```

## Future Improvements

1. **Mock Services Documentation**: Complete guide for Netcup API and SMTP mocks
2. **Automated CI**: Run local tests in CI pipeline before production deployment
3. **Performance**: Cache `deploy-local/` between runs if `deploy.zip` unchanged
4. **HTTPS Local**: Optional local TLS proxy for complete HTTPS parity testing
