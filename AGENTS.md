# Build and deployment

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

The database will be reset and on first login the admin password needs to be changed. 

**Default credentials**: 'admin' / 'admin'

**Testing workflow**: After deployment, tests must go through the initial password change
flow (admin/admin → TestAdmin123!). Subsequent test runs use TestAdmin123! and don't
reset the password. This is by design - the database persists state between test runs
while code changes are deployed without database resets. 

## Preseeded Test Client

Every freshly built deployment now ships with a ready-to-use client for quick smoke testing:

- Client ID: `test_qweqweqwe_vi`
- Token: `qweqweqwe-vi-readonly`
- Scope: host `qweqweqwe.vi`, record type `A`, operation `read`

Use this token in the `Authorization: Bearer ...` header to exercise read-only flows or to validate UI/API plumbing before creating real clients. Rotate or delete it on production installs once your own clients exist.

You can use the script `./build-and-deploy.sh` to build and deploy to the server and directoy defined in the script.

see defined variables `NETCUP_USER`, `NETCUP_SERVER`, `REMOTE_DIR`, `PUBLIC_FQDN` how to access it.

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
