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
