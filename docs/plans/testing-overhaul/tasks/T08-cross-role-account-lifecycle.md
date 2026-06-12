# T08 — Round-trips #1–3: cross-role account lifecycle (pattern-setting)

| Status | Model / effort | Depends on | Size |
|--------|----------------|------------|------|
| open | **Opus 4.8 / xhigh** (flake-prone Playwright work — do not delegate to Sonnet) | T07 | M |

## Objective

Create `ui_tests/tests/test_cross_role_account_lifecycle.py` — the first true cross-role
round-trip tests (admin action → user's API/portal experience verifiably changes), and the
**pattern file** T09–T11 will copy. Quality and flake-resistance matter more than speed here.

## Context — read first (mandatory)

- `docs/TESTING_LESSONS_LEARNED.md` — **required reading before any Playwright auth/2FA work**
  (JS `form.submit()` for 2FA, live `browser._page.url`, session detection).
- `ui_tests/tests/test_account_sessions.py` — the proven two-parallel-sessions pattern.
- `ui_tests/parallel_session_manager.py` — `admin_session` (152),
  `account_session(username, login=False, password=None)` (176), `anonymous_session` (206).
- `ui_tests/workflows.py` — `ensure_admin_dashboard` (818), `ensure_user_dashboard` (1140),
  `handle_2fa_if_present` (150), `generate_account_data` (85).
- `ui_tests/verification.py` (from T07) — channels A (sqlite RO) and B (JSON endpoints),
  `wait_for(...)` poller.
- `ui_tests/mailpit_client.py` — `wait_for_message`, `clear` (admin email-2FA is mandatory,
  so Mailpit is required infra).
- `src/netcup_api_filter/api/admin.py` — **grep the real route names** for account disable /
  enable / approve / reset-password before writing navigation (don't guess URLs; e.g. search
  `accounts/<int:` and `def.*disable|approve|reset`).
- `src/netcup_api_filter/api/dns_api.py` + `docs/API_REFERENCE.md` — DNS API paths + the
  `error_code` vocabulary for denied calls (`docs/SECURITY_ERROR_TAXONOMY.md`).

## Spec

Shared module fixtures: one admin session + helpers to create a **throwaway** account, an
approved realm on it, and a token (all via UI/admin forms — never via DB writes). Capture the
once-shown token plaintext at creation. Restore/cleanup in `finally` (re-enable account,
delete throwaway artifacts if a delete UI exists; otherwise document residue). **Never touch
the primary demo client** other suites depend on.

### Test 1 — `test_admin_disable_account_blocks_api_and_portal`

1. Setup: throwaway account (active, password known), approved realm, token; user logged in
   in a second session; baseline: DNS API GET with the token succeeds (C1 → 200).
2. Admin disables the account via the admin UI.
3. Assert, in order:
   - Channel A: `wait_for(lambda: verification.get_account(u)["is_active"] == 0)`.
   - Channel C1: same API GET now fails with the documented status + `error_code` for a
     disabled account (assert the exact code from the taxonomy, not "any 4xx").
   - Cross-role UI: the user's existing portal session is bounced to login on next navigation
     (or per actual session-invalidation semantics — pin what the code does and comment it).
   - Channel B: `admin_api_accounts(browser)` shows `is_active: false` for the account.
4. Re-enable via admin UI → API GET succeeds again (recovery proves the test isn't one-way).

### Test 2 — `test_admin_approval_enables_login`

1. Register a fresh account via `/account/register` (use `generate_account_data`); complete
   email verification via Mailpit (extract code/link per lessons-learned patterns).
2. Assert login is **rejected** while pending (exact pending-state behavior).
3. Admin approves via admin UI.
4. Channel A: `approved_at` set / `is_active` per model semantics; then the user logs in
   successfully in a second session (full 2FA flow via Mailpit).

### Test 3 — `test_admin_password_reset_forces_change`

1. Admin triggers reset-password on the throwaway account; capture the temp password from the
   admin UI response.
2. Channel A: `must_change_password == 1`.
3. User logs in with the temp password → lands on the forced password-change page; completes
   the change; next login with the new password reaches the dashboard.
4. Channel A: `must_change_password == 0`.

### Pattern rules (T09–T11 will copy these — get them right)

- Every backend assertion goes through `verification.wait_for(...)` — never `sleep`.
- Every assertion is exact (status code, error_code, column value). No `or`-chains, no
  `if element: assert`.
- 2FA/login flows go through `workflows.py` helpers, not hand-rolled fill/click.
- Use `request_get_json`/httpx for API calls; assert on parsed JSON fields.
- `finally`-restore so a mid-test failure doesn't poison later suites.

## Acceptance criteria

- [ ] All 3 tests pass **twice consecutively** against a fresh `./deploy.sh local` (flake check).
- [ ] Anti-false-green proof (do it, then revert): temporarily disable the admin "disable"
      effect (e.g. comment the `is_active` mutation in `api/admin.py`, restart flask) and
      confirm Test 1 FAILS; restore the code. Record this in your summary.
- [ ] No sleeps; no skips; primary demo client untouched (verify via Channel A before/after).
- [ ] File is clean enough to be the copy-pattern: a short module docstring states the rules above.

## Verify

```bash
cd /workspaces/netcup-api-filter
./run-local-tests.sh --skip-build --with-mocks ui_tests/tests/test_cross_role_account_lifecycle.py
# run it twice; both must pass
```

## Guardrails (non-negotiable)

- Never write the live DB from tests (verification channel is read-only).
- Credentials from `deployment_state_local.json` via the harness — never hardcoded.
- No `pytest.skip` to go green, no `if found:` assertions, no `or`-chained assertions, no sleeps.
- Run from repo root; don't edit `deploy/`, `deploy-local/`, `deploy-webhosting/`.
- deploy.sh suite-list registration happens in T12 — don't edit deploy.sh here.
- Leave changes uncommitted for review unless your operator says otherwise.
- When done: tick T08 in `docs/plans/testing-overhaul/PLAN.md` + add a worklog line.
