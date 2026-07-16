# naf-P03 — REPORT (implemented directly, not dispatched)

**Status:** DONE · implemented by the review session on 2026-07-16, at the operator's
request ("do directly yourself"), rather than dispatched to an agent. Handoff archived.

## What landed

`api/account.py`
- Six `ActivityLog(details=...)` sites → `status_reason=` (1344, 1359, 1449, 1545, 1628, 1704).
- `realm_detail` per-token stats (1211): dropped `ActivityLog.details.like(...)` for a
  join on the indexed `token_id` FK, and replaced the dead action-name filter
  (`updateDnsRecords`, … — Netcup API method names that are never written as an action)
  with `log.operation in ('update','create','delete')`. Those stats were always 0.

`api/admin.py`
- `realm_revoke` / `token_revoke`: replaced the undefined `log_activity(...)` name with a
  real `ActivityLog(...)` row, moved INTO the same transaction as the revoke, so a
  destructive action can no longer commit without its audit trail. In `token_revoke` the
  owner notification now fires only after revoke+audit are durable.

## A trap the handoff did not name

The handoff said "replace `details=` with `status_reason=`". That alone would NOT have
worked: **`source_ip` is `nullable=False`, and none of the six sites set it** — a pure
rename swaps `TypeError` for an `IntegrityError`. Every site now passes `source_ip`
(`request.remote_addr`, ProxyFix-normalized — deliberately not the spoofable
`X-Forwarded-For` pattern used elsewhere in `account.py`; see backlog B-AUTH).

If this package had been dispatched as written, an agent would likely have hit the
IntegrityError and either BLOCKED or improvised. Worth remembering when carving: a
"mechanical rename" that crosses a NOT NULL boundary is not mechanical.

## Oracles

- **O1** (portal DNS routes write a row, no TypeError) — *partially* proven. The static
  guards in `tests/test_audit_writes.py` prove no call site uses the phantom API and none
  omits `source_ip`; they FAIL against the pre-fix code (verified: 6 `details=` sites +
  the `.details` attribute in account.py, `log_activity` undefined in admin.py). Driving
  the routes end-to-end needs session auth + a live backend — that is the `e2e` gate and
  was not run here.
- **O2** (realm_detail renders, stats non-zero) — query shape proven by unit test
  (`TestRealmDetailStats`); page render not exercised (same reason as O1).
- **O3** (revokes audit without NameError) — undefined-name guard proven; route-level
  execution not exercised.

**Honest gap:** the behavioural half of O1–O3 needs `testing-exec.sh e2e` against a
deploy-local. The unit-level contract + static guards are green on both interpreters.

## Gate

`./tooling/test-runner/testing-exec.sh unit` → **379 passed on python 3.11 and 3.9**
(373 pre-existing + 6 new).
