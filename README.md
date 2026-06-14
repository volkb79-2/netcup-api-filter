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

## Quick Start - Installation

Initial Setup Flow for fresh installation via provided `deploy.zip` package:

1. Extract deploy.zip → Access site
2. Login: admin/admin → Forced password change
3. Dashboard → See 2FA warning banner
4. Click "Set Up Authenticator App (TOTP)" → Scan QR code
5. Configure Netcup API credentials
6. Configure Email SMTP (optional)
7. System ready for use


## Quick Start - Development

`deploy.sh` is the master orchestrator (build → deploy → test). Its shape:

```
deploy.sh (master orchestrator)
├── local (default)
│   ├── --mock (default): start mocks, build, deploy, test via HTTPS
│   └── --mode live    : build, deploy, test via HTTPS using real services
├── webhosting          : build, upload, restart Passenger, test
└── Common phases: infra → build → deploy → start (gunicorn/Passenger) → tests
```

```bash
# 1. Clone and open in the devcontainer (VS Code builds it and runs post-create,
#    which installs packages and generates .env.workspace: PUBLIC_FQDN,
#    PHYSICAL_REPO_ROOT, DOCKER_GID). The public FQDN is auto-detected there.
git clone git@github.com:user/netcup-api-filter.git
cd netcup-api-filter

# 2. Clean restart + local deploy (mocked services by default)
./deploy.sh --stop && ./deploy.sh local | tee deploy.log

# 3. Access the deployment
echo "Admin UI:    https://${PUBLIC_FQDN}/admin/login"
echo "Mailpit:     https://${PUBLIC_FQDN}/mailpit/"
echo "Credentials: admin / admin (fresh deploy; forced password change)"

# 4. Run the UI test suite directly (optional; deploy.sh also runs it)
./run-local-tests.sh                 # build + run ui_tests against deploy-local
./run-local-tests.sh --with-mocks    # also start mock services
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

## Upgrading an Existing Deployment (Database Migrations)

The app does not use Alembic. On startup, after `db.create_all()`, it runs a lightweight
automatic migration (`run_lightweight_migrations` in `database.py`) that adds any columns or
indexes present in the models but missing from the existing SQLite file. This means you can
upgrade a deployment that keeps its `netcup_filter.db` across releases without getting
`OperationalError: no such column` errors on the first request after the update.

**What the auto-migration handles:**
- Adding nullable columns (new column gets `NULL` for all existing rows).
- Adding columns with a scalar default (e.g. `INTEGER DEFAULT 0`).
- Creating new single-table indexes declared in the models.

**What it does NOT handle (requires a hand-written migration):**
- Dropping columns or renaming them.
- Changing a column's type.
- Adding a `NOT NULL` column without a scalar default.
- Data backfills (transforming existing row values).

If a release note mentions one of those operations, apply the migration manually before (or
immediately after) restarting the app. The lightweight migrator logs every `ALTER TABLE` it
executes at `WARNING` level so you can verify what was applied.

## Testing

Two independent test suites; run them separately:

| Type | What it checks | Framework | Count | Speed |
|---|---|---|---|---|
| Unit + property | Pure functions, parsing, validation invariants | pytest + Hypothesis | 355 | <1 min total |
| Route smoke | Every Flask route returns the correct HTTP status | Playwright | 86 | Medium |
| Widget | Individual UI components in isolation | Playwright | 19 | Medium |
| Round-trip | UI action → backend state verified via 3 independent channels | Playwright | ~30 | Medium |
| Security | Auth, 2FA, recovery codes, IP allowlist, attack attribution | Playwright | ~60 | Medium |
| Feature E2E | Full feature workflows (registration, DNS, email, audit) | Playwright | ~200 | Slow |
| Journey | Multi-step stateful scenario suites (j1/j2/j3) | Playwright | ~20 | Slow |
| Nonfunctional | Accessibility + performance | Playwright | ~20 | Slow |
| Upstream resilience | netcup_client / filter_proxy bad-response paths | pytest + mock | ~15 | <30 s |
| Mocks / live | Mock-service self-tests + real-backend tests | Playwright | ~15 | Varies |
| **Total (ui_tests)** | | | **450** | |

**Key commands:**

```bash
pytest tests/                                  # unit + property (355 tests, no app needed)
HYPOTHESIS_PROFILE=dev pytest tests/           # Hypothesis with 500 examples/property
pytest ui_tests/tests                          # full Playwright suite (requires running deployment)
pytest ui_tests/tests -m smoke                 # route-smoke + widget smoke (fast)
pytest ui_tests/tests -m roundtrip             # backend-truth round-trip tests
pytest ui_tests/tests -m security              # auth, 2FA, recovery, allowlist
pytest ui_tests/tests -m ci_smoke              # 93-test CI subset
pytest ui_tests/tests -m upstream_resilience   # bad upstream-response paths
./run-local-tests.sh --with-mocks              # full local run: build + deploy + all tests
```

The `ui_tests/tests/` directory uses a **bucket schema**: `smoke/ roundtrip/ security/ features/
journeys/ nonfunctional/ live/ mocks/`. Select any bucket with `-m <marker>` regardless of path.

See `docs/TESTING_INFRASTRUCTURE.md` for full suite details and CI job configuration.

## Security Expectations

- Everything is config-driven; add new settings only through `.env.defaults` + overrides.
- Scripts error out when required variables are missing (fail-fast). Fix the error, export the variable, rerun.
- Default admin credentials and the test client are defined in `.env.defaults` and reset on every deployment. Change them immediately on live systems.
- Always run behind HTTPS in production; use the bundled TLS proxy workflow for local parity.

## License & Support

- License: MIT
- Questions about the upstream API? See https://helpcenter.netcup.com/en/wiki/domain/our-api

PRs and issues are welcome—just make sure new docs update the guide set listed above.
