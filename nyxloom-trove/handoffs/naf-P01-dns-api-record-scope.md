---
schema_version: 1
id: naf-P01-dns-api-record-scope
project: naf
title: "REST DNS API: enforce record-level scope on delete and update-by-id"
tier: sonnet5-high
input_revision: "adcba7d"
depends_on: []
session: fresh
source: {kind: review, ref: "docs/deprecated/FOLLOWUP_REVIEW_2026-07-16.md#P0-1"}
scope:
  touch:
    - "src/netcup_api_filter/api/dns_api.py"
    - "tests/test_dns_api_record_scope.py"
  forbid:
    - "src/netcup_api_filter/token_auth.py"
    - "src/netcup_api_filter/models.py"
    - "src/netcup_api_filter/api/account.py"
oracles:
  - id: O1
    observable: "A token whose realm is host-scoped to `vpn.example.com` gets 403 (error_code `hostname_denied`) from `DELETE /api/dns/example.com/records/<id>` when <id> is the record id of a DIFFERENT hostname in the same zone (e.g. `www`), and the mock backend still holds that record afterwards; deleting its OWN record id still returns 200 and removes it"
    negative: "the cross-hostname delete returns 200 and the record is gone from the backend — today's behavior, because check_permission is called with no record_name"
    gate: unit
  - id: O2
    observable: "`PUT /api/dns/example.com/records/<id>` is authorized against the hostname of the record ACTUALLY stored under <id>, not the hostname in the request body: a host-scoped token that supplies its own hostname in the body but another host's record id gets 403 and the stored record is unchanged"
    negative: "the request body's hostname is what gets checked, so passing an in-scope hostname with an out-of-scope record id succeeds and repoints another host's record"
    gate: unit
  - id: O3
    observable: "a record id that does not exist in the zone yields 404 (not 403, and not a backend mutation), and no ActivityLog row with status 'success' is written for it"
    negative: "an unknown id falls through to the backend or is reported as a permission error, hiding the difference between 'not yours' and 'not there'"
    gate: unit
gates: [unit]
escalate_if:
  - "a named contract cannot be met as specified"
  - "scope requires editing a forbidden file (token_auth.py / models.py / api/account.py)"
  - "check_permission cannot express hostname scope without a signature change"
---

# P01 — REST DNS API: record-level scope on delete + update-by-id

> Tier: sonnet5-high · Base branch: main (input_revision adcba7d).
> Source: the deep review, finding **P0-1** (`docs/deprecated/FOLLOWUP_REVIEW_2026-07-16.md`).
> This is a **live authorization bypass**, not a cleanup: on a shared
> `ManagedDomainRoot`, a host-scoped token can delete any record in the zone.

## Context to read first (read ONLY these)

- `src/netcup_api_filter/api/dns_api.py` — `delete_record` (~line 423) and
  `update_record` (~line 320). `delete_record` calls
  `check_permission(auth, 'delete', domain, client_ip=client_ip)` with **no
  `record_name`/`record_type`**; the inline comment says "For now, we'll use a generic
  check". `update_record` passes the **request body's** hostname, not the stored
  record's. Note `create_record` in the same file — it already does this correctly and
  is the pattern to mirror.
- `src/netcup_api_filter/token_auth.py` `check_permission` (~line 345) — READ ONLY, do
  NOT edit. Key mechanic: hostname scope is enforced only when `record_name is not
  None` (~line 400), and record-type only when `record_type` is truthy. This is why
  omitting them silently skips the check. Also read `AccountRealm.matches_hostname` via
  its use here.
- `src/netcup_api_filter/netcup_client.py` — `extract_dns_records` and the
  `info_dns_records` call shape, for resolving a record id → its stored hostname/type.
- `tests/conftest.py` — the `app`/`client` fixtures and the `make_account` /
  `make_realm` / `make_token` factories. **Use these**; do not hand-roll fixtures.
- `tests/test_token_auth_unit.py` — the assertion style for permission/error_code
  outcomes to mirror.

## Work

1. In `dns_api.delete_record`: before mutating, fetch the zone's records and locate the
   one matching `record_id`. If absent → 404. If present → call `check_permission` with
   that record's real `record_name` **and** `record_type`, and only then delete.
2. In `dns_api.update_record`: resolve `record_id` to the stored record the same way and
   authorize against the **stored** hostname/type. If the request also changes the
   hostname, the *target* hostname must pass `check_permission` too (a host-scoped token
   must not be able to move a record out of, or into, its scope).
3. Factor the "resolve a record id to its stored record within a zone" step into one
   private helper in `dns_api.py` and use it from both routes — do not copy it twice.
4. Keep the denied-path contract identical to the existing denied branches: same
   `error_code` values, same `log_activity` call shape. Do not invent new error codes.
5. Tests in `tests/test_dns_api_record_scope.py` (new): O1, O2, O3 above. Assert
   **backend truth** (the record is/isn't in the mock backend afterwards), not only the
   status code — a status-only test is hollow here.

## Oracles

See frontmatter. All three run under the `unit` gate.

## Gate (the ONLY accepted gate)

```
./tooling/test-runner/testing-exec.sh unit
```

Runs `pytest tests/` inside the test-runner container on **python 3.11** (the Passenger
deploy target). Never the devcontainer — its 3.14 is not a ship signal. See
`tooling/test-runner/README.md`.

## Scope / forbid

Touch only the two files in `scope.touch`. `token_auth.py` is FROZEN for this package:
`check_permission` already accepts `record_name`/`record_type` — the bug is the *call
sites*, not the checker. If you believe the checker must change, that is a BLOCKED
trigger, not a stretch. `api/account.py` has the same class of bug and is deliberately a
separate package (naf-P02) — do not fix it here.

## BLOCKED rule

If a named contract cannot be met as specified, or the work requires editing a forbidden
file, STOP — write `BLOCKED: <reason>` to the LOG, commit, and exit. Do NOT improvise a
workaround.
