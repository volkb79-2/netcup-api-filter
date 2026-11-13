# Playwright UI Testing Guide

**Project**: netcup-api-filter  
**Updated**: 2026-11-13

---

## Overview

UI tests live in `ui_tests/tests/` and use Playwright via `ui_tests/playwright_client.py`.
The browser connection is owned by `ui_tests/pwmcp_connection.py`. One pytest session (one xdist
worker) starts one Playwright driver and reuses a gateway connection within a test file or recycle
window; each test receives a fresh context and page.

| Mode | When | How |
|------|------|-----|
| **pwmcp remote** | gate/e2e, shared Docker stacks | Set `PLAYWRIGHT_SERVER_WS`; the session checks `/contract`, then connects with bounded retry and short lease headers |
| **In-process** | isolated manual runs when browser binaries are installed | No `PLAYWRIGHT_SERVER_WS`; the session launches one local browser instead |

Both modes expose the identical `Browser` / `Page` / `page.request` API — tests are
unaware of which mode is active.

---

## Gate and pwmcp mode

The supported e2e path runs in the project's test-runner container and drives the estate pwmcp
instance. The cockpit never runs pytest. From a shell on the same shared network, the wrapper uses:

```bash
set -a; . ./.env.services; set +a
export PLAYWRIGHT_SERVER_WS=ws://pwmcp:3000/
run-gate local-build --worktree "$PWD"
run-gate e2e --worktree "$PWD"
```

At session start the harness:

1. GETs `/contract` and checks schema and Playwright major.minor compatibility.
2. Starts one Playwright driver and connects with a finite timeout.
3. Retries only HTTP 503 ("all browser slots are in use") with bounded exponential backoff under a
   60-second default deadline (three attempts with the default backoffs).
4. Creates a fresh context/page per test. Before the next test file, or after
   `E2E_PWMCP_RECYCLE_INTERVAL_SECONDS`, the harness closes the browser connection and reconnects
   immediately; a per-test fixture runs this before new contexts open.
5. Between tests, it replaces a dead browser (at most `E2E_PWMCP_MAX_RECONNECTS` times per session)
   and renews a lease near expiry. A failed replacement is latched: every later test fails
   immediately with the same reason, without connecting again.
6. Session teardown and SIGTERM/SIGINT close the browser connection and stop the driver.
7. Prints `pwmcp connects=<n> reconnects=<n> recycles=<n> contexts=<n>` once in the terminal summary,
   plus reconnect causes or the latched failure when present.

The gateway allows two estate-wide clients. Two concurrent worktrees can therefore run; a third sees
503 until a slot frees. On exhaustion, the error says the slots are busy and gives the
`naf-e2e:<lane>:<pid-or-xdist-worker>` label to find in the pwmcp admin session list. The browser is
idle-recycled only when no websocket session is open. An open session prevents the 30-second idle
recycle during slow app-start tests, so no heartbeat is required. The default 25-minute recycle
interval plus 5-minute margin requests an 1800-second lease; `/contract` caps it at 7200 seconds.

### Role-specific storage state

Use an explicit fixture or role:

| Fixture | Starting state |
|---|---|
| `admin_browser` / back-compat `browser` | admin persona cache only |
| `user_browser` | user persona cache only |
| `anon_browser` | no cookies or origin storage |
| `browser_session("admin"|"user"|"anonymous")` | the named cache, or none |

The admin/user cache files are created after a real login and live in the per-session work dir. Each
fresh login rewrites that role's file; a valid cached login reuses it. Never put auth state in the
repository. Public/login/registration/forgot-password tests use
`anon_browser`; do not load admin state and clear cookies afterwards.

Assertion and log payloads must remain shareable: `Browser.fill`/`select` record lengths, not values,
and `Browser.evaluate` records script length and argument type. Navigation and request failures
redact one-time URL path tokens and secret-named query values from the payload and Playwright error
message. Workflow/test diagnostics use `logging`, never `print`, and omit passwords, tokens, 2FA or
verification codes, invite/reset links, and session cookies.

---

## In-process mode for isolated manual runs

Install browser binaries once:

```bash
python -m playwright install --with-deps chromium
```

The project-supported local path uses Run-Gate so the declared runner supplies the dependencies and
service topology:

```bash
run-gate local-build --worktree "$PWD"
run-gate e2e --worktree "$PWD"
```

CI's `e2e-smoke` job uses the in-process mode because it installs the matching browser in its own
runner; local e2e uses pwmcp.

**Key rules**:
- Address the service by its **container name** on the shared network (never `localhost`).
- The server controls headless mode; the `PLAYWRIGHT_HEADLESS` env var is ignored
  when connecting remotely.
- No `playwright install` is needed on the client side (browser binaries live on
  the server).

## Running the full local suite

```bash
# Build the production-parity local deployment and run tests
run-gate local-build --worktree "$PWD"

run-gate e2e --worktree "$PWD"
```

`run-gate.toml` remains the source of truth for the exact lane argv and environment.

---

## CI (GitHub Actions)

CI installs Playwright binaries in-process and runs the `ci_smoke` test subset.
See `.github/workflows/ci.yml` → `e2e-smoke` job.  To switch CI to a remote
service, set `PLAYWRIGHT_SERVER_WS` as a repo secret/env and remove the
`playwright install` step.

---

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `PLAYWRIGHT_SERVER_WS` | _(unset)_ | WebSocket URL of remote `run-server`; empty = in-process |
| `E2E_PWMCP_LANE_NAME` | `e2e` | Lane component of the `naf-e2e:<lane>:<pid-or-xdist-worker>` admin label |
| `E2E_PWMCP_CONTRACT_TIMEOUT_SECONDS` | `10` | `/contract` fetch timeout |
| `E2E_PWMCP_CONNECT_TIMEOUT_SECONDS` | `30` | Per connect-attempt timeout |
| `E2E_PWMCP_CONNECT_RETRY_TOTAL_SECONDS` | `60` | Total deadline for HTTP 503 retry |
| `E2E_PWMCP_CONNECT_RETRY_INITIAL_SECONDS` | `15` | First 503 backoff |
| `E2E_PWMCP_CONNECT_RETRY_MAX_SECONDS` | `30` | Maximum 503 backoff |
| `E2E_PWMCP_RECYCLE_INTERVAL_SECONDS` | `1500` | Reconnect after this window or at a test-file boundary, whichever comes first |
| `E2E_PWMCP_LEASE_RENEW_MARGIN_SECONDS` | `300` | Lease headroom; added to the recycle interval and used for early between-test renewal |
| `E2E_PWMCP_MAX_RECONNECTS` | `3` | Dead-browser replacements per session before the session latches as failed |
| `PLAYWRIGHT_HEADLESS` | `true` | Headless mode for in-process launch (ignored for remote) |
| `NAF_E2E_ADVERTISE_HOST` | _(set by tooling/test-runner)_ | Runner container name; the browser reaches the per-session app at `http://<it>:<port>` |
| `SCREENSHOT_DIR` | `E2E_SCREENSHOT_DIR` (`tmp/e2e-screenshots`) | Screenshot output directory |

---

## Test organisation

```
ui_tests/
├── playwright_client.py    # Browser connection (in-process or remote)
├── pwmcp_connection.py     # Session driver/connect, contract, retry, role state
├── conftest.py             # pytest fixtures
├── config.py               # Test config from environment
└── tests/
    ├── smoke/              # Smoke tests (fast, ci_smoke mark)
    ├── journeys/           # Full user journeys
    ├── features/           # Feature-specific tests
    ├── roundtrip/          # Cross-role verification tests
    ├── security/           # Security tests
    ├── nonfunctional/      # Performance, accessibility
    ├── mocks/              # Mock-service tests
    └── live/               # Real-service tests (requires credentials)
```
