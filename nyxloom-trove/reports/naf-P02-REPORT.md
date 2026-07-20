# naf-P02 — REPORT

**Status:** MERGED to `main` (merge `ebffa4e`, impl commit `46990c1` on wt/naf-p02).
Sonnet implementation in an isolated worktree; orchestrator review-merge (ACCEPTED as-is).

## What landed (`src/netcup_api_filter/api/account.py` + `tests/test_portal_record_scope.py`)

- `_realm_fqdn_for(realm, hostname)`: builds the FQDN for a relative hostname; `'@'`/empty →
  the bare zone (apex), mirroring the `dns_records` listing view. (Verified apex maps to
  `realm.domain`, not a literal `@`, so a legitimate apex record isn't spuriously rejected.)
- `_find_realm_record(netcup, realm, record_id)`: id → stored record within the zone.
- `dns_record_create`: replaced the `realm_type == 'host'`-only guard with
  `realm.matches_hostname(fqdn)` — now enforces scope for host / subdomain / subdomain_only.
- `dns_record_edit` / `dns_record_delete`: validate the resolved record's hostname against
  `realm.matches_hostname` BEFORE `update_dns_records`; unknown id keeps the not-found UX.

## Cross-cutting honored (CC-1)

The `ActivityLog(...)` writes in these routes (fixed by naf-P03) were left byte-for-byte
untouched. The edit form has no hostname field, so "move a record into/out of scope via
edit" is structurally unreachable — the stored-hostname check covers it by construction.

## Oracles

- **O1** (subdomain / subdomain_only realm cannot create outside its subtree, incl. apex) —
  PROVEN, with the subtle case split: `subdomain` includes its subtree apex, `subdomain_only`
  excludes it (`test_subdomain_realm_rejects_apex_hostname`,
  `test_subdomain_only_realm_rejects_apex`).
- **O2** (edit/delete of an out-of-scope resolved record rejected, backend unchanged; unknown
  id → not-found) — PROVEN.
- **O3** (a denied create/edit/delete performs ZERO backend mutations) — PROVEN (parametrized;
  the fake backend's mutation-call count is asserted 0).

15 backend-truth tests (fake-backend mutation counts + stored records), not flash-message
checks.

## Gate

`./tooling/test-runner/testing-exec.sh unit` → **398 passed on python 3.11 AND 3.9**.
