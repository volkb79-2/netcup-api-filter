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

## Quick Start

1. **Clone & enter**
   ```bash
   git clone https://github.com/volkb79-2/netcup-api-filter.git
   cd netcup-api-filter
   ```
2. **Prepare environment** – copy `.env.defaults` to `.env.workspace`, fill in secrets, and `source .env.workspace`.
3. **Run local package build + smoke tests**
   ```bash
   ./build-and-deploy-local.sh
   ./run-local-tests.sh
   ```
4. **Need browser coverage?** Export the required `UI_*` variables and run `bash tooling/run-ui-validation.sh` for the HTTPS + Playwright flow.
5. **Deploy** with `./build-and-deploy.sh` once the local suite passes (see `OPERATIONS_GUIDE.md`).

## Document Map (read these, skip the clutter)

- `README.md` – High-level overview (this file).
- `docs/README.md` – Overview of the documentation hub.
- `docs/CONFIGURATION_GUIDE.md` – How configuration, secrets, and fail-fast policies work.
- `docs/OPERATIONS_GUIDE.md` – Day-to-day runbook for building, testing, and deploying.
- `docs/ADMIN_GUIDE.md` – Admin UI walkthrough (user-oriented doc retained as-is).
- `docs/CLIENT_USAGE.md` – Instructions for client token holders and API examples.
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
