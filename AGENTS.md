# Build and deployment

## Configuration-Driven Architecture (CRITICAL)

**DIRECTIVE**: This project enforces 100% config-driven approach. **NO HARDCODED VALUES** in code.

All configuration MUST come from:
1. **`.env.defaults`** - Single source of truth for defaults (version-controlled)
2. **Environment variables** - Override defaults per environment (dev/staging/production)
3. **Database settings** - Runtime configuration via admin UI

Examples of config-driven values:
- Flask session settings (cookie flags, lifetime, SameSite policy)
- Admin/client credentials (username, password, tokens)
- Rate limiting (requests per minute/hour, max content size)
- Timeouts (HTTP requests, SMTP, API calls)
- TLS proxy settings (domain, ports, certificate paths)

**Before** (hardcoded ❌):
```python
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Hardcoded!
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # Magic number!
```

**After** (config-driven ✅):
```python
app.config['SESSION_COOKIE_SAMESITE'] = os.environ.get('FLASK_SESSION_COOKIE_SAMESITE', 'Lax')
app.config['PERMANENT_SESSION_LIFETIME'] = int(os.environ.get('FLASK_SESSION_LIFETIME', '3600'))
```

See `CONFIG_DRIVEN_ARCHITECTURE.md` for complete guidelines and migration plan.

## Local Testing with Production Parity

**Quick command (HTTP testing):**
```bash
./run-local-tests.sh
```

**Quick command (HTTPS testing with real Let's Encrypt certificates):**
```bash
cd tooling/local_proxy && ./auto-detect-fqdn.sh && cd ../.. && ./run-local-tests.sh
```

This runs the complete test suite (90 tests: 27 comprehensive UI, 10 admin, 4 client, 8 API proxy, and more) against a deployment that **exactly mirrors production**:

### What It Does

1. **Builds deployment package** - Same `deploy.zip` that goes to production
2. **Extracts locally** - `deploy-local/` contains exact production structure (gitignored, regenerated each run)
3. **Preseeded database** - `admin`/`admin` credentials, test client ready
4. **Starts Flask** - Same `passenger_wsgi:application` entry point
5. **Runs all tests** - 26 functional + 21 E2E tests
6. **Cleans up** - Kills Flask automatically

### Key Files

- **`build-and-deploy-local.sh`** - Builds and extracts deployment locally
- **`run-local-tests.sh`** - Complete automated test runner (BUILD + RUN + CLEANUP)
- **`LOCAL_TESTING_GUIDE.md`** - Full documentation

### Why This Matters

- ✅ **No surprises** - If tests pass locally, production deployment will work
- ✅ **Fast iteration** - Full test suite runs in ~1 minute
- ✅ **True parity** - Same code, same database, same workflows as production
- ✅ **Session cookies work** - Fixed via `FLASK_ENV=local_test` flag

### Session Cookie Configuration

**Session cookies are now 100% config-driven** (no hardcoded values in code):

```bash
# .env.defaults (single source of truth)
FLASK_SESSION_COOKIE_SECURE=auto
FLASK_SESSION_COOKIE_HTTPONLY=True
FLASK_SESSION_COOKIE_SAMESITE=Lax
FLASK_SESSION_LIFETIME=3600
```

**`FLASK_SESSION_COOKIE_SECURE=auto` behavior**:
- **Production** (no FLASK_ENV): Secure=True → HTTPS enforced
- **Local testing** (FLASK_ENV=local_test): Secure=False → HTTP allowed
- **HTTPS local** (HTTPS proxy): Secure=True → HTTPS enforced (100% production parity)

See `LOCAL_TESTING_GUIDE.md` and `CONFIG_DRIVEN_ARCHITECTURE.md` for complete details.

## HTTPS Local Testing with Let's Encrypt Certificates (NEW)

**Test with real TLS certificates and 100% production parity:**

```bash
cd tooling/local_proxy

# Auto-detect public FQDN from external IP + reverse DNS
./auto-detect-fqdn.sh --verify-certs

# Start HTTPS proxy with Let's Encrypt certificates
./render-nginx-conf.sh && ./stage-proxy-inputs.sh
docker compose --env-file proxy.env up -d

# Run tests against HTTPS endpoint
FQDN=$(grep LOCAL_TLS_DOMAIN proxy.env | cut -d= -f2)
UI_BASE_URL="https://$FQDN" pytest ui_tests/tests -v
```

### What This Provides

- **Real certificates**: Let's Encrypt CA (same as production webhosting)
- **True HTTPS**: Secure cookies work identically to production
- **Full observability**: Access Flask logs, database, internal state
- **Auto-detection**: Automatically finds public FQDN from external IP
- **No self-signed**: Browsers accept certificates without warnings

**Architecture**:
```
Browser → nginx:443 (TLS termination, Let's Encrypt cert)
  → Flask:5100 (HTTP, X-Forwarded-Proto: https)
    → Secure cookies work (Secure=True, HTTPS protocol)
```

See `HTTPS_LOCAL_TESTING.md` for complete setup, debugging, and integration guides.

## Fail-Fast Policy

**CRITICAL**: This project enforces NO DEFAULTS, NO FALLBACKS. Missing configuration = immediate error.

- All scripts use `${VAR:?VAR must be set}` instead of `${VAR:-default}`
- Docker Compose requires all environment variables explicitly
- Clear error messages guide fixes: "NETWORK: must be set (source .env.workspace)"
- See `FAIL_FAST_POLICY.md` for complete documentation

**Agent workflow:**
1. Run script → see clear error about missing variable
2. Read error message for fix hint
3. Apply fix (source .env.workspace, export variable, etc.)
4. Re-run script → next error or success
5. Iterate until all prerequisites met

## deploy to live server via webhosting

**CRITICAL: ALWAYS use `./build-and-deploy.sh` for deployments**

DO NOT manually copy files, use scp directly, or touch `passenger_wsgi.py`. The deployment script is the ONLY supported deployment method.

The deployment script:
- Builds the deployment package with `build_deployment.py` (includes fresh preseeded database)
- Uploads `deploy.zip` to the server
- Cleans old deployment (including dotfiles AND database)
- Extracts the new package
- **Restarts Passenger by touching `tmp/restart.txt`** (required for code changes to take effect)

**Every deployment resets the database to fresh state with default credentials** from `.env.defaults` (typically `admin` / `admin`).

On first login after deployment, you must change the admin password. Tests handle this automatically and persist the new password to `/screenshots/.env.webhosting` (writable Playwright container mount).

**Default credentials are defined in `.env.defaults`** (single source of truth). The build process reads these values and writes them to `/screenshots/.env.webhosting` representing the live deployment state.

See `ENV_DEFAULTS.md` for complete documentation on the environment defaults system.

**Testing workflow**: After deployment, tests must go through the initial password change
flow (default credentials from `.env.defaults` → TestAdmin123!). The password change is persisted to `.env.webhosting`
(stored in Playwright's writable `/screenshots/` mount) so subsequent test runs automatically
use the new password. Database resets are only needed when you want to start fresh.

## Preseeded Test Client

Every freshly built deployment now ships with a ready-to-use client for quick smoke testing (credentials defined in `.env.defaults`):

- Client ID: (from `DEFAULT_TEST_CLIENT_ID`)
- Token: (from `DEFAULT_TEST_CLIENT_TOKEN`)
- Scope: Configured via `DEFAULT_TEST_CLIENT_REALM_*`, `DEFAULT_TEST_CLIENT_RECORD_TYPES`, `DEFAULT_TEST_CLIENT_OPERATIONS`

Use this token in the `Authorization: Bearer ...` header to exercise read-only flows or to validate UI/API plumbing before creating real clients. Rotate or delete it on production installs once your own clients exist.

**Deployment Command:**
```bash
./build-and-deploy.sh
```

This is the ONLY supported deployment method. Do not manually scp files.

**Live Server Access Credentials** (from `./build-and-deploy.sh`):
- SSH: `hosting218629@hosting218629.ae98d.netcup.net`
- Remote Directory: `/netcup-api-filter`
- Public URL: `https://naf.vxxu.de/`
- Log File: `/netcup-api-filter/netcup_filter.log`
- Database: `/netcup-api-filter/netcup_filter.db`
- Restart: `touch /netcup-api-filter/tmp/restart.txt` (Passenger reload)

## deploy locally 

You can still hit the Flask server directly via the devcontainer address for
quick smoke checks. When you need production-like HTTPS (real hostname,
Let’s Encrypt certificates) but with full control and logging, use the local
TLS proxy tooling under `tooling/local_proxy/`:

- The README in that folder explains how to configure the reverse proxy via
  environment files so no values are hard-coded.
- This workflow mirrors `## deploy to live server via webhosting` but keeps all
  traffic on your machine, making it ideal for debugging flows that are opaque
  on the shared host.

Follow the instructions in `tooling/local_proxy/README.md` to generate the
nginx config from your `.env`, mount the Let’s Encrypt tree read-only, and
point clients at the public FQDN of this host.

- `tooling/local_proxy/render-nginx-conf.sh` renders the nginx config using
  your `.env` choices, while `tooling/local_proxy/stage-proxy-inputs.sh`
  copies the resulting config and cert bundle into `/tmp/...` so Docker can
  mount them from inside the devcontainer. Run both before restarting the
  proxy.
- When you need the whole local stack (backend + TLS proxy + Playwright MCP)
  just for validating UI changes, use `tooling/run-ui-validation.sh`. It
  starts gunicorn, launches the proxy, brings up the MCP container, and runs
  `pytest ui_tests/tests -vv` end-to-end. Override `UI_BASE_URL`,
  `UI_MCP_URL`, or `SKIP_UI_TEST_DEPS=1` before calling the script if you need
  a custom target or want to skip dependency installation.
  The script now also auto-attaches the current devcontainer to the
  `naf-local` Docker network (or whatever `LOCAL_PROXY_NETWORK` is set to) so
  nginx can reach the gunicorn backend; it aborts early if that step fails so
  you are not left polling an unreachable proxy.

# Use Playwright

Use the Playwright container under `tooling/playwright/` for browser automation
and UI testing. The quick steps are:

1. `cd tooling/playwright`
2. `docker compose up -d`
3. `docker exec playwright pytest /workspace/ui_tests/tests -v`

For MCP access (optional), use SSH tunnel to expose port 8765 internally.
See `tooling/playwright/README.md` for detailed setup and usage.

## Automated local UI validation

- Prefer `tooling/run-ui-validation.sh` when you want a single command that
  renders/stages the proxy config, spins up the TLS proxy and Playwright container,
  installs the UI test dependencies, and executes `pytest ui_tests/tests -vv`.
- The script writes backend logs to `tmp/local_app.log` and tears down the
  containers automatically (trap on `EXIT`).
- Customize the run by exporting environment variables beforehand:
  `UI_BASE_URL` to point at a different host, `PLAYWRIGHT_HEADLESS=false` for
  headed browser mode, or `SKIP_UI_TEST_DEPS=1` if your environment already has
  the UI testing requirements installed.

# Webhosting constraints

- the python application resides not inside the web server's document root
- via webhoster's management UI passenger is configured to pick up `passenger_wsgi.py` as startup

## `.htaccess` 

`.htaccess` is not used by the hoster, no overrides possible

# Repository structure

- `/deploy` is a generated temporary folder holding only copied data for creating the `deploy.zip` created by `build_deploy.py`
- installed python modules are defined in `.devcontainer/requirements.txt` 

# python 

As we use a VSC devcontainer with defined / definable environment, we do not create a separate `venv` on purpose, but install all modules directly for the user `vscode`.

# FUSE / sshfs for remote file access

The devcontainer includes `sshfs` for mounting remote filesystems. However, FUSE requires kernel module support from the Docker **host**, not the container.

## Host Setup (One-time, requires host root access)

FUSE was already installed on the host:

```bash
# On the Docker host (outside container) - already completed
sudo apt-get install -y fuse
sudo modprobe fuse

# Verify FUSE device exists
ls -l /dev/fuse
```

**Important**: The `fuse` package installation on the host does NOT require a reboot. The kernel module is loaded automatically via `modprobe fuse` during package installation. The devcontainer can immediately use `/dev/fuse` after the host installation completes.

## Usage in Devcontainer

Once the host has FUSE installed, you can use `sshfs` from inside the devcontainer:

```bash
# Mount remote filesystem
mkdir -p /tmp/netcup-webspace
sshfs user@netcup-server.com:/path/to/remote /tmp/netcup-webspace

# Access files
ls /tmp/netcup-webspace

# Unmount when done
fusermount -u /tmp/netcup-webspace
```

**Note**: Do not attempt to install `fuse` package inside the devcontainer. The devcontainer only needs `sshfs` (already installed in Dockerfile) and access to the host's `/dev/fuse` device.

# Running commands via Copilot / Agents — safe pattern

CRITICAL: Do not use compound shell statements (pipes, &&, ;, here-documents, inline environment-variable assignments, or multi-line commands) in Copilot/agent instructions. Those compound commands are hard or impossible to reliably whitelist in VS Code's auto-approve rules and often require manual approval.

Instead: have the agent write a single, well-known script file and run that script. **Canonical file**: `.vscode/copilot-cmd.sh`. That script is whitelisted in the project's Copilot rules and gets a single, simple invocation that VS Code can match. CRITICAL: As we lack a history of commands run, *before* executing the actual code, the script must 1. debug print the brief intention of following code (e.g. `[PLAN] list domains handled by letsencrypt `) and 2. debug print the code itself that will be executed (e.g. `[EXEC] ls -l /etc/letsencrypt/live/`). To *not* call the script with variables on the command line (prevent compound statement) use `.vscode/copilot-plan.sh` to define variables. e.g. like this:

```bash file=.vscode/copilot-plan.sh
COPILOT_PLAN="Idle placeholder"
COPILOT_EXEC="true"
```

```bash file=.vscode/copilot-cmd.sh
#!/usr/bin/env bash
set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

log_plan() {
    echo -e "${BLUE}[PLAN]${NC} $*"
}
log_exec() {
    echo -e "${BLUE}[EXEC]${YELLOW} $*${NC}"
}

log_info "pwd: $(pwd)"
WORKSPACE_DIR="/workspaces/netcup-api-filter"
PLAN_FILE="${PLAN_FILE:-${WORKSPACE_DIR}/.vscode/copilot-plan.sh}"

if [[ -f "${PLAN_FILE}" ]]; then
    # shellcheck source=/dev/null
    source "${PLAN_FILE}"
fi

if [[ -z "${COPILOT_PLAN:-}" || -z "${COPILOT_EXEC:-}" ]]; then
    echo "COPILOT_PLAN or COPILOT_EXEC command not set" >&2
    exit 1
fi

log_plan "${COPILOT_PLAN}"
log_exec "${COPILOT_EXEC}"

cd "${WORKSPACE_DIR}"

eval "${COPILOT_EXEC}"
```

Why
- Copilot/VS Code matches the whole terminal string. Compound statements (cd ... && export=... pytest ...) and here-docs contain special characters and newlines that break pattern matching and are rejected for automatic execution.
- Keeping a single script reduces the allowed surface area and makes review/change auditing (and secret handling) easier.

Recommended rule (human-readable)
- Do not pass secrets or passwords on the command line (e.g., UI_ADMIN_PASSWORD=... before a command). Command-line args can leak (process lists, logs). Instead:
  - Export secrets into the environment from a secure source before running the script, or
  - Read secrets inside the script from a secure source (.env not committed, secret manager, or interactive prompt).
- Do not send multi-line here-documents as a single Copilot command. Put the here-doc inside the script instead.
- Keep the Copilot invocation a single command that executes the canonical script, e.g.:
  - ./ .vscode/copilot-cmd.sh
  - bash .vscode/copilot-cmd.sh

Do / Don't examples

Don't:
```bash
# compound command — brittle, not whitelisted
cd /workspaces/netcup-api-filter && UI_ADMIN_PASSWORD=Admin123! pytest ui_tests/tests
```
Don't
```bash
cd /workspaces/netcup-api-filter && INTENT="create tmp directory" PLANNED="mkdir -p /workspaces/netcup-api-filter/tmp" bash ./.vscode/copilot-cmd.sh
```

Do:
```bash
# one-line, whitelisted script execution
bash ./.vscode/copilot-cmd.sh
```

Inside `.vscode/copilot-cmd.sh` put the real steps, secrets handling, and here-doc content. 
