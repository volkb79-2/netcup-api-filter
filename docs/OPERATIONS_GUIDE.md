# Operations Guide

> Day-to-day runbook for the Netcup API Filter. Lives in `/docs` and should stay in sync with `CONFIGURATION_GUIDE.md` so setup + operations remain aligned.

## 1. Environment Preparation

1. **Install dependencies** inside the devcontainer (already provisioned). If you are outside the container, use `pip install -r requirements.txt`.
2. **Load your workspace env file**:
   ```bash
   source .env.workspace   # or .env.local / .env.webhosting
   ```
3. **Export required variables**:
   - `DEPLOYMENT_ENV_FILE` → points to the env file that mirrors the target deployment.
   - `UI_*` variables → required for UI tests (see below).
   - `LOCAL_DB_PATH`, `LOCAL_APP_HOST`, `LOCAL_TLS_DOMAIN`, etc., as referenced in `tooling/local_proxy/proxy.env`.
4. **Verify configuration** using the fail-fast errors provided by each script. Missing variables will halt execution with a clear hint.

## 2. Local Backend Smoke Test

Use the same packaging flow you ship to production:

```bash
./build-and-deploy-local.sh
./run-local-tests.sh
```

- `build-and-deploy-local.sh` builds `deploy.zip`, extracts it into `deploy-local/`, seeds the database, and starts the Passenger-compatible entry point.
- `run-local-tests.sh` runs the full pytest suite (UI + API + admin) against that extracted deployment.

Both scripts honor `DEPLOYMENT_ENV_FILE`. For example:

```bash
export DEPLOYMENT_ENV_FILE=.env.local
./run-local-tests.sh
```

## 3. Full UI Validation (Local HTTPS + Playwright)

When you need true production parity—including TLS, nginx proxy, and Playwright-driven browser tests—use the bundled orchestrator:

```bash
export DEPLOYMENT_ENV_FILE=.env.local
export UI_BASE_URL=https://<host-or-fqdn>
export UI_ADMIN_USERNAME=...
export UI_ADMIN_PASSWORD=...
export UI_CLIENT_ID=...
export UI_CLIENT_TOKEN=...
export UI_CLIENT_DOMAIN=...
export UI_SCREENSHOT_PREFIX=local
export PLAYWRIGHT_HEADLESS=true
export KEEP_UI_STACK=0
export LOCAL_DB_PATH=/workspaces/netcup-api-filter/tmp/local.db
bash tooling/run-ui-validation.sh
```

The script performs the following steps automatically:

1. Renders and stages the nginx TLS proxy configuration (using `tooling/local_proxy/render-nginx-conf.sh` and `stage-proxy-inputs.sh`).
2. Starts Gunicorn for `tooling/local_proxy/local_app:app` on the configured port.
3. Launches the TLS proxy via Docker Compose and waits for HTTPS readiness.
4. Boots the Playwright container (`tooling/playwright/docker-compose.yml`) and confirms the API is reachable.
5. Runs the requested pytest command inside the Playwright container (default: `pytest ui_tests/tests -vv`).
6. Tears everything down unless `KEEP_UI_STACK=1`.

If you need to run the proxy separately (for manual browser checks), follow `tooling/local_proxy/README.md` using the same environment variables.

## 4. Real-Certificate HTTPS Testing

To test with real Let's Encrypt certificates and a public FQDN (perfect production parity):

```bash
cd tooling/local_proxy
./auto-detect-fqdn.sh --verify-certs
./render-nginx-conf.sh
./stage-proxy-inputs.sh
docker compose --env-file proxy.env up -d
```

The proxy terminates TLS at nginx and forwards to the local Gunicorn server with `X-Forwarded-Proto: https`, ensuring Secure cookies behave the same as on the shared host. Point `UI_BASE_URL` to `https://$LOCAL_TLS_DOMAIN` and run the Playwright suite or manual smoke tests.

## 5. Deployment Workflow (Webhosting / Production)

> **Always** deploy via `./build-and-deploy.sh`. Do not manually copy files or touch `passenger_wsgi.py`.

1. **Prepare env overrides** in `.env.webhosting` with the target hostnames, admin seed, SMTP, etc.
2. **Build and deploy**:
   ```bash
   export DEPLOYMENT_ENV_FILE=.env.webhosting
   ./build-and-deploy.sh
   ```
   The script:
   - Builds `deploy.zip` with the seeded SQLite database and version metadata.
   - Uploads the package to the hosting provider via the configured transport.
   - Cleans the previous deployment (including dotfiles and database).
   - Extracts the new package and triggers Passenger restart via `tmp/restart.txt`.
3. **Post-deploy validation**:
   ```bash
   export DEPLOYMENT_ENV_FILE=.env.webhosting
   pytest ui_tests/tests -v
   ```
   This uses the same env file so tests hit the deployed instance with correct credentials.

The deployment resets the database to the defaults defined in `.env.defaults`. The first admin login forces a password change; UI tests automatically persist the rotated password inside `/screenshots/.env.webhosting` when running through the Playwright container.

## 6. Troubleshooting Checklist

- **Script fails immediately** → Missing env var. Read the error, export the variable (often by sourcing `.env.workspace`), and rerun.
- **Proxy unreachable** → Ensure the devcontainer is attached to `LOCAL_PROXY_NETWORK` (handled automatically by `run-ui-validation.sh`, but double-check via `docker network inspect`).
- **Playwright cannot connect** → Confirm `UI_BASE_URL` matches the TLS proxy, `LOCAL_TLS_BIND_HTTPS` is open, and certificates are staged.
- **Session cookies invalid locally** → Use `FLASK_ENV=local_test` or run through the HTTPS proxy so `FLASK_SESSION_COOKIE_SECURE=auto` flips correctly.
- **Admin password mismatch after deployment** → Read `/screenshots/.env.webhosting` for the latest rotated password or rerun the password reset flow via the admin UI.

Keep this guide updated whenever operational steps change so team members do not need to hunt through historical documents.
