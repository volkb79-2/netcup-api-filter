---
schema_version: 1
id: naf-P04-settings-encoding-and-smtp-key
project: naf
title: "Settings store: double JSON encoding 500s the DNS API; invite email reads the wrong key"
tier: sonnet5-high
input_revision: "adcba7d"
depends_on: []
session: fresh
source: {kind: review, ref: "docs/deprecated/FOLLOWUP_REVIEW_2026-07-16.md#P0-7"}
scope:
  touch:
    - "src/netcup_api_filter/passenger_wsgi.py"
    - "src/netcup_api_filter/password_reset.py"
    - "tests/test_settings_encoding.py"
  forbid:
    - "src/netcup_api_filter/database.py"
    - "src/netcup_api_filter/models.py"
    - "src/netcup_api_filter/api/admin.py"
oracles:
  - id: O1
    observable: "After importing a TOML with a legacy `[netcup]` section, `get_setting('netcup_config')` returns a dict (not a str), and a DNS API request against that config reaches the client instead of raising AttributeError"
    negative: "passenger_wsgi json.dumps()es a value that set_setting encodes again, so get_setting returns a string, `.get(...)` on it raises AttributeError, and every DNS/DDNS request 500s until an admin re-saves the config"
    gate: unit
  - id: O2
    observable: "Every settings key written by the TOML importer round-trips through get_setting as the same Python type it was given (dict stays dict) — asserted for netcup_config, smtp_config, and geoip_config together, not just the one that crashes loudest"
    negative: "one key is fixed and the others keep double-encoding, surviving only via defensive isinstance(str) guards in their readers"
    gate: unit
  - id: O3
    observable: "`send_account_invite_email` sends when SMTP is configured under the `smtp_config` key (what the admin UI and the TOML importer actually write), not only under `email_config` (what the local Mailpit seeder writes)"
    negative: "the invite path reads only email_config and silently fails with 'Email configuration not set' on every production-configured deployment"
    gate: unit
gates: [unit]
escalate_if:
  - "a named contract cannot be met as specified"
  - "scope requires editing a forbidden file (database.py / models.py / api/admin.py)"
  - "removing the double encode breaks an existing reader that depends on the string form"
---

# P04 — Settings encoding + the SMTP key split

> Tier: sonnet5-high · Base branch: main (input_revision adcba7d).
> Source: the deep review, finding **P0-7**. Both bugs are invisible locally and fire
> only on a production-shaped config — which is exactly why they survived.

## Context to read first (read ONLY these)

- `src/netcup_api_filter/database.py` `set_setting` / `get_setting` (~line 448) — READ
  ONLY. `set_setting` JSON-encodes its value (via `Settings.set_value`). This is the
  contract: **callers pass a Python object, not a JSON string.**
- `src/netcup_api_filter/passenger_wsgi.py` — the TOML importer. ~line 383 does
  `set_setting('netcup_config', json.dumps(...))` → double encode. Check EVERY
  `set_setting(...)` call in this file for the same pattern (`smtp_config`,
  `geoip_config`, …), not only the netcup one.
- `src/netcup_api_filter/api/dns_api.py` ~line 38 and `api/ddns_protocols.py` ~line 203
  — READ ONLY. They do `config.get(...)` on the value; that is what raises
  `AttributeError` when it is a string. They are the victims, not the bug.
- `src/netcup_api_filter/api/admin.py` ~line 1908/1960 — READ ONLY. Shows the CORRECT
  writer shape (passes a dict) and that the admin UI writes the **`smtp_config`** key.
- `src/netcup_api_filter/password_reset.py` ~line 459 (registration verification) and
  ~586 (`send_account_invite_email`) — read only `email_config`. Compare with
  `send_password_reset_email` (~line 317), which already delegates to
  `notification_service._get_smtp_config()`.
- `src/netcup_api_filter/notification_service.py` `_get_smtp_config` — the ONE reader
  that already handles both keys and both encodings. This is the helper to reuse
  (AGENTS.md §3: don't re-implement).
- `src/netcup_api_filter/bootstrap/seeding.py` ~line 450 — writes `email_config`; this
  is why local Mailpit runs work and production does not.
- `tests/conftest.py` — fixtures/factories.

## Work

1. In `passenger_wsgi.py`, drop the redundant `json.dumps` at every `set_setting(...)`
   call so callers hand `set_setting` a Python object, honoring its contract.
2. In `password_reset.py`, replace the `email_config`-only reads at ~459 and ~586 with
   `notification_service._get_smtp_config()` (as `send_password_reset_email` already
   does). If that helper is private-by-name only, promote it to a public name in
   `notification_service` and update its callers — that is in scope; changing its
   behavior is not.
3. Do NOT add a compatibility shim to `get_setting` that unwraps double-encoded values.
   Fix the writers. A shim would preserve the corruption in existing DBs and hide the
   next occurrence. (Existing deployments re-save config on the next admin save, and
   webhosting deploys reseed — see decisions.md D-003.)
4. Tests in `tests/test_settings_encoding.py` (new): O1–O3.

## Gate (the ONLY accepted gate)

```
./tooling/test-runner/testing-exec.sh unit
```

python 3.11 in the test-runner container — never the devcontainer.

## Scope / forbid

Touch only the three files in `scope.touch`. `database.py` is FROZEN: its encode-once
contract is correct and other callers depend on it. `api/admin.py` is the reference for
the correct shape — read it, don't edit it.

## BLOCKED rule

If a named contract cannot be met as specified, or the work requires editing a forbidden
file, STOP — write `BLOCKED: <reason>` to the LOG, commit, and exit. Do NOT improvise a
workaround.
