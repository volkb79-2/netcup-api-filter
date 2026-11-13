---
kind: backlog
schema_version: 1
items:
  - {id: B001, title: Honor notification preferences, type: feature, component: notifications, context_estimate: medium, folds_into: F012}
  - {id: B002, title: Add token usage analytics, type: feature, component: portal, context_estimate: medium, folds_into: F013}
  - {id: B003, title: Add webhook notifications, type: feature, component: notifications, context_estimate: medium, folds_into: F014}
  - {id: B004, title: Add self-service 2FA unlock status, type: feature, component: account-auth, context_estimate: medium, folds_into: F015}
  - {id: B005, title: Dispatch remaining notification mail in background, type: bugfix, component: notifications, context_estimate: medium, folds_into: F016}
  - {id: B006, title: Deliver documented security alerts, type: bugfix, component: token-auth, context_estimate: medium, folds_into: F017}
  - {id: B007, title: Repair account docs and admin app-log routes, type: bugfix, component: portal-admin, context_estimate: medium, folds_into: F011}
  - {id: B008, title: Filter DNS reads by realm hostname, type: bugfix, component: token-auth, context_estimate: medium, folds_into: F003}
  - {id: B009, title: Remove legacy filter proxy, type: bugfix, component: dns-api, context_estimate: small, folds_into: F018}
  - {id: B010, title: Remove unused Netcup mock stack, type: bugfix, component: dns-api, context_estimate: medium, folds_into: F019}
  - {id: B011, title: Wire and correct live backend execution, type: feature, component: backends, context_estimate: large, folds_into: F020}
  - {id: B012, title: Preserve audit rows on token deletion, type: bugfix, component: models, context_estimate: medium, folds_into: F021}
  - {id: B013, title: Enforce SQLite foreign keys, type: bugfix, component: database, context_estimate: medium, folds_into: F021}
  - {id: B014, title: Stop plaintext credential logging, type: bugfix, component: bootstrap, context_estimate: medium, folds_into: F022}
  - {id: B015, title: Enforce non-null invariants in lightweight migrations, type: bugfix, component: database, context_estimate: small, folds_into: F025}
  - {id: B016, title: Choose and apply one configuration precedence, type: feature, component: config, context_estimate: medium, folds_into: M3}
  - {id: B017, title: Complete the environment-default catalog, type: bugfix, component: config, context_estimate: small, folds_into: M3}
  - {id: B018, title: Remove or implement documented 2FA knobs, type: bugfix, component: account-auth, context_estimate: small, folds_into: M3}
  - {id: B019, title: Reject or wire dead TOML sections, type: bugfix, component: config, context_estimate: medium, folds_into: M3}
  - {id: B020, title: Honor the invite-expiry DB setting, type: bugfix, component: password-reset, context_estimate: small, folds_into: M3}
  - {id: B021, title: Correct startup credential validation and example config, type: bugfix, component: config, context_estimate: small, folds_into: M3}
  - {id: B022, title: Consolidate Netcup client creation, type: bugfix, component: dns-api, context_estimate: medium, folds_into: M6}
  - {id: B023, title: Reuse DNS response-envelope helpers, type: bugfix, component: dns-api, context_estimate: small, folds_into: M6}
  - {id: B024, title: Make malformed DNS envelopes fail loudly, type: bugfix, component: netcup-client, context_estimate: small, folds_into: M6}
  - {id: B025, title: Prevent logout from masking successful backend reads, type: bugfix, component: netcup-client, context_estimate: small, folds_into: M6}
  - {id: B026, title: Harden GeoIP endpoint and configuration consistency, type: bugfix, component: geoip, context_estimate: medium, folds_into: M3}
  - {id: B027, title: Make rate limiting fail closed and shared, type: bugfix, component: rate-limiting, context_estimate: medium, folds_into: M3}
  - {id: B028, title: Correct realm-token regeneration and realm state updates, type: bugfix, component: realm-tokens, context_estimate: small, folds_into: M5}
  - {id: B029, title: "Correct notification code, URLs, and realm types", type: bugfix, component: notifications, context_estimate: small, folds_into: F012}
  - {id: B030, title: Reconcile duplicate demo seeding, type: bugfix, component: bootstrap, context_estimate: medium, folds_into: M3}
  - {id: B031, title: Repair exported default test-client setup, type: bugfix, component: bootstrap, context_estimate: small, folds_into: M3}
  - {id: B032, title: Support delegated ccTLD DDNS zones, type: feature, component: ddns, context_estimate: medium, folds_into: M6}
  - {id: B033, title: Remove global first-failure and tighten pytest policy, type: bugfix, component: test-runner, context_estimate: small, folds_into: F010}
  - {id: B034, title: Remove dead UI test modules and workflows, type: bugfix, component: ui-tests, context_estimate: medium, folds_into: F009}
  - {id: B035, title: Resolve browser session naming collision, type: bugfix, component: ui-tests, context_estimate: small, folds_into: F009}
  - {id: B036, title: Consolidate tests on shared account fixtures, type: bugfix, component: tests, context_estimate: medium, folds_into: F009}
  - {id: B037, title: Replace assert-free UI tests, type: bugfix, component: ui-tests, context_estimate: medium, folds_into: F009}
  - {id: B038, title: Remove colliding mock SMTP fixture, type: bugfix, component: ui-tests, context_estimate: medium, folds_into: F009}
  - {id: B039, title: "Adopt a meaningful, verified gate: confirm/build a separate runtime-faithful test env (not the cockpit) + coverage floor + parallelism, and prove the gate rejects a known-bad canary — nyxloom reference/STANDARD.md gate contract + docs/plan-gate-adoption.md checklist", type: feature, component: test-infra, context_estimate: medium, folds_into: F009}
  - {id: B040, title: Offer HTTP SCRAM-SHA-256 for scoped DNS API clients, type: feature, component: api-auth, context_estimate: large, folds_into: F027}
  - {id: B041, title: "Close R2: survivor files in the lane lists, rerun on the stable commit, triage", type: bugfix, component: tests, context_estimate: small, folds_into: F028}
  - {id: B042, title: "Single source for PowerDNS URLs; PowerDNS API key as a ciu secret", type: bugfix, component: config, context_estimate: medium, folds_into: F028}
  - {id: B043, title: "Trusted-proxy hops setting; no raw X-Forwarded-For reads", type: bugfix, component: api-auth, context_estimate: medium, folds_into: F029}
  - {id: B044, title: "Webhoster forwarded-headers probe script and runbook", type: feature, component: tooling, context_estimate: small, folds_into: F029}
  - {id: B045, title: "ciu 7.24 spike: profiles, shared infra, shared secrets, ASK_EXTERNAL", type: feature, component: infra, context_estimate: small, folds_into: F028}
  - {id: B046, title: "Identity: INSTANCE_ID in every checkout, derived traefik names, ciu resolve instead of name building", type: feature, component: infra, context_estimate: large, folds_into: F028}
  - {id: B047, title: "Public stacks: OCI release-image frontends, public-dns role, realm-label reaper", type: feature, component: infra, context_estimate: large, folds_into: F028}
  - {id: B048, title: "Credentials: ASK_EXTERNAL secrets and .env.live skeleton, delivered as files", type: feature, component: infra, context_estimate: medium, folds_into: F028}
  - {id: B049, title: "Deployment-contract suite and on-demand e2e-public lane with probing preflight", type: feature, component: tests, context_estimate: large, folds_into: F028}
  - {id: B050, title: "cmru versions: cover every stack image, check in the release gate, select PowerDNS 5.1 series", type: feature, component: release, context_estimate: medium, folds_into: F028}
  - {id: B051, title: "OCI release image boot smoke", type: feature, component: tests, context_estimate: medium, folds_into: F028}
  - {id: B052, title: "Docs and closeout of the deployed tier", type: feature, component: docs, context_estimate: small, folds_into: F028}
  - {id: B053, title: "Deployment type as a per-checkout fact with a change guard", type: feature, component: infra, context_estimate: medium, folds_into: F028}
  - {id: B054, title: "Passenger WSGI forwarded-headers probe", type: feature, component: tooling, context_estimate: small, folds_into: F029}
  - {id: B055, title: "On-demand e2e-remote lane against the webhoster", type: feature, component: tests, context_estimate: medium, folds_into: F028}
  - {id: B056, title: "Legacy filter_proxy duplicate blueprint: remove or repair", type: bug, component: api, context_estimate: small, folds_into: F029}
  - {id: B057, title: "Portal token form: IP allow-list, expiry, rate limit and notes are silently dropped", type: bugfix, component: portal, context_estimate: medium, folds_into: F001}
  - {id: B058, title: "Reset-password form posts 'password' but the route reads 'new_password'; remove the e2e workaround", type: bugfix, component: password-reset, context_estimate: small, folds_into: F026}
  - {id: B059, title: "Template-to-route form-field contract guard; journeys submit through the real form", type: feature, component: tests, context_estimate: medium, folds_into: F009}
  - {id: B060, title: "ui_tests: never print typed values or 2FA codes in failure output", type: bugfix, component: ui-tests, context_estimate: small, folds_into: F022}
  - {id: B061, title: "Cross-account and cross-role authorization sweep over every id-bearing portal route", type: feature, component: tests, context_estimate: medium, folds_into: F002}
  - {id: B062, title: "Replace security-tier browser tests that cannot fail; CSRF-rejection sweep; admin cookie replay after logout", type: bugfix, component: tests, context_estimate: medium, folds_into: F009}
  - {id: B063, title: "Lockout and recovery: a locked account rejects valid credentials; recovery-code lockout and exhaustion", type: feature, component: account-auth, context_estimate: medium, folds_into: F026}
  - {id: B064, title: "Credential-invalidation controls: alias regeneration, token regenerate, change-email, one-time token display", type: feature, component: tests, context_estimate: medium, folds_into: F004}
  - {id: B065, title: "Rate limiting has no test at any layer", type: feature, component: rate-limiting, context_estimate: small, folds_into: M3}
  - {id: B066, title: "ui_tests: per-role storage state, an explicit anonymous context, and the forgot-password journey", type: bugfix, component: ui-tests, context_estimate: small, folds_into: F009}
  - {id: B067, title: "Honest skips in the e2e lane: hollow param smoke, data-dependent email skips, dead content tests, live deselect, -rs", type: bugfix, component: ui-tests, context_estimate: medium, folds_into: F010}
  - {id: B068, title: "Per-test browser instrumentation: fail on JS/console/network errors, artifacts on failure, per-test timeout, hermetic CDN", type: feature, component: test-infra, context_estimate: medium, folds_into: F009}
  - {id: B069, title: "pwmcp connection model: short recycle window, contract check, bounded connect and 503 retry", type: feature, component: test-infra, context_estimate: medium, folds_into: F009}
  - {id: B070, title: "Mailpit isolation and loop-safe waits; enable 2-worker parallelism within pwmcp's 2-slot cap", type: feature, component: test-infra, context_estimate: medium, folds_into: F009}
  - {id: B071, title: "Exercise Telegram and configured GeoIP in the hermetic tier with mocks", type: feature, component: ui-tests, context_estimate: medium, folds_into: F017}
  - {id: B072, title: "Audit all login outcomes and emit numeric rate-limit retries", type: bugfix, component: security, context_estimate: small}
  - {id: B073, title: "`account.disable_2fa` asks for a 2FA code the handler never verifies", type: bugfix, component: security, context_estimate: small}
  - {id: B074, title: "`/account/settings`: delete-account, disable-TOTP and unlink-Telegram forms do nothing", type: bugfix, component: security, context_estimate: small}
  - {id: B075, title: "Admin token detail page never shows IP restrictions", type: bugfix, component: admin-ui, context_estimate: small}
  - {id: B076, title: "Portal token regenerate always fails with 'Token name already exists'", type: bugfix, component: account, context_estimate: small}
  - {id: B077, title: "Login 'Remember me' checkbox has no effect", type: bugfix, component: account, context_estimate: small}
  - {id: B078, title: "Admin email 2FA code is compared with `==`", type: bugfix, component: security, context_estimate: small}
  - {id: B079, title: "Failed admin logins create one Settings row per submitted username and log the raw username", type: bugfix, component: security, context_estimate: small}
  - {id: B080, title: "ActivityLog `user_agent` is stored untruncated", type: bugfix, component: security, context_estimate: small}
  - {id: B081, title: "`/admin/settings` SMTP quick form omits fields the handler overwrites", type: bugfix, component: admin-ui, context_estimate: small}
  - {id: B082, title: "netcup config page: 'Test connection' posts a field the handler ignores", type: bugfix, component: admin-ui, context_estimate: small}
  - {id: B083, title: "pwmcp planned recycle can lose the released slot before reconnect", type: bugfix, component: test-infra, context_estimate: small}
  - {id: B090, title: "app-local seed-domain hook crashes when a delegated zone is set: its config has no backend_powerdns section", type: bugfix, component: infra, context_estimate: small}
  - {id: B091, title: "Mailpit webroot and message-size defaults come from stack config", type: bugfix, component: infra, context_estimate: small}
  - {id: B092, title: "PROXY-CALIBRATE: measure the proxy chain after extract and set trusted hops (Passenger default 0 first)", type: feature, component: deploy, context_estimate: medium}
  - {id: B093, title: "Switch the PowerDNS backend to the 5.1 series (pdns-auth-51) via cmru versions", type: feature, component: infra, context_estimate: medium}
  - {id: B094, title: "Fail fast on missing CIU inputs in local stacks", type: bugfix, component: infra, context_estimate: small}
  - {id: B095, title: "Verify PowerDNS 5.1.5 on a real start: logs, version API, zone and record round trip, health", type: feature, component: infra, context_estimate: small}
---

# Backlog

This is the enumerated ledger for the un-carved buckets from the former backlog. STATE.md
remains the status dashboard; completed B-AUTH work is intentionally not re-opened here.

## B-PORTAL

- **B001 — Honor notification preferences.** `api/account.py:787`, `models.py:305`, and
  `notification_service.py`: preferences and `notification_email` are stored but senders do
  not honor them; `notify_new_ip_login` and `notify_token_expiring` have no callers.
- **B002 — Add token usage analytics.** `api/account.py:realm_detail` and `ActivityLog`:
  expose last use, call count, denied count, and source IPs after the P03 audit fix.
- **B003 — Add webhook notifications.** `notification_service.py`: add a webhook delivery
  channel after B001 preference plumbing.
- **B004 — Add self-service 2FA unlock status.** `account_auth.py` and portal UI: lockout
  exists but users have no status or supported unlock path.
- **B005 — Dispatch remaining notification mail in background.**
  `notification_service.py:300,431,638`: replace request-thread `_send_email_sync()` calls
  and their hardcoded 30-second SMTP wait with the existing executor.
- **B006 — Deliver documented security alerts.** `token_auth.py:507` and
  `notification_service.py:2230`: connect the security-notification stub to the alert sender,
  or correct the documentation claim.

## B-API-AUTH

- **B040 — Offer HTTP SCRAM-SHA-256 for scoped DNS API clients.** The app currently offers
  Bearer tokens for machine DNS requests and has no SCRAM/SASL authentication path. Add the
  RFC 7804 HTTP SCRAM-SHA-256 exchange for REST and DDNS requests. Define credential
  issuance, rotation, revocation, and mapping to an account realm; store a SCRAM verifier
  rather than a reusable plaintext password; verify server proofs and protect against
  nonce replay; rate-limit and audit failures. Successful requests must continue through
  the existing record-level authorization checks. Keep Bearer authentication available.

## B-UI

- **B007 — Repair account docs and admin app-log routes.** `/account/docs`,
  `/admin/app-logs`, and `ui_tests/tests/smoke/test_route_smoke.py:49`: replace the tracked
  exclusions with working routes or intentional xfails that turn when repaired.
- **B008 — Filter DNS reads by realm hostname.** `api/dns_api.py:105` and
  `token_auth.py:600`: pass record hostname into authorization and filter records by hostname,
  not record type alone.

## B-DEAD

- **B009 — Remove legacy filter proxy.** `filter_proxy.py` and
  `passenger_wsgi.py:85,99`: remove the registered obsolete path that can 500 on
  `GET /api/ddns/<domain>/<hostname>`.
- **B010 — Remove unused Netcup mock stack.** `netcup_client_mock.py`, `utils.py:403`,
  `deploy.sh:529`, and `build_deployment_lib.sh:123`: remove orphan mocks and misleading
  `MOCK_NETCUP_API` exports.
- **B011 — Wire and correct live backend execution.** `backends/netcup.py:120,161`,
  `backends/powerdns.py:97`, and `backends/registry.py:129`: implement D-002's realm backend
  path without delete-by-omission, priority loss, hostname/RRset corruption, or optional
  schema validation.

## B-DATA

- **B012 — Preserve audit rows on token deletion.** `models.py:611,699`: remove the
  contradictory delete-orphan cascade so token deletion retains audit history.
- **B013 — Enforce SQLite foreign keys.** database engine connection setup: enable
  `PRAGMA foreign_keys=ON` and re-verify declared `ondelete` behavior.
- **B014 — Stop plaintext credential logging.** `bootstrap/platform_backends.py:348`,
  `database.py:437`, and `docs/TOML_CONFIGURATION.md:430`: do not log generated passwords or
  full demo tokens; use restricted deployment state where retrieval is necessary.
- **B015 — Enforce non-null invariants in lightweight migrations.** `database.py:238`:
  upgraded schemas must not omit model-declared non-null scalar-default constraints.

## B-CONFIG

- **B016 — Choose and apply one configuration precedence.**
  `docs/CONFIGURATION_GUIDE.md:19`, rate-limit/reset/IP-binding settings, and AGENTS.md:
  settle and align the contradictory env/DB/default precedence.
- **B017 — Complete the environment-default catalog.** `.env.defaults`: add or account for
  runtime keys including `LOG_LEVEL`, `MAX_CONTENT_LENGTH`, `BASE_URL`, expiry settings,
  token IP binding, demo flags, and `NETCUP_*`.
- **B018 — Remove or implement documented 2FA knobs.** `account_auth.py:60` and
  `.env.defaults:237`: reconcile hardcoded TFA and recovery lockout constants with docs.
- **B019 — Reject or wire dead TOML sections.** `passenger_wsgi.py:274+`: make imported
  `[session]`, `[admin]`, `[logging]`, and `[notifications]` settings effective or rejected.
- **B020 — Honor the invite-expiry DB setting.** `password_reset.py:567`: use the admin-set
  `invite_expiry_hours` rather than environment only.
- **B021 — Correct startup credential validation and example config.**
  `passenger_wsgi.py:670` and `app-config.example.toml:100-152`: read `netcup_config` and
  remove uncommented live-looking sample values.

## B-QUALITY

- **B022 — Consolidate Netcup client creation.** `api/dns_api.py:34`,
  `api/ddns_protocols.py:199`, and `api/account.py`: replace repeated factories/endpoints.
- **B023 — Reuse DNS response-envelope helpers.** `api/dns_api.py:555-611`: use imported
  `extract_dns_records`, `mutation_failed`, and `mutation_message`.
- **B024 — Make malformed DNS envelopes fail loudly.** `netcup_client.py:31`: do not turn a
  dict without envelope keys into an empty record list.
- **B025 — Prevent logout from masking successful backend reads.** `netcup_client.py:114`:
  ensure `finally: logout()` does not turn a successful read into `BackendError`.
- **B026 — Harden GeoIP endpoint and configuration consistency.** `api/dns_api.py:67` and
  `geoip_service.py:181`: authenticate/protect lookup, avoid leaking exception strings,
  align status and lookup config, and handle IPv6 private addresses.
- **B027 — Make rate limiting fail closed and shared.** `app.py:256` and rate-limit storage:
  no ImportError disablement, per-worker `memory://` budgets, or catalog-bypassing fallbacks.
- **B028 — Correct realm-token regeneration and realm state updates.**
  `realm_token_service.py:~559`: preserve name validation, update rejected-realm backend IDs,
  and avoid spurious pending-realm notifications.
- **B029 — Correct notification code, URLs, and realm types.** `notification_service.py`:
  register lockout codes, remove the hardcoded `https://naf.example.com` fallback, and render
  allowed record types rather than raw JSON.
- **B030 — Reconcile duplicate demo seeding.** `database.py:327` and
  `bootstrap/seeding.py:459`: keep the two seed paths and settings writers consistent.
- **B031 — Repair exported default test-client setup.** `bootstrap/seeding.py:368`: use
  `_get_env_defaults()` rather than dereferencing `_ENV_DEFAULTS`.
- **B032 — Support delegated ccTLD DDNS zones.** `api/ddns_protocols.py:118`: do not infer a
  zone as simply the final two labels.

## B-TESTS

- **B033 — Remove global first-failure and tighten pytest policy.** `pytest.ini`: remove
  global `-x`, scope coverage to unit runs, and add strict marker handling.
- **B034 — Remove dead UI test modules and workflows.** `ui_tests/auth_state.py`,
  `conftest_mock_api.py`, `conftest.py:319-349`, `workflows.py`, and `test_admin_*` helpers:
  remove unused parallel login, mock, client, and base-url paths.
- **B035 — Resolve browser session naming collision.** UI test conftest and `browser.py`:
  give the fixture and async context manager distinct names.
- **B036 — Consolidate tests on shared account fixtures.**
  `tests/test_telegram_linking.py:25`, `test_2fa_security_functional.py:24`, and
  `test_telegram_2fa.py:23`: use conftest `app`/`make_account` rather than private replicas.
- **B037 — Replace assert-free UI tests.** `journeys/test_journey_master.py:133` and
  `smoke/test_screenshot_capture_and_ux.py:486`: add behavioral assertions or remove tests.
- **B038 — Remove colliding mock SMTP fixture.** UI test `mock_smtp_server`: remove the
  hardcoded-port self-test fixture that duplicates Mailpit.
- **B039 — Adopt the shared testing library once it exists (do NOT build one now).**
  This project has no changed-line coverage floor, no canary probe and no mutation
  gate today. The right answer is to consume the shared library rather than write a
  fourth-and-a-half copy: `coverage_gate.py` already exists FOUR times across the
  estate (nyxloom 455 lines, dstdns 804, topos 299, plus srdm's Go `tools/covergate`)
  and every copy has diverged.

  The extraction is specified in
  `vbpub/nyxloom/nyxloom-trove/handoffs/nyxloom-P90-extract-testing-library.md` and
  is queued behind nyxloom's core redesign. **Blocked on that; nothing to do here
  until it lands.**

  This project is also the honest test of whether that extraction succeeded: it uses
  ciu + cmru but has no nyxloom-internal coupling, so if the library cannot be
  adopted here standalone, it is a nyxloom sub-module wearing a library's name (the
  P90 handoff's oracle O1 states exactly this).

## B-INFRA (added 2026-11-05, run-gate/assay conversion)

- **Step 3 landed, unverified:** bake group `release` (py311+py314), tarball build via `docker exec` into the ciu runner, cockpit scripts removed, `local-build`/`e2e` lanes. Nothing has been run. Still open: docs may still describe `flask-manager.sh`/`start-ui-stack.sh`/`.vscode/run-*.sh` (grep and sweep); e2e `forward_env` list is a first guess; app-local uses the py311 runner image tag (`py311`).
- Assay R1 lanes (`token_auth`, `account_auth`, `recovery_codes`) are `advisory` with `fail_under = 100`: measure, then set honest floors and promote to `gate`; add lanes for the remaining modules, R2 (replaces mutmut) and R3 canary.
- Dead code at the 3.11 floor: `tomli` fallbacks in `passenger_wsgi.py` and `database.py`; vestigial `create_app(config_path="config.yaml")`.
- `ui_tests/requirements.txt` is a bare manifest name (estate: `requirements-<use>.txt`); `.devcontainer/finalize.post.d/10-netcup-setup.sh` installs test deps into the cockpit venv (cockpit must not run tests).
- Cgroup placement: `ciu.compose` runners rely on the ciu governance overlay; verify `$CGROUP_PARENT_DEV_GATES` for exec runners after first `ciu up`.
- Add a run-gate docs-example test and a freshness check of the assay pin against the latest release.
- Ruff: `ruff check src` clean at py311 as of 2026-11-05 (commit 5288060); keep it that way.
- **cmru versions (2026-11-05 through 2026-11-11):** the first registry resolution hit HTTP 429; WP8 later recorded the stack/build image pins and added the pin-drift test. At that point the PowerDNS target still used `pdns-auth-48`; B093 now moves the target to the chosen 5.1 series.
- **cmru release is gated on the push:** `cmru release --dry-run` validates the new config and stops at "local main is N commits ahead of origin/main". The `run-tests` step runs `run-gate release-gate --worktree .` which needs a runner named from the judged tree's `ciu.global.toml` (gitignored): inside cmru's isolated release clone that file is absent, so the step must be reworked (declared runner `container_name` is wrong per RG-165 text; consider cmru `tester-gate` or running `run-gate` against the main checkout) before the first real `cmru release`.
- Defaults-as-hazards: `ui_tests/mailpit_client.py:468` falls back to SMTP port `1025` when `MAILPIT_SMTP_PORT` is unset.
- Mocks no longer publish host ports (tests reach them by name); restart the mock stacks to apply, and drop the now-unused `*_PORT` keys from `tooling/*/.env` when convenient.

## B-SETUP (added 2026-11-05, from docs/plans/credentials-and-test-setup-2026-11.md)

Root cause of the 2026-11-05 e2e meltdown: the suite uses the shipped admin as its test persona and changes its password as a side effect of logging in; five call sites then copy the new plaintext into `deployment_state_local.json` non-atomically; the e2e lane never resets the DB; a kill between the two leaves DB and file disagreeing, and the DB-stored 5-attempt lockout (15 min) then makes only a rebuild help. Staged plan (each stage ships alone; detail, files and rollback in the report):
- **S1 detect, don't flood (hours):** session-start guard (bcrypt-check the state password against the DB admin row and the lockout key; `pytest.exit` with the remedy), atomic `save_state`, drop the swallow in j1.
- **S2 one admin seeder, sane secrets:** `seed_bootstrap_admin()` for build/init_db/OCI first boot; race-free SECRET_KEY row in `init_db` (gunicorn workers can create different keys); stop logging tokens/generated passwords (`database.py` demo token: DONE 2026-11-05; `platform_backends.*` open). `activate.py` SECRET_KEY upsert: DONE 2026-11-05.
- **S3 per-session e2e environment:** throwaway copy of a golden DB + own app instance per session; drop `UI_BASE_URL`/`DEPLOYMENT_TARGET` from the lane's required env.
- **S4 personas replace the shipped admin:** provisioned in-memory credentials incl. a TOTP admin; the forced-password-change path becomes ONE dedicated test on its own DB; delete the state-file refresh machinery.
- **S5 clean artifacts:** tarball/golden DB without demo data and without `.env.defaults`; `build_deployment.py` stops writing `deployment_state_*.json`; one `.env` parser.
- **S6 dev-infra separation + dead code; S7 webhosting smoke is read-only (`UI_ALLOW_WRITES=0`); S8 move HTTP-only suites from `ui_tests/` to `tests/`.**
- Also open: the shipped tarball includes demo accounts/tokens whose password is published in `.env.defaults` (decide: strip in S5); the e2e lane takes > 60 min; `require_account_auth` rejection falls back to `logout()`, which revokes the session row named by the token alone (a cookie naming account A with account B's token revokes B's row; low severity, signed cookie).

## B-DEPLOY

Plan: [`docs/plans/deployed-e2e-and-modern-ciu-2026-11.md`](../docs/plans/deployed-e2e-and-modern-ciu-2026-11.md) (amended after the
Opus review); decisions D-008..D-013.

- **B041 — Close R2.** `assay.toml` R2 lanes listed curated test files that omitted the survivor files, so killed mutants were still
  reported (token_auth_r2: 9 survivors on e2c34cf). Lists fixed on main by `d077df0`; rerun all four lanes on the stable commit, triage.
- **B042 — Single source for PowerDNS.** `.env.defaults` carried retired proxy-path variables and an invented SOA default
  (contradicting D-007); `.env.services` derives `naf-pdns.<fqdn>`. WP1 removed the dead defaults and helpers, added drift tests, and retains
  `POWERDNS_API_KEY` as an empty operator entry. (The key moving to a checkout-local `GEN_LOCAL` secret is B046/B047.)
- **B043 — Proxy trust (D-013).** `app.py:75` hardcodes `ProxyFix(x_for=1, x_proto=1, x_host=1)`; ten raw `X-Forwarded-For` reads
  (`api/account.py` 187,356,822,1258,1307,1851,2148,2192; `filter_proxy.py` 505,597); session cookie domain `auto` = `.PUBLIC_FQDN`.
  `TRUSTED_PROXY_HOPS`, `x_host=0`, `PUBLIC_BASE_URL`, host-only cookies, static guard test; tarball keeps 1 until B044/B054.
- **B044 — Webhoster probe.** Run the existing `test-webspace-php-environment.php` (reports XFF/XFP/REMOTE_ADDR) and the new
  `test-webspace-forwarded-headers.php` (forged-header verdict) in vbpub scripts; the operator reports the result.
- **B045 — ciu spike. DONE 2026-11-11, corrected by the Opus review** (plan section 6).
- **B046 — Identity.** `environment_tag = "$INSTANCE_ID"` everywhere (CIU-193 open), derived traefik router/service/middleware/
  subdomain, `ciu resolve --json [--live]` instead of name building in `.env.services` and hooks, `.gitignore` ciu entries,
  `ciu.user_tables`, re-run the CIU-176 repro (fixed in 7.23.0), PowerDNS key as checkout-local `GEN_LOCAL`.
  **Implemented on `wp4b1-identity`:** container/Traefik/frontend names derive from `INSTANCE_ID`; `.env.services` and hooks
  consume ciu-resolved identities (against the `full` profile, so a narrow selection cannot hide a peer); `.gitignore` covers
  worktree artifacts; `ciu.user_tables = ["build"]`; app-local, which sits behind the host traefik, sets an explicit public origin
  and `trusted_proxy_hops = 0` until WP4b-2/WP5 measure the hop chain (so all human clients appear as the proxy address); and the
  PowerDNS key is a shared checkout-local `GEN_LOCAL` consumed by backend and app. Every checkout runs its own gate runners; a
  linked worktree's runner mounts the git common dir (Opus review H1). Review FIX round 1 (H1, H2, M1-M5, L1, L2, L4-L6) is on
  the branch; release-builder runner readiness moved to WP9 (M4). Awaits re-review, main-checkout cutover and its gate receipt.
- **B047 — Public stacks.** Frontends on the OCI release image (no repo mount), `public-dns` (`${PUBLIC_IP}:53`, IPv6 decision,
  delegated zone, realm-label reaper) and `public-edge` roles, public PowerDNS API route dropped, seed hook tested end to end.
- **B048 — Credentials.** Prompt/`ASK_FILE` secrets for SMTP/IMAP/netcup CCP, `.env.live.example`, mounts only into the frontend
  and a dedicated live runner, applied at first boot only.
- **B049 — Deployment-contract suite / `e2e-public`.** Contract suite on the remote target (TLS, cookies, forged headers through
  the edge, https links, guard, app-to-PowerDNS wire, live mail/netcup/DNS), `endpoints.json` manifest, lane preflight with real
  read-only login probes, certificate SAN wait, failure classes, secret scrubbing, per-instance guard credential.
- **B050 — cmru versions coverage.** Every stack image a target, floating tags gone, `cmru versions check` in the release gate,
  and the PowerDNS series decision. **Decision made 2026-11-13:** use the 5.1 series (`pdns-auth-51`); B093 updates the target and stack.
- **B051 — OCI boot smoke.** Build the release image, boot with/without `NAF_BOOTSTRAP_ADMIN_*`, non-root `/data` and `/config`.
- **B052 — Closeout.** Docs, STATE, release-gate + e2e on the final HEAD, R2 evidence, push.
- **B053 — Deployment type guard.** Per-checkout fact (`[topology.deployment] type`, `service_profiles`), pre-compose guard that
  refuses a change until `ciu clean`, v8-named realness/publish keys; ciu request: selection context under `--dir`.
- **B054 — Passenger probe.** Standalone WSGI app dir in vbpub scripts dumping what Passenger gives the app for a forged header.
- **B055 — `e2e-remote`.** On-demand remote smoke against the Passenger tarball on the webhoster.
- **B056 — Legacy `filter_proxy` duplicate blueprint.** Registered a second time in `passenger_wsgi.py` although `dns_api` shadows it; its route body has verified defects (reads `g.token`/`g.realm` while `require_auth` sets `g.auth`; calls `check_permission(token, realm, op)` against the current `(auth, operation, domain, ...)` signature; reads `realm.record_types_list`, which the model does not expose; `log_activity(details=...)`). WP2's test stubs these mismatches. Remove the duplicate registration and the dead module (preferred, see B-DEAD) or repair it; either way delete the stubs in `tests/test_proxy_hops.py`.

## B-E2E-REVIEW (2026-11-12 independent e2e/pwmcp review)

Priority: B057 and B058 first (security product defects; both **in progress 2026-11-12** on
`fixup3-form-contracts`), then B059, B060, B061, B062, then the rest. Entries marked **(b)** need the
deployed tier; the review's class-(b) scope remains with B049/B051/B054/B055, and no new item below is
class (b).

- **B057 — Portal token form: IP allow-list, expiry, rate limit and notes are silently dropped.**
  **In progress 2026-11-12** (`fixup3-form-contracts`); that branch owns the product fix and visible-form e2e.
  Evidence: `templates/account/create_token.html:79,96,109,123` submits `expires_in`, `ip_whitelist`,
  `rate_limit_per_minute`, `notes`; `api/account.py:688-697` reads `expires`, `ip_ranges`, `description` and
  no handler reads a rate limit. Static evidence was not confirmed by a form request (review §7).
  Oracle: submit the visible form with `203.0.113.0/24` and 30 days; Channel A must show that CIDR and
  `expires_at`, and the runner's API call must return 403 `ip_denied`. Current main stores NULLs and returns 200.

- **B058 — Reset-password form posts 'password' but the route reads 'new_password'; remove the e2e workaround.**
  **In progress 2026-11-12** (`fixup3-form-contracts`).
  Evidence: `templates/account/reset_password.html:24` posts `password`; `api/account.py:222` reads
  `new_password`, so a real reset fails with "Passwords do not match". The unit test posts the route's names
  (`tests/test_password_policy_reset_invite.py:87-131`), while the browser test injects `new_password`
  (`roundtrip/test_cross_role_account_lifecycle.py:642-663`).
  Oracle: the reset journey fills only `#password`/`#confirm-password`, clicks `#submit-btn`, then proves the
  hash changed and the old password is rejected; it fails before the fix.

- **B059 — Template-to-route form-field contract guard; journeys submit through the real form.**
  Depends on B057 and B058 (both in progress 2026-11-12); the other branch owns the guard.
  Evidence: both defects share a template/route field-name mismatch masked by handler-shaped unit POSTs and
  e2e field injection. Add a `tests/` guard over every rendered `<form>` endpoint and its `request.form`
  reads, with an explicit optional/alias allowlist; forbid input-creating/modifying `evaluate` in real-form
  journeys.
  Oracle: the guard reports `account.reset_password` and `account.create_new_token` before B057/B058 and passes
  after; re-introducing a renamed field turns it red.

- **B060 — ui_tests: never print typed values or 2FA codes in failure output. Status: complete**
  (harness1, report `/tmp/naf-ctl/harness1-luna-report.md`).
  Evidence: `browser.py:210` puts `value` in `ToolError.payload` and `browser.py:26-27` prints it; remote
  smoke uses the operator password (`config.py:173-175`), and `test_2fa_security.py:581` prints a 2FA code.
  Implemented: fill/select/evaluate errors retain only safe operation metadata; timeout and other
  navigation failures redact one-time URL tokens and secret-named query values; the AST guard checks
  print/logging calls and f-string raise/assert/pytest.fail messages. Unit tests cover typed values,
  navigation failures, and the diagnostic guard.

- **B061 — Cross-account and cross-role authorization sweep over every id-bearing portal route.**
  Evidence: only `test_ddns_quick_update_http.py:105` checks another account's realm; 18 `/account` rules take
  an integer id. As user B, request user A's realm/token/backend/DNS/session ids, and as a portal user request
  every `/admin/*` GET.
  Oracle: each request redirects/404s without A's data or a DB mutation; deleting the `realm_detail`
  ownership check (`api/account.py:1209-1211`) or `revoke_user_token` check fails. A new id route without
  ownership fails automatically.

- **B062 — Replace security-tier browser tests that cannot fail; CSRF-rejection sweep; admin cookie replay after logout.**
  Evidence: review §3.1 lists tautological `test_security_scenarios.py` checks and hollow/misnamed checks at
  `test_2fa_security.py:323,351,392,441,471,486`; source-grep tests default `REPO_ROOT` to the main checkout.
  Move CSRF to `tests/`: every cookie-auth POST without/with a forged token must return 400 and not mutate.
  Evidence for replay: admin sessions are signed cookies (`api/admin.py:756-760`) and logout only pops the
  client cookie (`api/admin.py:839-856`); section 7 leaves replay unverified pending cookie-lifetime tracing.
  Oracle: disabling `CSRFProtect` fails the sweep; replaying the saved admin cookie after logout redirects to
  `/admin/login`. Fix revocation or use a strict-xfail tied to a recorded SECURITY.md product decision.

- **B063 — Lockout and recovery: a locked account rejects valid credentials; recovery-code lockout and exhaustion.**
  Dependencies: unlock UX remains B004/F015. Evidence: `test_2fa_security.py:96-233` checks the counter/message,
  not rejection; recovery-code lockout/exhaustion lack behavioural tests. Tests must reject a correct TOTP,
  email code, recovery code, and admin password while locked, then accept after an injected clock advance.
  Oracle: forcing `is_2fa_locked` to False fails unit and e2e; removing the recovery-attempt increment fails
  recovery lockout.

- **B064 — Credential-invalidation controls: alias regeneration, token regenerate, change-email, one-time token display.**
  Dependencies: B028's regeneration correction lands under these tests. Evidence: no test covers
  `/admin/accounts/<id>/regenerate-alias`, `/account/tokens/<id>/regenerate`, admin change-email, or token
  activity. Use a throwaway account and assert old/new token API outcomes and audit rows; change-email
  updates, verifies, and notifies; reload/back never re-displays plaintext.
  Oracle: making `account_regenerate_alias` a no-op leaves an old token at 200 and fails; after token
  regeneration the old plaintext is 401 and the new one is 200.

- **B065 — Rate limiting has no test at any layer.**
  Dependencies: B027 owns the fail-closed/shared semantics this test pins. Evidence: no `429` assertion exists
  in `tests/` or `ui_tests/`. Configure a tiny DB limit, exceed it on admin login, account login, and the DNS
  API, assert 429 plus `errors/429.html`, then raise the limit and expect success.
  Oracle: removing the DNS limiter decorator or forcing the ImportError fallback fails; the per-worker caveat
  is asserted explicitly so B027 changes the expectation deliberately.

- **B066 — ui_tests: per-role storage state, an explicit anonymous context, and the forgot-password journey.**
  **Status: partial** (harness1 delivers the per-role files and explicit empty anonymous context; the full reset
  journey remains open). Depends on B058. The former shared state let admin and user cookies contaminate each
  other and defeated forgot-password checks at `test_email_notifications.py:452` and
  `test_security_scenarios.py:323`. The harness now selects admin/user state by role, does not pass a missing
  file to Playwright, and leaves anonymous contexts empty. Remaining oracle: follow a mailed reset link through
  the real form, prove the password hash changed, and log in with the new password.

- **B067 — Honest skips in the e2e lane: hollow param smoke, data-dependent email skips, dead content tests, live deselect, -rs.**
  References, rather than duplicates: P06 O2/O3 for skip-downgrades/live skeletons and B006 for token-revoked
  delivery. Evidence: `test_route_smoke.py:228-270` computes `_PARAM_PATHS` before the DB path fixture, so the
  detail smoke is empty; email tests skip on fixture-less data (`test_email_notifications.py:366-628`); `TestEmailContent`
  (`937-985`) always sees an empty mailbox; L765 is an unconditional TODO skip; the lane collects live tests.
  Oracle: use runtime ids, create keyed pending account/realm data, delete/fold dead content and TODO checks,
  deselect live, add `-rs`, and fail any unallowlisted runtime skip; the log must show only allowlisted gates.

- **B068 — Per-test browser instrumentation: fail on JS/console/network errors, artifacts on failure, per-test timeout, hermetic CDN.**
  Evidence: only route smoke/two perf tests collect errors, route smoke filters `net::` (`test_route_smoke.py:107`);
  failure artifacts and app logs disappear with the work dir; CDN pages load Bootstrap/List.js/Chart.js and floating
  `alpinejs@3.x.x` (`head_includes.html:3`, `scripts_includes.html:3`, `base.html:110`), so the lane depends on public CDNs.
  Oracle: a canary `throw new Error()` fails with its message; a deliberate failure leaves screenshot, trace,
  console log, and app-log tail; blocking `cdn.jsdelivr.net` breaks no test.

- **B069 — pwmcp connection model: short recycle-window connection, contract check, bounded connect and 503 retry.**
  **Status: complete** (harness1, report `/tmp/naf-ctl/harness1-luna-report.md`). The harness starts one
  Playwright driver, then recycles the gateway browser at each test-file boundary or after the configured
  interval, whichever comes first. It checks `/contract` once, uses the contract's lease cap, requests an
  interval-plus-margin lease, retries 503 for a bounded interval, and labels the holder
  `naf-e2e:<lane>:<pid-or-xdist-worker>`. A failed replacement is latched, and the session closes on teardown
  and bounded SIGTERM/SIGINT cleanup. Planned recycle disposes and counts leaked contexts. Oracle: exact fake-clock
  file/time recycle counts, bounded retry and busy-label message; final e2e evidence records connects/reconnects/
  recycles/contexts/leaked_contexts and duration.

- **B070 — Mailpit isolation and loop-safe waits; enable 2-worker parallelism within pwmcp's 2-slot cap.**
  Dependency: concurrent worktree identity is B046. Evidence: global clears at `conftest.py:289,297`,
  `test_2fa_security.py:103-105`, and `test_journey_master.py:39`; message predicates are mostly subject-only;
  33 async-loop call sites block in `verification.wait_for`/`MailpitClient.wait_for_message`.
  Oracle: two concurrent sessions sharing Mailpit both pass; a grep forbids `.clear()` in `ui_tests/tests`;
  `pytest-xdist -n 2` is evaluated only after isolation and remains within pwmcp's two shared slots.

- **B071 — Exercise Telegram and configured GeoIP in the hermetic tier with mocks.**
  References B026 for production GeoIP hardening; configured GeoIP is not the deployed-tier work in B049.
  Evidence: three Telegram tests skip because linking is disabled (`.env.defaults:237`); the GeoIP URL
  is forwarded but not configured, so `smoke/test_geoip_admin_and_api.py:54-73` tests only "not configured".
  Oracle: add a Telegram Bot API mock and enable it plus GeoIP in `e2e_env.py`; the three Telegram skips disappear,
  Telegram-2FA login fails if the mock receives no `sendMessage`, and the audit modal fails if a mock-known IP
  shows geo country "—".

**Referenced, not re-filed:** the `/account/docs` and `/admin/app-logs` gaps are B007; the assert-free
J2/J3 journeys, including J3's wrong `/api/dns/records` endpoint, are B037.

## B-SECURITY (added 2026-11-12 from the sweeps1 defects)

- **B072 — Audit all login outcomes and emit numeric rate-limit retries. Status: done**
  (implemented and merged 2026-11-12). The portal 2FA verifier returned its
  active-lock rejection before writing `ActivityLog`; the admin login flow wrote no persistent
  `login` outcome for wrong passwords, lock-rejected attempts, successful logins, or invalid and
  lock-rejected second factors; and Flask-Limiter 429s carried `Retry-After: None`, which also
  rendered as a non-numeric HTML countdown. The fix adds one admin audit helper that takes the
  already-resolved admin (NULL `account_id` for unknown and non-admin usernames), never stores
  submitted credentials or codes in the reason, and derives a positive retry delay from the
  limiter's reset or the configured window.

## B-FOLLOWUPS (found by the sweeps/guard reviews 2026-11-12)

- **B073 — `account.disable_2fa` asks for a 2FA code the handler never verifies. Status: open**
  The security-page form marks a 2FA code `required` (templates/account/security.html, the `disable_2fa` form) but `api/account.py` `disable_2fa` checks only the password. A control shown in the UI that does nothing; decide whether to verify the code (needs a product decision for email-only accounts) or remove the field. The B059 form-route guard waives it with a reference to this id; delete the waiver when fixed.

- **B074 — `/account/settings`: delete-account, disable-TOTP and unlink-Telegram forms do nothing. Status: open**
  templates/account/settings.html posts `action=delete_account`, `disable_totp` and `unlink_telegram`; the `settings` handler in api/account.py handles only `update_profile` and `change_password`, so the three actions re-render the page with no flash and no change. A user who unlinks Telegram keeps receiving 2FA codes there; a user who deletes the account keeps it. Wire the actions (with audit and CSRF tests) or remove the buttons. The B059 guard cannot express multi-action handlers: cover it per hidden `action`.

- **B075 — Admin token detail page never shows IP restrictions. Status: open**
  templates/admin/token_detail.html reads `token.ip_whitelist`, which does not exist; use `token.get_allowed_ip_ranges()`. An admin auditing a token restricted through the (now working, B057) form sees no allow-list.

- **B076 — Portal token regenerate always fails with "Token name already exists". Status: open**
  `regenerate_token` in api/account.py calls `create_token(token_name=old_token.token_name)` before revoking the old token and trips `uq_realm_token_name`; delegate to `realm_token_service.regenerate_token`, which renames. Related: B028, B064.

- **B077 — Login "Remember me" checkbox has no effect. Status: open**
  The control is rendered by templates/account/login.html and the handler ignores `remember`; either implement persistent sessions (a security decision: cookie lifetime, rotation) or remove the control. Waived in the B059 guard with this id.

- **B078 — Admin email 2FA code is compared with `==`. Status: open**
  api/admin.py (email 2FA verification, around the `==` on the submitted code) must use `hmac.compare_digest` like the portal flow (AGENTS.md convention 4).

- **B079 — Failed admin logins create one Settings row per submitted username and log the raw username. Status: open**
  `_track_failed_login` creates a `failed_login_user_<username>` Settings row per distinct submitted username, so spraying unknown usernames grows the table without bound; application log lines echo the raw username (CR/LF log injection, api/admin.py around the failed-password and lock branches). Bound or hash the key, expire rows, sanitise the logged value.

- **B080 — ActivityLog `user_agent` is stored untruncated. Status: open**
  models.py `ActivityLog.user_agent` is `Text` and every writer stores the header verbatim; truncate in one place (codebase-wide). Server header limits and the per-IP rate limit bound it in practice.

- **B081 — `/admin/settings` SMTP quick form omits fields the handler overwrites. Status: open**
  The quick form on /admin/settings posts to `admin.config_email` without reply-to, admin email and the notification flags; the handler overwrites them on every save, so saving that form clears them and turns notifications off. Found by the B059 guard (waived with this id; delete the waiver when the template carries the fields or the handler ignores absent ones).

- **B082 — netcup config page: "Test connection" posts a field the handler ignores. Status: open**
  templates/admin/config_netcup.html JS posts `test_only=true`; `config_netcup` ignores it, saves the configuration and returns HTML where the script expects JSON. Add a test-only branch that validates without saving.

- **B083 — pwmcp planned recycle can lose the released slot before reconnect. Status: open**
  With two estate-wide slots, another consumer can acquire a slot after this session closes its browser
  and before the immediate reconnect. If bounded 503 retry exhausts, the current session latches failed.
  Consider a longer reconnect deadline specifically for planned recycles, or skip a recycle while the
  slot is contested. Preserve the short initial-connect budget and the prompt slot yield between files.


- **B090 — app-local seed-domain hook crashes when a delegated zone is set. Status: open**
  `tooling/app-local/post_compose_seed_domain.py` reads `config["backend_powerdns"]` (name, ports.api) but
  app-local's own rendered config has no such section, so with `NAF_DELEGATED_DNS_ZONE` set the post-compose hook
  fails with "Missing required value: backend_powerdns.name" (found at the WP4b-1 cutover; the same lookup exists
  before it, the zone-empty no-op hid it). Resolve the PowerDNS container identity and API port from `ciu resolve`
  and the backend-powerdns stack contract, add a test that runs the hook with a zone set and a fake context,
  and prove it once with the long-lived backend-powerdns stack (WP5).

- **B091 — Mailpit webroot and message size are stack-owned. Status: done (`mailpit-config`)**
  `tooling/mailpit/ciu.defaults.toml.j2` now owns `web_root` and `max_message_size_mb`; Compose renders both values,
  and its healthcheck uses the same `web_root`. `tooling/ciu_resolve_env.py` reads the configured web port and
  webroot when deriving `MAILPIT_URL` and `MAILPIT_API_URL`. Static tests reject caller-shell reads, a healthcheck
  path that differs from `MP_WEBROOT`, and resolver drift from a changed configured webroot. A clean shell no longer
  needs Mailpit-specific exports for these settings.

- **B092 — PROXY-CALIBRATE. Status: open**
  The webhoster forwarded-header probe (2026-11-13, two hosts) showed no proxy appends `X-Forwarded-For`, the client
  value arrives unchanged and `X-Forwarded-Proto` is not normalised, so trusted hops = 0 on that host. A release must
  work on any webhoster: keep the fail-closed default 0 (change the Passenger catalog default from 1 to 0, resolving
  B044), then add a self-check after extract/activate: the app requests its own public URL with a TEST-NET-3
  `X-Forwarded-For` marker and a forged `X-Forwarded-Proto`, reads back what arrives, and proposes hops and scheme
  trust. Auto-apply only an unambiguous positive result, with an audit row and an admin-visible banner; otherwise
  report only; admins can re-run or override in settings. Verify with `/api/myip` plain and forged after the first
  deploy.

- **B093 — PowerDNS 5.1 series. Status: implementation and resolution committed; B095 real-start verification open**
  Operator decision 2026-11-13: use PowerDNS 5.1 (`pdns-auth-51`), with 5.1.5 selected. The cmru target and stack
  declarations move to the new series; the controller recorded the resolution in commit `9847b7b`. The stack renders
  configuration using the image's `TEMPLATE_FILES` mechanism and creates zones through the HTTP API with explicit
  SOA content and per-zone `soa_edit_api`. The gsqlite3 schema is byte-identical to upstream auth-4.8.5 and auth-5.1.5.
  `UNVERIFIED`: a real 5.1.5 start must confirm rendered config acceptance, API zone creation/readback, and health; see B095.

- **B094 — Fail fast on missing CIU inputs in local stacks. Status: open (Low)**
  `tooling/app-local/ciu.compose.yml.j2:27,57` interpolates `CONTAINER_UID`, `DOCKER_GID` and
  `PHYSICAL_REPO_ROOT` without a required-value guard; `tooling/backend-powerdns/ciu.compose.yml.j2:56,73,142`
  interpolates `DOCKER_GID` without one. If `ciu.env` is not loaded, UID/GID values can render empty (including
  `user: ":"`). Host-path handling is inconsistent: app-local uses a bare `PHYSICAL_REPO_ROOT`, Netcup mock and
  PowerDNS require it, and GeoIP mock falls back to its configured workspace path. Make the identity and host-path
  inputs fail fast consistently, retaining a configured fallback only where explicitly intended.

- **B095 — PowerDNS 5.1.5 real-start verification. Status: open**
  On the controller's real start, inspect container logs for config parse/backend/API startup errors and absence of
  fatal messages; call `GET /api/v1/servers/localhost` and verify `version` reports 5.1.5; create a disposable zone
  in the `.invalid` test namespace through `POST /api/v1/servers/localhost/zones`, read it back and verify its SOA,
  NS, serial, `soa_edit_api`, and a record round trip through `PATCH`/`GET`; confirm the `pdns_control version`
  healthcheck is healthy. **UNVERIFIED:** the 5.1.5 image's acceptance of the per-zone `soa_edit_api` field and
  exact readback normalization must be confirmed on that start.
