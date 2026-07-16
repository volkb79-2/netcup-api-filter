---
schema_version: 1
id: naf-P02-portal-record-scope
project: naf
title: "Account portal: enforce realm hostname scope on record create/edit/delete"
tier: sonnet5-high
input_revision: "adcba7d"
depends_on: []
session: fresh
source: {kind: review, ref: "docs/FOLLOWUP_REVIEW_2026-07-16.md#P0-2"}
scope:
  touch:
    - "src/netcup_api_filter/api/account.py"
    - "tests/test_portal_record_scope.py"
  forbid:
    - "src/netcup_api_filter/token_auth.py"
    - "src/netcup_api_filter/models.py"
    - "src/netcup_api_filter/api/dns_api.py"
oracles:
  - id: O1
    observable: "For a realm of type `subdomain` scoped to `sub.example.com`, the portal create route rejects a hostname outside that subtree (e.g. the apex `example.com` or `other.example.com`) with a flashed error and NO backend mutation; a hostname inside the subtree still creates"
    negative: "only `host`-type realms are scope-checked (today's `if realm.realm_type == 'host'` guard), so a subdomain realm can create at the apex"
    gate: unit
  - id: O2
    observable: "The portal edit and delete routes resolve `record_id` to its stored record and reject when that record's hostname is outside the realm's scope, leaving the record unchanged in the backend; an in-scope record id still edits/deletes"
    negative: "the record is found by id across the whole zone and mutated after only a realm-level op check, so a host-scoped realm edits/deletes a sibling's record"
    gate: unit
  - id: O3
    observable: "All three routes authorize BEFORE any backend mutation call: on a denied request the mock backend records zero mutation calls"
    negative: "authorization happens after `update_dns_records`, so a denied request has already changed DNS"
    gate: unit
gates: [unit]
escalate_if:
  - "a named contract cannot be met as specified"
  - "scope requires editing a forbidden file (token_auth.py / models.py / api/dns_api.py)"
  - "AccountRealm.matches_hostname does not cover a realm_type the portal allows"
---

# P02 — Account portal: realm hostname scope on record mutations

> Tier: sonnet5-high · Base branch: main (input_revision adcba7d).
> Source: the deep review, findings **P0-2** and **P0-3**. Same class of bypass as
> naf-P01 but through the UI, and independently reachable — carve them separately.

## Context to read first (read ONLY these)

- `src/netcup_api_filter/api/account.py`:
  - create (~line 1505): the guard is literally
    `if realm.realm_type == 'host' and hostname != realm.realm_value` — no validation at
    all for `subdomain` / `subdomain_only`.
  - edit (~line 1563) and delete (~line 1647): find the record by `record_id` across the
    zone, then call `netcup.update_dns_records` after only a realm-level op check.
  - the `dns_records` view in the same file — it DOES filter by hostname; mirror its
    notion of "in scope".
- `src/netcup_api_filter/models.py` `AccountRealm.matches_hostname` — READ ONLY. This is
  the single correct scope predicate (`host` / `subdomain` / `subdomain_only`). Use it;
  do not re-derive the semantics inline.
- `tests/conftest.py` — `app`/`client` fixtures + `make_account`/`make_realm`/
  `make_token` factories. Use them.
- `tests/test_realm_scope.py` — the existing scope-semantics tests; mirror their table
  of realm types so the portal tests line up with the model's contract.

## Work

1. Replace the create route's `realm_type == 'host'` special case with
   `realm.matches_hostname(...)` so every realm type is validated identically.
2. In edit and delete: resolve `record_id` → the stored record first, then validate that
   record's hostname with `realm.matches_hostname`. Reject (flash + redirect, matching
   the routes' existing error UX) before any backend call. Unknown id → not-found UX,
   not a permission error.
3. If the edit changes the hostname, the target hostname must also pass
   `matches_hostname` — a realm must not move a record into or out of its scope.
4. Factor the id→record resolution into one private helper used by both routes.
5. Tests in `tests/test_portal_record_scope.py` (new): O1–O3. Assert **backend truth**
   (mutation count / stored records), not just the flash message.

## Note on a collision with naf-P03

These routes ALSO construct `ActivityLog(details=...)`, which raises `TypeError` because
there is no `details` column — that is naf-P03's package. If a test here trips over that
crash, do **not** fix it: either land naf-P03 first, or assert the scope contract in a
way that does not depend on the audit write succeeding. Fixing it here is out of scope.

## Gate (the ONLY accepted gate)

```
./tooling/test-runner/testing-exec.sh unit
```

python 3.11 (the Passenger deploy target) in the test-runner container — never the
devcontainer. See `tooling/test-runner/README.md`.

## Scope / forbid

Touch only the two files in `scope.touch`. The REST API has the same bug and is
naf-P01 — do not fix it here. `models.py` is read-only for this package.

## BLOCKED rule

If a named contract cannot be met as specified, or the work requires editing a forbidden
file, STOP — write `BLOCKED: <reason>` to the LOG, commit, and exit. Do NOT improvise a
workaround.
