# Local TLS Proxy Workspace

This folder contains the tooling required to run a local reverse proxy that
terminates TLS for the host's public Fully Qualified Domain Name (FQDN) while
ts certificates, secure cookies) but also want full observability that is not
forwarding traffic to a locally running instance of the Netcup API Filter.
Use this when you need production-like HTTPS behaviour (real hostname,
Let's Encrypt certificates, secure cookies) but also want full observability that is not
available on the shared webhosting setup.

## When to use this project

- **Debugging complex flows**: run the Flask stack locally, capture logs and
  traces, yet continue driving the UI via `https://<public-fqdn>/...` so the
  Playwright MCP harness and browsers behave exactly as in production.
- **Pre-deployment validation**: exercise password rotations or token
  provisioning locally before publishing to the live webhoster.
- **TLS parity**: confirm that modern browsers, MCP tools or API clients accept
  the same certificate chain that production uses (no self-signed certs).

If the shared hosting target already provides the telemetry you need, keep
using the `## deploy to live server via webhosting` flow from `AGENTS.md`.
Otherwise, spin up this local proxy and point clients at it.

## Files in this folder

| File | Purpose |
| ---- | ------- |
| `docker-compose.yml` | Defines the `local_proxy` service (nginx) and mounts all inputs via configuration. |
| `proxy.env.example` | Template for a `.env` file consumed by Docker Compose so no values are hard-coded. |
| `nginx.conf.template` | Parametrised nginx config; render it with `envsubst` using the values from your `.env`. |
| `stage-proxy-inputs.sh` | Copies rendered configs and test certs into host-visible staging directories (useful inside devcontainers). |
| `local_app.py` | WSGI entry point that boots the Flask app in database mode with a fake Netcup backend. |
| `README.md` | You are here. |

## Configuration

### Recommended: Auto-Detection (Zero Configuration)

```bash
# Automatically detect public FQDN and generate proxy.env
./auto-detect-fqdn.sh [--verify-certs] [--output proxy.env]

# What it does:
# 1. Queries external IP from ipify.org, icanhazip.com, etc.
# 2. Performs reverse DNS lookup on detected IP
# 3. Constructs Let's Encrypt certificate paths
# 4. Generates proxy.env with all values populated
# 5. Optional: Verifies certificates exist on host (--verify-certs)
```

**When to use auto-detection:**
- ✅ You have Let's Encrypt certificates for your public IP's reverse DNS
- ✅ You want 100% production parity (same certificates as webhosting)
- ✅ You need HTTPS testing with real CA-signed certificates

### Manual: Copy and Edit (Fallback)

```bash
# Copy template and manually configure
cp proxy.env.example proxy.env
# Edit proxy.env with your values
```

**Configuration Variables:**

- **`LOCAL_TLS_DOMAIN`** (auto-detected or manual)
  - Public FQDN where nginx accepts HTTPS connections
  - Auto-detected via reverse DNS of external IP
  - Example: `gstammtisch.dchive.de`
  - Used to construct certificate paths: `/etc/letsencrypt/live/${LOCAL_TLS_DOMAIN}/`
  - Fallback: `naf.localtest.me` (uses self-signed certs in `./certs/`)

- **`LOCAL_APP_HOST`** and **`LOCAL_APP_PORT`**
  - Backend Flask/Gunicorn endpoint (HTTP, not HTTPS)
  - Use devcontainer hostname: `$(hostname)` or `netcup-api-filter-devcontainer`
  - Set `LOCAL_APP_HOST=__auto__` if using `tooling/run-ui-validation.sh`
  - Must be reachable from nginx container via `LOCAL_PROXY_NETWORK`

- **`LOCAL_PROXY_NETWORK`**
  - Docker network for proxy ↔ backend communication
  - Must exist: `docker network create naf-local`
  - Both nginx and devcontainer must join this network

- **`LE_CERT_BASE`**
  - **Option 1 (Recommended):** `/etc/letsencrypt` - Real Let's Encrypt certificates
    - Auto-detected by `./auto-detect-fqdn.sh`
    - Requires certificates on Docker host (not devcontainer)
    - 100% production parity (same CA as webhosting)
  - **Option 2 (Fallback):** `/tmp/netcup-local-proxy/certs` - Self-signed test certs
    - Uses pre-generated certs from `./certs/` directory
    - For testing when Let's Encrypt unavailable
    - Browsers will show security warnings

- **`LOCAL_PROXY_CONFIG_PATH`**
  - Host-visible path for nginx configs (required in devcontainer)
  - Default: `/tmp/netcup-local-proxy/conf.d`
  - Docker daemon can't read `/workspaces/` directly

### Render nginx Configuration

```bash
# Render nginx.conf from template (uses values from proxy.env)
./render-nginx-conf.sh
```

Rerun whenever you change proxy.env values.

3. (Devcontainer/local Docker tip) Stage the rendered config and bundled test
  certificates into a host-visible directory so Docker can mount them:
  ```bash
  ./stage-proxy-inputs.sh
  ```
  The script copies `conf.d/` and `certs/` into the directories defined by
  `LOCAL_PROXY_CONFIG_PATH` and `LE_CERT_BASE` by streaming the files through a
  short-lived `alpine` container. That extra hop is required because the
  Docker daemon cannot directly read `/workspaces/...` inside devcontainers.
  By default the `.env.example` file points both variables to
  `/tmp/netcup-local-proxy/...`, which works on the Codespaces/devcontainer
  hosts. To sync into another location, export
  `ALLOW_PROXY_ASSET_STAGE_ANYWHERE=1` before running the script.

4. Start the Flask backend (new terminal):
  ```bash
  # Choose where the sqlite DB should live
  export LOCAL_DB_PATH="$PWD/tmp/local-netcup.db"

  # Run the seeded backend on port 5100
  gunicorn tooling.local_proxy.local_app:app -b 0.0.0.0:5100
  ```
  The `local_app.py` helper seeds the default admin credentials and the
  `test_qweqweqwe_vi` client inside the sqlite database and wires a fake
  Netcup client so that the client portal can load DNS data without contacting
  the real API.

5. Start the local proxy (separate terminal):
   ```bash
   docker compose --env-file proxy.env up -d
   ```
   The proxy publishes TLS and HTTP redirect ports on the host so that
   `https://$LOCAL_TLS_DOMAIN/...` now terminates on your machine.

6. Update `/etc/hosts` (inside the devcontainer, testing containers, and the
   Playwright MCP stack) so the public hostname resolves to `172.17.0.1` or the
   appropriate Docker bridge IP. All tools can then continue to use the public
   FQDN while hitting your local proxy.

7. When finished debugging, stop the stack:
   ```bash
   docker compose --env-file proxy.env down
   ```

ts tree read-only (already configured) so the proxy cannot alter certificates.
## Safety notes

- Mount the Let's Encrypt tree read-only (already configured) so the proxy cannot alter certificates.
- The rendered nginx config sets `disable_symlinks off;` so the container can follow the
  standard `live/ → archive/` symlink layout provided by certbot.
- Never check the populated `.env` or rendered `nginx.conf` file into source
  control; they contain machine-specific paths.
- Ensure the devcontainer and proxy share the same Docker network so the proxy
  can forward requests via the hostname defined by `LOCAL_APP_HOST`.

## Automating the full UI validation flow

- Use `tooling/run-ui-validation.sh` when you want to smoke test the UI.
  It renders + stages this proxy config, starts gunicorn, launches the proxy,
  brings up the Playwright MCP harness, and runs `pytest ui_tests/tests -vv`
  against the HTTPS endpoint (defaulting to `https://<host-gateway>:4443`).
- Override `UI_BASE_URL`, `LOCAL_TLS_DOMAIN`, or `PLAYWRIGHT_START_URL`
  environment variables before executing the script if you need to target a
  different hostname or port.
