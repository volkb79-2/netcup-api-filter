# T14 — Docs sync (definition of done for the whole overhaul)

| Status | Model / effort | Depends on | Size |
|--------|----------------|------------|------|
| open | Sonnet 4.6 / medium | T01–T13 (run last) | S |

## Objective

Bring the canonical docs in line with the new testing reality, per AGENTS.md's
"keep the canonical docs in sync" rule. No code changes.

## Context — read first

- `AGENTS.md` § Testing and § Documentation (the doc-sync contract and the rule against new
  top-level markdown files).
- `docs/plans/testing-overhaul/PLAN.md` — worklog of what actually landed (source of truth;
  document what shipped, not what was planned).
- `docs/TESTING_LESSONS_LEARNED.md`, `docs/TESTING_INFRASTRUCTURE.md`, `docs/README.md`,
  `CHANGELOG.md`, `AGENTS.md` § Testing.

## Spec

1. **`docs/TESTING_LESSONS_LEARNED.md`** — add a section on the verification-channel pattern:
   why round-trip assertions (UI action → independent backend truth) are required for new E2E
   tests; the three channels in `ui_tests/verification.py` (read-only sqlite / authed JSON /
   mock-netcup state) and when to use each; the `wait_for` poller instead of sleeps; the
   anti-false-green rules (no `if found:` asserts, no or-chains, no green-making skips);
   pointer to `test_cross_role_account_lifecycle.py` as the pattern file.
2. **`AGENTS.md` § Testing** — update the two-layer description: mention the unit conftest +
   factories, the route-smoke suite (auto-covers new routes — tell contributors they get smoke
   for free but must add round-trip tests for new behavior), and the CI `e2e-smoke` job.
3. **`docs/TESTING_INFRASTRUCTURE.md`** — reflect deleted runners (T01/T12) and the CI job;
   remove references to anything that no longer exists.
4. **`docs/README.md`** — Testing section lists the plan link (added when the plan landed) —
   verify it and the descriptions still match.
5. **`CHANGELOG.md`** — one consolidated entry for the overhaul (unit coverage added,
   verification channel, cross-role round-trips, smoke consolidation, CI e2e job, deletions).
6. Sweep: grep live docs for filenames deleted in T01/T12 and fix stragglers
   (`docs/deprecated/` stays untouched).

## Acceptance criteria

- [ ] No live doc references a deleted file (grep proof in summary).
- [ ] TESTING_LESSONS_LEARNED's new section teaches the channel pattern with a concrete example.
- [ ] No doc claims anything that didn't actually ship (check PLAN.md worklog).
- [ ] No new top-level markdown files created.

## Verify

```bash
cd /workspaces/netcup-api-filter
for f in run-screenshot-tests.sh test_installation_workflow.sh test-https-deployment.sh \
         test_ui_comprehensive test_account_portal_complete test_admin_portal_complete; do
  grep -rn "$f" docs/ README.md AGENTS.md --exclude-dir=deprecated && echo "FAIL: $f still referenced"
done; echo done
```

## Guardrails (non-negotiable)

- Don't invent doc claims the code doesn't back; aspirational items go to the roadmap/plan, not
  stated as current.
- Leave changes uncommitted for review unless your operator says otherwise.
- When done: tick T14 in `docs/plans/testing-overhaul/PLAN.md` + add a worklog line; the plan
  itself can then be marked complete (move a copy to `docs/deprecated/` only when the team is
  done referencing it).
