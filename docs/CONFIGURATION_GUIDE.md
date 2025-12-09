# Configuration Guide

> Core reference for configuration, secrets, and environment preparation. Lives in `/docs` alongside `OPERATIONS_GUIDE.md`, `ADMIN_GUIDE.md`, and `CLIENT_USAGE.md`.

## Core Principles

- **100% config-driven** – No hardcoded defaults anywhere in the codebase. Every runtime decision must originate from `.env.defaults`, an environment override, or data in the database (set via the admin UI).
- **Fail fast** – Missing configuration stops scripts immediately. We never fall back silently; every required variable must be exported explicitly.
- **Single source of truth** – `.env.defaults` is version-controlled and documents every supported variable plus sensible defaults for local work. Each environment overrides values via its own `.env.*` file (not committed) or through the admin UI after bootstrap.

See `AGENTS.md` for the rationale enforced by the automation agents.

## Configuration Layers

1. **`.env.defaults`** – Checked into git. Defines the full catalog of variables with safe defaults for dev/local parity (admin credentials, seeded client, session flags, rate limits, etc.). Never edit these values for environment-specific tweaks—create overrides instead.
2. **Workspace overrides (`.env.workspace`, `.env.local`, etc.)** – Not committed. Load one of these before running any scripts: `source .env.workspace`. Use these files to supply secrets (Netcup credentials, SMTP values) or to change behavior (hostnames, TLS domains).
3. **Runtime database settings** – After bootstrap, the admin UI writes to the database: admin password rotation, client scopes, rate-limit policies, SMTP credentials, etc. Database entries win over env files at runtime, so always double-check the admin UI when troubleshooting.

The precedence for any setting is: `env override > database value > .env.defaults`.

## Required Variables for Tooling

Scripts intentionally abort unless every variable they rely on is exported. Common ones:

- `DEPLOYMENT_ENV_FILE` – Points to the env file that mirrors the target deployment (`.env.local`, `.env.webhosting`, etc.). Required by `build-and-deploy*.sh`, `run-local-tests.sh`, UI tests, and screenshot capture.
- `UI_*` variables – Used by `tooling/run-ui-validation.sh` and `ui_tests/tests`. Export `UI_BASE_URL`, `UI_ADMIN_USERNAME`, `UI_ADMIN_PASSWORD`, `UI_CLIENT_ID`, `UI_CLIENT_TOKEN`, `UI_CLIENT_DOMAIN`, `UI_SCREENSHOT_PREFIX`, `PLAYWRIGHT_HEADLESS`, and `KEEP_UI_STACK` before running the validation script.
- `LOCAL_PROXY_*` variables – Provide host/port/domain bindings for the local TLS proxy as described in `tooling/reverse-proxy/proxy.env`.

When unsure, run the script once—its fail-fast message will identify the missing variable and usually suggest the exact file to source.

## Session & Security Settings

Session cookie behavior stays config-driven via env vars:

- `FLASK_SESSION_COOKIE_SECURE=auto` switches between Secure cookies when HTTPS is available and HTTP for `FLASK_ENV=local_test`.
- `FLASK_SESSION_COOKIE_HTTPONLY`, `FLASK_SESSION_COOKIE_SAMESITE`, and `FLASK_SESSION_LIFETIME` (seconds) control browser session handling.
- Timeouts, rate limits, TLS proxy values, and admin/client credentials all follow the same pattern.

Whenever you add a new security-relevant constant, update `.env.defaults`, document it in this guide, and use `os.environ[...]` (or equivalent) in code.

## Preseeded Accounts & Test Clients

The build pipeline seeds the database using the values from `.env.defaults`:

- **Admin user** – Default username/password (`ADMIN_DEFAULT_USERNAME`, `ADMIN_DEFAULT_PASSWORD`). The first login forces a password change, and UI tests expect the rotated password stored under `/screenshots/.env.webhosting` when running against staging/production-like targets.
- **Preseeded client** – `DEFAULT_TEST_CLIENT_ID`, `DEFAULT_TEST_CLIENT_TOKEN`, `DEFAULT_TEST_CLIENT_DOMAIN`, `DEFAULT_TEST_CLIENT_OPERATIONS`, and related realm variables create a ready-to-use client for smoke testing and automated flows.

If you change any of these defaults, also update the Playwright environment variables or the UI tests will fail.

## Adding New Configuration

When a feature requires new settings:

1. **Define the variable** in `.env.defaults` with a sensible example value and comment.
2. **Document it** in this guide under an appropriate section (Security, Email, Proxy, etc.).
3. **Consume it** in code using the `os.environ[...]` helpers (or the existing `config` utilities) and avoid fallbacks—require callers to provide it.
4. **Expose overrides** where relevant (admin UI fields, deployment scripts, tests) so every environment can set it without editing code.
5. **Test it** via `run-local-tests.sh` (HTTP) and `tooling/run-ui-validation.sh` (HTTPS + Playwright) to ensure defaults and overrides behave as expected.

Following these steps keeps the entire system consistent with the configuration-driven policy and prevents regressions across deployments.
