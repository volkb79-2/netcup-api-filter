# UI Inspection Workflow Guide

## Overview

This document describes the correct workflow for capturing UI screenshots with proper credentials after a fresh deployment.

## The Problem

When we build a fresh deployment with `./build-and-deploy-local.sh`:
1. A new database is created with default credentials (`admin` / `admin`)
2. On first login, the admin is forced to change their password
3. Tests change the password to a random secure token and persist it to `.env.webhosting`
4. Screenshot scripts must use the changed password, not the default one

## The Solution: Three-Step Workflow

### Step 1: Build Fresh Deployment

```bash
./build-and-deploy-local.sh
```

This creates:
- `/workspaces/netcup-api-filter/deploy-local/` - extracted deployment
- `/workspaces/netcup-api-filter/deploy-local/netcup_filter.db` - fresh preseeded database
- Flask running on `http://localhost:5100`

**Default credentials:**
- Admin: `admin` / `admin`
- Client: `test_qweqweqwe_vi` / `qweqweqwe_vi_readonly_secret_key_12345`

### Step 2: Run Authentication Test (Sets Password)

```bash
pytest ui_tests/tests/test_admin_ui.py::test_admin_authentication_flow -v
```

This test:
1. Logs in with default password (`admin`)
2. Navigates to password change page
3. Changes password to a secure random token (via `generate_token()`)
4. **Persists the new password to `.env.webhosting`**
5. Updates in-memory settings for current test session

**After this step:** `.env.webhosting` contains the new admin password.

### Step 3: Capture Screenshots

```bash
python3 ui_tests/capture_ui_screenshots.py
```

The script:
1. **Reads password from `.env.webhosting`** (not from settings default!)
2. Logs in with the persisted password
3. Navigates through all admin and client pages
4. Captures screenshots to `/workspaces/netcup-api-filter/tmp/screenshots/ui-inspection/`

## Automated Workflow Script

Use `./inspect-ui-local.sh` to run all three steps automatically:

```bash
./inspect-ui-local.sh
```

This script:
- ✅ Builds fresh deployment
- ✅ Runs authentication test to set password
- ✅ Captures screenshots with correct credentials
- ✅ Provides clear status output

## Manual Workflow (For Debugging)

If you need to run steps manually:

```bash
# 1. Build
./build-and-deploy-local.sh

# 2. Fix database permissions (if needed)
chmod 666 /workspaces/netcup-api-filter/deploy-local/netcup_filter.db
chmod 777 /workspaces/netcup-api-filter/deploy-local

# 3. Restart Flask with proper environment
pkill -9 gunicorn
cd /workspaces/netcup-api-filter/deploy-local
NETCUP_FILTER_DB_PATH=/workspaces/netcup-api-filter/deploy-local/netcup_filter.db \
  FLASK_ENV=local_test \
  SECRET_KEY="local-test-secret-key" \
  gunicorn -b 0.0.0.0:5100 --daemon passenger_wsgi:application

# 4. Wait for Flask to start
sleep 3
curl http://localhost:5100/admin/login

# 5. Run authentication test
pytest ui_tests/tests/test_admin_ui.py::test_admin_authentication_flow -v

# 6. Capture screenshots
python3 ui_tests/capture_ui_screenshots.py
```

## Key Files

- **`./build-and-deploy-local.sh`** - Builds and extracts deployment package
- **`./inspect-ui-local.sh`** - Automated 3-step workflow
- **`ui_tests/capture_ui_screenshots.py`** - Screenshot capture script (reads `.env.webhosting`)
- **`.env.webhosting`** - Persisted deployment state (password, tokens)
- **`ui_tests/workflows.py`** - Contains `_update_deployment_state()` for persistence
- **`deploy-local/netcup_filter.db`** - Local deployment database

## Troubleshooting

### "readonly database" errors

The Flask process may be running with stale permissions. Fix:

```bash
pkill -9 gunicorn
chmod 666 /workspaces/netcup-api-filter/deploy-local/netcup_filter.db
chmod 777 /workspaces/netcup-api-filter/deploy-local
# Then restart Flask (see manual workflow step 3)
```

### Screenshots show password change page instead of actual pages

This means screenshot script couldn't authenticate. Check:

1. Does `.env.webhosting` exist with the new password?
2. Is Flask using the correct database path?
3. Was the authentication test successful?

### "Account is locked out" errors

Too many failed login attempts. Solutions:
1. Wait 15 minutes for lockout to expire
2. OR rebuild deployment (resets database): `./build-and-deploy-local.sh`

## Best Practices

1. **Always use the automated script** (`./inspect-ui-local.sh`) for UI inspection
2. **Don't manually edit `.env.webhosting`** - let tests manage it
3. **Rebuild deployment when switching branches** to ensure clean state
4. **Check Flask logs** if screenshots fail: `/workspaces/netcup-api-filter/tmp/local_app.log`

## Integration with CI/CD

For production deployments (`./build-and-deploy.sh` to webhosting):
- The deployment package includes fresh database with default credentials
- First login after deployment requires password change
- Tests handle this automatically via `perform_admin_authentication_flow()`
- Password persists to `/screenshots/.env.webhosting` (Playwright container mount)

## Related Documentation

- `LOCAL_TESTING_GUIDE.md` - Complete local testing setup
- `TEST_SUITE_STATUS.md` - Test suite architecture
- `AGENTS.md` - Build and deployment instructions
