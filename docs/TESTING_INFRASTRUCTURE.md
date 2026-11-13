# Testing Infrastructure

## Overview

This document describes the testing infrastructure: the two-layer suite layout,
the local runners, the CI jobs, and the tooling that supports them.

---

## Testing types at a glance

| Type | What it checks | Framework | Count | Speed |
|---|---|---|---|---|
| Unit + property + hermetic HTTP | Pure functions, validation invariants, and HTTP-only behaviour (DDNS protocols, REST API security, registration negatives, admin bulk actions, quick update) via the Flask test client, tmp SQLite DB and in-memory Netcup fake | pytest + Hypothesis | many (see `tests/`) | minutes (bcrypt-bound) |
| Route smoke | Every Flask route returns correct status | Playwright | 86 | Medium |
| Widget | Individual UI components in isolation | Playwright | 19 | Medium |
| Round-trip | UI action → backend state via 3 channels | Playwright | ~25 | Medium |
| Security | 2FA, recovery codes, IP allowlist, attack attribution (REST API security moved to `tests/`) | Playwright | ~45 | Medium |
| Feature E2E | Full browser feature workflows (registration, DNS, audit, etc.) | Playwright | ~165 | Slow |
| Journey | Multi-step stateful scenario suites (j1/j2/j3) | Playwright | ~20 | Slow |
| Nonfunctional | Accessibility + performance | Playwright | ~20 | Slow |
| Upstream resilience | netcup_client / filter_proxy bad-response paths | pytest + unittest.mock | 24 | <30 s |
| Mocks / live | Mock-service self-tests (GeoIP mock moved to `tests/`) + real-backend tests | Playwright | ~15 | Varies |
| **Total (ui_tests)** | | | **~355** | |

The unit suite runs in CI on every push (<60 s). A tagged `@pytest.mark.ci_smoke` subset
of 93 Playwright tests also runs in CI against a per-session app + Mailpit on every PR.
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
- **Hermetic HTTP modules** (`tests/test_*_http.py`, moved from the browser lane in S8): requests
  that need no browser/JS run through the Flask test client against a tmp SQLite DB with an
  in-memory Netcup upstream (`tests/fake_netcup.py`) and real CSRF (`tests/http_helpers.py`).
  They cover the DynDNS2/No-IP endpoints (`test_ddns_protocols_http.py`), REST API security
  (`test_api_security_http.py`), registration/approval negatives and CSRF
  (`test_registration_negative_http.py`), admin bulk actions (`test_admin_bulk_http.py`), the
  DDNS quick-update/realm UI routes (`test_ddns_quick_update_http.py`) and the GeoIP mock
  self-test (`test_mock_geoip_http.py`). Assertions check the DB (ActivityLog, token usage,
  account/realm rows) and the upstream zone contents, not only status codes.
- Hypothesis property tests live in `tests/test_*_property.py`, default profile `ci` (50 examples), set `HYPOTHESIS_PROFILE=dev` for 500.
- CI runs this suite on every push/PR (see **`unit-tests` job** below).

### Gate lanes (run-gate + assay)

`run-gate.toml` is the single source for lanes; `assay.toml` declares what each assay lane proves.
`run-gate --list` is authoritative. Rigor ladder per security-relevant module (`token_auth`,
`account_auth`, `recovery_codes`, `utils`): `<m>` = R0+R1 whole-target coverage floor, `<m>_r3` = plus an
import-break canary, `<m>_r2` = native mutation (asynchronous, never a gate member). `gate` = both unit
lanes + trove + R1; `release-gate` adds the R3 canaries. Assay lanes are judged on the 3.14 runner
(assay backlog B229); 3.11 is gated by the plain pytest lane `unit-py311`. Browser tests use the estate
pwmcp instance: the runners and `app-local` join its network (`PWMCP_NETWORK`).

**Every checkout runs its own runners.** The main checkout and each linked worktree have their own ciu
`INSTANCE_ID`; run-gate execs into `naf-<INSTANCE_ID>-test-runner-py311`/`-py314` of the judged checkout
(the name comes from that checkout's rendered `ciu.global.toml`). `ciu up --dir tooling/test-runner` in the
checkout is therefore a precondition of any gate there (it builds `test-runner:py3xx-<INSTANCE_ID>`,
CIU-117); a missing runner fails as "no such container". A linked worktree's runner mounts the worktree
plus the main checkout's `.git` (the git common dir its `.git` pointer file names): without it assay lanes
abort with `ERROR/GIT_FAILED` and git-backed hygiene tests fall back to a filesystem walk. The mount is
read-write because `snapshot_selection = "repository"` lanes run `git worktree add`; details in
[`tooling/test-runner/README.md`](../tooling/test-runner/README.md).

### `ui_tests/` — Playwright E2E (browser required)

**Every e2e session owns its app and database** (credentials/test-setup plan, S1/S3/S4). The suite
needs no running app, no target URL and no credentials from the cockpit:

1. `run-gate local-build` builds `deploy-local/` and its **golden DB** (`netcup_filter.db`: exactly
   the shipped admin with `must_change_password`, the Mailpit email config and the **mock Netcup
   backend** as `netcup_config`: URL `MOCK_NETCUP_API_URL` (forwarded from the cockpit after sourcing
   `.env.services`; the build fails without it), credentials the `LOCAL_MOCK_NETCUP_*` keys of `.env.defaults` = the public test
   credentials of `ui_tests/mock_netcup_api.py`, checked for drift by `tests/test_mock_netcup_seed.py`.
   Without it every DNS read is an HTTP 500. Tarball and OCI never get it. Tests that rewrite
   `netcup_config` through the admin UI must restore it. Nothing may serve that file.
2. The session fixture (`ui_tests/conftest.py` → `ui_tests/e2e_env.py`) copies the golden DB (SQLite
   backup API) into a temp work dir, checks it is pristine, and **provisions personas** into the copy
   (`ui_tests/personas.py`): `e2e-admin` (TOTP, deterministic logins), `e2e-mail-admin` (email 2FA;
   the 2FA failure/lockout tests may lock it), `e2e-user01` (email 2FA, full-CRUD realm + token),
   `e2e-readonly` (read-only realm + token), the demo domain root and some activity history. All
   passwords, TOTP seeds and tokens are random per session and live in memory only.
3. It starts `gunicorn passenger_wsgi:application` from the deploy tree (same package, same entry
   point as production) on a free port inside the 3.11 runner, with `FLASK_ENV=local_test` and
   `FLASK_SESSION_COOKIE_SECURE=false` stated explicitly (plain HTTP). The pwmcp browser reaches it
   at `http://$NAF_E2E_ADVERTISE_HOST:<port>` (the runner's container name, set by
   `tooling/test-runner`).
4. A broken environment (no deploy tree, mutated golden DB, app not ready) stops the whole session
   with one message (`pytest.exit`, exit code 3) instead of hundreds of failing logins.

Tests that change credentials start their **own** instance (`e2e_env.app_instance(prepare=...)`):
the shipped admin's forced first-login change is tested exactly once
(`smoke/test_installation_workflow.py`); voluntary password changes use a throwaway admin
(`personas.provision_throwaway_admin`). Nothing is ever written back to a state file. Every session
DB except the forced-change test's (`app_instance(keep_shipped_admin=True)`) gets an unknown random
password for the shipped admin, because the session app listens on the shared pwmcp network. The
port is chosen free and retried if gunicorn finds it taken; the fixture stops the app on any setup
error. Keep the work
dir for debugging with `NAF_E2E_KEEP_WORKDIR=1`. Settings: `E2E_*` keys in `.env.defaults`.

### Browser connection and state model

The Playwright driver is session-scoped; its pwmcp browser connection is recycled between test
files or after the configured recycle window, whichever comes first:

```text
pytest session / xdist worker
  -> GET /contract, validate schema + Playwright major.minor once
  -> start one Playwright driver
  -> bounded chromium.connect(), retrying only gateway HTTP 503
  -> before a test's first context, recycle at a test-file boundary or after
     E2E_PWMCP_RECYCLE_INTERVAL_SECONDS (whichever comes first); reconnect immediately
  -> for each test: fresh browser.new_context() [+ page] -> test -> close context
  -> between tests only, replace a dead browser (capped by E2E_PWMCP_MAX_RECONNECTS)
     or renew a lease that is near expiry
  -> latch a failed replacement: every later test fails immediately with the original reason
  -> session teardown and SIGTERM/SIGINT: close the browser connection and stop the driver
```

`ui_tests/pwmcp_connection.py` owns this lifecycle; `ui_tests/conftest.py` installs it through the
autouse `pwmcp_connection` session fixture and the `pwmcp_recycle_window` function fixture. The
counters are emitted once at the end of the session as
`pwmcp connects=<n> reconnects=<n> recycles=<n> contexts=<n> leaked_contexts=<n>`.
`connects` counts successful browser connections including the first, `reconnects` counts successful
replacements, `recycles` counts the
intentional file/time/lease replacements, and `contexts` counts successful contexts. A
`pwmcp reconnect causes: ...` line and a `pwmcp connection latched as failed: ...` line follow when
applicable. There is one driver per pytest process (therefore one per xdist worker); xdist is not
enabled by the current e2e lane, and its worker counters are not aggregated by the controller.
An open context found at a planned file/time recycle is counted as leaked, then disposed by closing
the old browser so one missed context cleanup does not fail every later file. The lease-renewal path
still waits for a between-test point with no open contexts.

The contract check is fail-fast: `/contract` must publish schema version 1 and a protocol matching
the installed Playwright major.minor, plus a maximum lease. A missing contract, incompatible
Playwright, or unavailable gateway exits the session with code 3 and one actionable message. Remote
connects carry `X-PWMCP-Lease-Seconds` and `X-PWMCP-Session-Label`, have a finite per-attempt timeout,
and retry HTTP 503 ("all browser slots are in use") with exponential backoff under one 60-second
default deadline (three attempts with the default 15-second and 30-second backoffs). Exhaustion says
the slots are busy and prints the `naf-e2e:<lane>:<pid-or-xdist-worker>` session label shown in the
pwmcp admin view. The retry interval, connect timeout and backoffs are configurable in `.env.defaults`.

An open pwmcp websocket is an active gateway session. The 30-second idle browser recycle runs only
while there are zero sessions, so an open connection survives the long installation/app-start test
without a heartbeat. At each test-file boundary, or after the default 1500-second (25-minute) window,
the harness closes the old websocket and reconnects immediately. It requests a short 1800-second
lease by adding the 300-second `E2E_PWMCP_LEASE_RENEW_MARGIN_SECONDS` to the recycle interval; the
requested value is capped by `/contract` `max_lease_seconds` (7200). If a configured interval reaches
the gateway cap, the margin triggers an earlier between-test renewal. Closing a websocket releases
its slot immediately, and a crashed pytest can hold a slot for at most the short lease rather than the
lane budget. A browser found dead between tests (gateway restart or recycle) is replaced at most
`E2E_PWMCP_MAX_RECONNECTS` (3) times. A failed replacement is latched: every later test errors
immediately with the same reason instead of spending a connect/503-retry budget each. A browser lost
in the middle of a test is still a failure of that test (there is no mid-test retry).
At a deliberate recycle, another estate consumer can take the released slot before the immediate
reconnect; if its bounded 503 retry is exhausted, the session latches failed. B083 tracks two options:
give recycle reconnects a longer deadline, or skip a recycle while the slot is contested.
SIGTERM/SIGINT cleanup is bounded by `E2E_PWMCP_SIGNAL_CLEANUP_TIMEOUT_SECONDS`; a second signal
forwards immediately. The handler runs only while the asyncio loop is running, so a signal received
during blocking synchronous work waits until the loop can dispatch it.

### Per-role browser state

Storage state is explicit and per role:

| Fixture/context | Storage loaded |
|---|---|
| `admin_browser`, and the back-compat `browser` alias | `admin_auth_state.json` |
| `user_browser` | `user_auth_state.json` |
| `anon_browser` | none |
| `browser_session("admin"|"user"|"anonymous")` | the named role, or none for anonymous |

State files are created after a successful role login and live under the throwaway session work dir,
never in the repository. A context for a role whose file does not exist yet starts empty (the file is
never handed to Playwright, which would raise `FileNotFoundError`); the login helpers then log in and
write it. Every fresh login rewrites the role's file (a test may have invalidated the old session);
a cached login that is still valid reuses it unchanged. Login is therefore normally done once per role
per session, while admin and user cookies cannot contaminate each other. Public pages, login forms, registration, and
forgot-password tests use an explicit anonymous context; cookie clearing is a symptom, not the
isolation mechanism. `ParallelSessionManager` still creates multiple independent contexts on the
shared browser and selects the admin/user cache only for the matching session persona.

### Browser operation redaction

`Browser.fill`, `Browser.select`, and `Browser.evaluate` never place typed values, selected values, or
evaluated code in `ToolError.payload`; they record lengths/type and a redacted operation message.
`Browser.goto` masks one-time URL tokens on timeout and other navigation errors; the `request_*`
helpers and `verify_status` mask tokens in errors (the segment after `/verify/`, `/reset/`,
`/reset-password/`, `/invite/`) and secret-named query values and request params, in both the payload
and the Playwright message. Tests and workflow helpers use `logging`,
never `print`, and do not log passwords, tokens, 2FA or verification codes, invite/reset links, or full
session cookies. The unit lane enforces the `ToolError` redaction and a source guard over `print(...)`
and logger calls, plus f-string `raise`, `assert`, and `pytest.fail` messages in every `ui_tests/`
Python file. It flags secret-named variables and attributes such as `settings.admin_password`; only
length, truthiness, or type metadata may be logged or included in a failure message. The guard runs
without a browser.

```bash
# cockpit env, in this order: .env.services runs `ciu resolve`, which needs the layers before it
eval "$(ciu env print)"
export PWMCP_NETWORK="$(sed -n 's/^network_name = "\(.*\)"$/\1/p' /srv/pwmcp-instance/ciu.global.toml)"
set -a; . ./.env.guard; . ./.env.services; set +a
ciu up --dir tooling/test-runner          # this checkout's own runners
ciu up --dir tooling/mailpit; ciu up --dir tooling/geoip-mock; ciu up --dir tooling/netcup-api-mock
run-gate local-build --worktree "$PWD"   # deploy-local/ + golden DB (3.11 runner)
run-gate e2e --worktree "$PWD"           # full suite, per-session app, estate pwmcp
```

`build_deployment.py --local` reads `MAILPIT_HOST` and `MOCK_NETCUP_API_URL` only from its process
environment (run-gate forwards them from the cockpit, `forward_env` in `run-gate.toml`); it never
evaluates `.env.services` itself, because `ciu` is not installed in the runner. A missing value fails
the build with an instruction to source `.env.services` first.

**Remote read-only smoke.** `NAF_E2E_TARGET=remote` (default: local) starts no instance and binds
`ui_tests.config.settings.bind_remote()` to a deployed host from `NAF_REMOTE_*` env vars (password via
`*_FILE`); `allow_writes=False`, no user persona/tokens/DB path. Only tests marked `remote_smoke`
run (`smoke/test_remote_smoke.py`); the rest are skipped by that explicit condition. Hermetic checks:
`tests/test_e2e_remote_config.py`. How to run it: [`WEBHOSTING_TESTING_GUIDE.md`](WEBHOSTING_TESTING_GUIDE.md).

**Directory layout** under `ui_tests/tests/` (E2 schema — applied 2026-06-14):

```
ui_tests/tests/
  smoke/          # Route-smoke + widget smoke: page-loads/status/element checks
  roundtrip/      # Independent-channel backend-truth (cross_role_*, dns crud, ddns)
  security/       # Auth, 2FA, recovery codes, IP allowlist, attack attribution
  features/       # Feature E2E: registration, email, backends, config, audit, etc.
  journeys/       # Stateful multi-step sequences (j1/j2/j3 + test_journey_master)
  nonfunctional/  # Accessibility and performance
  live/           # @live — require real external dependencies
  mocks/          # Mock-service self-tests that need real sockets/fixed ports (test the mock, not the app)
```

**Marker taxonomy** (registered in `pytest.ini`):

| Marker | Selects |
|--------|---------|
| `smoke` | Route and widget smoke tests |
| `roundtrip` | Backend-truth round-trip tests |
| `security` | Security/auth/2FA tests |
| `feature` | Feature E2E tests |
| `journey` | Stateful journey tests |
| `nonfunctional` | Accessibility + performance |
| `mock_selftest` | Mock-service self-tests |
| `accessibility` | Accessibility-specific (subset of nonfunctional) |
| `performance` | Performance-specific (subset of nonfunctional) |
| `live` | Requires real external dependencies |
| `remote_smoke` | Read-only subset allowed against a deployed instance (`NAF_E2E_TARGET=remote`) |
| `ci_smoke` | Runs in CI against a per-session app + Mailpit |
| `installation` | The forced first-login change of the shipped admin (own instance) |
| `e2e_local` | Requires local deployment with mock services |

Use `-m <marker>` to select by bucket regardless of path.

---

## Standard local runner

There is no cockpit runner script: the e2e flow is the two run-gate lanes above (header of
`run-gate.toml` has the full sequence including the mock stacks). To run a subset, use the
lane's command inside the runner, e.g.
`docker exec -w "$PWD" naf-<INSTANCE_ID>-test-runner-py311 /opt/tester-venv/bin/python -m pytest ui_tests/tests/smoke -q -p no:cacheprovider -o addopts=`.
`tooling/app-local` is the long-lived instance for humans; the e2e lane never uses it.

---

## Route-smoke suite

**`ui_tests/tests/smoke/test_route_smoke.py`** (86 tests) — parametrized over every route
discovered at import time via Flask's URL map. New routes added to any blueprint are
automatically smoke-tested without any manual update. Smoke checks: correct status codes,
no unhandled exceptions, basic page structure for HTML routes.

Contributors get smoke for free; they must still add round-trip tests for new behavior
(see `roundtrip/test_cross_role_account_lifecycle.py` for the pattern).

---

## CI jobs

Two jobs run on every push and pull request (`.github/workflows/ci.yml`):

### `unit-tests`

Runs `python -m pytest tests/` with coverage. No services required; fast (< 60 s).
Uploads `coverage.xml` as an artifact on every run.

### `e2e-smoke`

Builds the deploy tree with `python build_deployment.py --local --python-version 3.11 --build-dir deploy-local`
(the same builder as `run-gate local-build`; the golden DB holds only the shipped admin with
`must_change_password=1` plus the Mailpit email config and the mock Netcup backend), then runs all tests tagged
`@pytest.mark.ci_smoke` (93 tests) with in-process Playwright. There is no external app server and no
bootstrap script: the `e2e_environment` session fixture (`ui_tests/e2e_env.py`) starts a per-session app
on a copy of the golden DB and provisions the personas, exactly as in the local lane. Services: Mailpit
on ports 1025/8025 (no authentication), and the Netcup CCP mock (`flask --app ui_tests.mock_netcup_api`, port 5555, started before the build).

Env vars set by the job:

| Var | Value | Purpose |
|-----|-------|---------|
| `MAILPIT_HOST` | `localhost` | Mailpit container identity written into the golden DB's email config (`build_deployment.py --local`; locally `.env.services` reads it from `ciu resolve --json`) |
| `MOCK_NETCUP_API_URL` | `http://localhost:5555` | Netcup mock written into the golden DB's `netcup_config` (`build_deployment.py --local`; locally `.env.services` reads the container identity from `ciu resolve --json`) |
| `NAF_E2E_ADVERTISE_HOST` | `127.0.0.1` | Host under which the browser reaches the per-session app (same host as the runner) |
| `MAILPIT_URL` | `http://localhost:8025` | Mailpit REST client |
| `NAF_E2E_KEEP_WORKDIR` | `1` | Keeps the per-session work dir so the app logs can be uploaded on failure |

The app instance itself states `FLASK_ENV=local_test` and `FLASK_SESSION_COOKIE_SECURE=false` (plain
HTTP origin); the job does not set them.

**Failure artifacts**: on failure the job uploads the per-session app logs (`/tmp/naf-e2e-*/*.log`), `mailpit-messages.json`,
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

`ui_tests/tests/roundtrip/test_cross_role_*.py` verify that an admin action propagates to the user's
API/portal experience via independent channels:

| File | What it tests |
|------|---------------|
| `roundtrip/test_cross_role_account_lifecycle.py` | disable/enable account (401+error_code), invite+approval, password reset link |
| `roundtrip/test_cross_role_realm_propagation.py` | realm approval/rejection/revocation + token behavior |
| `roundtrip/test_cross_role_token_lifecycle.py` | admin revoke, user self-revoke, read-only scope enforcement |

See `test_cross_role_account_lifecycle.py` — it is the **pattern file** for all cross-role
suites (channel use, `wait_for`, state cleanup in `finally`).

`ui_tests/cross_role_helpers.py` provides shared helpers (login, account creation via
invite form, realm/token creation).

---

## Troubleshooting

### App won't start

```bash
# Check logs
docker logs naf-<INSTANCE_ID>-app

# Check if port is in use
netstat -tuln | grep 5100

# Rebuild from scratch
run-gate local-build (see run-gate.toml)
```

### Tests fail with "Connection Refused"

```bash
# Verify the app is running
curl http://localhost:5100/health

# Check the configured local port in the built deployment
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
| Shared utilities | `utils.py` | 50% | Validators covered by `test_validators_unit.py` + `test_validators_property.py` (Hypothesis) |
| DDNS protocols | `api/ddns_protocols.py` | 42% | Parsing logic covered by `test_ddns_parsing_unit.py` + `test_ddns_property.py` (Hypothesis) |
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

## Mutation testing

Mutation testing is **assay R2** (native, asynchronous, never a gate member): lanes `<module>_r2` in
`assay.toml` for `token_auth`, `account_auth`, `recovery_codes` and `utils`, run with
`run-gate <module>_r2 --worktree <linked worktree>` in an ephemeral container with the cgroup observer.
A surviving mutant gets a root-cause analysis first: add a test that kills it, or record a waiver only for a
provably equivalent mutant. The former manual mutmut tooling was removed 2026-11-05.

## Gaps and next steps

Known gaps — none are blockers; documented here for future prioritisation.

| Gap | Effort | Value |
|---|---|---|
| Add `--cov-fail-under=22` to `pytest.ini` | 5 min | Prevents silent backslide |
| ~~Property-based testing (Hypothesis) for parsers/validators~~ DONE (2026-06-14) | — | `tests/test_ddns_property.py`, `tests/test_validators_property.py`, `tests/test_token_model_property.py` (~86 properties). Default profile `ci` (50 examples); set `HYPOTHESIS_PROFILE=dev` for 500 — see [`TESTING_LESSONS_LEARNED.md` § 5](TESTING_LESSONS_LEARNED.md) |
| Visual regression baseline (Playwright `to_have_screenshot`) | 1 day | Catches unintended CSS/layout regressions |
| ~~Mutation testing spot-check (`mutmut` on `token_auth.py`)~~ DONE (2026-06-14) | — | See `docs/plans/testing-hardening/MUTATION_REPORT.md` |
| Performance budget in CI (`test_performance.py` tagged `ci_smoke`) | 1 day | Pins per-endpoint p95 latency to prevent quiet regressions |

---

## Related documentation

- [`TESTING_LESSONS_LEARNED.md`](TESTING_LESSONS_LEARNED.md) — patterns for flakiness-free E2E tests (read before writing Playwright tests).
- [`JOURNEY_CONTRACTS.md`](JOURNEY_CONTRACTS.md) — end-to-end journey definitions.
- [`MAILPIT_CONFIGURATION.md`](MAILPIT_CONFIGURATION.md) — SMTP capture for email tests.
- [`PLAYWRIGHT_CONTAINER.md`](../PLAYWRIGHT_CONTAINER.md) — Playwright container architecture.
