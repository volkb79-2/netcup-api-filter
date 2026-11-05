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

- Release and webhosting deployment follow the `cmru` and `ciu` workflows in [`DEPLOYMENT_WORKFLOW.md`](DEPLOYMENT_WORKFLOW.md); no env file is shipped or copied to the webhoster except the generated `app-defaults.env`.
- The e2e suite takes no target or credentials from the environment: it starts its own app per session and provisions random personas (`E2E_*` keys in `.env.defaults`; see [`TESTING_INFRASTRUCTURE.md`](TESTING_INFRASTRUCTURE.md)). Only `PLAYWRIGHT_SERVER_WS` and the mock-service URLs are forwarded by `run-gate.toml`.
- **Shipped defaults catalog**: `.env.defaults` is never shipped (it holds the documented pre-set admin password and test fixtures). Builds write `app-defaults.env` into every shipped tree instead — an **allowlist**: only the keys in `config_defaults.RUNTIME_DEFAULT_KEYS` (the keys the running app resolves through `get_default`/`require_default`/`load_defaults`), and never a credential-like name (`PASSWORD`, `SECRET`, `TOKEN`, `API_KEY`, …). A new `.env.defaults` key does not ship until it is added there; keys the app reads only from the environment never need to ship. There is no `SECRET_KEY` default anywhere. `config_defaults` reads it first, so `require_default()` keeps working in a deployment; environment variables still override every value. `tests/test_shipped_defaults.py` fails when runtime code reads a key the allowlist lacks, or when a non-runtime/credential key would ship.
- Host-edge settings are operator infrastructure, not naf application settings. Exposed ciu
  stacks join `ingress_public` and use Traefik labels; TLS and certificates remain owned by
  the host edge. See [`DEV_INFRA_SETUP.md`](DEV_INFRA_SETUP.md).

When unsure, run the script once—its fail-fast message will identify the missing variable and usually suggest the exact file to source.

## Session & Security Settings

Session cookie behavior stays config-driven via env vars:

- `FLASK_SESSION_COOKIE_SECURE=auto` switches between Secure cookies when HTTPS is available and HTTP for `FLASK_ENV=local_test`.
- `FLASK_SESSION_COOKIE_HTTPONLY`, `FLASK_SESSION_COOKIE_SAMESITE`, and `FLASK_SESSION_LIFETIME` (seconds) control browser session handling.
- `ADMIN_LOGIN_LOCKOUT_THRESHOLD` (default `5`) and `ADMIN_LOGIN_LOCKOUT_MINUTES` (default `15`) control the admin login brute-force lockout. They are read at call time (environment first, then `.env.defaults`); a non-integer or `< 1` value raises an error instead of silently defaulting.
- Timeouts, rate limits, and admin/client credentials all follow the same pattern.

Whenever you add a new security-relevant constant, update `.env.defaults`, document it in this guide, and use `os.environ[...]` (or equivalent) in code.

## Bootstrap admin, first start and SECRET_KEY

Every database is initialized by one idempotent function, `bootstrap.instance.init_instance()`:
schema + lightweight migrations, enum tables and backend providers, default settings (absent keys
only), the administrator, and (local stacks only) the Mailpit email config. Its callers differ only
in where the administrator comes from:

| Artifact / caller | Administrator | Notes |
|---|---|---|
| Passenger tarball (`cmru release`) | the **pre-set admin** `DEFAULT_ADMIN_USERNAME` / `DEFAULT_ADMIN_PASSWORD` / `DEFAULT_ADMIN_EMAIL` from `.env.defaults`, `must_change_password` | the only account in the tarball. The first login must replace the password (and set the 2FA email). No demo data. |
| Local golden DB (`run-gate local-build`) | same pre-set admin + Mailpit email config | `deploy-local/netcup_filter.db`; never served, the e2e gate copies it per session |
| OCI image / any fresh container (first start) | **operator-configured**, no default: `NAF_BOOTSTRAP_ADMIN_USERNAME`, `NAF_BOOTSTRAP_ADMIN_EMAIL` and `NAF_BOOTSTRAP_ADMIN_PASSWORD_FILE` (a mounted secret; `NAF_BOOTSTRAP_ADMIN_PASSWORD` also accepted, not both), or an `[[users]]` entry with `is_admin = true` and an explicit password in `app-config.toml` | created only when the DB has no admin yet; `must_change_password` off (the operator chose the password). Without either source the start **fails** with a message naming these keys. |
| ciu app stack (`tooling/app-local`) | as the OCI image, with the password a ciu `GEN_LOCAL` secret | its `post_compose` hook runs `python -m netcup_api_filter.bootstrap init` inside the container: creates the admin from the secret on first run only (to rotate it: `ciu clean` the volumes, then `up` fresh); mail config for Mailpit (created once; SMTP changes made in the admin UI are kept). The hook never passes `--enforce-admin`, so a re-run changes no state. It prints the secret's store path, never the value. |

A configured bootstrap admin is a **first-start input only**: an initialized database never gets a
second admin from it, and its password is never reset — except through the explicit operator
command `python -m netcup_api_filter.bootstrap init --enforce-admin` (not used by any hook). Admin usernames are not bound by the portal's
self-registration rules (the shipped default is the short `admin`).

A new bootstrap admin has no 2FA method. For the shipped tarball admin the forced first-login change
enables email 2FA when an email is entered there. A **configured** bootstrap admin (env/TOML,
`must_change_password` off) never passes that page: it logs in without 2FA, the admin dashboard shows
the "no 2FA" warning banner, and the admin must set up TOTP (admin account security page) — email 2FA
is not switched on automatically, because a broken SMTP configuration would then lock the only admin
out. A configured password must satisfy the product password policy (`models.validate_password`:
length, allowed characters, entropy); a weaker one fails the start with the rule that was violated.

**First start is serialized and fatal on error.** Every process that opens the database
(gunicorn workers — `preload_app` is off —, Passenger processes, the hook's CLI) runs the
initializer under an exclusive `flock` on `<db>.init.lock` (`bootstrap/init_lock.py`): exactly one
initializes a fresh database, the others wait (at most `NAF_INIT_LOCK_TIMEOUT_SECONDS`) and then
find it initialized. If initialization fails (no bootstrap admin configured, unreadable database,
lock timeout, an `app-config.toml` that cannot be claimed), `passenger_wsgi` re-raises after
logging the traceback: under gunicorn the worker fails to boot and the master exits non-zero
("Worker failed to boot"), so a container stops (or restarts) visibly; Passenger shows its own
generic error page. No error text is ever rendered into an HTTP response.

**SECRET_KEY** (sessions, CSRF): `SECRET_KEY_FILE` (mounted secret) or `SECRET_KEY` (not both,
at least 16 characters). Unset, the app creates a random key **once** in `settings.secret_key`
(`INSERT OR IGNORE`, so all gunicorn workers agree) and reuses it; `scripts/activate.py` carries
that row across greenfield webhosting releases. There is no published default key.

**Local Mailpit config** (local builds and the app stack only): host from `SERVICE_MAILPIT`
(`.env.services`), `LOCAL_MAILPIT_SMTP_PORT`, `LOCAL_MAIL_FROM`, `LOCAL_MAIL_ADMIN_EMAIL`.

**Local mock Netcup backend** (local/e2e builds only, never the tarball or OCI image): URL from
`MOCK_NETCUP_API_URL` (environment or `.env.services`; the local build fails without it), credentials
and timeout from `LOCAL_MOCK_NETCUP_CUSTOMER_ID` / `_API_KEY` / `_API_PASSWORD` / `_TIMEOUT`
(the mock's public test values; `LOCAL_` keys are never shipped). Stored as `netcup_config`.

Test personas (admin, portal user, read-only client) are **not** seeded into any artifact: the e2e
gate provisions them per session (see `docs/TESTING_INFRASTRUCTURE.md`).

## Adding New Configuration

When a feature requires new settings:

1. **Define the variable** in `.env.defaults` with a sensible example value and comment.
2. **Document it** in this guide under an appropriate section (Security, Email, Proxy, etc.).
3. **Consume it** in code using the `os.environ[...]` helpers (or the existing `config` utilities) and avoid fallbacks—require callers to provide it.
4. **Expose overrides** where relevant (admin UI fields, deployment scripts, tests) so every environment can set it without editing code.
5. **Test it** via `run-gate local-build` (HTTP) and `run-gate e2e` (Playwright) to ensure defaults and overrides behave as expected.

Following these steps keeps the entire system consistent with the configuration-driven policy and prevents regressions across deployments.
