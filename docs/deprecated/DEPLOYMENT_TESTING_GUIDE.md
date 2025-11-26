# Deployment and Testing Guide

> **Status:** Archived. See `OPERATIONS_GUIDE.md` for the maintained deployment and validation steps.

## Overview

This project uses a **config-driven** approach for deployments and testing with complete separation between local and webhosting environments. All configuration comes from environment files - NO hardcoded values in scripts or code.

## Configuration Architecture

### Three-Tier Configuration System

1. **`.env.defaults`** - Single source of truth for default values (version-controlled)
2. **`.env.local`** - Local deployment state (NOT committed, auto-updated)
3. **`.env.webhosting`** - Webhosting deployment state (NOT committed, auto-updated)

```
Priority (highest to lowest):
┌─────────────────────────────────┐
│ 1. Explicit Environment Variables│  ← CI/CD, manual overrides
├─────────────────────────────────┤
│ 2. .env.local / .env.webhosting │  ← Runtime state (passwords, tokens)
├─────────────────────────────────┤
│ 3. .env.defaults                │  ← Initial defaults
└─────────────────────────────────┘
```

### Environment Files

#### `.env.defaults` (Committed)

Contains default values for fresh deployments:

```bash
# Default admin credentials
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=admin

# Default test client
DEFAULT_TEST_CLIENT_ID=test_qweqweqwe_vi
DEFAULT_TEST_CLIENT_SECRET_KEY=qweqweqwe_vi_readonly_secret_key_12345

# Flask configuration
FLASK_SESSION_COOKIE_SECURE=auto
FLASK_SESSION_LIFETIME=3600
```

#### `.env.local` (NOT Committed)

Tracks local deployment state, updated automatically:

```bash
# Current credentials (updated after password change)
DEPLOYED_ADMIN_USERNAME=admin
DEPLOYED_ADMIN_PASSWORD=<random-secure-token>

# Deployment metadata
DEPLOYED_AT=2025-11-24T17:45:00Z
DEPLOYED_COMMIT=a1b2c3d
DEPLOYED_BUILD_ID=2025-11-24T17:45:00Z_a1b2c3d

# Local configuration
UI_BASE_URL=http://localhost:5100
FLASK_ENV=local_test
```

#### `.env.webhosting` (NOT Committed)

Tracks webhosting deployment state:

```bash
# Current credentials (updated after password change)
DEPLOYED_ADMIN_USERNAME=admin
DEPLOYED_ADMIN_PASSWORD=<random-secure-token>

# Webhosting configuration
UI_BASE_URL=https://naf.vxxu.de
FLASK_ENV=production
```

## Local Deployment

### Quick Start

```bash
./build-and-deploy-local.sh
```

This automated script:
1. **Loads configuration** from `.env.defaults` and `.env.local`
2. **Builds** deployment package (same as webhosting)
3. **Deploys** to `$REPO_ROOT/deploy-local/`
4. **Starts Flask** on http://localhost:5100
5. **Runs authentication test** (changes password, updates `.env.local`)
6. **Captures screenshots** to `$REPO_ROOT/deploy-local/screenshots/`

### Directory Structure

```
$REPO_ROOT/
├── deploy-local/              # Local deployment (gitignored)
│   ├── netcup_filter.db       # Preseeded database
│   ├── passenger_wsgi.py      # Flask entry point
│   ├── screenshots/           # UI screenshots
│   └── ...                    # All deployment files
├── .env.defaults              # Default values (committed)
├── .env.local                 # Local state (NOT committed)
└── tmp/
    └── local_app.log          # Flask logs
```

### Manual Testing

Run tests against local deployment:

```bash
# Full test suite
pytest ui_tests/tests -v

# Specific test
pytest ui_tests/tests/test_admin_ui.py -v

# With explicit env file
DEPLOYMENT_ENV_FILE=.env.local pytest ui_tests/tests -v
```

The test framework automatically:
- Loads configuration from `.env.local` (if exists)
- Falls back to `.env.defaults` for missing values
- Updates `.env.local` when passwords change

### Recapture Screenshots

```bash
python3 capture_ui_screenshots.py
# Screenshots saved to: $REPO_ROOT/deploy-local/screenshots/
```

## Webhosting Deployment

### Quick Start

```bash
./build-and-deploy.sh
```

This automated script:
1. **Loads configuration** from `.env.defaults` and `.env.webhosting`
2. **Builds** deployment package
3. **Uploads** to netcup webhosting
4. **Deploys** and restarts Passenger
5. **Mounts remote filesystem** via SSHFS (optional, for logs)
6. **Records deployment metadata** in `.env.webhosting`

### First Login After Deployment

⚠️ **IMPORTANT**: Every fresh deployment requires password change!

1. Visit https://naf.vxxu.de/admin/
2. Login with default credentials from `.env.defaults`:
   - Username: `admin`
   - Password: `admin`
3. Change password when prompted
4. Run tests to persist new password to `.env.webhosting`

### Testing Webhosting Deployment

```bash
# Run authentication test (updates .env.webhosting with new password)
pytest ui_tests/tests/test_admin_ui.py::test_admin_authentication_flow -v

# Full test suite
pytest ui_tests/tests -v
```

The test framework automatically:
- Loads credentials from `.env.webhosting`
- Updates `.env.webhosting` when passwords change
- Uses the persisted password for subsequent test runs

### Capture Webhosting Screenshots

```bash
python3 capture_ui_screenshots.py
# Screenshots saved to: $REPO_ROOT/deploy-webhosting/screenshots/
```

## Shared Deployment Library

Both deployment scripts use `deployment-lib.sh` for DRY principles:

```bash
source "${REPO_ROOT}/deployment-lib.sh"

# Available functions:
load_defaults                              # Load .env.defaults
load_deployment_state "$env_file"          # Load .env.local/.env.webhosting
update_deployment_state "$env_file" "KEY=value" ...
fix_database_permissions "$db_path"
start_flask_local "$deploy_dir" "$db_path" "$log_file"
stop_flask
run_tests "$env_file" "$test_pattern"
run_auth_test "$env_file"
capture_screenshots "$env_file" "$screenshot_dir"
record_deployment "$env_file"
```

## Test Configuration

Tests automatically detect and load the correct environment file:

```python
# ui_tests/config.py
# Priority:
# 1. Explicit env vars (UI_ADMIN_PASSWORD=...)
# 2. DEPLOYMENT_ENV_FILE if set
# 3. .env.local if exists (local deployment)
# 4. .env.webhosting if exists (webhosting)
# 5. .env.defaults (fallback)
```

### Override Deployment Environment

```bash
# Force specific env file
DEPLOYMENT_ENV_FILE=.env.webhosting pytest ui_tests/tests -v

# Override specific values
UI_ADMIN_PASSWORD=CustomPassword pytest ui_tests/tests -v
```

## URL Configuration

URLs are derived from environment:

### Local Deployment
- **Flask Backend**: `http://localhost:5100`
- **Screenshots**: `$REPO_ROOT/deploy-local/screenshots/`
- **Database**: `$REPO_ROOT/deploy-local/netcup_filter.db`

### Webhosting Deployment
- **Public URL**: `https://naf.vxxu.de`
- **Screenshots**: `$REPO_ROOT/deploy-webhosting/screenshots/`
- **Remote FS**: Mounted via SSHFS at `/home/vscode/sshfs-hosting218629@...`

## Devcontainer Variables

The following variables are exported by `post-create.sh` and available in all scripts:

```bash
# Source workspace environment
source "${REPO_ROOT}/.env.workspace"

# Available variables:
$REPO_ROOT                 # /workspaces/netcup-api-filter
$PHYSICAL_REPO_ROOT        # Host path for Docker bind mounts
$DEVCONTAINER_NAME         # netcup-api-filter-devcontainer-vb
$DOCKER_NETWORK_INTERNAL   # naf-local
```

Use these in scripts for portable, config-driven URLs:

```bash
UI_BASE_URL="http://${DEVCONTAINER_NAME}:5100"
```

## Comparison: Local vs Webhosting

| Aspect | Local Deployment | Webhosting Deployment |
|--------|------------------|----------------------|
| **Environment File** | `.env.local` | `.env.webhosting` |
| **Base URL** | `http://localhost:5100` | `https://naf.vxxu.de` |
| **Deployment Dir** | `$REPO_ROOT/deploy-local/` | Remote: `/netcup-api-filter/` |
| **Database** | `deploy-local/netcup_filter.db` | Remote: `/netcup-api-filter/netcup_filter.db` |
| **Screenshots** | `deploy-local/screenshots/` | `deploy-webhosting/screenshots/` |
| **Flask Mode** | `FLASK_ENV=local_test` | `FLASK_ENV=production` |
| **Session Cookies** | Secure=False (HTTP) | Secure=True (HTTPS) |
| **Deployment Script** | `./build-and-deploy-local.sh` | `./build-and-deploy.sh` |
| **Auto-Test** | ✅ Yes (integrated) | ❌ No (manual) |
| **Auto-Screenshots** | ✅ Yes (integrated) | ❌ No (manual) |

## Best Practices

1. **Never commit `.env.local` or `.env.webhosting`** - Contains runtime credentials
2. **Always use deployment scripts** - Don't manually copy files or run Flask
3. **Let tests manage passwords** - Don't manually edit env files
4. **Source `.env.workspace` in custom scripts** - Gets canonical paths
5. **Use `deployment-lib.sh` functions** - DRY, tested, consistent

## Troubleshooting

### "REPO_ROOT must be set"

Source the workspace environment:

```bash
source .env.workspace
```

Or rebuild devcontainer (runs `post-create.sh`).

### "readonly database" errors

Database permissions issue:

```bash
chmod 666 deploy-local/netcup_filter.db
chmod 777 deploy-local/
pkill -9 gunicorn
./build-and-deploy-local.sh
```

### Screenshots show password change page

Password wasn't persisted. Run auth test:

```bash
pytest ui_tests/tests/test_admin_ui.py::test_admin_authentication_flow -v
```

### Tests use wrong password

Check which env file is loaded:

```bash
# Show current config
python3 -c "from ui_tests.config import settings; print(f'URL: {settings.base_url}'); print(f'Password length: {len(settings.admin_password)}')"
```

Force specific env file:

```bash
DEPLOYMENT_ENV_FILE=.env.local pytest ui_tests/tests -v
```

## Related Documentation

- `CONFIG_DRIVEN_ARCHITECTURE.md` - Detailed config system design
- `UI_INSPECTION_WORKFLOW.md` - Screenshot capture workflow
- `LOCAL_TESTING_GUIDE.md` - Local testing setup
- `AGENTS.md` - Build and deployment instructions
