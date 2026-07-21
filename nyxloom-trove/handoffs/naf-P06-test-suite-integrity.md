---
schema_version: 1
id: naf-P06-test-suite-integrity
project: naf
title: "Test suite: silent route-discovery fallback and tests that cannot fail"
tier: sonnet5-high
input_revision: "a5a9397"
depends_on: []
session: fresh
source: {kind: review, ref: "docs/deprecated/FOLLOWUP_REVIEW_2026-07-16.md#P1-F"}
scope:
  touch:
    - "ui_tests/route_discovery.py"
    - "ui_tests/tests/smoke/test_route_smoke.py"
    - "ui_tests/tests/nonfunctional/test_performance.py"
    - "ui_tests/tests/nonfunctional/test_accessibility.py"
    - "ui_tests/tests/live/test_live_email_verification.py"
    - "ui_tests/tests/features/test_registration_negative.py"
  forbid:
    - "src/netcup_api_filter/app.py"
    - "pytest.ini"
oracles:
  - id: O1
    observable: "When app import fails inside `discover_routes_from_app()`, collection of test_route_smoke.py fails loudly (error or explicit pytest.exit naming the cause); with a healthy app the discovered route count is asserted against a floor (>15 admin routes) so a silent collapse to the 21-route static list cannot pass"
    negative: "discovery swallows the exception, prints a warning pytest hides, and falls back to a stale hardcoded list — route-smoke silently shrinks from ~86 to 45 and ci_smoke from ~93 to 50 while staying green"
    gate: unit
  - id: O2
    observable: "No test in the touched files converts its own failure condition into pytest.skip: each of the four (images-without-dimensions, >5 console warnings, heading-level skips, table-header scope) either asserts a stated threshold or is deleted; a grep for `pytest.skip` in those files returns only config-gated skips"
    negative: "the assertion is commented out and replaced by a skip, so the test reports green for a page that violates the very rule it names"
    gate: unit
  - id: O3
    observable: "The six skeleton bodies in live/test_live_email_verification.py and the unconditional skip in features/test_registration_negative.py are gone (deleted, or implemented with real assertions); collected counts drop accordingly and the new totals are recorded in the REPORT"
    negative: "skip-only bodies keep inflating the suite count, so the reported number overstates real coverage"
    gate: unit
gates: [unit]
escalate_if:
  - "a named contract cannot be met as specified"
  - "scope requires editing a forbidden file (app.py / pytest.ini)"
  - "a route-count floor cannot be established without running the full app"
---

# P06 — Test-suite integrity: the silent fallback and the can't-fail tests

> **STATUS (2026-07-21):** O1 part-1 merged (do not re-implement); active work = O2 + O3 (+ any O1 part-2 STATE.md names); the unit gate re-verifies all oracles. See [../STATE.md](../STATE.md).

> Tier: sonnet5-high · Base branch: main (input_revision a5a9397).
> Source: the deep review, finding **P1-F**. This is the "testing framework" priority.
> A suite that silently covers half of what it claims is worse than a smaller honest one.

## Context to read first (read ONLY these)

- `ui_tests/route_discovery.py` ~line 152 — `discover_routes_from_app()` wraps app import
  in a bare `except Exception`, prints a warning (pytest swallows it), and falls back to
  `discover_routes_static()` — a stale ~21-route hardcoded list. Observed trigger: an
  unwritable `tmp/route_discovery.db`.
- `ui_tests/tests/smoke/test_route_smoke.py` — parametrized over the discovered routes;
  also ~line 49 permanently excludes `/account/docs` (500s) and `/admin/app-logs`
  (traceback) as "tracked separately" with no tracking anywhere. Leave the exclusions in
  place for this package (they are backlog item B-ROUTES) but do not add new ones.
- `ui_tests/tests/nonfunctional/test_performance.py` ~179, ~295 — failure → `pytest.skip`.
- `ui_tests/tests/nonfunctional/test_accessibility.py` ~187 (strict assert commented out
  at ~190), ~560 — same pattern.
- `ui_tests/tests/live/test_live_email_verification.py` ~350-414 — six bodies that are
  only `pytest.skip("Skeleton test - ...")`.
- `ui_tests/tests/features/test_registration_negative.py` ~398 — body is solely
  `pytest.skip("Requires complex state setup - covered by unit tests")`.
- `AGENTS.md` "Test hygiene" — the rule being violated: *"a test that can't fail is worse
  than no test… skip only when a feature is genuinely disabled by config, and gate the
  skip on that specific condition."*

## Work

1. `route_discovery.py`: make discovery failure LOUD — re-raise, or `pytest.exit` with
   the underlying error. Keep `discover_routes_static()` only if some caller genuinely
   needs an app-free list; if nothing does, delete it (a stale list that can silently
   substitute for the real one is the hazard). Do not "fix" it by making the fallback
   list longer.
2. `test_route_smoke.py`: assert a floor on discovered routes at module import (e.g.
   `assert len(ADMIN_ROUTES) > 15`) so a collapse fails collection instead of passing.
3. For each of the four skip-instead-of-fail tests: restore the assertion with an
   explicit, stated threshold, or delete the test outright. A test that names a rule must
   enforce it. Do not lower a threshold to make a currently-failing page pass — if a page
   genuinely violates it, that is a finding for the REPORT and a backlog item, not a
   reason to weaken the oracle.
4. Delete the six skeleton tests and the unconditional skip in registration-negative
   (its claim "covered by unit tests" is the reason it should not also exist here).
5. Record the resulting collected counts (`tests/` and `ui_tests/`) in the REPORT.
   `docs/TESTING_INFRASTRUCTURE.md` currently claims 355 unit / 450 ui / 93 ci_smoke;
   the real unit count is **373** (verified in the gate). Doc sync is backlog B-DOCS —
   report the numbers, do not edit the docs here.

## Gate (the ONLY accepted gate)

The daemon runs this package in a git **worktree** under `.worktrees/` off the `main` branch;
the `unit` gate mounts the repo and `cd`s into that worktree. Run the gate there, never in the
devcontainer:

```
./tooling/test-runner/testing-exec.sh unit
```

Note: the ui_tests changes are mostly not exercised by the `unit` gate (they need a
deployed app + pwmcp via the `e2e` gate). Use `unit` to prove nothing regressed, and
verify collection of the touched ui_tests modules explicitly:

```
./tooling/test-runner/testing-exec.sh shell
# inside: /opt/tester-venv/bin/python -m pytest ui_tests/tests --collect-only -q
```

Never the devcontainer.

## Scope / forbid

Touch only the six files in `scope.touch`. `pytest.ini` changes (dropping `-x`, adding
`--strict-markers`, scoping `--cov`) are a separate backlog item — they change every
run's behavior and deserve their own carve. `app.py` is not the problem here.

## BLOCKED rule

If a named contract cannot be met as specified, or the work requires editing a forbidden
file, STOP — write `BLOCKED: <reason>` to the LOG, commit, and exit. Do NOT improvise a
workaround.
