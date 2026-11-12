# Playwright UI Testing Guide

**Project**: netcup-api-filter  
**Updated**: 2026-11-12

---

## Overview

UI tests live in `ui_tests/tests/` and use Playwright via `ui_tests/playwright_client.py`.
The browser connection is owned by `ui_tests/pwmcp_connection.py`. One pytest session (one xdist
worker) starts one Playwright driver and makes one browser connection; each test receives only a
fresh context and page.

| Mode | When | How |
|------|------|-----|
| **pwmcp remote** | gate/e2e, shared Docker stacks | Set `PLAYWRIGHT_SERVER_WS`; the session checks `/contract`, then calls `connect(ws_url)` once with bounded retry and lease headers |
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

The runner renders `PWMCP_LEASE_SECONDS` and `PWMCP_SESSION_LABEL`; both are required when the remote
endpoint is set. At session start the harness:

1. GETs `/contract` and checks schema and Playwright major.minor compatibility.
2. Starts one Playwright driver and connects once with a finite timeout.
3. Retries only HTTP 503 ("all browser slots are in use") with bounded exponential backoff.
4. Creates a fresh context/page per test and checks browser liveness between tests.
5. Reconnects exactly once if the shared browser died; otherwise the session fails clearly.
6. Prints `pwmcp connects=<n> contexts=<n>` in the terminal summary.

The gateway allows two estate-wide clients. Two concurrent worktrees can therefore run; a third sees
503 until a slot frees. The browser is idle-recycled only when no websocket session is open. An open
session also prevents the 30-second idle recycle during slow app-start tests, so no heartbeat is
required.

### Role-specific storage state

Use an explicit fixture or role:

| Fixture | Starting state |
|---|---|
| `admin_browser` / back-compat `browser` | admin persona cache only |
| `user_browser` | user persona cache only |
| `anon_browser` | no cookies or origin storage |
| `browser_session("admin"|"user"|"anonymous")` | the named cache, or none |

The admin/user cache files are created after a real login and live in the per-session work dir. Never
put auth state in the repository. Public/login/registration/forgot-password tests use
`anon_browser`; do not load admin state and clear cookies afterwards.

Assertion and log payloads must remain shareable: `Browser.fill`/`select` record lengths, not values,
and `Browser.evaluate` records script length and argument type. Workflow/test diagnostics use
`logging`, never `print`, and omit passwords, tokens, 2FA or verification codes, invite/reset links,
and session cookies.

---

## In-process mode for isolated manual runs

Install browser binaries once:

```bash
python -m playwright install --with-deps chromium
```

Run a narrow test in an environment that actually has the app and test dependencies:

```bash
python -m pytest ui_tests/tests/smoke -q -p no:cacheprovider -o addopts=
```

No containers required.

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
| `PWMCP_LEASE_SECONDS` | rendered by runner (`1800`) | Requested gateway lease, capped by `/contract` |
| `PWMCP_SESSION_LABEL` | rendered by runner | Gateway admin/log session label |
| `E2E_PWMCP_CONTRACT_TIMEOUT_SECONDS` | `10` | `/contract` fetch timeout |
| `E2E_PWMCP_CONNECT_TIMEOUT_SECONDS` | `30` | Per connect-attempt timeout |
| `E2E_PWMCP_CONNECT_RETRY_TOTAL_SECONDS` | `120` | Total deadline for HTTP 503 retry |
| `E2E_PWMCP_CONNECT_RETRY_INITIAL_SECONDS` | `1` | First 503 backoff |
| `E2E_PWMCP_CONNECT_RETRY_MAX_SECONDS` | `8` | Maximum 503 backoff |
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
