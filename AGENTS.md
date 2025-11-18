# Build and deployment


## deploy to live server via webhosting

The database will be reset and on first login the admin password needs to be changed. 

**Default credentials**: 'admin' / 'admin' 

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

# Use Playwright

Use the Playwright MCP harness under `tooling/playwright-mcp/` whenever you
need to interact with the deployed UI (login, create clients, inspect logs,
etc.). The quick steps are:

1. `cd tooling/playwright-mcp`
2. `docker compose up -d`
3. Register `http://172.17.0.1:8765/mcp` in your MCP-enabled chat client

The detailed build (including `docker buildx`) and troubleshooting notes are in
`tooling/playwright-mcp/README.md`.

## Automated local UI validation

- Prefer `tooling/run-ui-validation.sh` when you want a single command that
  renders/stages the proxy config, spins up the TLS proxy and MCP harness,
  installs the UI test dependencies, and executes `pytest ui_tests/tests -vv`.
- The script writes backend logs to `tmp/local_app.log` and tears down the
  containers automatically (trap on `EXIT`).
- Customize the run by exporting environment variables beforehand:
  `UI_BASE_URL` to point at a different host, `PLAYWRIGHT_HEADLESS=false` to
  VNC into Chromium, or `SKIP_UI_TEST_DEPS=1` if your environment already has
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

# Running commands via Copilot / Agents — safe pattern

CRITICAL: Avoid using compound shell statements (pipes, &&, ;, here-documents, inline environment-variable assignments, or multi-line commands) in Copilot/agent instructions. Those compound commands are hard or impossible to reliably whitelist in VS Code's auto-approve rules and often require manual approval.

Instead: have the agent write a single, well-known script file and run that script. **Canonical file**: `.vscode/copilot-cmd.sh`. That script is whitelisted in the project's Copilot rules and gets a single, simple invocation that VS Code can match. CRITICAL: As we lack a history of commands run, *before* executing the actual code, the script must 1. debug print the brief intention of following code (e.g. `INTENT: list domains handled by letsencrypt `) and 2. debug print the code itself that will be executed (e.g. `PLANNED: ls -l /etc/letsencrypt/live/`). To *not* call the script with variables on the command line (prevent compound statement) use `.vscode/copilot-plan.sh` to define variables. e.g. like this:

```bash file=.vscode/copilot-plan.sh
INTENT="Tail backend log"
PLANNED="tail -n 50 /tmp/local_app.log"
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

log_intent() {
    echo -e "${BLUE}[INTENT]${NC} $*"
}
log_planned() {
    echo -e "${BLUE}[PLANNED]${NC} $*"
}

cd /workspaces/dstdns

INTENT="Audit repository for hardcoded vault URLs"
PLANNED="rg -n \"http://vault\""

log_intent "${INTENT}"
log_planned "${PLANNED}"

eval "${PLANNED}"
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
