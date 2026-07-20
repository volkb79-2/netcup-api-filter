# naf-P04 — REPORT

**Status:** MERGED to `main` (merge `2d0d35e`, impl commit `121b23b` on wt/naf-p04).
Sonnet implementation in an isolated worktree; orchestrator review-merge (ACCEPTED as-is).

## What landed

- `src/netcup_api_filter/passenger_wsgi.py`: removed the redundant `json.dumps(...)` at
  **all 12** `set_setting(key, json.dumps(...))` sites (`set_setting` already JSON-encodes,
  so these double-encoded → `get_setting` returned a str → `.get(...)` raised → DNS API 500
  on real config). The carve named 10; the agent grepped and found 2 more that had drifted
  in since (`free_domains_config`, `platform_backends_config`) and fixed those too.
- `src/netcup_api_filter/password_reset.py`: extracted `_get_smtp_config()` (reads
  `smtp_config` then falls back to `email_config`, decodes a str value) and pointed all three
  senders at it — registration-verification and invite were `email_config`-only, so they
  silently failed on production (which writes `smtp_config`). None-on-invalid preserves the
  old False early-return behavior.

## Oracles

- **O1/O2** (settings round-trip as dicts, not strings; DNS-API config usable) — PROVEN via
  the REAL import path: the test copies `passenger_wsgi.py` into a scratch app-root with a
  crafted `app-config.toml`, `exec_module`s it in a subprocess, then reads
  `get_setting('netcup_config'|'smtp_config'|'geoip_config')` back inside the module's own
  app context and asserts `dict`. A cheaper `set_setting`/`get_setting` round-trip + a
  negative control (pre-fix `AttributeError`) back it up.
- **O3** (invite/verification send when only `smtp_config` is set) — PROVEN; plus the legacy
  `email_config`-only path still works, and `smtp_config` wins when both are present.

11 tests. `database.py` (the encode-once contract) left untouched — the callers were fixed,
not a shim added to `get_setting`.

## Gate

`./tooling/test-runner/testing-exec.sh unit` → **394 passed on python 3.11 AND 3.9**.

## Note for follow-up

The four write-only config keys (`session/admin_security/logging/notifications_config`) are
now correctly single-encoded but are still read by nobody (backlog **B-CONFIG**): wiring or
rejecting them is separate work.
