# Testing Hardening — Plan & Task Index

**Status: IN PROGRESS.** Phase-2 follow-on to the completed [`testing-overhaul`](../testing-overhaul/PLAN.md)
(T01–T14, landed 2026-06-12). That overhaul explicitly **deferred** three things; this plan executes them:

1. **Property-based testing (Hypothesis)** for parsers/validators — already pre-scoped in
   [`TESTING_LESSONS_LEARNED.md` §5](../../TESTING_LESSONS_LEARNED.md) with worked example files.
2. **Mutation-testing spot-check** — broaden beyond the `mutmut on token_auth.py` hint in the gaps table:
   audit the pure-logic core, pick interesting targets, run **locally only** behind a **toggleable** runner
   (never CI, never auto-run), triage survivors, fix or document.
3. **E2E reorganization + more backend-truth journeys** — audit the ~70-file `ui_tests/` estate, delete
   legacy/dead, re-classify under a **modern directory + marker schema**, and upgrade the highest-value
   security-critical smoke/ui-feedback tests to **round-trip grade** (independent backend-truth assertions).

Created 2026-06-14.

## Why (carried from the overhaul audit)

- The overhaul's own audit found **~60–65% of E2E tests are L0 smoke** and another ~30% assert only UI
  feedback. Only 12 flows (T08–T11) assert against independent backend truth via the
  [`verification.py`](../../../ui_tests/verification.py) channels. The rest of the security-critical surface
  (auth, token scope, IP allowlist, recovery codes, attack attribution) is still smoke/ui-feedback grade.
- There are **two journey directories**: modern `ui_tests/tests/journeys/{j1,j2,j3}` (wired into
  `test_journey_master.py`) and legacy `ui_tests/journeys/test_00..09_*.py` (10 files, ~5,500 LOC) that
  **no runner collects** (`test_journey_master` imports only j1–j3; `run-local-tests.sh` collects only
  `ui_tests/tests`; nothing imports the legacy modules). Confirmed orphaned 2026-06-14.
- **Marker taxonomy is essentially absent** (only `live`, `ci_smoke`, one `skip`). There is no way to run
  "just the round-trips" or "just security" — the schema is the fix.
- Hand-written `parametrize` lists cover only cases the author imagined; the parsing/validation code
  (`validate_hostname_format`, `parse_hostname`, `validate_ip_range`, `matches_hostname`) is
  security-adjacent and full of manual boundary logic that property-based generation explores far better.
- High line coverage ≠ good assertions. Mutation testing proves the unit suite actually *detects* broken
  behavior on the security core, rather than just executing it.

## Workstreams & task index

| ✓ | ID | Task | Depends | Model / effort | Size |
|---|----|------|---------|----------------|------|
| [x] | [P1](tasks/P1-hypothesis-bootstrap.md) | Hypothesis bootstrap: dep + profiles + conftest registration | — | Sonnet / high | S |
| [x] | [P2](tasks/P2-pbt-ddns.md) | PBT: DDNS hostname parse/validate invariants | P1 | Sonnet / high | M |
| [x] | [P3](tasks/P3-pbt-validators.md) | PBT: IP-range / domain / email / `check_ip_allowed` invariants | P1 | Sonnet / high | M |
| [x] | [P4](tasks/P4-pbt-token-model.md) | PBT: token round-trip + realm scope (`matches_hostname`) invariants | P1 | Sonnet / high | M |
| [ ] | [M1](tasks/M1-mutation-tooling.md) | Mutation tooling: `mutmut` dep + config + **toggleable** local runner (no CI) | — | Sonnet / high | M |
| [ ] | [M2](tasks/M2-mutation-spotcheck.md) | Run spot-check over the pure-logic core; triage survivors; fix or document | M1, P2–P4 | **Sonnet/high impl → Opus/xhigh triage review** | M |
| [x] | [E0](AUDIT.md) | E2E estate audit & classification → `AUDIT.md` | — | Explore (sonnet) + Opus synthesis | M |
| [ ] | [E1](tasks/E1-delete-legacy.md) | Delete legacy/dead test files (orphaned journeys dir + audit-flagged) | E0 | Sonnet / high | M |
| [ ] | [E2](tasks/E2-schema-reorg.md) | Apply modern dir + marker schema; move/rename; fix wiring (deploy.sh, runner, CI, docs) | E0, E1 | **Sonnet/high → Opus review** | L |
| [ ] | [E3](tasks/E3-roundtrip-upgrades.md) | Upgrade top security-critical files to round-trip grade + new backend-truth journeys | E0, E2, P-stream | **Sonnet/high → Opus review** | L |
| [ ] | [E4](tasks/E4-docs-sync.md) | Docs sync: schema, PBT, mutation; mark deferred gaps done | P*, M*, E* | Sonnet / medium | S |

P-stream and M-stream are independent of the E-stream and can land first. Within E, order is strict
(E0 → E1 → E2 → E3 → E4).

## Modern E2E schema (target — refined by E0 audit, applied in E2)

**Directory layout** under `ui_tests/tests/` (pytest `conftest.py` at `ui_tests/tests/` applies to all
subdirs, so fixtures keep working after moves):

```
ui_tests/tests/
  smoke/         # route-smoke + widget smoke (parametrized, page-loads/status only)
  roundtrip/     # independent-channel backend-truth (cross_role_*, dns crud, ddns round-trips)
  security/      # auth, 2FA, recovery codes, IP allowlist, attack attribution (round-trip grade target)
  features/      # feature E2E: registration, email notifications, backends UI, config, audit, geoip
  journeys/      # stateful sequences (j1/j2/j3 + future), driven by test_journey_master
  nonfunctional/ # accessibility, performance
  live/          # @live, needs real external deps
  mocks/         # mock-service self-tests (test the mock, not the app)
```

**Marker taxonomy** (registered in `pytest.ini`, orthogonal to directory so either axis can select):
`smoke`, `roundtrip`, `security`, `feature`, `journey`, `nonfunctional`, `mock_selftest`, plus the
existing `live`, `ci_smoke`, `e2e_local`, `installation`. Every test file declares a module-level
`pytestmark` so `-m roundtrip` / `-m security` work regardless of path.

**Naming:** `test_<area>_<surface>.py`; round-trip files keep the `test_cross_role_*` lineage or move to
`test_rt_*`. Final names are fixed in E2 from the audit buckets.

**Grade definitions (the rubric every E-task uses):**
- **smoke** — asserts only that a page loads / an element exists / status is 2xx.
- **ui-feedback** — asserts only flash text / redirect / rendered value; never backend state.
- **round-trip** — asserts against independent backend truth (Channel A read-only sqlite, B authed JSON,
  C DNS-API/mock-netcup, or Mailpit) per [`TESTING_LESSONS_LEARNED.md` §4](../../TESTING_LESSONS_LEARNED.md),
  obeying the four anti-false-green rules (no `if found: assert`, no `or`-chained status, no skip-to-green,
  never UI-only for a mutation).

## Mutation-testing scope (M-stream)

Local only, **toggleable**, **never in CI or `pytest.ini`**. Targets = the security-critical *pure-logic*
modules that already have a unit suite (mutmut is only meaningful where tests exist):

| Module | Interesting targets (why) |
|---|---|
| `token_auth.py` | `authenticate_token` (check ordering, error codes), `check_permission` (chain), `check_ip_allowed` (CIDR/single-IP loop), `_resolve_fqdn` |
| `models.py` | `matches_hostname` (host/subdomain/subdomain_only boundaries — `endswith('.'+fqdn)` and the `!= apex` guard), `matches_domain`, `get_effective_record_types/operations` (None-fallback inheritance), `is_expired` (`<` boundary), `parse_token`/`verify_token_hash` |
| `utils.py` | `validate_ip_range` (manual CIDR/range/wildcard branching), `validate_domain`, `validate_email` |
| `api/ddns_protocols.py` | `validate_hostname_format` (`>63`, isalnum, char-set), `parse_hostname`, `should_auto_detect_ip` |
| `recovery_codes.py` | `verify_recovery_code` (one-time consumption — survivors here mean a test checks the return value but not that the code was actually removed), `hash_recovery_code` (normalization), `_recovery_code_count` (bounds) |

Runner runs only the matching unit subset (not the whole suite, no `--cov`/`-x`) so each mutant evaluation
is fast. M2 documents the surviving-mutant count per module and either adds a killing test or records the
mutant as equivalent/acceptable with a one-line justification.

## Execution protocol (same discipline as the overhaul)

1. **One task at a time**, in dependency order. **Never run implementation agents in parallel** (operator
   is often near rate limits — also the cost-conscious default for this repo).
2. Each `tasks/*.md` is **self-contained**: a fresh `claude --model sonnet` (`/effort high`) session pointed
   at the file can execute it. Orchestration mode: an Opus session spawns **one** Sonnet subagent with the
   task file as prompt, then reviews the diff.
3. **Review gate:** every diff reviewed (Opus 4.8 @ xhigh) before commit. One commit per task. Do not push
   unless asked.
4. **Specs are contracts where they state rules, hints where they cite line numbers / counts.** Trust the
   code you read over the spec when they disagree; fix everything you find, not just the enumerated items;
   call out discrepancies in your summary so later specs can be corrected. (Lesson from the T01 pilot.)
5. When a task lands: tick its checkbox, add a worklog line (date, task, commit, notes).

## Verification milestones

1. **After P1–P4:** `python -m pytest tests/` green locally and in the CI `unit-tests` job (Python 3.11),
   including the new Hypothesis files; a deliberately-introduced parser bug is caught by a property test.
2. **After M1–M2:** `tooling/mutation/` runner works on demand; it is referenced by **no** CI workflow and
   **no** `pytest.ini` addopts (grep-verified); the mutation report lists per-module survivor counts and
   every meaningful survivor is either killed by a new test or justified.
3. **After E0–E2:** the legacy journeys dir is gone; `pytest ui_tests/tests` still collects (no import
   errors); `-m roundtrip`, `-m security`, `-m smoke` select sensible subsets; `deploy.sh` suite list,
   `run-local-tests.sh`, and the CI `e2e-smoke` path all still resolve. Anti-false-green check: total test
   count before vs after the move is unchanged except for intentional deletions (documented).
4. **After E3:** the new round-trip/security tests fail when the corresponding behavior is deliberately
   broken locally (e.g. comment out the IP-allowlist check) — the anti-false-green gate from the overhaul.
5. **After E4:** docs match reality per AGENTS.md definition-of-done.

## Findings (source issues surfaced by this work — for maintainer decision)

- **P4 / token-level scope setters coerce `[]` → `None`** (`APIToken.set_allowed_operations` /
  `set_allowed_record_types` in `models.py` use `json.dumps(x) if x else None`). This collapses an intended
  **deny-all** (`[]`) into **inherit-from-realm** (`None`) — a potential privilege-escalation if any caller/UI
  expresses "no operations" via the setter. The getter/effective layer is correct (`is not None`); only the
  setter loses the distinction, and it's **inconsistent with the realm-level setter** which stores `[]`
  verbatim. Characterized by `tests/test_token_model_property.py::test_effective_scope_setter_coerces_empty_list_to_none`
  (asserts current behavior; will go red when fixed). **Not fixed** (P4 is a test-only task). Decide: fix the
  setter to store `json.dumps(operations)` unconditionally (matching the realm setter) + flip the test, or
  confirm `[]`-at-token-level is unsupported by design.

## Worklog

- 2026-06-14 — Plan created. Source audit done (mutation/PBT targets identified). Legacy journeys dir
  confirmed orphaned. P-/M-/E-stream specs written.
- 2026-06-14 — E0 landed: [`AUDIT.md`](AUDIT.md) classifies all ~89 `ui_tests/` files. Key results: 13
  pure-delete + 9 merge-then-delete; concrete bucket→dir assignment; ranked top-8 upgrade list. Confirmed
  brute-force attribution already round-trip-covered (dropped from E3); found two or-chained and several
  skip-to-green anti-patterns to fix in E3. E1/E3 specs reconciled to the audit.
- 2026-06-14 — P1 landed (commit 125c912). hypothesis>=6.100 + ci/dev profiles in tests/conftest.py
  (guarded). 239 unit tests green on both profiles; no flags leaked into pytest.ini. No spec discrepancies.
- 2026-06-14 — P2 landed (commit 65513e1). tests/test_ddns_property.py (42 properties). validate↔parse
  consistency, never-raises, accepted-set structural, case idempotence, valid-IP acceptance. No bugs found
  under ci/dev. Reviewer trimmed two unused imports. 281 total unit tests green.
- 2026-06-14 — P3 landed (commit 0d9a64d). tests/test_validators_property.py (20 properties). check_ip_allowed
  soundness run against real transient APIToken; CIDR prefix edges; phantom-range guard; wildcard octet bounds.
  No bugs found. Reviewer simplified the out-of-network construction + dropped an unused import. 301 total green.
- 2026-06-14 — P4 landed (commit ac92003). tests/test_token_model_property.py (23 properties). Scope
  monotonicity boundaries pinned for the M2 mutation pass; token round-trip; effective-scope sentinels;
  is_expired. **Surfaced a real source finding** (token setter `[]`→`None` coercion — see Findings above).
  Reviewer trimmed 3 unused imports. 324 total unit tests green. P-stream complete.
