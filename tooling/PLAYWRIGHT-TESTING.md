# Playwright UI Testing Guide

**Project**: netcup-api-filter  
**Updated**: 2026-06

---

## Overview

UI tests live in `ui_tests/tests/` and use Playwright via `ui_tests/playwright_client.py`.
The test runner connects to a browser in one of two modes:

| Mode | When | How |
|------|------|-----|
| **In-process** (default) | local dev, CI | `playwright install` installs browser binaries; `PlaywrightClient.connect()` launches them locally |
| **Remote service** | shared dev envs, Docker stacks | Set `PLAYWRIGHT_SERVER_WS`; the client calls `bt.connect(ws_url)` instead of `bt.launch()` |

Both modes expose the identical `Browser` / `Page` / `page.request` API — tests are
unaware of which mode is active.

---

## In-process mode (default)

Install browser binaries once:

```bash
python -m playwright install --with-deps chromium
```

Run tests:

```bash
pytest ui_tests/tests -v
```

No containers required.

---

## Remote Playwright-as-a-Service mode

When an external `playwright run-server` container is available on the Docker
network, point tests at it:

```bash
export PLAYWRIGHT_SERVER_WS=ws://<service-name>:3000/
pytest ui_tests/tests -v
```

**Key rules**:
- Address the service by its **container name** on the shared network (never `localhost`).
- The server controls headless mode; the `PLAYWRIGHT_HEADLESS` env var is ignored
  when connecting remotely.
- No `playwright install` is needed on the client side (browser binaries live on
  the server).

Example with the estate's resolved pwmcp service:

```bash
export PLAYWRIGHT_SERVER_WS=ws://<pwmcp-service>:3000/
```

---

## Running the full local suite

```bash
# Build the production-parity local deployment and run tests
run-gate local-build (see run-gate.toml)

# Reuse an existing deployment
run-gate local-build (see run-gate.toml)
```

With remote Playwright:

```bash
PLAYWRIGHT_SERVER_WS=ws://<pwmcp-service>:3000/ run-gate local-build (see run-gate.toml)
```

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
| `PLAYWRIGHT_HEADLESS` | `true` | Headless mode for in-process launch (ignored for remote) |
| `NAF_E2E_ADVERTISE_HOST` | _(set by tooling/test-runner)_ | Runner container name; the browser reaches the per-session app at `http://<it>:<port>` |
| `SCREENSHOT_DIR` | `E2E_SCREENSHOT_DIR` (`tmp/e2e-screenshots`) | Screenshot output directory |

---

## Test organisation

```
ui_tests/
├── playwright_client.py    # Browser connection (in-process or remote)
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
