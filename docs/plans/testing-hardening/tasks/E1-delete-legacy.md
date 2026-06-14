# E1 — Delete legacy / dead test files

**Goal:** Remove test code that no runner collects and that is superseded, so the reorg (E2) operates on a
live estate only.

**Model/effort:** Sonnet / high. **Depends:** E0 (`AUDIT.md`). **Size:** M.

## Inputs
- `AUDIT.md` "Delete/legacy" list (authoritative per-file justification).
- Known anchor (confirmed 2026-06-14): the legacy directory `ui_tests/journeys/` —
  `test_00_auth_enforcement.py … test_09_multibackend.py` (10 files), its `conftest.py` and `__init__.py` —
  is imported by nothing and collected by no runner (`test_journey_master.py` imports only
  `ui_tests/tests/journeys/{j1,j2,j3}`; `run-local-tests.sh` and the CI `e2e-smoke` job collect only
  `ui_tests/tests`; `deploy.sh`'s suite list does not reference it).

## Do
1. **Re-confirm orphan status before deleting anything** (don't trust the spec blindly):
   - `grep -rn "ui_tests.journeys" --include=*.py .` and `grep -rn "journeys/test_0" .` → only self-references.
   - `python -m pytest ui_tests/journeys --collect-only -q` to see what (if anything) collects, vs
     `pytest ui_tests/tests --collect-only -q`.
   - Check `deploy.sh`, `run-local-tests.sh`, `.github/workflows/ci.yml`, `tooling/` for any path reference.
2. For each file in `AUDIT.md`'s delete list, verify the stated reason still holds (broken import, dead
   route, superseded duplicate, orphaned), then `git rm` it. **If the audit says a legacy file covers a
   surface NOT covered elsewhere, do NOT delete it here** — leave it and flag it for E3 (port its unique
   coverage into a round-trip test first). Deleting unique coverage is the one thing this task must not do.
3. Remove now-dead helper code that only the deleted files used (check with grep before removing).
4. **Update `tooling/coverage/route_vs_tests_report.py` (~line 143)** — it *scans* both journey dirs for a
   report (it does not collect them as pytest tests, which is why they were orphaned). After deleting
   `ui_tests/journeys/`, that scan path dangles; update or drop the legacy-dir branch so the report still runs.
5. Update any doc that references a deleted file (`JOURNEY_CONTRACTS.md` mentions the legacy/planned
   journeys; `docs/TESTING_INFRASTRUCTURE.md`; the overhaul `PLAN.md` worklog is history — leave it).

### Per AUDIT.md, this task's concrete delete set
The 13 pure-delete files + the merge-then-delete set are enumerated in
[`AUDIT.md`](../AUDIT.md) "Delete list" and "Merge-then-delete". **This task does the pure-delete set only**
(the 10 legacy `test_0X` + `journeys/conftest.py` + `journeys/__init__.py` + `test_registration_2fa_complete.py`).
The merge-then-delete set (which must preserve unique coverage first) belongs to **E2** (it's part of the
move/consolidate pass), not here.

## Verify
- `python -m pytest ui_tests/tests --collect-only -q` succeeds with **no import/collection errors** and the
  same count as before minus only intentional deletions.
- The three runner configs (`deploy.sh` suite list, `run-local-tests.sh`, CI `e2e-smoke`) still reference
  only existing paths (`grep` each).
- Record in your summary: exact files deleted, LOC removed, and any legacy file you *kept* for E3 porting.

## Notes
One commit. List every deletion in the PLAN worklog with its justification.
