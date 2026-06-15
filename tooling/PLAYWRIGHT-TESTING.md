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

Example with a service named `naf-dev-playwright`:

```bash
export PLAYWRIGHT_SERVER_WS=ws://naf-dev-playwright:3000/
```

---

## Running the full local suite

```bash
# Build + deploy + test (all phases)
./deploy.sh local

# Skip build, run tests only
./deploy.sh local --tests-only
```

Or use the lightweight helper (no deploy):

```bash
source .env.workspace
./run-local-tests.sh
# With remote browser:
PLAYWRIGHT_SERVER_WS=ws://naf-dev-playwright:3000/ ./run-local-tests.sh
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
| `UI_BASE_URL` | `http://127.0.0.1:5100` | Flask app base URL |
| `SCREENSHOT_DIR` | `deploy-local/screenshots` | Screenshot output directory |
| `DEPLOYMENT_TARGET` | `local` | `local` or `webhosting` |

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
