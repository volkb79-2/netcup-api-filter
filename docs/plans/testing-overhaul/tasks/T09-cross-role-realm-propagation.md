# T09 — Round-trips #4–6: realm request → approval/rejection/revocation propagation

| Status | Model / effort | Depends on | Size |
|--------|----------------|------------|------|
| open | Sonnet 4.6 / high | T08 (copy its pattern exactly) | M |

## Objective

Create `ui_tests/tests/test_cross_role_realm_propagation.py`: the realm lifecycle as a true
round trip across roles — user requests, admin decides, user's portal and API access change
verifiably. Also retire the direct-DB realm seeding in journey 03.

## Context — read first (mandatory)

- `ui_tests/tests/test_cross_role_account_lifecycle.py` (from T08) — **copy its structure,
  fixtures, and pattern rules verbatim**; its module docstring states the rules.
- `docs/TESTING_LESSONS_LEARNED.md`.
- `ui_tests/verification.py` — channels A/B/C1, `wait_for`.
- `src/netcup_api_filter/api/account.py` — grep the real realm-request routes
  (`/account/realms/...`); `src/netcup_api_filter/api/admin.py` — grep the approve / reject /
  revoke realm routes before writing navigation.
- `ui_tests/journeys/test_03_realm_management.py:86-137` — the legacy DB write-seeding this
  task replaces.
- `docs/SECURITY_ERROR_TAXONOMY.md` — exact error codes for unapproved/revoked realms.

## Spec

Shared fixtures (reuse T08's helpers; factor truly shared ones into a small
`ui_tests/cross_role_helpers.py` if duplication exceeds ~50 lines — keep it minimal).
Throwaway account per test class; `finally`-restore; never touch the primary demo client.

### Test 4 — `test_realm_request_approval_propagates`

1. User (second session) requests a realm via the portal form (pick a domain the deployment's
   managed roots allow — read what the seeded deployment offers, e.g. from the request form).
2. Channel A: realm row exists with `status='pending'`; Channel B: `account_api_realms`
   shows it pending.
3. Admin sees it in the pending list and approves via UI.
4. Channel A: `status='approved'`; user portal shows approved; user creates a token on the
   realm via UI (capture plaintext) and a DNS API call with it succeeds (C1 → 200).
5. Before approval, the same API call path must have been impossible/denied — pin whichever
   the product enforces (no token creation on pending realm, or `realm_not_approved` on use).

### Test 5 — `test_realm_rejection_reason_visible_to_user`

1. User requests another realm; admin rejects with a distinctive reason string.
2. Channel A: `status='rejected'` + the reason persisted (column per model).
3. User portal realm view shows the reason text verbatim.

### Test 6 — `test_realm_revocation_kills_existing_tokens`

1. On the approved realm from Test 4 (or fresh setup): token works (C1 → 200).
2. Admin revokes/disables the realm via UI.
3. Channel A: realm status updated; C1: same call now denied with the exact documented
   status + error_code; Channel A: `count_activity` for the denial action increased.

### Replace journey 03's DB seeding

In `ui_tests/journeys/test_03_realm_management.py`, replace `create_pending_realm_in_db()`
(lines ~86–137) with UI-driven realm requests (the same flow as Test 4 step 1), keeping the
journey's downstream assertions working. Delete the now-unused sqlite write helper. If the
journey's structure makes this disproportionate, do the minimal correct version and flag the
rest in your summary — do not leave both paths.

## Acceptance criteria

- [ ] All 3 tests pass twice consecutively against a fresh `./deploy.sh local`.
- [ ] Journey 03 passes without any direct DB write (grep: no `sqlite3.connect` left in it).
- [ ] Exact-assertion rules from T08 hold (no sleeps/skips/or-chains/if-found).
- [ ] Anti-false-green spot check on Test 6 (temporarily neuter the revoke effect, confirm
      failure, restore) recorded in summary.

## Verify

```bash
cd /workspaces/netcup-api-filter
./run-local-tests.sh --skip-build --with-mocks ui_tests/tests/test_cross_role_realm_propagation.py
./run-local-tests.sh --skip-build --with-mocks ui_tests/journeys/test_03_realm_management.py
```

## Guardrails (non-negotiable)

- Never write the live DB from tests. Credentials via `deployment_state_local.json` harness only.
- No `pytest.skip` to go green, no `if found:` assertions, no `or`-chains, no sleeps.
- Run from repo root; don't edit `deploy/`, `deploy-local/`, `deploy-webhosting/`; deploy.sh suite list is T12's job.
- Leave changes uncommitted for review unless your operator says otherwise.
- When done: tick T09 in `docs/plans/testing-overhaul/PLAN.md` + add a worklog line.
