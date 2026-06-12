# T01 — Cleanup & quick fixes (broken tests, dead scripts, stale CI ignore)

| Status | Model / effort | Depends on | Size |
|--------|----------------|------------|------|
| open | Sonnet 4.6 / high | — | S |

## Objective

Make the broken/dead test tooling honest: fix two test files that cannot currently pass,
remove the stale CI `--ignore`, and delete provably dead runner scripts and orphaned test
utilities. No behavior changes to `src/` application code.

## Context — read first

- `AGENTS.md` § Testing (test hygiene rules) and § Documentation (doc-sync definition of done).
- `.github/workflows/ci.yml:68-86` — the `--ignore` and its now-stale justification comment.
- `src/netcup_api_filter/database.py:139-148` — the in-memory `pool_size` guard that already
  fixes the bug the CI comment cites (landed in commit `f99ea20`).
- `tests/test_telegram_linking.py:25-44` — the proven fixture pattern (monkeypatch + tmp_path
  file DB) to mirror.
- `src/netcup_api_filter/models.py` — the `Account` model (~line 300+): confirm field names
  before editing the fixture. There is **no `approved` column**; there are `is_active`,
  `approved_at`, `approved_by_id`, `email_verified`, `email_2fa_enabled`.

## Spec

### 1. Fix `ui_tests/journeys/test_09_multibackend.py` (crashes at runtime)

It calls two methods that don't exist:

- `await browser.wait_for_load()` → `await browser.wait_for_load_state()`
  (real method: `ui_tests/browser.py:434`, signature `wait_for_load_state(state="networkidle", timeout=30000)`).
- `await ss.take("name")` → `await ss.capture("name")`
  (real method: `ScreenshotHelper.capture(name, description="")`, `ui_tests/journeys/conftest.py:75`).

Known call sites around lines 92–148; grep the whole file for `wait_for_load(` and `ss.take(`
and fix every occurrence. Do not change anything else in the file.

### 2. Fix `tests/test_2fa_security_functional.py` (fails on invalid model kwarg)

The `app` fixture (lines ~24–55) has three problems:

1. `Account(..., approved=True)` — `approved` is not a mapped column → `TypeError`.
   Replace with `is_active=1`, and add `approved_at=datetime.utcnow()` and
   `email_verified=1` (import `datetime`). Keep `email_2fa_enabled=True`.
2. Direct `os.environ['...'] = ...` writes leak into the test session. Convert the fixture to
   take `monkeypatch` and `tmp_path`, and use
   `monkeypatch.setenv("NETCUP_FILTER_DB_PATH", str(tmp_path / "test.db"))` +
   `monkeypatch.setenv("SECRET_KEY", "test_secret_key_for_testing_only")`
   (mirror `tests/test_telegram_linking.py:25-44`).
3. `app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'` after `create_app()` is
   ineffective (engine already bound) — delete the line.

Then run the file. If further failures surface, fix them **by reading the real model/function
signatures** (`src/netcup_api_filter/models.py`, `src/netcup_api_filter/account_auth.py`) —
never by skipping or loosening assertions. If a test asserts genuinely outdated behavior,
update the assertion to the current behavior and say so in your summary.

### 3. CI: drop the stale ignore

In `.github/workflows/ci.yml`: change the test step to plain `python -m pytest tests/`
(remove `--ignore=tests/test_2fa_security_functional.py` and the trailing `\`), and delete the
whole "known infra issue" comment block (lines ~68–82) — the bug it describes is fixed.

### 4. Delete dead files (grep-verify each first)

Verification protocol per file: `grep -rn "<basename>" . --exclude-dir=.git --exclude-dir=.venv
--exclude-dir=deploy --exclude-dir=deploy-local --exclude-dir=deploy-webhosting
--exclude-dir=tmp --exclude-dir=__pycache__ --exclude-dir=node_modules`.
Self-references and `docs/deprecated/` hits don't block deletion; a hit in a **live** doc means
update that doc in the same change; a hit in live code means **stop and report instead of deleting**.

Unconditional (verified dead in the audit):

- `run-screenshot-tests.sh` — runs `ui_tests/tests/test_screenshot_coverage.py`, which doesn't exist.
- `test_installation_workflow.sh`, `test-https-deployment.sh` — curl-based, superseded by
  deploy.sh journeys, incompatible with the 2FA auto-submit flow.
- `ui_tests/test_console_errors.py` — **top-level file only**; it targets legacy `/client/…`
  and `/admin/client/` routes that no longer exist. Do NOT touch
  `ui_tests/tests/test_console_errors.py` (live, runs in deploy.sh).
- `ui_tests/analyze_ui_screenshots.py`, `ui_tests/compare_visuals.py`,
  `ui_tests/mailpit_client_selftest.py`, `ui_tests/quick_capture.py` — orphaned utilities.

Conditional (delete only if your grep confirms unreferenced and broken):

- `tooling/run-tests.sh` (reportedly calls a nonexistent `setup.sh`),
  `tooling/setup-playwright.sh`, `tooling/start-ui-stack.sh`, `tooling/run-ui-validation.sh`
  (all superseded by `tooling/playwright/start-playwright.sh` + deploy.sh). If one turns out
  to be referenced or working, leave it and note that in your summary.

Do **not** delete: `run-2fa-tests.sh` (its target exists), `run-local-tests.sh`,
`run-2fa-security-tests.sh`, `ui_tests/route_discovery.py` (becomes load-bearing in T12).

### 5. Doc sync

Grep `docs/` (excluding `docs/deprecated/`) and `README.md` for each deleted filename; update
any live mention. Add a CHANGELOG entry under the current Unreleased section (short bullets:
fixed broken journey 09 + 2FA functional fixture, CI ignore removed, dead test tooling deleted).

## Acceptance criteria

- [ ] `python -m pytest tests/ -v` is green locally, **including** `test_2fa_security_functional.py`, with no new skips.
- [ ] `ui_tests/journeys/test_09_multibackend.py` byte-compiles and contains no `wait_for_load(` / `ss.take(`.
- [ ] `.github/workflows/ci.yml` contains no `--ignore` and no stale comment block.
- [ ] Every deleted file has a recorded grep showing no live references; no live doc still mentions a deleted file.
- [ ] CHANGELOG updated. No `src/` runtime code changed (the `database.py` guard already exists — don't touch it).

## Verify

```bash
cd /workspaces/netcup-api-filter
python -m pytest tests/ -v
python -m py_compile ui_tests/journeys/test_09_multibackend.py
grep -n "wait_for_load()\|ss\.take(" ui_tests/journeys/test_09_multibackend.py && echo "FAIL: stale calls" || echo OK
grep -n "ignore=tests" .github/workflows/ci.yml && echo "FAIL: ignore still present" || echo OK
```

## Guardrails (non-negotiable)

- A test that can't fail is worse than no test: no `pytest.skip` to make anything green, no
  assertions inside `if found:` blocks, no `or`-chained tolerant assertions.
- Never hardcode credentials anywhere (tests read `deployment_state_local.json` via the harness).
- Run pytest from the repo root. Don't edit `deploy/`, `deploy-local/`, `deploy-webhosting/` (generated).
- Leave changes uncommitted for review unless your operator says otherwise.
- When done: tick T01 in `docs/plans/testing-overhaul/PLAN.md`, add a worklog line there, and
  summarize what you deleted/kept and why.
