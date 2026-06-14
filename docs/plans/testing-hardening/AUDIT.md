# E0 — E2E Estate Audit & Classification

Source: read-only classification of all ~89 `ui_tests/` files (2026-06-14). Grades use the
[`TESTING_LESSONS_LEARNED.md` §4](../../TESTING_LESSONS_LEARNED.md) rubric: **smoke** (page-loads/element/2xx
only), **ui-feedback** (flash/redirect/UI text only), **round-trip** (independent Channel A/B/C backend
truth), **mixed**, **mock-selftest**, **live-only**. This is the authoritative input for E1/E2/E3.

## Headline findings

- **Legacy journeys dir is fully dead.** All 10 `ui_tests/journeys/test_00..09_*.py` + its `conftest.py` +
  `__init__.py` are collected by no runner and every one is superseded. `test_09_multibackend.py` is also
  *broken* (uses a `user_session` fixture that `ui_tests/journeys/conftest.py` never defines). **Delete all 12.**
  ⚠️ `tooling/coverage/route_vs_tests_report.py:143` *scans* both journey dirs for a report (it does not
  collect them as tests) — E1 must update that script so it doesn't dangle on the deleted paths.
- **Brute-force attribution is already round-trip-covered** by
  `test_admin_security_api_contracts.py::test_failed_token_auth_produces_security_event` (Channel A
  `count_activity`/`latest_activity` + Channel B `/admin/api/security/events`). **Drop it from E3** — it was
  the candidate I'd flagged as possibly redundant; confirmed redundant.
- **Two or-chained anti-false-green assertions** in the API auth tests: `test_api_proxy.py` and
  `test_api_security.py` use `assert status in [403, 500]` — a backend that 500s on every auth failure passes
  them. Fix to exact `403` in E3.
- **Skip-to-green** in `test_security.py` (lines 69, 288, 308, 330, 425) and `test_security_scenarios.py`
  (168, 186). Convert to unconditional/feature-flag-gated in E3.
- The overhaul's "lone good cross-role example" `test_account_sessions.py` is genuinely **round-trip** grade
  (revoke in session B → session A force-redirected; behavioral, not UI-scraping). Add to curated list.
- `test_holistic_coverage.py` (690 L) is **smoke** despite its size (screenshots + CSS/UX checks, no backend
  truth). Rename to `test_screenshot_capture_and_ux.py`; keep as a UX/visual audit, not a correctness test.

## Delete list (pure delete)

| file | justification |
|------|---------------|
| `ui_tests/journeys/test_00_auth_enforcement.py` | orphaned; superseded by `test_route_smoke.py` protected-redirect parametrize |
| `ui_tests/journeys/test_01_admin_bootstrap.py` | orphaned; superseded by `j1_fresh_deployment.py` |
| `ui_tests/journeys/test_02_account_lifecycle.py` | orphaned; superseded by `j2` + `test_cross_role_account_lifecycle.py` |
| `ui_tests/journeys/test_03_realm_management.py` | orphaned; verification use is setup-only; superseded by `test_cross_role_realm_propagation.py` |
| `ui_tests/journeys/test_04_token_generation.py` | orphaned; superseded by `test_cross_role_token_lifecycle.py` |
| `ui_tests/journeys/test_05_api_usage.py` | orphaned; skips when `settings.client_token` is None; superseded by `test_api_security.py` |
| `ui_tests/journeys/test_06_system_config.py` | orphaned; superseded by `test_config_pages.py` + `test_admin_ui.py` |
| `ui_tests/journeys/test_07_error_scenarios.py` | orphaned; superseded by `test_security_scenarios.py` |
| `ui_tests/journeys/test_08_email_verification.py` | orphaned; superseded by `test_email_notifications.py` + `test_registration_e2e.py` |
| `ui_tests/journeys/test_09_multibackend.py` | orphaned **and broken** (missing `user_session` fixture); superseded by `test_backends_ui.py` |
| `ui_tests/journeys/conftest.py` | only collected for the above; defines `admin_session` but not the `user_session` test_09 needs — dead once test_0X gone |
| `ui_tests/journeys/__init__.py` | empty package; dead once test_0X gone |
| `ui_tests/tests/test_registration_2fa_complete.py` | 13 smoke form-structure tests fully covered by `test_route_smoke.py` + `test_registration_e2e.py` |

## Merge-then-delete (preserve unique coverage, then remove)

| file | merge target | preserve |
|------|-------------|----------|
| `test_multi_backend_dns.py` | `test_backends_ui.py` | ~2–3 non-overlapping tests (rest ~90% dup) |
| `test_security.py` | `test_security_scenarios.py` | `X-Content-Type-Options`, `httpOnly`/`SameSite` cookie, no-debug-mode checks |
| `test_2fa_enabled_flows.py` | `test_2fa_security.py` | `test_complete_2fa_flow_with_mailpit` |
| `test_admin_totp_and_recovery_codes.py` | `test_2fa_security.py` | TOTP setup page-load assertion |
| `test_account_2fa_routes.py` | `test_route_smoke.py` | 5 redirect checks (mostly already covered) |
| `test_admin_login_2fa_routes.py` | `test_route_smoke.py` | 2 redirect checks |
| `test_admin_audit_and_logs.py` | `test_audit_logs.py` | audit-trim CSRF test + JSON logs endpoint test |
| `test_api_proxy.py` | `test_api_security.py` | DDNS endpoint existence check |
| `test_public_misc_routes.py` | `test_route_smoke.py` | 3 checks already in PUBLIC_ROUTES parametrize |

## Bucket assignment for kept files → directory schema

Audit bucket → `ui_tests/tests/` dir (PLAN.md schema): `smoke`→`smoke/`, `round-trip`→`roundtrip/`,
`feature-e2e`→`features/`, `journey`→`journeys/`, `security`→`security/`, `mock-service-selftest`→`mocks/`,
`live`→`live/`, `accessibility`+`performance`→`nonfunctional/` (distinguished by `accessibility`/`performance`
markers).

| bucket (dir) | files |
|--------|-------|
| `smoke/` | `test_route_smoke.py`, `test_ui_widgets.py`, `test_admin_ui.py`, `test_backends_ui.py`, `test_holistic_coverage.py`→rename `test_screenshot_capture_and_ux.py`, `test_public_misc_routes.py`, `test_account_remaining_routes.py`, `test_installation_workflow.py`, `test_geoip_admin_and_api.py` |
| `roundtrip/` | `test_cross_role_account_lifecycle.py`, `test_cross_role_realm_propagation.py`, `test_cross_role_token_lifecycle.py`, `test_account_sessions.py`, `test_api_dns_crud_success_with_mock_backend.py`, `test_admin_security_api_contracts.py`, `test_ddns_quick_update.py` |
| `features/` | `test_registration_e2e.py`, `test_registration_negative.py`, `test_email_notifications.py`, `test_audit_logs.py`, `test_audit_export.py`, `test_config_pages.py`, `test_bulk_operations.py`, `test_admin_system_security_settings.py`, `test_password_change_flow.py`, `test_ddns_protocols.py`, `test_account_byod_backends.py`, `test_domain_roots_lifecycle.py`, `test_domain_root_grants.py` |
| `journeys/` | `test_journey_master.py`, `j1_fresh_deployment.py`, `j2_account_lifecycle.py`, `j3_comprehensive_states.py`, `state_matrix.py`, `journey_state` (`__init__.py`) |
| `security/` | `test_security_scenarios.py`, `test_2fa_security.py`, `test_account_2fa_disable.py`, `test_recovery_codes.py`, `test_api_security.py` |
| `mocks/` | `test_mock_api_standalone.py`, `test_mock_smtp.py`, `test_mock_geoip.py`, `test_verification_selftest.py` |
| `live/` | `test_live_dns_verification.py`, `test_live_email_verification.py`, `test_ui_flow_e2e.py` |
| `nonfunctional/` | `test_accessibility.py` (marker `accessibility`), `test_performance.py` (marker `performance`) |

## Top upgrade→round-trip candidates (ranked — drives E3)

Each lists the **exact missing backend-truth assertion**. Verify column names against the live schema before
implementing (audit cited plausible names; the schema is the contract).

1. **`test_recovery_codes.py`** (auth bypass) — confirm codes stored after generation and consumed after
   login via Channel A on the recovery-codes store (`accounts.recovery_codes` JSON in this codebase — the
   audit guessed a `recovery_codes` table; **`recovery_codes.py` actually stores a JSON list on the account**,
   so assert the hash count decremented / `recovery_codes_generated_at` cleared). Pairs with `verify_recovery_code` (M2 hot-spot).
2. **`test_2fa_security.py`** (lockout/brute-force) — Channel A on `failed_2fa_attempts` / lockout columns
   after each failure and at lockout.
3. **`test_account_2fa_disable.py`** (TOTP credential state) — `verification.get_account(u)["totp_secret"] is None` after disable.
4. **`test_api_security.py`** (token authz) — fix `in [403,500]`→exact `403`; add Channel A `count_activity(action="api_auth_failed"…)>0`.
5. **`test_audit_logs.py` + `test_audit_export.py`** (audit-trail integrity) — `count_activity(action=…)>0`; export CSV row count == DB count.
6. **`test_api_proxy.py`** (API auth enforcement) — same `in [403,500]`→`403`; Channel A denial row. (Merges into `test_api_security.py`.)
7. **`test_security_scenarios.py`** (session/CSRF/rate-limit) — Channel A session revoked after logout; kill the two skip-to-green guards.
8. **`test_admin_system_security_settings.py`** (rate-limit config) — `verification.get_setting_value("admin_rate_limit") == submitted` after POST.

**Plus two not in the ranked list but genuinely uncovered / pairing with the P+M targets:**
- **NEW: IP-allowlist enforcement round-trip** — no existing test asserts `ip_denied`. Token with
  `allowed_ip_ranges` → request from out-of-range IP → exact 401/403 + Channel A `error_code=='ip_denied'`,
  `severity=='critical'`, `is_attack==1`; in-range IP succeeds. Pairs with `check_ip_allowed` (PBT P3 + M2).
- **DDNS protocol Channel-C upgrade** — `test_ddns_protocols.py` (19 tests) asserts HTTP codes only; add
  `mock_netcup_records` confirmation that records actually changed, plus the `notfqdn`/`!yours` paths. Pairs
  with `validate_hostname_format`/`parse_hostname` (PBT P2).

**Dropped:** brute-force attack-attribution journey — already round-trip-covered (see Headline findings).

## Full per-file inventory

The complete 89-file table (grade/wired/legacy-signals/overlaps/recommendation per file) is preserved in the
E0 audit-agent transcript and summarized by the lists above. Every kept test file appears in the bucket table;
every removed file appears in the delete or merge-then-delete table. Helper/mock/conftest files (≈25) are all
`keep` except `ui_tests/journeys/{conftest,__init__}.py` (delete with the legacy dir).
