# Changelog

## [Unreleased] — Testing-overhaul plan — 2026-06-12

### Documentation

- **Added `docs/plans/testing-overhaul/`** — full test-suite audit findings and a 14-task
  execution plan as self-contained agent specs (`tasks/T01…T14`). Scope: fix broken/dead test
  tooling, unit coverage for untested security logic (`check_permission`, DDNS parsing,
  migrations, validators), a read-only backend-verification channel for E2E tests
  (`ui_tests/verification.py`), 12 cross-role round-trip tests (admin action → user's
  API/portal verifiably changes), smoke-suite consolidation behind route discovery, and a CI
  `e2e-smoke` job. Plan only — no test or code changes yet; tasks execute sequentially per
  `PLAN.md`.

## [Unreleased] — Security & reliability fixes — 2026-06-11

### Security

- **Telegram callback: constant-time secret comparison.** The `POST /api/telegram/link`
  endpoint now compares `X-NAF-TELEGRAM-SECRET` with `hmac.compare_digest` to prevent
  timing-based secret discovery. The endpoint is rate-limited (same `api_rate_limit` as the
  DNS API, default 60/min) to prevent brute-forcing the secret.

- **Telegram placeholder secret rejected on non-local deployments.** The public placeholder
  value (`local-test-telegram-callback-secret-change-me`) shipped in `.env.defaults` is now
  rejected at runtime on any deployment where `DEPLOYMENT_TARGET != local`. Telegram linking
  stays disabled and returns 503 until a real secret is configured. Production must set a
  strong, unique `TELEGRAM_LINK_CALLBACK_SECRET`.

- **Telegram chat_id uniqueness enforced.** A Telegram chat_id can only be linked to one
  account. Attempting to link a chat already bound to another account returns HTTP 409 instead
  of silently rebinding the chat. This prevents a single Telegram chat from receiving 2FA codes
  or security alerts for multiple accounts.

- **Telegram linking audit-logged.** Successful `telegram_linked` events are now written to
  the activity log (severity `medium`) so the admin audit trail reflects when a 2FA channel
  was bound to an account.

- **DNS authorization enforces hostname scope, not just zone.** Token authorization now
  enforces the realm's hostname scope for write operations:
  - `host` — exact FQDN only.
  - `subdomain` — apex plus all children.
  - `subdomain_only` — children only, not the apex.
  Previously only the DNS zone (`matches_domain`) was checked; a `host`-scoped token could
  write any record in the zone. The new `hostname_denied` error code (severity `high`) is
  logged and triggers user notification.

- **Expired domain-root grants no longer authorize access.** Grant expiry is now enforced in
  authorization checks; expired grants are excluded the same way revoked grants are.

### Reliability

- **Automatic lightweight database migration on startup.** After `db.create_all()`, the app
  now runs `run_lightweight_migrations()` which adds any columns and single-table indexes
  present in the models but missing from the existing SQLite file. Upgrading a deployment that
  keeps its `netcup_filter.db` no longer fails with `OperationalError: no such column` on the
  first query. Limitation: only additive nullable/scalar-default columns and simple indexes —
  drops, renames, type changes, NOT NULL without a default, and data backfills still need a
  hand-written migration.

- **GeoIP API URL falls back to environment variable when admin field is blank.** When the
  `geoip_config.api_url` setting is saved as empty in admin settings, the service now falls
  back to `MAXMIND_API_URL` env var before using the hardcoded MaxMind production host. A
  configured mock/proxy endpoint is honored even if the admin UI field is cleared.

### Behavior

- **Telegram 2FA only offered when delivery is possible.** At login, Telegram is offered as a
  2FA method only when `TELEGRAM_NOTIFICATIONS_ENABLED=true` AND `TELEGRAM_BOT_TOKEN` is set.
  An account that has Telegram linked while notifications are globally disabled will not see
  Telegram in the 2FA prompt; email, TOTP, and recovery codes continue to work.

- **Telegram link token stable across page refreshes.** The one-time link token is now reused
  for the duration of its TTL: reloading the link page or opening it in a second tab returns
  the same deep-link instead of rotating the token. A new token is only issued when the cached
  one has expired.

- **Revoked domain-root grants can be re-granted.** Using the Add Grant form on an account that
  previously had its grant revoked now reactivates the existing row instead of attempting a
  duplicate insert (which would hit the unique constraint and fail). The reactivation is
  audit-logged as `domain_root_grant_reinstated`.

- **Domain-root grant expiry is inclusive end-of-day.** When setting an expiry date on a grant,
  the date is stored as 23:59:59 of that day (UTC), so a grant dated for today remains valid
  for the entire day.

### Added

- **DNS/DDNS API rate limiting.** The Bearer-token DNS (`/api/dns/*`) and DDNS (`/api/ddns/*`)
  blueprints are now rate-limited per IP (`api_rate_limit`, default 60/min) — previously they
  fell under only the global default. A stolen or misbehaving token can no longer hammer the
  provider backend.

- **2FA lockout notifications.** When an account is locked after repeated failed 2FA attempts,
  the affected user is notified (email + Telegram if opted in) and, optionally, an operator
  (`NOTIFY_USER_ON_2FA_LOCKOUT` / `NOTIFY_ADMIN_ON_2FA_LOCKOUT` / `ADMIN_SECURITY_EMAIL`). Fired
  once, from `increment_2fa_failures`, covering both the account and admin 2FA paths.

- **Background notification delivery.** The synchronous Telegram send is now dispatched off the
  request thread (email was already async), so a slow/unreachable endpoint never blocks a
  request. `NOTIFICATIONS_SYNC=true` (and `FLASK_ENV=local_test`) force synchronous delivery for
  deterministic tests.

- **Env-configurable password policy.** `PASSWORD_MIN_LENGTH` and `PASSWORD_MIN_ENTROPY` are now
  read from the environment (defaults 20 / 100 bits), parsed defensively. The admin
  account-creation path now validates against this canonical policy instead of a weaker
  hardcoded `len < 12` check.

- **Continuous integration.** A GitHub Actions workflow runs the `tests/` unit suite with
  coverage (`pytest-cov`) and a compile gate on every push/PR.

### Changed

- **Realm templates single-sourced.** The DNS realm presets (DDNS single host, subdomain
  delegation, read-only, LetsEncrypt DNS-01, full management, CNAME delegation) are now defined
  once in `realm_templates.py` and consumed by both the admin and account portals, replacing
  divergent hardcoded copies.

- **In-memory SQLite supported in tests.** `init_db()` no longer sets `pool_size` on the
  StaticPool used for in-memory databases (which rejected it), unblocking in-memory test setups.

### Documentation

- **`AGENTS.md` rewritten** (920 → ~210 lines): architecture-first, accurate scripts/commands,
  a canonical-docs map, and a "keep docs in sync" definition-of-done.
- **Docs consolidated** from 71 to ~37 active guides: 6 empty stubs deleted, ~32 stale
  point-in-time/old-architecture write-ups archived to `docs/deprecated/`, dead links repointed.
- **New `docs/FEATURES.md`** — canonical capability + roadmap map.
- **`docs/SECURITY.md` rewritten** to match the implementation (it described a removed
  `config.yaml`/`filter_proxy` architecture), with an honest "Not yet implemented" list.
- Corrected stale claims across the canonical docs (rate-limit defaults, env var names, GeoIP
  field, deploy flags, the "admin CRUD not implemented" note — that CRUD exists).

### Known gaps / roadmap

Tracked in [`docs/FEATURES.md`](docs/FEATURES.md): additional DNS backends (Cloudflare, Route53);
data-preserving in-place upgrades (deploys are intentionally greenfield today); encryption at
rest for TOTP secrets (candidate: filesystem master key on the webspace); self-service 2FA
unlock; background dispatch for the remaining notification paths.
