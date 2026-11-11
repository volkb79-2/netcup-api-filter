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
  - {id: B046, title: "Modern ciu configuration: instance-scoped names, internal and public profiles", type: feature, component: infra, context_estimate: large, folds_into: F028}
  - {id: B047, title: "Public stack: PowerDNS singleton, per-instance frontend name, sub-zone helper", type: feature, component: infra, context_estimate: large, folds_into: F028}
  - {id: B048, title: "Credentials: ASK_EXTERNAL secrets and .env.live skeleton, delivered as files", type: feature, component: infra, context_estimate: medium, folds_into: F028}
  - {id: B049, title: "On-demand e2e-public lane with preflight and hard-failing live tests", type: feature, component: tests, context_estimate: large, folds_into: F028}
  - {id: B050, title: "cmru versions: cover every stack image, check in the release gate", type: feature, component: release, context_estimate: medium, folds_into: F028}
  - {id: B051, title: "Internal-profile e2e against the app container", type: feature, component: tests, context_estimate: medium, folds_into: F028}
  - {id: B052, title: "Docs and closeout of the deployed tier", type: feature, component: docs, context_estimate: small, folds_into: F028}
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
- **cmru versions (2026-11-05):** `[versions]` now declares mailpit, powerdns (pdns-auth-48) and the python 3.11/3.14 slim-trixie bases (14-day age window), but `cmru versions resolve naf` has not completed: Docker Hub answered HTTP 429 (anonymous pull limit shared by this host). Retry after the window (or with Docker Hub credentials via `username_env`/`password_env`), commit `versions/oci-images.json`, then pin `tooling/mailpit` and `tooling/backend-powerdns` `image_tag` from it (they are still `latest`) and add a test that the pins equal the record.
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

Plan: [`docs/plans/deployed-e2e-and-modern-ciu-2026-11.md`](../docs/plans/deployed-e2e-and-modern-ciu-2026-11.md); decisions D-008..D-011.

- **B041 — Close R2.** `assay.toml` R2 lanes listed curated test files that omitted the survivor
  files, so killed mutants were still reported as survivors (token_auth_r2: 9 survivors on
  e2c34cf). Lists fixed (ab4f8c0); rerun all four lanes on the stable commit and triage.
- **B042 — Single source for PowerDNS.** `.env.defaults` still carries `POWERDNS_PROXY_*`
  (`/backend-powerdns` path) and `POWERDNS_SOA=powerhosts.vxxu.de` (contradicts D-007);
  `.env.services` derives `naf-pdns.<fqdn>`. `POWERDNS_API_KEY` is a plaintext dev key in
  `.env.operator`, passed through the shell; make it a `GEN_LOCAL` ciu secret read through ciu.
- **B043 — Trusted-proxy hops.** `app.py:75` hardcodes `ProxyFix(x_for=1, x_proto=1, x_host=1)`;
  `api/account.py:187,356,822,1258,1307` read the raw `X-Forwarded-For` header. Add
  `TRUSTED_PROXY_HOPS` (fail-fast), use `request.remote_addr` everywhere, test through the middleware.
- **B044 — Webhoster probe.** `scripts/test-webspace-forwarded-headers.php` in vbpub next to the
  other `test-webspace-*` scripts; the operator runs it once; the tarball default stays 0 until then.
- **B045 — ciu spike. DONE 2026-11-11** (findings: plan section 6). Flags derive from
  `ciu.selected_profiles`; shared-infra join via `--shared-infra-ref-services`; `GEN_LOCAL` is per
  checkout (a joined worktree needs `ASK_EXTERNAL`/`ASK_FILE` for the primary's PowerDNS key);
  `ASK_EXTERNAL` aborts non-interactively without a value; `ciu check` passes (gitignore WARN for B046).
- **B046 — Modern ciu configuration.** `environment_tag = "$INSTANCE_ID"` for worktrees (ciu
  CONSUMERS section 26), profiles `internal`/`public`, flags under `[topology.*]`, no hand-formed names.
- **B047 — Public stack.** PowerDNS singleton on port 53 (data dir outside the checkout),
  `naf-<instance>.<PUBLIC_FQDN>` frontend, per-session sub-zone create/delete, seed hook tested end to end.
- **B048 — Credentials.** `ASK_EXTERNAL` for SMTP/IMAP and netcup CCP, `.env.live.example`,
  delivered as files, applied at first boot only.
- **B049 — `e2e-public` lane.** On-demand; preflight names each missing prerequisite; UI suite
  through the edge; live tests (DNS propagation, TLS, mail round trip, real netcup) hard-fail.
- **B050 — cmru versions coverage.** `alpine` (pdns init), the `python` bases of the mocks and
  runners; `cmru versions check` in the release gate; the drift test covers every stack image.
- **B051 — Internal-profile e2e.** Same suite against the app container by container name.
- **B052 — Closeout.** Docs, STATE, release-gate + e2e on the final HEAD, R2 evidence, push.
