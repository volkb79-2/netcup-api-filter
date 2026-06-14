# E2 — Apply the modern directory + marker schema

**Goal:** Move/rename the surviving test files into the schema from `PLAN.md`, add a real marker taxonomy,
and update every place that references test paths — without changing what any test asserts.

**Model/effort:** Sonnet/high implement → **Opus 4.8/xhigh review** (mechanical but high-blast-radius: a
wrong move silently drops a suite from CI). **Depends:** E0 (`AUDIT.md` bucket assignments), E1. **Size:** L.

## Scope boundary (read first)
**E2 is purely structural: moves + markers + wiring. ZERO content changes.** Do **not** merge, consolidate,
delete, or edit any test body. The merge-then-delete consolidations and the round-trip upgrades from
`AUDIT.md` are **E3's** job. Concretely:
- Move only the files listed in `AUDIT.md` "Bucket assignment for kept files" into their bucket dirs.
- **Leave the `AUDIT.md` "Merge-then-delete" source files where they are** (at `ui_tests/tests/` root) — E3
  merges their unique tests into the (already-moved) targets and deletes them. Do not move or touch them here.
- The collected-test count must be **identical before and after** (483 under `ui_tests/tests`). Nothing is
  added or removed; only path prefixes change. This exactness is the review gate.

## Schema (from PLAN.md "Modern E2E schema")
Directories under `ui_tests/tests/`: `smoke/ roundtrip/ security/ features/ journeys/ nonfunctional/ live/
mocks/`. Markers registered in `pytest.ini`: `smoke roundtrip security feature journey nonfunctional
mock_selftest` (+ existing `live ci_smoke e2e_local installation`). Each test module gets a module-level
`pytestmark = [pytest.mark.<bucket>]` (and `pytest.mark.live` etc. where applicable) so `-m <bucket>` selects
by marker independent of path.

## Do
1. **Create the subdirectories** with an `__init__.py` where the existing layout uses them (mirror current
   package style — `ui_tests/tests/journeys/` already has `__init__.py`). Confirm `ui_tests/tests/conftest.py`
   fixtures reach subdirs (pytest applies a `conftest.py` to all descendant dirs — verify with a
   `--collect-only` after the first move).
2. **Move each KEPT test file to its bucket** per `AUDIT.md`'s bucket assignment. Use `git mv` so history is
   preserved. Apply the naming convention (`test_<area>_<surface>.py`); keep the `test_cross_role_*` names if
   the audit says so, otherwise rename to the agreed scheme. journeys/ keeps `j1/j2/j3` + `state_matrix.py` +
   `journey_state`.
3. **Add `pytestmark`** to the top of every moved test module (after imports) with its bucket marker(s).
   Register the markers in `pytest.ini`.
4. **Fix all references** (this is where suites silently disappear if missed — be exhaustive):
   - intra-suite imports (`from ui_tests.tests.X import …`, `from .X import …`) — grep and update.
   - `test_journey_master.py` import paths if journeys moved.
   - `deploy.sh` suite list (lines ~1190–1221): update every `ui_tests/tests/test_*.py` path to its new home.
   - `run-local-tests.sh` default `TEST_PATH` (still `ui_tests/tests`, which recurses — confirm).
   - `.github/workflows/ci.yml` `e2e-smoke` step (`-m ci_smoke ui_tests/tests` — recursive, confirm it still
     finds the `ci_smoke`-tagged test after the move).
   - any helper that hard-codes a path (`capture_ui_screenshots.py`, `route_discovery.py`, `tooling/`).
5. **Update docs:** `docs/TESTING_INFRASTRUCTURE.md` suite-layout section to the new tree + marker table.

## Verify (the anti-silent-drop gate)
- `pytest ui_tests/tests --collect-only -q | wc -l` **equals the pre-move count** (no test lost to a broken
  import or a missed `__init__.py`). Diff the collected node-id list before/after — the only changes should be
  path prefixes.
- `pytest ui_tests/tests -m roundtrip --collect-only`, `-m security`, `-m smoke` each select a non-empty,
  sensible set (cross-check against `AUDIT.md` buckets).
- `pytest ui_tests/tests -m ci_smoke --collect-only` still selects the same nodes as before the move (CI
  parity).
- Every path in `deploy.sh`, `run-local-tests.sh`, CI resolves (`grep` + `test -f` each referenced file).
- No assertion or test body changed (diff is moves + `pytestmark` + path edits only). Upgrades are E3.

One commit. This task changes locations and wiring only — **zero behavior change**.
