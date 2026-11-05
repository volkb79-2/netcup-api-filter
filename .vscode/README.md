# VS Code Dev Tools

## Playwright

Playwright runs in-process by default.  No container is required.

For remote Playwright-as-a-Service, set `PLAYWRIGHT_SERVER_WS`:

```bash
export PLAYWRIGHT_SERVER_WS=ws://<service-name>:3000/
pytest ui_tests/tests -v
```

See `tooling/PLAYWRIGHT-TESTING.md` for the full guide.

## Deploy-test loop

Retired (cockpit-run script removed 2026-11-05): use the run-gate lanes in `run-gate.toml`.
