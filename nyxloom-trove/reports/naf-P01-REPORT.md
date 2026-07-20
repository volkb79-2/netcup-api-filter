# naf-P01 — REPORT

**Status:** MERGED to `main` (merge `2035480`, impl commit `703281e` on wt/naf-p01).
Sonnet implementation in an isolated worktree; orchestrator (Opus) review-merge.

## What landed (`src/netcup_api_filter/api/dns_api.py` + `tests/test_dns_api_record_scope.py`)

- `_find_zone_record(netcup, domain, record_id)`: resolves an id to its STORED record via
  the shared `extract_dns_records`/`mutation_failed`/`mutation_message` helpers; returns
  `(record, fetch_error)` so callers distinguish 404 (no such id) from a 502 upstream error.
- `delete_record`: authorizes against the stored record's real `record_name`/`record_type`
  (was a generic zone-only check → any-record delete in a shared zone).
- `update_record`: authorizes against the stored record; on a move (hostname/type differs
  from stored) the TARGET must also pass `check_permission` — a host-scoped token cannot
  move a record into or out of its scope.

## Orchestrator review finding (fixed before merge)

The implementation removed the upfront zone-level `check_permission` and fetched the record
FIRST. That reintroduced a leak: an out-of-scope caller could (a) trigger an upstream fetch
for any zone and (b) tell 404 (no id) from 403 (id exists, not yours) — a cross-zone
record-existence oracle. Restored a cheap zone/op `check_permission` before the fetch in
both routes (the original delete path had exactly this; the impl dropped it). This is the
kind of subtle security regression a cheap-model-first dispatch can introduce, and why
review-merge re-derives against the code rather than trusting the receipt.

## Oracles

- **O1** (host-scoped token cannot delete a sibling's record; own record deletes) — PROVEN
  (`test_delete_cross_hostname_denied_and_backend_unchanged`, `..._own_record_succeeds`).
- **O2** (update authorized against the stored record, not the request body) — PROVEN
  (`test_update_cross_hostname_denied_even_with_in_scope_body_hostname`,
  `test_update_cannot_move_own_record_out_of_scope`).
- **O3** (unknown id → 404, no mutation, no success audit) — PROVEN (the fake store is
  asserted unchanged; status/error_code asserted on the audit row).

All 7 tests assert BACKEND TRUTH (fake-store record presence, status codes, error_code,
audit status), not just status codes.

## Gate

`./tooling/test-runner/testing-exec.sh unit` → **390 passed on python 3.11 AND 3.9** on the
worktree; the combined post-merge `main` gate confirms the batch together.
