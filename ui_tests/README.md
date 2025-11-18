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

## Running the suite

```bash
pytest ui_tests/tests -q
```

Screenshots stay inside the Playwright container under `/screenshots`; copy any
artifacts out with `docker cp playwright-mcp:/screenshots/<file> ./screenshots/`
if you need to attach them to an issue or PR.
