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
TLS proxy tooling under `tooling/local-proxy/`:

- The README in that folder explains how to configure the reverse proxy via
  environment files so no values are hard-coded.
- This workflow mirrors `## deploy to live server via webhosting` but keeps all
  traffic on your machine, making it ideal for debugging flows that are opaque
  on the shared host.

Follow the instructions in `tooling/local-proxy/README.md` to generate the
nginx config from your `.env`, mount the Let’s Encrypt tree read-only, and
point clients at the public FQDN of this host.

# Use Playwright

Use the Playwright MCP harness under `tooling/playwright-mcp/` whenever you
need to interact with the deployed UI (login, create clients, inspect logs,
etc.). The quick steps are:

1. `cd tooling/playwright-mcp`
2. `docker compose up -d`
3. Register `http://172.17.0.1:8765/mcp` in your MCP-enabled chat client

The detailed build (including `docker buildx`) and troubleshooting notes are in
`tooling/playwright-mcp/README.md`.

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

Instead: have the agent write a single, well-known script file and run that script. **Canonical file**: `.vscode/copilot-cmd.sh`. That script is whitelisted in the project's Copilot rules and gets a single, simple invocation that VS Code can match. CRITICAL: As we lack a history of commands run, *before* executing the actual code, the script must 1. debug print the brief intention of following code (e.g. `INTENT: list domains handled by letsencrypt `) and 2. debug print the code itself that will be executed (e.g. `PLANNED: ls -l /etc/letsencrypt/live/`), e.g. like this:

```bash file=.vscode/copilot-cmd.sh
#!/usr/bin/env bash
set -euo pipefail

cd /workspaces/netcup-api-filter

INTENT=${INTENT:-"No action configured"}
PLANNED=${PLANNED:-"echo 'Update .vscode/copilot-cmd.sh before running it.'"}

echo "INTENT: ${INTENT}"
echo "PLANNED: ${PLANNED}"

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

Do:
```bash
# one-line, whitelisted script execution
bash ./.vscode/copilot-cmd.sh
```

Inside `.vscode/copilot-cmd.sh` put the real steps, secrets handling, and here-doc content. 
