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
| `docker-compose.yml` | Defines the `local-proxy` service (nginx) and mounts all inputs via configuration. |
| `proxy.env.example` | Template for a `.env` file consumed by Docker Compose so no values are hard-coded. |
| `nginx.conf.template` | Parametrised nginx config; render it with `envsubst` using the values from your `.env`. |
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
     Flask/Gunicorn server listens. Use the container name plus port if both run
     on the same Docker network.
   - `LOCAL_PROXY_NETWORK` is an existing user-defined Docker network that both
     the devcontainer and the proxy will join.
   - `LE_CERT_BASE` points to the parent directory that holds the `live/` and
     `archive/` trees (typically `/etc/letsencrypt`).

2. Render the nginx configuration so it contains the selected values:
   ```bash
   source proxy.env
   envsubst < nginx.conf.template > nginx.conf
   ```
   Rerun the `envsubst` command whenever you change the `.env` values.

3. Start the local proxy:
   ```bash
   docker compose --env-file proxy.env up -d
   ```
   The proxy publishes TLS and HTTP redirect ports on the host so that
   `https://$LOCAL_TLS_DOMAIN/...` now terminates on your machine.

4. Update `/etc/hosts` (inside the devcontainer, testing containers, and the
   Playwright MCP stack) so the public hostname resolves to `172.17.0.1` or the
   appropriate Docker bridge IP. All tools can then continue to use the public
   FQDN while hitting your local proxy.

5. When finished debugging, stop the stack:
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
