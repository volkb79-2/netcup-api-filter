---
schema_version: 1
id: naf-P03-audit-log-api-misuse
project: naf
title: "Audit writes crash: phantom ActivityLog.details column and undefined log_activity"
tier: sonnet5-high
input_revision: "adcba7d"
depends_on: []
session: fresh
source: {kind: review, ref: "docs/FOLLOWUP_REVIEW_2026-07-16.md#P0-4"}
scope:
  touch:
    - "src/netcup_api_filter/api/account.py"
    - "src/netcup_api_filter/api/admin.py"
    - "tests/test_audit_writes.py"
  forbid:
    - "src/netcup_api_filter/models.py"
    - "src/netcup_api_filter/token_auth.py"
oracles:
  - id: O1
    observable: "Exercising the account portal DNS routes (records view, create, edit, delete, DDNS quick-update) writes an ActivityLog row and returns the success UX; no route raises TypeError and none flashes a failure for an operation that actually succeeded"
    negative: "ActivityLog(details=...) raises TypeError('details' is an invalid keyword argument) AFTER the backend mutation, so the change lands while the user is told it failed (and retries, duplicating creates)"
    gate: unit
  - id: O2
    observable: "`GET /account/realms/<id>` renders for a realm that HAS tokens, and the per-token stats it shows are derived by joining ActivityLog on token_id (non-zero for a token with recorded activity)"
    negative: "the view raises AttributeError on ActivityLog.details.like(...) and 500s whenever the realm has at least one token; or it renders but every stat is 0 because it filters on action names that are never logged"
    gate: unit
  - id: O3
    observable: "Admin realm-revoke and token-revoke complete without NameError AND write an ActivityLog row recording the revoke (actor + target resolvable from the row)"
    negative: "log_activity is an undefined name in admin.py, so the revoke commits, the request 500s, and no audit row exists for a destructive security action"
    gate: unit
gates: [unit]
escalate_if:
  - "a named contract cannot be met as specified"
  - "scope requires editing a forbidden file (models.py / token_auth.py)"
  - "the intended audit semantics cannot be expressed with the existing ActivityLog columns"
---

# P03 — Audit writes are broken in two blueprints

> Tier: sonnet5-high · Base branch: main (input_revision adcba7d).
> Source: the deep review, findings **P0-4** and **P0-5**. Both were reproduced against
> the real model/imports — this is not speculative. One package because it is one
> concern: *the audit write does not work*.

## Context to read first (read ONLY these)

- `src/netcup_api_filter/models.py` `ActivityLog` (~line 690) — READ ONLY. The real
  columns are: `token_id, account_id, action, operation, realm_type, realm_value,
  record_type, record_name, source_ip, user_agent, status, error_code, status_reason,
  severity, is_attack, request_data, response_summary, created_at`. There is **no
  `details` column** — the human-readable field is `status_reason`.
- `src/netcup_api_filter/api/account.py` — `ActivityLog(details=...)` at ~1344, 1359,
  1449, 1545, 1628, 1704, and `ActivityLog.details.like(...)` at ~1211. Also note the
  1211 loop filters `action in ('updateDnsRecords','createDnsRecords','deleteDnsRecords')`
  — action names nothing ever writes (real ones are `api_call` / `ddns_*` / `dns_*`), so
  the stats are dead logic even once the column is fixed.
- `src/netcup_api_filter/api/admin.py` ~1538 (`realm_revoke`) and ~1595 (`token_revoke`)
  — both call `log_activity(...)`, which is neither defined nor imported in this module.
  Look at how OTHER admin routes write audit rows (`ActivityLog(...)` directly) and
  mirror that; note both routes commit the revoke BEFORE the log call.
- `src/netcup_api_filter/token_auth.py` `log_activity` (~line 438) — READ ONLY, for its
  signature `log_activity(auth, action, ..., status=...)`. It is token-auth shaped and
  is **not** a drop-in for admin's session-authed routes; that mismatch is why the call
  sites are wrong. Do not import it into admin.py just to satisfy the name.
- `tests/conftest.py` — fixtures + factories to use.

## Work

1. `api/account.py`: replace every `ActivityLog(details=...)` with the real column
   (`status_reason=`), preserving each site's message content.
2. `api/account.py` ~1211: rewrite the per-token stats query to join `ActivityLog` on
   `token_id` (the indexed FK) instead of `LIKE`-matching a prefix into a non-existent
   column, and drop the dead action-name filter — count what is actually logged.
3. `api/admin.py` 1538/1595: write an `ActivityLog(...)` row with real columns, matching
   the pattern already used elsewhere in `admin.py`. Record actor + target. Keep the
   revoke's existing commit semantics; make the audit row part of the same transaction
   so a revoke can never succeed with no audit trail.
4. Tests in `tests/test_audit_writes.py` (new): O1–O3. Assert the **row exists with the
   expected column values** — a test that only asserts "no exception" is hollow here.

## Gate (the ONLY accepted gate)

```
./tooling/test-runner/testing-exec.sh unit
```

python 3.11 in the test-runner container — never the devcontainer.

## Scope / forbid

Touch only the three files in `scope.touch`. **Do not add a `details` column** to
`ActivityLog` to make the call sites work — the column set is correct; the call sites are
wrong. Adding a column is a schema change and a BLOCKED trigger here (and would need a
hand-written migration per AGENTS.md, since the lightweight pass is additive-only).

## BLOCKED rule

If a named contract cannot be met as specified, or the work requires editing a forbidden
file, STOP — write `BLOCKED: <reason>` to the LOG, commit, and exit. Do NOT improvise a
workaround.
