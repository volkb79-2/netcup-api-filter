# E4 — Docs sync

**Goal:** Make the testing docs match the post-hardening reality (per AGENTS.md definition-of-done).

**Model/effort:** Sonnet / medium. **Depends:** all P*, M*, E* tasks landed. **Size:** S.

## Do
1. `docs/TESTING_INFRASTRUCTURE.md`:
   - "Testing types at a glance" + "Suite layout": new directory tree and marker taxonomy (from E2).
   - "Gaps and next steps" table: flip **Property-based testing** and **Mutation testing spot-check** rows to
     done, linking the new `tests/test_*_property.py`, `tooling/mutation/`, and `MUTATION_REPORT.md`.
   - Add the `HYPOTHESIS_PROFILE` note (P1) and the mutation "local-only, toggleable, not in CI" note.
   - Refresh the coverage table if the P/M tasks moved any numbers.
2. `docs/TESTING_LESSONS_LEARNED.md`: §5 (Hypothesis) — change "Integration plan" from future tense to "done";
   point at the real files. Add a short §6 "Mutation testing" describing the runner and how to read survivors.
3. `docs/JOURNEY_CONTRACTS.md`: reconcile with the new journey/round-trip layout; remove or update references
   to any deleted legacy journeys (E1); note where the new round-trip security journeys (E3) live.
4. `CHANGELOG.md` + `README.md` (testing section): one entry summarising the hardening (PBT, mutation
   spot-check, E2E reorg, new round-trip security coverage).
5. Stale-reference sweep: `grep -rn` for paths/filenames deleted or moved in E1/E2 across `docs/`, `AGENTS.md`,
   `deploy.sh`, runners — fix every dangling reference.

## Verify
- `grep -rn` for every deleted/old path returns no live references (only historical worklogs).
- Docs describe the markers and directories that actually exist (`pytest --markers` matches the doc table).
- Mark the plan COMPLETE in `PLAN.md` and tick all checkboxes; final worklog line.
