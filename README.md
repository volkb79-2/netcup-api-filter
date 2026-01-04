# netcup-api-filter

A hardened proxy that lets you expose just enough of the Netcup DNS API to specific clients without handing out full credentials.

## Why It Exists

Netcup issues a single credential set with full control over every DNS record, domain, and order. This project inserts a policy-aware proxy in front of that API so you can:

- Mint independent tokens for each automation client.
- Scope tokens to domains, subdomains, record types, and operations.
- Enforce rate limits, origin restrictions, and audit logging.
- Offer a browser-based admin UI and a self-service client portal without leaking the master credentials.

## Highlights

- Token-based auth with bcrypt storage.
- Realm-based permission engine (host, subdomain, wildcard).
- Admin UI plus client portal backed by SQLite.
- Config-driven email notifications, auditing, and IP/network allowlists.
- Build + deployment scripts that mirror the production package.
- Playwright UI tests (local HTTP, HTTPS with real certs, and MCP mode).
- **DDNS protocol support** - DynDNS2 and No-IP compatible endpoints for routers and DDNS clients.

## Quick Start

```

deploy.sh (master orchestrator)
├── local (default)
│   ├── --mock (default): Start mocks, build, deploy, test via HTTPS
│   └── --live: Build, deploy, test via HTTPS (use real services)
├── webhosting
│   └── Build, upload, restart Passenger, test via HTTPS
└── Common flow:
    1. Start infrastructure (mocks if --mock, TLS proxy always)
    2. Build deployment
    3. Deploy (local extract or remote upload)
    4. Start backend (gunicorn or Passenger restart)
    5. Run tests via HTTPS


# 1. Clone repository
git clone git@github.com:user/netcup-api-filter.git
cd netcup-api-filter

# 2. Open in devcontainer (automatic setup)
# VS Code will:
# - Build devcontainer from Dockerfile
# - Run postCreateCommand (installs packages)
# - Source .env.workspace (PUBLIC_FQDN, PHYSICAL_REPO_ROOT, DOCKER_GID)

# 3. Detect public FQDN (if PUBLIC_FQDN not set)
./detect-fqdn.sh --update-workspace  # Populates .env.workspace

# safe clean restart / deploy 
./deploy.sh --stop && ./deploy.sh local | tee deploy.log

# 4. run deployment script
deploy.sh (master orchestrator)
├── local (default)
│   ├── --mock (default): Start mocks, build, deploy, test via HTTPS
│   └── --live: Build, deploy, test via HTTPS (use real services)
├── webhosting
│   └── Build, upload, restart Passenger, test via HTTPS
└── Common flow:
    1. Start infrastructure (mocks if --mock, TLS proxy always)
    2. Build deployment
    3. Deploy (local extract or remote upload)
    4. Start backend (gunicorn or Passenger restart)
    5. Run tests via HTTPS

# 6. Access deployment
echo "Admin UI: https://${PUBLIC_FQDN}/admin/login"
echo "Mailpit: https://${PUBLIC_FQDN}/mailpit/"
echo "Credentials: admin / admin (from .env.defaults)"

# 7. Run tests (optional)
./run-local-tests.sh  # Full test suite (90 tests)
```

## DDNS Protocol Support

Use your router, ddclient, or inadyn with DynDNS2/No-IP protocols:

```bash
# Example: Update device.iot.example.com with auto-detected IP
curl "https://${PUBLIC_FQDN}/api/ddns/dyndns2/update?hostname=device.iot.example.com&myip=auto" \
  -H "Authorization: Bearer naf_<your_token>"

# Response: good 203.0.113.42
```

**Supported:**
- ✅ DynDNS2 protocol (`/api/ddns/dyndns2/update`)
- ✅ No-IP protocol (`/api/ddns/noip/update`)
- ✅ Auto IP detection (respects X-Forwarded-For)
- ✅ IPv6 support (automatic AAAA record handling)
- ✅ Bearer token authentication (no username/password fallback)

**See:** [docs/DDNS_PROTOCOLS.md](docs/DDNS_PROTOCOLS.md) for complete documentation and client configuration examples.

## PowerDNS Self-Managed DNS Backend

PowerDNS provides an alternative to the Netcup API for DNS management:

**Benefits:**
- **Low TTL**: Set as low as 1 second (vs Netcup's 300s minimum)
- **Full control**: No provider constraints or domain transfer risks
- **REST API**: Native HTTP/JSON instead of SOAP
- **Immediate updates**: No propagation delays

**Quick Start:**
```bash
# PowerDNS starts automatically with deploy.sh
# Test API connectivity
curl -sf -H "X-API-Key: $(grep POWERDNS_API_KEY .env.defaults | cut -d= -f2)" \
  http://naf-dev-powerdns:8081/api/v1/servers/localhost | python3 -m json.tool

# Create test zone
cd tooling/backend-powerdns
./setup-zones.sh dyn.vxxu.de

# List zones
curl -s -H "X-API-Key: $(grep POWERDNS_API_KEY .env.defaults | cut -d= -f2)" \
  http://naf-dev-powerdns:8081/api/v1/servers/localhost/zones | python3 -m json.tool

# External access via reverse proxy
curl -sf -H "X-API-Key: YOUR_KEY" \
  https://${PUBLIC_FQDN}/backend-powerdns/api/v1/servers/localhost
```

**DNS Delegation (at parent zone, e.g., Netcup for vxxu.de):**
```dns
dyn.vxxu.de.  IN  NS  ${PUBLIC_FQDN}.
${PUBLIC_FQDN}.  IN  A   <server-public-ip>
```

See `tooling/backend-powerdns/README.md` for complete documentation.

## Document Map (read these, skip the clutter)

- `README.md` – High-level overview (this file).
- `docs/README.md` – Overview of the documentation hub.
- `docs/CONFIGURATION_GUIDE.md` – How configuration, secrets, and fail-fast policies work.
- `docs/OPERATIONS_GUIDE.md` – Day-to-day runbook for building, testing, and deploying.
- `docs/ADMIN_GUIDE.md` – Admin UI walkthrough (user-oriented doc retained as-is).
- `docs/CLIENT_USAGE.md` – Instructions for client token holders and API examples.
- `docs/DDNS_PROTOCOLS.md` – DynDNS2/No-IP protocol documentation with client configuration examples.
- `docs/API_REFERENCE.md` – Complete API reference including DDNS endpoints.
- `PLAYWRIGHT_CONTAINER.md` – Dedicated Playwright container architecture and usage.
- `PYTHON_PACKAGES.md` – Python dependencies and requirements management.
- `AGENTS.md` – Agent instructions and project context (for AI assistants).

Historical summaries (`ITERATION_SUMMARY.md`, `LOCAL_DEPLOYMENT_SUMMARY.md`, etc.) have been retired; use the guides above instead.

## Architecture Snapshot

```
Client token → Access policies → Netcup API Filter → Netcup DNS API
```

The proxy runs as a Flask app (WSGI via Passenger on webhosting, Gunicorn for local validation) with SQLite as the default persistence layer. All configuration flows through environment variables seeded from `.env.defaults` and finalized in the database via the admin UI.

## Testing & Validation Cheatsheet

- `./run-local-tests.sh` – Full pytest suite against the locally extracted deployment.
- `bash tooling/run-ui-validation.sh` – Spins up Gunicorn, TLS proxy, and Playwright to exercise the UI end-to-end.
- `pytest ui_tests/tests -m "not e2e_local"` – Browser tests that do not require the mock Netcup services (useful against staging/prod).
- `pytest ui_tests/tests -m e2e_local` – Requires the mock API + SMTP stack and is intended for local full-stack validation.

See `OPERATIONS_GUIDE.md` for environment variables and troubleshooting tips.

## Security Expectations

- Everything is config-driven; add new settings only through `.env.defaults` + overrides.
- Scripts error out when required variables are missing (fail-fast). Fix the error, export the variable, rerun.
- Default admin credentials and the test client are defined in `.env.defaults` and reset on every deployment. Change them immediately on live systems.
- Always run behind HTTPS in production; use the bundled TLS proxy workflow for local parity.

## License & Support

- License: MIT
- Questions about the upstream API? See https://helpcenter.netcup.com/en/wiki/domain/our-api

PRs and issues are welcome—just make sure new docs update the guide set listed above.
