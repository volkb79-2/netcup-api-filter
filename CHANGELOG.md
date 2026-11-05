# Changelog

## [Unreleased] — Gate on run-gate + assay; Python 3.11/3.14 — 2026-11-05

### Added

- **Remote read-only webhosting smoke** (credentials/test-setup plan, S7): `NAF_E2E_TARGET=remote`
  binds the e2e settings to a deployed host from `NAF_REMOTE_BASE_URL` / `NAF_REMOTE_ADMIN_*`
  (password and TOTP seed via `*_FILE`, value/file mutually exclusive), `allow_writes=False`; only
  tests marked `remote_smoke` run, everything else is skipped. `deployment_state_webhosting.json`,
  hardcoded production hostnames and the stale `WEBHOSTING_TESTING_GUIDE.md` flow are gone. The local
  mode stays the default.

### Security

- **Fixed (review #8):** the `e2e` run-gate lane requires `PLAYWRIGHT_SERVER_WS` again (without it
  the runner tried an in-process browser and every test errored one by one).

- **Fixed (review #7):** every `ciu up` of app-local re-wrote the Mailpit `email_config`,
  resetting SMTP settings changed in the admin UI. The mock email config is now create-only.

- **Fixed (review #5):** `app-defaults.env` shipped `SECRET_KEY=local-dev-secret-change-me` (and
  every other non-test key, e.g. `TELEGRAM_BOT_USERNAME`, `POWERDNS_SOA`). The dev `SECRET_KEY` line
  is deleted and the shipped catalog is now an allowlist (`config_defaults.RUNTIME_DEFAULT_KEYS`) that
  never contains a credential-like name.

- **Fixed (review #6):** init could report success with no admin: a configured username owned by a
  non-admin or deactivated account was returned "unchanged", and a colliding email raised a raw
  `IntegrityError`. Both are now `BootstrapAdminError`s naming the collision, and an existing
  database needs an *active* admin.

- **Fixed (review #3):** a configured bootstrap admin (`NAF_BOOTSTRAP_ADMIN_*`, TOML) accepted any
  non-empty password; it must now satisfy the password policy. Docs no longer claim email 2FA turns
  on by itself for a configured admin.

- **Fixed (review #9):** a bind-mounted `app-config.toml` file could not be claimed (`EBUSY`) and
  fell into the generic start-up error; the start now fails with "mount the directory" guidance.
  The `docker exec`-ed bootstrap CLI now resolves the app root like `passenger_wsgi.py` (it ignored
  `app-config.toml` before).

- **Fixed (review #1/#2):** a fresh database could be initialized by several gunicorn workers
  at once (check-then-insert races on the bootstrap admin, ~1/N requests failing), and any start-up
  error was swallowed into a stand-in WSGI app that rendered the exception text to clients (an
  `IntegrityError` can include row values). Initialization now runs under an exclusive lock file
  (`<db>.init.lock`, `NAF_INIT_LOCK_TIMEOUT_SECONDS`) in every process, and a failed start re-raises:
  gunicorn exits non-zero ("Worker failed to boot"); details are logged only.

- **One database initializer, no published secrets** (credentials/test-setup plan, S2):
  `bootstrap.instance.init_instance()` is the only seeder (tarball build, local golden DB, app
  start, ciu `post_compose` hook via `python -m netcup_api_filter.bootstrap init`). The tarball
  ships only the pre-set admin (`must_change_password`); the OCI image ships no account and refuses
  a first start without `NAF_BOOTSTRAP_ADMIN_*` (password via `*_FILE`) or an `app-config.toml`
  admin. The implicit runtime admin/demo seeders (`seed_admin_account`, `SEED_DEMO_ACCOUNTS`) and
  the legacy demo-client seeding are removed.
- `SECRET_KEY`: `SECRET_KEY_FILE`/`SECRET_KEY`, else one database row created with
  `INSERT OR IGNORE` (all gunicorn workers share it; the per-worker temporary key and the
  `.env.webhosting` loader in `passenger_wsgi.py` are gone). The dev `SECRET_KEY` default is removed
  from `.env.defaults`; the start-up error no longer echoes part of a key.
- `[[users]]` import: generated passwords are never logged; the imported list (plaintext
  passwords) is deleted from `settings` after the accounts exist; an admin may not use `"generate"`.
- **Fixed:** TOML `[[users]]` / `[[backends]]` / `[[domain_roots]]` were silently skipped
  (`get_setting` already decodes JSON; a second `json.loads` raised `TypeError`).
- `tooling/app-local` is a ciu-initialized instance: per-instance `GEN_LOCAL` secrets
  (`secret_key`, `bootstrap_admin_password`) mounted as files, its own data hostdir, and a
  `post_compose_init_instance.py` hook (readiness, then create-or-update init via `docker exec`).

- **Clean release artifacts** (S5): the OCI image ships `app-defaults.env` instead of nothing,
  `NETCUP_FILTER_DB_PATH=/data/netcup_filter.db` and `VOLUME /data` (still no account, no
  `.env.defaults`). `build_deployment.py` no longer writes `deployment_state_*.json` or
  `.env.webhosting` (the latter carried `DEPLOYED_ADMIN_PASSWORD`), no longer mutates `os.environ`
  from `.env.services` (`SERVICE_MAILPIT` from the environment, else evaluated read-only), and is
  ruff-clean. CI `e2e-smoke` uses the per-session fixture on the `--local` deploy tree;
  `scripts/ci_bootstrap_e2e.py` is deleted. New `tests/test_release_artifacts.py` pins the tarball
  contents (one admin with `must_change_password`, no `secret_key` row, no `.env*`/state files).

- **e2e without shared credentials** (S1/S3/S4): every session starts its own app inside the 3.11
  runner on a copy of the golden DB (`ui_tests/e2e_env.py`) and provisions random in-memory personas
  (`ui_tests/personas.py`; admin with TOTP). `ui_tests/deployment_state.py`, `ui_tests/env_defaults.py`,
  `refresh_credentials()` and every state-file write are removed; the e2e lane no longer needs
  `UI_BASE_URL`/`DEPLOYMENT_TARGET`. The forced first-login change is one test on its own instance; a
  mutated golden DB or broken environment stops the session with one message.
- `.env.defaults` is never shipped: builds write `app-defaults.env` (runtime keys only; no pre-set
  admin password, no test fixtures). `DEFAULT_TEST_ACCOUNT_PASSWORD`, `DEFAULT_TEST_CLIENT_ID` and
  `DEFAULT_READONLY_TEST_CLIENT_ID` are removed.
- **Fixed:** account-portal login with TOTP never succeeded: choosing TOTP on `/account/login/2fa`
  did not record the method, so the TOTP code was checked as an email code.

- `token_auth.check_permission` no longer skips the record-type check for an empty-string type, and
  `validate_dns_records_update` denies records without a type (fail closed). The REST routes already
  checked the real type, so no route was exposed; found by the new R1 tests.

### Removed

- Manual mutmut tooling (`tooling/mutation/`, `requirements-mutation.txt`, `[mutmut]` in `setup.cfg`): assay R2 replaces it.

### Changed

- **S6 dev-infra separation:** Mailpit UI/API auth removed (internal-only stack; `MailpitClient`
  takes no credentials; `MAILPIT_USERNAME`/`MAILPIT_PASSWORD` gone from compose, CI and docs). The
  traefik basicauth guard is for humans only; the Playwright client no longer sends guard
  credentials (e2e targets the app over the internal network). Admin login lockout threshold/duration
  are now `ADMIN_LOGIN_LOCKOUT_THRESHOLD` / `ADMIN_LOGIN_LOCKOUT_MINUTES` in `.env.defaults`.
  Dead code removed: `global-config.{defaults,active}.toml`, `ui_tests/auth_state.py`.
- **Browser lane shrunk (S8):** the HTTP-only e2e suites moved to the hermetic `tests/` suite
  (Flask test client, tmp SQLite DB, in-memory Netcup fake, real CSRF): DDNS protocols, REST API
  security, registration/approval negatives, admin bulk actions, DDNS quick update, and the GeoIP
  mock self-test (`tests/test_*_http.py`, `tests/fake_netcup.py`, `tests/http_helpers.py`). The
  originals under `ui_tests/tests/` are deleted. Assertions are exact (no `in [200, 403, 502]`)
  and check ActivityLog/token-usage/account rows and the upstream zone. Tautological checks
  (self-computed capability table, badge-colour dict, "list contains its own element") were
  replaced by tests against the real rendered pages / endpoints.
- **Rigor ladder:** assay R1 floors at the measured baseline, R3 import-break canaries and R2 mutation
  lanes for `token_auth`, `account_auth`, `recovery_codes`, `utils`; `release-gate` sequence.
- **pwmcp is consumed, not hosted:** `infra/pwmcp` removed; runners and `app-local` join the estate
  instance's network (`PWMCP_NETWORK`); lease headers sent from config; Playwright client `1.64.*`.

- **Python targets are 3.11 (Passenger) and 3.14 (OCI).** The `py39` variant, the 3.9 test
  branch and the `tomli` marker are removed; ruff/mypy/CI target 3.11.
- **Gate is `run-gate`** (`run-gate.toml` + assay-judged `assay.toml`, assay 12.0.0 vendored in
  `tools/assay/`): one ciu-managed runner per Python version; `nyxloom.toml` gates are pointers.
  `testing-exec.sh` and `runner.env` are removed.
- **Manifests follow the estate naming:** `requirements-runtime.txt`, `requirements-test.txt`,
  Unused `pyyaml` dropped from the runtime set.
- **Release images:** bake group `release` builds `app:py311` and `app:py314`; the Passenger
  tarball is built inside the matching ciu runner (`docker exec`), not via `testing-exec.sh`.
- **Local flow runs in containers:** `run-gate local-build` / `e2e` replace `run-local-tests.sh`;
  cockpit runner scripts (`flask-manager.sh`, `.vscode/run-*.sh`, `tooling/run-*.sh`) removed.

## [Unreleased] — Planned SCRAM API authentication — 2026-10-15

### Added

- **SCRAM-SHA-256 API authentication backlog item.** Added the RFC 7804 HTTP
  challenge-response option for scoped DNS API clients to the product definition and
  roadmap (F027/M8, B040). This records planned work; the app still uses Bearer tokens.

## [Unreleased] — CMRU release and CIU webhosting deployment — 2026-07-21

### Changed

- **Release and deployment flow reconciled.** `cmru release` now publishes the Python 3.14 OCI
  image plus ABI-matched Passenger `py39`/`py311` tarball variants and a variant-selecting
  installer; `ciu up --host webhoster --thin -- --variant <variant>` deploys a selected
  Passenger asset. Local development remains `run-local-tests.sh` →
  `build_deployment.py --local` → `deploy-local/`.
- **Greenfield Passenger activation.** Activation extracts the selected tarball, preserves only
  `SECRET_KEY`, touches Passenger's `tmp/restart.txt`, and health-probes the application.

### Removed

- Retired the bespoke webhosting release/push plumbing and its obsolete SSH environment samples.

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
