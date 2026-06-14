# Testing Infrastructure

## Overview

This document describes the testing infrastructure: the two-layer suite layout,
the local runners, the CI jobs, and the tooling that supports them.

---

## Testing types at a glance

| Type | What it checks | Framework | Count | Speed |
|---|---|---|---|---|
| Unit | Single function in isolation, no I/O | pytest + pytest-cov | 239 | <1 min (total) |
| Integration | Multi-component DB round-trips | pytest | 5 | Fast |
| Route smoke | Every Flask route returns correct status | Playwright | 86 | Medium |
| Widget | Individual UI components in isolation | Playwright | 19 | Medium |
| Round-trip | UI action → backend state via 3 channels | Playwright | 12 | Medium |
| E2E domain | Full feature workflows (auth, DNS, 2FA, etc.) | Playwright | ~250 | Slow |
| Journey | Multi-step stateful scenario suites | Playwright | ~20 | Slow |
| **Total** | | | **~631** | |

The unit suite runs in CI on every push (<60 s). A tagged `@pytest.mark.ci_smoke` subset
of 93 Playwright tests also runs in CI against a live gunicorn + Mailpit stack on every PR.
See **CI jobs** below.

---

## Suite layout

### `tests/` — unit/integration (no browser)

Run with `python -m pytest tests/` (or plain `pytest tests/`). No running app required.

- **`tests/conftest.py`** — shared fixtures: `app`, `client`, `db` (in-memory SQLite per
  test), and factories `make_account` / `make_realm` / `make_token`.
- Unit modules cover: token auth (`authenticate_token`, `check_permission`, `check_ip_allowed`),
  realm matching, validators, password policy, recovery codes, DDNS parsing, netcup client
  envelope helpers, and lightweight migrations.
- Hypothesis property tests live in `tests/test_*_property.py`, default profile `ci` (50 examples), set `HYPOTHESIS_PROFILE=dev` for 500.
- CI runs this suite on every push/PR (see **`unit-tests` job** below).

### `ui_tests/` — Playwright E2E (browser required)

Requires a running deployment and the Playwright container.

```bash
cd tooling/playwright && docker compose up -d
./tooling/playwright/playwright-exec.sh pytest ui_tests/tests -v
```

Or via the standard runner (builds a fresh deployment first):

```bash
./run-local-tests.sh --with-mocks    # Mailpit + GeoIP + Netcup-API mocks
./run-local-tests.sh --skip-build    # reuse existing deploy-local
```

---

## Standard local runner

**`run-local-tests.sh`** — the single entry point for local testing:

```bash
./run-local-tests.sh                          # build + run full ui_tests suite
./run-local-tests.sh --with-mocks             # also start mock services
./run-local-tests.sh --skip-build             # reuse existing deploy-local
./run-local-tests.sh --with-mocks <file>      # run a single test file
```

The script builds a production-parity deployment under `deploy-local/`, starts the app,
and runs the `ui_tests` suite. `deploy.sh` manages the suite list; it is updated alongside
test additions and deletions so the two stay in sync.

---

## Route-smoke suite

**`ui_tests/tests/test_route_smoke.py`** (86 tests) — parametrized over every route
discovered at import time via Flask's URL map. New routes added to any blueprint are
automatically smoke-tested without any manual update. Smoke checks: correct status codes,
no unhandled exceptions, basic page structure for HTML routes.

Contributors get smoke for free; they must still add round-trip tests for new behavior
(see `test_cross_role_account_lifecycle.py` for the pattern).

---

## CI jobs

Two jobs run on every push and pull request (`.github/workflows/ci.yml`):

### `unit-tests`

Runs `python -m pytest tests/` with coverage. No services required; fast (< 60 s).
Uploads `coverage.xml` as an artifact on every run.

### `e2e-smoke`

Boots the full app in the CI runner (gunicorn, plain HTTP :5100) and runs all tests
tagged `@pytest.mark.ci_smoke` (93 tests). Services: Mailpit on ports 1025/8025.

**Bootstrap**: `scripts/ci_bootstrap_e2e.py` initialises the DB and writes
`deployment_state_local.json` so the test helpers find the admin credentials.

Key env vars that make plain-HTTP CI work:

| Var | Value | Purpose |
|-----|-------|---------|
| `FLASK_ENV` | `local_test` | Clears `SESSION_COOKIE_SECURE`, disables rate limiting |
| `DEPLOYMENT_TARGET` | `local` | Selects local state-file path |
| `NAF_VERIFY_DB_PATH` | `ci-deploy/netcup_filter.db` | Directs `verification.py` channel A to the CI DB |
| `UI_BASE_URL` | `http://127.0.0.1:5100` | Playwright base URL |

**Failure artifacts**: on failure the job uploads `gunicorn.log`, `mailpit-messages.json`,
and `tmp/ui-screenshots` for debugging.

To tag a test for the `e2e-smoke` job:

```python
@pytest.mark.ci_smoke
async def test_my_feature(browser):
    ...
```

Tests should be fast, hermetic, and not require mock-netcup or other external services
beyond Mailpit.

---

## Verification channels (`ui_tests/verification.py`)

Three independent backend-truth channels for E2E round-trip assertions — see
[`TESTING_LESSONS_LEARNED.md`](TESTING_LESSONS_LEARNED.md) § 4 for the full pattern.

| Channel | API | Reads |
|---------|-----|-------|
| A | `verification.get_account()`, `get_token()`, `count_activity()`, `wait_for()`, … | Read-only sqlite (mode=ro) |
| B | `verification.admin_api_accounts()`, `account_api_realms()`, … | Authed JSON endpoints via browser session |
| C | `verification.dns_api_list_records()`, `mock_netcup_records()` | DNS API (Bearer) / mock Netcup backend |

Channel A uses `NAF_VERIFY_DB_PATH` (env override) or the default `deploy-local/netcup_filter.db`.
Call `verification.require_db()` at the top of tests that need Channel A; it calls
`pytest.skip` automatically if no DB file is accessible.

---

## Cross-role round-trip tests

`ui_tests/tests/test_cross_role_*.py` verify that an admin action propagates to the user's
API/portal experience via independent channels:

| File | What it tests |
|------|---------------|
| `test_cross_role_account_lifecycle.py` | disable/enable account (401+error_code), invite+approval, password reset link |
| `test_cross_role_realm_propagation.py` | realm approval/rejection/revocation + token behavior |
| `test_cross_role_token_lifecycle.py` | admin revoke, user self-revoke, read-only scope enforcement |

See `test_cross_role_account_lifecycle.py` — it is the **pattern file** for all cross-role
suites (channel use, `wait_for`, state cleanup in `finally`).

`ui_tests/cross_role_helpers.py` provides shared helpers (login, account creation via
invite form, realm/token creation).

---

## Troubleshooting

### App won't start

```bash
# Check logs
./tooling/flask-manager.sh logs

# Check if port is in use
netstat -tuln | grep 5100

# Rebuild from scratch
./deploy.sh local
```

### Tests fail with "Connection Refused"

```bash
# Verify the app is running
curl http://localhost:5100/health

# Check which port deploy-local is using (deploy.sh sets this)
grep PORT deploy-local/.env 2>/dev/null || echo "not set, using default 5100"
```

### Channel A (sqlite) fails in tests

- Ensure `NAF_VERIFY_DB_PATH` points to the actual DB, or that `deploy-local/netcup_filter.db` exists.
- If running against webhosting (no direct DB access), Channel-A tests will auto-skip via `require_db()`.

### CI e2e-smoke fails

1. Download the `e2e-smoke-debug` artifact from the failed Actions run.
2. Check `gunicorn.log` for startup errors.
3. Check `mailpit-messages.json` for email delivery issues.
4. Screenshots are in `tmp/ui-screenshots`.

---

## Coverage report

Running `python -m pytest tests/ --cov=src/netcup_api_filter` against the unit suite alone
(last measured: 2026-06-14):

| Module group | Key files | Unit coverage | Notes |
|---|---|---|---|
| Security-critical pure functions | `token_auth.py` (63%), `recovery_codes.py` (80%) | 63–80% | Intentionally targeted; high-value |
| Data models | `models.py` | 75% | ORM model helpers covered by factory tests |
| Config / realm templates | `config_defaults.py` (83%), `realm_templates.py` (100%) | 83–100% | Fully covered |
| Telegram service | `telegram_service.py` | 96% | Driven by `test_telegram_*.py` |
| App factory + DB migration | `app.py` (59%), `database.py` (50%) | 50–59% | Integration-level coverage |
| Shared utilities | `utils.py` | 50% | Validators partially covered; Hypothesis target |
| DDNS protocols | `api/ddns_protocols.py` | 42% | Parsing logic; Hypothesis target |
| Flask route handlers | `api/account.py` (14%), `api/admin.py` (13%), `api/dns_api.py` (15%) | 13–15% | Covered by E2E, not unit tests — expected |
| Backend adapters | `backends/*.py` | 0% | Require running backend; covered by E2E |
| Deploy / infra artefacts | `passenger_wsgi.py`, `filter_proxy.py`, `example_client.py` | 0% | Not unit-testable by design |

**TOTAL (unit suite against full source package): 24% (9 097 stmts, 6 942 not hit)**

The 24% headline is intentional and expected. It reflects:

1. Flask route handlers (~3 000 lines) are covered by the Playwright E2E suite, not unit tests — running
   the Flask app inside a unit test provides no value over a real request cycle.
2. Backend adapters require a running DNS backend; their coverage comes from E2E with mock backends.
3. The unit suite targets *pure functions* where a single isolated test exercises one deterministic path.

Per-file detail is in the CI artifact `coverage.xml` uploaded by the `unit-tests` job on every run.

### Coverage floor

`pytest.ini` does not currently enforce a minimum. Recommended addition to lock in the current level:

```ini
# in pytest.ini addopts:
--cov-fail-under=22
```

Set 2 points below the current 24% so the floor rises naturally as unit tests are added without
false-failing from ±1% variance across Python minor versions.

---

## Gaps and next steps

Known gaps — none are blockers; documented here for future prioritisation.

| Gap | Effort | Value |
|---|---|---|
| Add `--cov-fail-under=22` to `pytest.ini` | 5 min | Prevents silent backslide |
| Property-based testing (Hypothesis) for parsers/validators | 1–2 days | Finds edge cases unreachable by hand-written parametrize lists — see [`TESTING_LESSONS_LEARNED.md` § 5](TESTING_LESSONS_LEARNED.md) |
| Visual regression baseline (Playwright `to_have_screenshot`) | 1 day | Catches unintended CSS/layout regressions |
| Mutation testing spot-check (`mutmut` on `token_auth.py`) | 2–4 h | Validates that unit tests assert the right thing, not just achieve line coverage |
| Performance budget in CI (`test_performance.py` tagged `ci_smoke`) | 1 day | Pins per-endpoint p95 latency to prevent quiet regressions |

---

## Related documentation

- [`TESTING_LESSONS_LEARNED.md`](TESTING_LESSONS_LEARNED.md) — patterns for flakiness-free E2E tests (read before writing Playwright tests).
- [`JOURNEY_CONTRACTS.md`](JOURNEY_CONTRACTS.md) — end-to-end journey definitions.
- [`MAILPIT_CONFIGURATION.md`](MAILPIT_CONFIGURATION.md) — SMTP capture for email tests.
- [`PLAYWRIGHT_CONTAINER.md`](../PLAYWRIGHT_CONTAINER.md) — Playwright container architecture.
