# Playwright Browser Architecture

> The old `tooling/playwright/` container has been removed.  Browser automation
> now runs in-process by default, or connects to an external
> Playwright-as-a-Service container via `PLAYWRIGHT_SERVER_WS`.

## Quick Start

```bash
# Install UI test deps and browser binaries (in-process mode, default)
pip install -r ui_tests/requirements.txt
playwright install --with-deps chromium

# Run tests
pytest ui_tests/tests -v
```

## Remote Playwright-as-a-Service

When an external `playwright run-server` container is available on the shared
Docker network:

```bash
export PLAYWRIGHT_SERVER_WS=ws://<service-name>:3000/
pytest ui_tests/tests -v
```

- Address the service by **container name** (never `localhost`).
- No `playwright install` needed on the client side.
- The server controls headless mode.

See `tooling/PLAYWRIGHT-TESTING.md` for the full guide.
