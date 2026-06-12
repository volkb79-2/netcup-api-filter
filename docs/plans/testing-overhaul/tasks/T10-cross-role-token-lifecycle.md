# T10 — Round-trips #7–9: token lifecycle & scope enforcement

| Status | Model / effort | Depends on | Size |
|--------|----------------|------------|------|
| open | Sonnet 4.6 / high | T08 (copy its pattern exactly) | M |

## Objective

Create `ui_tests/tests/test_cross_role_token_lifecycle.py`: token revocation (by admin and by
user) takes effect immediately at the API, and token scope restrictions created through the UI
are actually enforced by the API.

## Context — read first (mandatory)

- `ui_tests/tests/test_cross_role_account_lifecycle.py` (T08) — copy structure + rules.
- `docs/TESTING_LESSONS_LEARNED.md`; `ui_tests/verification.py` (A/B/C1, `wait_for`).
- Token creation UI flow reference: `ui_tests/journeys/test_04_token_generation.py`
  (token plaintext extraction — `naf_` prefix; harden, don't copy its skip-on-missing habits).
- Grep real routes: token revoke in `src/netcup_api_filter/api/admin.py` and
  `src/netcup_api_filter/api/account.py`; DNS API mutation endpoints in `api/dns_api.py`.
- `docs/SECURITY_ERROR_TAXONOMY.md` — `token_revoked` / operation-denied codes.

## Spec

Throwaway account + approved realm + tokens created via UI (reuse T08 helpers /
`cross_role_helpers.py` if T09 created it). `finally`-restore. Primary demo client untouched.

### Test 7 — `test_admin_token_revocation_immediate`

1. User creates token via portal (capture plaintext); C1 GET → 200.
2. Admin revokes that token via the admin UI.
3. Channel A (`wait_for`): token row `is_active == 0` (+ `revoked_at` if the column exists).
4. C1: same GET now → exact documented status + `error_code` (e.g. `token_revoked`).
5. Channel B: `account_api_realm_tokens(browser, realm_id)` shows the token inactive.

### Test 8 — `test_user_token_revocation_blocks_api_and_logs`

Same as Test 7 but the user revokes via the portal; additionally Channel A:
`count_activity(action=<revocation action name>)` increments and a denial activity row
appears after the failed API call (read the actual action strings from `token_auth.log_activity`
usage / ActivityLog rows — assert exact action names).

### Test 9 — `test_readonly_token_scope_enforced`

1. Via the portal token form, create a token restricted to read-only operations (use the real
   form controls; if the form expresses scopes differently — record types, ops — pin what it
   offers).
2. Channel A: token row's `allowed_operations` JSON is exactly the chosen set (e.g. `["read"]`).
3. C1: GET records → 200; create/update record → exact operation-denied status + error_code.
4. Also assert the inverse guard: a full-scope token on the same realm CAN mutate (proves the
   denial came from the scope, not from something else broken).

## Acceptance criteria

- [ ] All 3 tests pass twice consecutively against a fresh `./deploy.sh local`.
- [ ] Exact-assertion rules from T08 hold (no sleeps/skips/or-chains/if-found).
- [ ] Test 9's inverse guard present (mutation succeeds with full scope).
- [ ] Anti-false-green spot check on Test 7 (neuter revoke effect temporarily → test fails →
      restore) recorded in summary.

## Verify

```bash
cd /workspaces/netcup-api-filter
./run-local-tests.sh --skip-build --with-mocks ui_tests/tests/test_cross_role_token_lifecycle.py
```

## Guardrails (non-negotiable)

- Never write the live DB from tests. Credentials via the harness only; never log token plaintext.
- No `pytest.skip` to go green, no `if found:` assertions, no `or`-chains, no sleeps.
- Run from repo root; don't edit `deploy/`, `deploy-local/`, `deploy-webhosting/`; deploy.sh suite list is T12's job.
- Leave changes uncommitted for review unless your operator says otherwise.
- When done: tick T10 in `docs/plans/testing-overhaul/PLAN.md` + add a worklog line.
