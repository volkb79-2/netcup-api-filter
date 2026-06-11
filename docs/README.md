# Documentation Hub

Living documentation for netcup-api-filter. Start with [`../AGENTS.md`](../AGENTS.md) for
the architecture overview, then dive into the relevant guide below.

> Treat these as the single source of truth. When behaviour changes, update the matching
> guide here. Historical / superseded write-ups live in [`deprecated/`](deprecated/) — read
> them for context, but don't update them and don't link them as current.

## Architecture & onboarding

- [`../AGENTS.md`](../AGENTS.md) — project orientation, architecture, conventions (read first).
- [`../README.md`](../README.md) — top-level overview and quick start.
- [`../CHANGELOG.md`](../CHANGELOG.md) — dated change history.

## Configuration

- [`CONFIGURATION_GUIDE.md`](CONFIGURATION_GUIDE.md) — config layers and the `.env.defaults` → env → DB hierarchy.
- [`TOML_CONFIGURATION.md`](TOML_CONFIGURATION.md) — first-start `app-config.toml` seeding (`[[users]]`, `[[backends]]`, `[[domain_roots]]`).
- [`CONFIGURATION_SEEDING.md`](CONFIGURATION_SEEDING.md) — the one-time TOML import mental model.
- [`FAIL_FAST_PRINCIPLE.md`](FAIL_FAST_PRINCIPLE.md) — the no-silent-fallback config convention.
- [`ENV_WORKSPACE.md`](ENV_WORKSPACE.md) · [`FQDN_DETECTION.md`](FQDN_DETECTION.md) — auto-generated `.env.workspace` and public-FQDN detection.

## API & clients

- [`API_REFERENCE.md`](API_REFERENCE.md) — REST DNS API and endpoints.
- [`DDNS_PROTOCOLS.md`](DDNS_PROTOCOLS.md) — DynDNS2 / No-IP compatible DDNS endpoints.
- [`CHARSET_VALIDATION.md`](CHARSET_VALIDATION.md) — username/password/token formats and validation rules.
- [`../CLIENT_TEMPLATES.md`](../CLIENT_TEMPLATES.md) — pre-configured realm/token templates in the admin UI.

## Security

- [`SECURITY.md`](SECURITY.md) — threat model, controls, and known gaps (start here).
- [`SECURITY_IMPROVEMENTS_2FA.md`](SECURITY_IMPROVEMENTS_2FA.md) — 2FA hardening (lockout, session regen, recovery codes).
- [`SECURITY_ERROR_TAXONOMY.md`](SECURITY_ERROR_TAXONOMY.md) — auth error codes, severities, attack attribution.
- [`RATE_LIMITING.md`](RATE_LIMITING.md) — rate-limit configuration and hierarchy.
- [`TELEGRAM_LINKING.md`](TELEGRAM_LINKING.md) · [`TELEGRAM_BOT_SETUP.md`](TELEGRAM_BOT_SETUP.md) — Telegram 2FA/notification linking and bot setup.
- [`SECURITY_ISSUE_2FA_LOCKOUT_NOTIFICATIONS.md`](SECURITY_ISSUE_2FA_LOCKOUT_NOTIFICATIONS.md) — backlog spec (lockout alerts, not yet implemented).

## Admin & UI

- [`ADMIN_GUIDE.md`](ADMIN_GUIDE.md) — admin UI walkthrough for operators.
- [`ADMIN_UI_UX_REVIEW.md`](ADMIN_UI_UX_REVIEW.md) — template inventory, theme/density system.
- [`UI_REQUIREMENTS.md`](UI_REQUIREMENTS.md) — design-system spec and route↔template map.
- [`TEMPLATE_CONTRACT.md`](TEMPLATE_CONTRACT.md) — template naming conventions and required context vars.

## Deployment & operations

- [`DEPLOYMENT_WORKFLOW.md`](DEPLOYMENT_WORKFLOW.md) — `deploy.sh` build/test/deploy runbook (canonical).
- [`DEPLOY_ARCHITECTURE.md`](DEPLOY_ARCHITECTURE.md) — deployment phases and package layout.
- [`GUNICORN_CONFIG.md`](GUNICORN_CONFIG.md) — local gunicorn tuning.
- [`CERTIFICATE_MOUNTING.md`](CERTIFICATE_MOUNTING.md) · [`DOCKER_NETWORKS.md`](DOCKER_NETWORKS.md) — local TLS proxy and container networking.
- [`SSH_AGENT_PERSISTENCE.md`](SSH_AGENT_PERSISTENCE.md) — persistent SSH agent in the devcontainer.

## Testing

- [`TESTING_LESSONS_LEARNED.md`](TESTING_LESSONS_LEARNED.md) — **read before writing Playwright auth/2FA tests**.
- [`TESTING_INFRASTRUCTURE.md`](TESTING_INFRASTRUCTURE.md) — flask-manager / reset / installation-test tooling.
- [`JOURNEY_CONTRACTS.md`](JOURNEY_CONTRACTS.md) — end-to-end journey definitions.
- [`PARALLEL_SESSION_STRATEGY.md`](PARALLEL_SESSION_STRATEGY.md) — multi-session test harness.
- [`UI_TESTING_GUIDE.md`](UI_TESTING_GUIDE.md) · [`WEBHOSTING_TESTING_GUIDE.md`](WEBHOSTING_TESTING_GUIDE.md) — screenshot/UX validation and HTTPS-target testing.
- [`PLAYWRIGHT_MCP_SETUP.md`](PLAYWRIGHT_MCP_SETUP.md) · [`PLAYWRIGHT_WAITING_PATTERNS.md`](PLAYWRIGHT_WAITING_PATTERNS.md) · [`../PLAYWRIGHT_CONTAINER.md`](../PLAYWRIGHT_CONTAINER.md) — Playwright container and patterns.
- [`MAILPIT_CONFIGURATION.md`](MAILPIT_CONFIGURATION.md) — SMTP capture for email tests.

## Repository root

- [`../PYTHON_PACKAGES.md`](../PYTHON_PACKAGES.md) — dependencies and requirements files.
- [`../PLAYWRIGHT_CONTAINER.md`](../PLAYWRIGHT_CONTAINER.md) — Playwright container architecture.
