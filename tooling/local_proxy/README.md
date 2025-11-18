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

1. Copy the example environment file and edit it with your values:
   ```bash
   cp proxy.env.example proxy.env
   # Edit proxy.env with the host FQDN, target port, and desired network name
   ```
   - `LOCAL_TLS_DOMAIN` must match the reverse DNS name of this host (e.g.
     `gstammtisch.dchive.de`).
   - `LOCAL_APP_HOST` and `LOCAL_APP_PORT` describe the HTTP endpoint where your
     Flask/Gunicorn server listens. Use the devcontainer hostname (output of
     `hostname`) if both run on the same Docker network. When running
     `tooling/run-ui-validation.sh` you can leave `LOCAL_APP_HOST` empty or set
     it to `__auto__` and the script will inject the correct value at runtime.
   - `LOCAL_PROXY_NETWORK` is an existing user-defined Docker network that both
     the devcontainer and the proxy will join.
   - `LE_CERT_BASE` points to the parent directory that holds the `live/` and
     `archive/` trees (typically `/etc/letsencrypt`). When you run inside a
     devcontainer/Codespace, prefer a directory under `/tmp/...` because the
     Docker daemon cannot see `/workspaces/...` directly.

2. Render the nginx configuration so it contains the selected values:
   ```bash
   source proxy.env
   envsubst < nginx.conf.template > nginx.conf
   ```
  Rerun the `envsubst` command whenever you change the `.env` values.

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
