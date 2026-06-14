# Changelog

## [Unreleased] — Testing hardening (E1–E4, P1–P4, M1–M2) — 2026-06-14

Testing infrastructure hardened in six areas. No functional app changes except one bug fix.

### Added

- **Property-based testing (Hypothesis)** — three new modules: `tests/test_ddns_property.py`,
  `tests/test_validators_property.py`, `tests/test_token_model_property.py` (~86 properties
  total). Default Hypothesis profile `ci` (50 examples); set `HYPOTHESIS_PROFILE=dev` for 500.
  Profiles registered in `tests/conftest.py`. `hypothesis>=6.100` added to
  `requirements-dev.txt`. Runs in the existing `unit-tests` CI job (no new services required).
- **New security round-trip tests** — `ui_tests/tests/security/test_ip_allowlist_enforcement.py`
  (new). `test_recovery_codes.py`, `test_account_2fa_disable.py`, `test_2fa_security.py`,
  `test_api_security.py`, `test_security_scenarios.py`, and several `features/` tests now carry
  Channel-A/C backend-truth assertions (DB-row checks + DNS API / mock-backend state).
- **Mutation spot-check tooling** — `tooling/mutation/run.sh` wraps mutmut 3.6.0 for periodic
  single-module mutation testing. Local-only; NOT wired into CI or `pytest.ini`. Results and
  22 new killing tests from the M2 run (5 modules, ~1 637 mutants) documented in
  `docs/plans/testing-hardening/MUTATION_REPORT.md`.

### Changed

- **E2E bucket schema (E2)** — `ui_tests/tests/` is now organised into eight named bucket
  subdirectories (`smoke/ roundtrip/ security/ features/ journeys/ nonfunctional/ live/ mocks/`).
  Each test module carries a `pytestmark` bucket marker. Markers registered in `pytest.ini`:
  `smoke roundtrip security feature journey nonfunctional mock_selftest` (plus the existing
  `live ci_smoke e2e_local installation`). Select any bucket with `-m <marker>`.
  Total `ui_tests` collection: **450** tests; `pytest tests/` unit suite: **355**.

### Fixed

- **`dns_api.py` error_code logging** — permission-denied branches now log `error_code` in
  the activity log so Channel-A assertions can verify the exact refusal reason.

### Removed

- **Legacy `ui_tests/journeys/` directory** (E1) — `test_00`–`test_09` and the legacy conftest
  deleted. Journey tests now live exclusively under `ui_tests/tests/journeys/` (j1/j2/j3 +
  `test_journey_master.py`).
- **`ui_tests/tests/test_registration_2fa_complete.py`** (E1) — superseded by
  `features/test_registration_e2e.py`.
- **Nine duplicate test files merged into bucket targets** (E3): `test_security.py`,
  `test_api_proxy.py`, `test_multi_backend_dns.py`, `test_2fa_enabled_flows.py`,
  `test_admin_totp_and_recovery_codes.py`, `test_account_2fa_routes.py`,
  `test_admin_login_2fa_routes.py`, `test_admin_audit_and_logs.py`,
  `test_public_misc_routes.py`. Also `test_holistic_coverage.py` renamed to
  `smoke/test_screenshot_capture_and_ux.py`.

---

## [Unreleased] — Testing overhaul (T01–T13) — 2026-06-12

End-to-end testing overhaul across 13 sequential tasks. No functional app changes;
all changes are tests, tooling, CI, and test infrastructure.

### Added

- **Unit test suite** (`tests/`) now covers the previously untested security-critical
  paths: `token_auth.check_permission()` / `authenticate_token()` / `check_ip_allowed()`,
  `AccountRealm.matches_domain()`, `run_lightweight_migrations()`, DDNS hostname parsing,
  netcup client response-envelope helpers, `utils` validators, recovery codes, and
  password entropy — 200+ new cases across T02–T06.
- **`tests/conftest.py`** — shared app/client/db fixtures and `make_account` / `make_realm` /
  `make_token` factories so new unit tests can be written without boilerplate.
- **`ui_tests/verification.py`** — three independent backend-truth channels for round-trip
  E2E assertions: Channel A (read-only sqlite), Channel B (authed admin/account JSON
  endpoints), Channel C (Bearer DNS API / mock Netcup state). Includes `wait_for` poller;
  never use `time.sleep` to wait for a DB effect.
- **12 cross-role round-trip tests** (`test_cross_role_account_lifecycle.py`,
  `test_cross_role_realm_propagation.py`, `test_cross_role_token_lifecycle.py`) — each
  verifies that an admin or user action propagates to the other role's API/portal experience
  via independent backend channels. `test_cross_role_account_lifecycle.py` is the pattern
  file for all new round-trip suites.
- **`ui_tests/tests/test_route_smoke.py`** (86 tests) — parametrized over every Flask route
  at import time; automatically covers new routes without any manual update.
- **`ui_tests/tests/test_ui_widgets.py`** (19 tests) — widget-level smoke for shared UI
  components.
- **DNS/DDNS round-trip extensions** (`test_api_dns_crud_success_with_mock_backend.py`,
  `test_ddns_quick_update.py`, `test_admin_security_api_contracts.py`) — verify records at
  the mock Netcup backend and assert security events surface in `/admin/api/security/events`.
- **CI `e2e-smoke` job** (`.github/workflows/ci.yml`) — boots the app on the GitHub Actions
  runner and runs 93 `@pytest.mark.ci_smoke` tests on every push/PR. Bootstrap via
  `scripts/ci_bootstrap_e2e.py`. Failure artifacts: gunicorn log, Mailpit message dump,
  screenshots.
- **`ui_tests/cross_role_helpers.py`** — shared helpers for cross-role test suites.
- **Mock netcup API** — added `/_test/records/<domain>` and `/_test/reset` routes for fast
  test-only state inspection without a full CCP login cycle.

### Fixed

- **Broken journey 09** and **broken 2FA functional fixture** — see T01 entry below for
  details.
- **Stale CI `--ignore`** — removed from `.github/workflows/ci.yml` (T01).

### Removed

- **Dead runner scripts**: `run-screenshot-tests.sh`, `test_installation_workflow.sh`,
  `test-https-deployment.sh` (T01).
- **9 overlapping smoke test files** — consolidated into `test_route_smoke.py`,
  `test_config_pages.py`, `test_audit_logs.py`, `test_admin_ui.py` (T12):
  `test_ui_comprehensive.py`, `test_ui_regression.py`, `test_ui_ux_validation.py`,
  `test_ui_interactive.py`, `test_ui_functional.py`, `test_user_journeys.py`,
  `test_mobile_responsive.py`, `test_account_portal_complete.py`,
  `test_admin_portal_complete.py`, plus `test_console_errors.py` (legacy `/client/` routes).
- **Journey 03 DB-write seeding** — retired in favour of UI-driven setup (T09).

---

## [Unreleased] — T01: Cleanup & quick fixes — 2026-06-12

### Fixed

- **Broken journey 09**: `ui_tests/journeys/test_09_multibackend.py` called nonexistent methods
  `browser.wait_for_load()` and `ss.take()`. Replaced with the real methods
  `wait_for_load_state()` and `ss.capture()` throughout.
- **Broken 2FA functional fixture**: `tests/test_2fa_security_functional.py` used an invalid
  `approved=True` kwarg on `Account` (no such column), leaked `os.environ` writes into the test
  session, and applied a post-`create_app()` SQLAlchemy URI rewrite that had no effect. Fixture
  now mirrors the `test_telegram_linking.py` pattern: `monkeypatch + tmp_path file DB`. Two
  tests with outdated assertions were updated to match current behavior (`test_2fa_lockout_expiry`
  used wrong Settings key format and a non-existent `json_value` attribute;
  `test_create_session_clears_old_session` asserted the old session was cleared when
  `create_session()` intentionally preserves data during session-ID rotation).
- **Stale CI `--ignore`**: Removed `--ignore=tests/test_2fa_security_functional.py` and its
  comment block from `.github/workflows/ci.yml`; the underlying `pool_size` / StaticPool bug
  was already fixed in `database.py` (commit `f99ea20`).

### Removed

- Dead runner scripts: `run-screenshot-tests.sh` (target `test_screenshot_coverage.py` does not
  exist), `test_installation_workflow.sh` and `test-https-deployment.sh` (curl-based, 2FA flow
  incompatible).
- Orphaned top-level UI test: `ui_tests/test_console_errors.py` (targets legacy `/client/…`
  routes that no longer exist; the live version in `ui_tests/tests/` is unaffected).
- Orphaned UI utilities: `ui_tests/analyze_ui_screenshots.py`, `ui_tests/compare_visuals.py`,
  `ui_tests/mailpit_client_selftest.py`, `ui_tests/quick_capture.py` (unused, not referenced by
  any live code or documentation).

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
