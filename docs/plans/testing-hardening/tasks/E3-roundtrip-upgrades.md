# E3 — Upgrade security-critical tests to round-trip grade + new backend-truth journeys

**Goal:** Add independent-channel backend-truth assertions to the highest-value security surfaces that today
are only smoke/ui-feedback grade — the core ask. Each upgrade turns "the UI said it worked" into "the backend
state actually changed, verified via Channel A/B/C."

**Model/effort:** Sonnet/high implement → **Opus 4.8/xhigh review**. **Depends:** E0 (ranked upgrade list),
E2 (final locations/markers), and the P-stream (shared invariants). **Size:** L — **may be split per area**
into reviewable commits (e.g. E3a IP-allowlist + DDNS, E3b recovery-codes + attack attribution).

## The pattern (non-negotiable — from TESTING_LESSONS_LEARNED §4)
Copy the structure of `ui_tests/tests/.../test_cross_role_account_lifecycle.py` (the designated pattern file):
UI action → poll backend truth with `verification.wait_for(...)` → assert exact backend state. Obey the four
anti-false-green rules: **no `if found: assert`**, **no `or`-chained status**, **no skip-to-green** (only
`require_db()`/feature-flag skips), **never assert from the UI layer alone** for a mutation. Channels live in
`ui_tests/verification.py` (A = read-only sqlite, B = authed JSON, C = DNS-API/mock-netcup; Mailpit for mail).

## Scope — `AUDIT.md` "Top upgrade→round-trip candidates" is authoritative
Work the audit's ranked list (1–8) plus its two explicit additions. Each entry there names the **exact missing
backend-truth assertion**. **Verify every DB column/table name against the live schema before asserting on it**
— the audit guessed some names. Group into reviewable commits, suggested split:

**E3a (security core — highest value, pairs with P/M):**
1. **Recovery-code one-time use** (`test_recovery_codes.py`, audit #1) — authenticate with a recovery code →
   Channel A confirms the code is **consumed**. Note: this codebase stores recovery codes as a **JSON list on
   `accounts.recovery_codes`** (see `src/.../recovery_codes.py`), *not* a separate table — assert the stored
   hash count decremented and `recovery_codes_generated_at` cleared when the last code is used. A **second**
   use of the same code is rejected. Exercises `verify_recovery_code` (the M2 hot-spot).
2. **2FA lockout** (`test_2fa_security.py`, audit #2) — Channel A on the failed-attempt/lockout columns after
   each failure and at lockout.
3. **TOTP disable clears secret** (`test_account_2fa_disable.py`, audit #3) —
   `verification.get_account(u)["totp_secret"] is None` after disable.
4. **NEW: IP-allowlist enforcement** (audit "Plus", no existing test) — token with `allowed_ip_ranges`
   excluding the client → DNS API → **exact** `401/403` (pin whichever the impl returns) + Channel A
   `error_code == 'ip_denied'`, `severity == 'critical'`, `is_attack == 1`; in-range IP (via `X-Forwarded-For`,
   per `get_client_ip`) succeeds. Exercises `check_ip_allowed` (P3 + M2).

**E3b (API/audit/DDNS):**
5. **API auth or-chain fix + denial logging** (`test_api_security.py` #4, `test_api_proxy.py` #6 — the
   latter merges in per AUDIT.md) — replace `assert status in [403, 500]` with exact `403` (+ a skip guard if
   the mock backend is unreachable, **not** a tolerant assertion); add Channel A
   `count_activity(action="api_auth_failed"…) > 0`.
6. **Audit-trail integrity** (`test_audit_logs.py` + `test_audit_export.py`, audit #5) —
   `count_activity(action=…) > 0`; exported CSV row count == DB count.
7. **Session/CSRF/rate-limit** (`test_security_scenarios.py`, audit #7) — Channel A session revoked after
   logout; **convert the two skip-to-green guards (lines ~168, 186) to unconditional/feature-flag-gated**.
8. **Rate-limit setting persists** (`test_admin_system_security_settings.py`, audit #8) —
   `verification.get_setting_value("admin_rate_limit") == submitted` after the admin POST.
9. **DDNS protocol Channel-C upgrade** (`test_ddns_protocols.py`, audit "Plus") — add `mock_netcup_records`
   confirmation that records actually changed, plus the `notfqdn` (400) and `!yours`/`abuse` (403) paths.
   Exercises `validate_hostname_format`/`parse_hostname` (P2) + `check_permission`.

**Explicitly dropped (per AUDIT.md):** brute-force attack-attribution — already round-trip-covered by
`test_admin_security_api_contracts.py::test_failed_token_auth_produces_security_event`. Do not duplicate it.

If `verification.py` lacks a helper an assertion needs (e.g. `get_setting_value`, `list_account_sessions`),
add it there (Channel A) following the existing read-only/`mode=ro` pattern — don't inline raw sqlite in tests.

## Do
- Place new/upgraded files in the `security/` or `roundtrip/` bucket (E2 schema) with the right `pytestmark`.
- Reuse `ui_tests/cross_role_helpers.py` for login/token/realm setup; add helpers there if missing.
- Each upgraded file keeps any genuinely-useful existing smoke assertions but **adds** the backend-truth
  assertion that makes it round-trip grade.
- Tag fast, hermetic, Mailpit-only ones `@pytest.mark.ci_smoke` if appropriate (so they join the CI subset);
  do not tag anything needing mock-netcup or real external deps.

## Verify (anti-false-green — required)
For at least the IP-allowlist and recovery-code upgrades, **deliberately break the backend behavior locally**
(e.g. make `check_ip_allowed` return `True` unconditionally, or comment out the `.remove()` in
`verify_recovery_code`) and confirm the new round-trip test **fails**. Restore, confirm green. Record this
check in your summary — a round-trip test that passes against broken backend logic is the exact failure mode
this task exists to prevent.

Run the upgraded files against a fresh `./deploy.sh local` (mock mode) via
`./run-local-tests.sh --skip-build --with-mocks <file>`. One commit per area if split.
