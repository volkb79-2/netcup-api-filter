# T06 — Unit tests: lightweight migrations (~6 cases)

| Status | Model / effort | Depends on | Size |
|--------|----------------|------------|------|
| open | Sonnet 4.6 / high | T02 | S |

## Objective

Pin the behavior of `run_lightweight_migrations()` — the mechanism that lets production
deployments keep their SQLite DB across upgrades. It is critical-path for every deploy and
currently untested.

## Context — read first

- `src/netcup_api_filter/database.py` — `run_lightweight_migrations` (196). Read the whole
  function: how it discovers missing columns/indexes, what it refuses to do.
- `AGENTS.md` § Database & migrations — the documented contract: additive nullable /
  scalar-default columns and simple indexes migrate automatically; anything else must NOT be
  attempted.
- T02 `app` fixture (tmp_path file DB — needed: in-memory DBs can't simulate "old schema on
  disk" across an ALTER cleanly; also sqlite ≥ 3.35 is required for `DROP COLUMN`, available
  on Python 3.11 runners).

## Spec

`tests/test_lightweight_migrations_unit.py` (~6 cases), each shaped as: create the schema via
`db.create_all()` → degrade it with raw SQL → run `run_lightweight_migrations()` → assert.

1. **Restores a dropped nullable column**: `ALTER TABLE accounts DROP COLUMN <pick a nullable
   or scalar-default column from the model, e.g. a telegram/notification flag>` → migration
   re-adds it with the model's default; `SELECT` works again.
2. **Creates a missing index**: drop one of the model-declared indexes (`DROP INDEX ...`) →
   migration recreates it (inspect `PRAGMA index_list`).
3. **Idempotent**: running it twice in a row makes zero further changes (capture and compare
   `PRAGMA` schema state, or assert its logged/returned change-set is empty on the second run).
4. **Refuses NOT-NULL-without-default**: if any model column is NOT NULL without a scalar
   default, dropping it must NOT be silently fixed — assert the migration skips it and (per
   implementation) logs a warning. If no such column exists in the current models, simulate by
   asserting on the function's internal predicate, or document why the case is structurally
   impossible — do not fake it.
5. **Fresh DB no-op**: on a brand-new `create_all()` schema, the migration reports nothing to do.
6. **Non-sqlite early return**: monkeypatch the engine dialect name (`db.engine.dialect.name`)
   to `"postgresql"` and assert the function returns early without executing DDL (read the
   guard in the implementation first; if no such guard exists, report that as a finding
   instead of inventing the test).

## Acceptance criteria

- [ ] File green; `python -m pytest tests/ -q` green overall; no skips.
- [ ] Case 1 uses a real column from the current model (named in a comment), so the test keeps
      protecting real upgrade paths.
- [ ] Any contract gaps discovered (e.g. missing non-sqlite guard) reported in the summary.

## Verify

```bash
cd /workspaces/netcup-api-filter
python -m pytest tests/test_lightweight_migrations_unit.py -v
python -m pytest tests/ -q
```

## Guardrails (non-negotiable)

- No `pytest.skip` to go green, no assertions inside `if found:` blocks, no `or`-chained assertions.
- Tests touch ONLY their tmp_path DB — never `deploy-local/netcup_filter.db` or the repo-root DB file.
- Run pytest from the repo root. Don't modify `src/` to make tests pass — report findings.
- Leave changes uncommitted for review unless your operator says otherwise.
- When done: tick T06 in `docs/plans/testing-overhaul/PLAN.md` + add a worklog line.
