# UI Regression Tests

Automated UI coverage is implemented on top of the Playwright MCP harness that
already runs under `tooling/playwright-mcp`. The tests are written in Python
with `pytest` + `pytest-asyncio` and drive the remote browser through the MCP
HTTP endpoint.

## Prerequisites

1. Start the MCP Playwright container and ensure screenshots are writable:
   ```bash
   cd tooling/playwright-mcp
   ./run.sh up -d
   ```
2. Install the test dependencies (this intentionally lives in a standalone file
   so production dependencies are untouched):
   ```bash
   pip install -r ui_tests/requirements.txt
   ```
3. Export any environment overrides before running the suite. Defaults cover
   the current deployment documented in `AGENTS.md`.

## One-command local validation

When you need to spin up the seeded backend, TLS proxy, Playwright MCP harness,
and the pytest suite in one go, run `tooling/run-ui-validation.sh` from the
repository root. The script will:

- Render/stage the nginx config and cert bundle under `/tmp/netcup-local-proxy`.
- Start gunicorn on port `LOCAL_APP_PORT` (default 5100) with a seeded SQLite
   database inside `tmp/local-netcup.db`.
- Launch the nginx proxy + Playwright MCP harness via docker compose.
- Install `ui_tests/requirements.txt` (skip via `SKIP_UI_TEST_DEPS=1`).
- Export sensible defaults for `UI_BASE_URL` (`https://<host-gateway>:4443`)
   and `UI_MCP_URL` (`http://<host-gateway>:8765/mcp`).
- Execute `pytest ui_tests/tests -vv` and tear everything down afterwards.

Override `UI_BASE_URL`, `PLAYWRIGHT_HEADLESS`, `UI_ADMIN_PASSWORD`, and similar
variables before running the helper if you need to target a different host or
credentials.

| Variable | Default | Purpose |
| --- | --- | --- |
| `UI_BASE_URL` | `https://naf.vxxu.de` | Target deployment root |
| `UI_MCP_URL` | `http://172.17.0.1:8765/mcp` | MCP HTTP endpoint inside the devcontainer |
| `UI_ADMIN_USERNAME` | `admin` | Admin login |
| `UI_ADMIN_PASSWORD` | `admin` | Current admin password |
| `UI_ADMIN_NEW_PASSWORD` | _(unset)_ | Provide if the server still forces password rotation |
| `UI_CLIENT_ID` | `test_qweqweqwe_vi` | Expected client row in the admin UI |
| `UI_CLIENT_TOKEN` | `qweqweqwe-vi-readonly` | Token for the client portal |
| `UI_CLIENT_DOMAIN` | `qweqweqwe.vi` | Domain shown for the seeded token |
| `UI_SCREENSHOT_PREFIX` | `ui-regression` | Prefix when capturing screenshots |
| `UI_ALLOW_WRITES` | `1` | Set to `0` to skip destructive admin flows |
| `UI_SMOKE_BASE_URL` | _(unset)_ | Optional second target (e.g., production host) |
| `UI_SMOKE_ALLOW_WRITES` | `0` | Controls whether smoke profile may perform writes |
| `UI_SMOKE_ADMIN_*` etc. | inherit primary | Override credentials/domain for smoke profile |

When `UI_SMOKE_BASE_URL` is provided, each test parametrizes over both the
primary (usually local) environment and the smoke target, automatically
reusing credentials unless the `UI_SMOKE_*` overrides are supplied. Write-heavy
flows (client creation, Netcup config saves, etc.) automatically skip any
profile that sets `*_ALLOW_WRITES=0`, allowing safe read-only validation
against production.

## Running the suite

```bash
pytest ui_tests/tests -q
```

Screenshots stay inside the Playwright container under `/screenshots`; copy any
artifacts out with `docker cp playwright-mcp:/screenshots/<file> ./screenshots/`
if you need to attach them to an issue or PR.
