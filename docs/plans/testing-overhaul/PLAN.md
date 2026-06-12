# Testing Overhaul — Plan & Task Index

**Status: in progress.** The task index below is the source of truth — tick a task's checkbox
and add a worklog line when it lands. Created 2026-06-12 from a full audit of the test suites
(5 parallel deep-dives over `tests/`, `ui_tests/`, the harness, runners, and CI).

## Why (audit summary)

The suite is large (~720 tests) but inverted:

- **~60–65% of E2E tests are L0 smoke** ("page loads / element present"), ~30% assert only UI
  feedback (flash message, redirect). Almost nothing verifies a UI action against independent
  backend truth (DB / API / Mailpit), the reverse direction (backend mutation → visible in UI),
  or cross-role propagation (admin acts → user's view/API access changes). The lone good
  cross-role example is `ui_tests/tests/test_account_sessions.py`.
- **False-green risk is real**: assertions inside `if found:` blocks, `or`-chained tolerant
  assertions, loose `pytest.skip` when an element is merely missing, screenshot-only tests.
  ~9 smoke files overlap heavily.
- **Security-critical pure logic has zero unit coverage**: `token_auth.check_permission()` /
  `authenticate_token()` / `check_ip_allowed()`, `AccountRealm.matches_domain()`,
  `database.run_lightweight_migrations()`, DDNS parsing (`parse_hostname`, X-Forwarded-For),
  `utils` validators, recovery codes, password entropy.
- **Provably broken/dead tooling**: `ui_tests/journeys/test_09_multibackend.py` calls methods
  that don't exist; `run-screenshot-tests.sh` targets a deleted test file; the top-level
  `ui_tests/test_console_errors.py` tests legacy `/client/` routes; CI `--ignore`s
  `tests/test_2fa_security_functional.py` for a bug that's already fixed (the file now fails
  for a different, trivial reason).
- **CI runs only the 31 unit tests** — zero UI/E2E regression protection on PRs, although a
  plain-HTTP E2E smoke job is feasible (verified: no TLS proxy / PUBLIC_FQDN needed).

Strategies adopted by this plan: independent-channel ("round-trip") assertions, a unit conftest
with model factories, route-discovery-driven parametrized smoke, a CI e2e-smoke job.
Considered and deferred: property-based testing (hypothesis) for parsers, coverage ratchet,
mutation testing, visual regression.

## Execution protocol

1. **Strictly one task at a time, in ID order** (dependencies form a chain; the operator is
   often near rate limits — never run implementation agents in parallel).
2. Each task file under [`tasks/`](tasks/) is **self-contained**: a fresh session with no other
   context must be able to execute it. Two supported modes:
   - an orchestrating session (Opus/Fable) spawns **one** subagent
     (`model: sonnet`) with the task file as its prompt, then reviews the diff; or
   - a fresh `claude --model sonnet` session (`/effort high`) is pointed at the task file,
     with a separate review pass afterwards.
3. **Review gate**: every diff is reviewed (Opus 4.8 @ xhigh or better) before commit.
   One commit per task. Do not push unless asked.
4. **E2E tasks (T07–T12) need a running local deployment** (`./deploy.sh local`, mock mode)
   and the Playwright container (`tooling/playwright/`). The task files say so.
5. When a task lands: tick its checkbox below, add a worklog line (date, task, commit, notes).
6. **Specs are hints where they cite counts/line numbers, contracts where they state rules.**
   Audit-derived details (number of failures, line refs, "this script is broken") can be
   stale or wrong — trust the code you read over the spec when they disagree, fix everything
   you find (not just the enumerated items), and call out each discrepancy in your summary so
   the remaining specs can be corrected. (Lesson from the T01 pilot: the spec listed 3 fixture
   problems, the file had 5; a "broken" tooling script turned out to be fine.)

## Task index

| ✓ | ID | Task | Depends | Model / effort | Size |
|---|----|------|---------|----------------|------|
| [x] | [T01](tasks/T01-cleanup-quick-fixes.md) | Cleanup & quick fixes (broken tests, dead scripts, stale CI ignore) | — | Sonnet / high | S |
| [x] | [T02](tasks/T02-unit-bootstrap.md) | `tests/conftest.py` + factories + `test_database_init.py` | T01 | Sonnet / high | M |
| [ ] | [T03](tasks/T03-unit-token-auth.md) | Unit: token auth + realm matching (~49 cases) | T02 | Sonnet / high | M |
| [ ] | [T04](tasks/T04-unit-validators-passwords-recovery.md) | Unit: validators + password policy + recovery codes (~59) | T02 | Sonnet / high | M |
| [ ] | [T05](tasks/T05-unit-ddns-netcup-client.md) | Unit: DDNS parsing + netcup envelopes (~42) | T02 | Sonnet / high | M |
| [ ] | [T06](tasks/T06-unit-migrations.md) | Unit: lightweight migrations (~6) | T02 | Sonnet / high | S |
| [ ] | [T07](tasks/T07-verification-channel.md) | `ui_tests/verification.py` backend-truth channel + migrate inline sqlite | — | Sonnet / high + Opus review | M |
| [ ] | [T08](tasks/T08-cross-role-account-lifecycle.md) | Round-trips #1–3: account lifecycle (pattern-setting) | T07 | **Opus 4.8 / xhigh** | M |
| [ ] | [T09](tasks/T09-cross-role-realm-propagation.md) | Round-trips #4–6: realm propagation | T08 | Sonnet / high | M |
| [ ] | [T10](tasks/T10-cross-role-token-lifecycle.md) | Round-trips #7–9: token lifecycle | T08 | Sonnet / high | M |
| [ ] | [T11](tasks/T11-dns-roundtrip-extensions.md) | Round-trips #10–12: DNS/DDNS backend truth + security-event contract | T08 | Sonnet / high | M |
| [ ] | [T12](tasks/T12-smoke-consolidation.md) | Route-smoke + widgets; delete 9 smoke files; deploy.sh suite list | T07 | Sonnet / high + Opus review | L |
| [ ] | [T13](tasks/T13-ci-e2e-smoke.md) | CI `e2e-smoke` job + `scripts/ci_bootstrap_e2e.py` + `ci_smoke` marker | T12 | **Opus 4.8 / xhigh** | M |
| [ ] | [T14](tasks/T14-docs-sync.md) | Docs sync (TESTING_LESSONS_LEARNED, README, CHANGELOG) | T01–T13 | Sonnet / medium | S |

## Round-trip catalog (what T08–T11 buy us)

Channels: **A** = read-only sqlite on the deployed DB · **B** = authed JSON endpoints via page
context · **C1** = REST DNS API (Bearer) · **C2** = mock netcup backend state.

| # | Flow | Verified via | Task |
|---|------|--------------|------|
| 1 | admin disables account → user's token 403s, portal session bounced; re-enable recovers | A, C1, B | T08 |
| 2 | register + Mailpit verify → admin approves → user can log in | A, Mailpit, parallel session | T08 |
| 3 | admin resets password → user forced to change on next login | A, cross-role UI | T08 |
| 4 | user requests realm → admin approves → user sees approved + token works | A, B, C1 | T09 |
| 5 | admin rejects realm with reason → user sees the reason | A, user UI | T09 |
| 6 | admin revokes realm → existing token denied + audit row | C1, A | T09 |
| 7 | admin revokes token → API denied immediately | C1, A, B | T10 |
| 8 | user revokes own token → API blocked + ActivityLog row | C1, A | T10 |
| 9 | read-only-scoped token: GET 200, mutate 403 | C1, A | T10 |
| 10 | API creates record → portal DNS page shows it → mock backend has it | C2, UI | T11 |
| 11 | portal DNS create → backend + API list; portal delete removes it | C2, C1 | T11 |
| 12 | DDNS update → backend record changed + token use_count/ActivityLog delta | C2, A | T11 |

Plus (T11): tampered-token call asserted to surface in `/admin/api/security/events`.

## Model & effort rationale

Pricing (per MTok in/out, 2026-06): Haiku 4.5 $1/$5 · Sonnet 4.6 $3/$15 · Opus 4.8 $5/$25 ·
Fable 5 $10/$50 plus a ~30%-hungrier tokenizer (≈2.6× Opus, ≈4× Sonnet effective).

- **Implementation default: Sonnet 4.6 @ effort `high`.** (`xhigh` does not exist on Sonnet —
  it's an Opus 4.7+/Fable level; Sonnet supports low/medium/high/max.) Reserve Sonnet `max`
  for T12 if its first attempt is sloppy.
- **Judgment-heavy tasks (T08, T13) and all diff review: Opus 4.8 @ `xhigh`.** Review reads
  diffs — a small share of total tokens.
- **Never Haiku for test code** — tolerant false-green assertions are exactly the cheap-model
  failure mode this plan exists to cure. **Never Fable for implementation** — its premium buys
  design/review depth, not better mechanical test-writing.

## Verification milestones

1. **After T01–T06:** `python -m pytest tests/` green locally **including**
   `test_2fa_security_functional.py`; CI green without the `--ignore`.
2. **After T07–T12:** targeted runs via `./run-local-tests.sh --skip-build --with-mocks <file>`
   against a fresh `./deploy.sh local`; then one full `./deploy.sh local` run with the updated
   suite list. **Anti-false-green check:** deliberately break one behavior locally (e.g.
   comment out the token-revoke commit) and confirm the matching round-trip test fails.
3. **After T13:** push a branch; the `e2e-smoke` job boots the app and passes; artifacts appear
   on a forced failure.
4. **After T14:** docs match reality per AGENTS.md definition-of-done.

## Worklog

- 2026-06-12 — plan + task specs created (audit session). No implementation yet.
- 2026-06-12 — T01 landed (working tree, not committed). Fixed journey 09 method names, 2FA
  functional fixture (monkeypatch+tmp_path, correct model fields, outdated assertions updated to
  current behavior). Removed CI --ignore. Deleted 9 dead files. Three conditional tooling scripts
  kept: `tooling/run-tests.sh` (setup.sh exists in tooling/playwright/), `tooling/setup-playwright.sh`,
  `tooling/start-ui-stack.sh` (unreferenced but not provably broken). All 30 unit tests green.
- 2026-06-12 — T02 landed (working tree, not committed). Added `tests/conftest.py` (app/client/db
  fixtures + make_account/make_realm/make_token factories), `tests/test_database_init.py` (4 cases:
  in-memory engine-options guard, file-DB pool options, get_db_path env precedence, default fallback),
  `tests/test_factories.py` (5 round-trip cases). All 39 unit tests green. Spec discrepancies: none —
  spec lined up with the code.
