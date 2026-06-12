# T13 — CI `e2e-smoke` job: Playwright smoke subset on every PR

| Status | Model / effort | Depends on | Size |
|--------|----------------|------------|------|
| open | **Opus 4.8 / xhigh** | T12 (route smoke exists), T08 (one round-trip exists) | M |

## Objective

Give PRs UI/E2E regression protection: a GitHub Actions job that boots the app over plain HTTP
on the runner (no TLS proxy, no PUBLIC_FQDN, no Playwright container) and runs a small marked
subset (`ci_smoke`). Feasibility was verified in the audit; the soft blockers and their
mitigations are listed below — design around them, they are load-bearing.

## Context — read first

- `.github/workflows/ci.yml` — existing lint + unit jobs; add `e2e-smoke` alongside.
- `build_deployment.py` — `create_deployment_state(deploy_dir, client_id, secret_key,
  all_demo_clients, target="local")` (line 259) and
  `initialize_database(deploy_dir, is_local=False, seed_demo=False) -> Tuple[str, str, list]`
  (line 371). Read both fully — the bootstrap script calls them directly (no zip build).
- `ui_tests/deployment_state.py` — env overrides (verified): `DEPLOYMENT_STATE_FILE` (199),
  `UI_BASE_URL` (374), `UI_PLAYWRIGHT_STORAGE_STATE_PATH` (68; also `ui_tests/conftest.py:40`).
- `ui_tests/config.py:~293` — module-level singleton **raises at import if the state file is
  missing** → the bootstrap must run before pytest starts.
- `ui_tests/mailpit_client.py:~219-226` — requires `MAILPIT_URL`/`MAILPIT_USERNAME`/
  `MAILPIT_PASSWORD` env (dummies fine when Mailpit auth is disabled).
- `ui_tests/playwright_client.py:89-99` — launches Chromium in-process
  (`playwright install --with-deps chromium` is all the runner needs).
- `bootstrap/seeding.py` — Mailpit email config seeding reads `MOCK_SMTP_HOST`-style env
  (read `seed_mock_email_config`); admin email-2FA is mandatory → Mailpit is required in CI.
- `pytest.ini` — `addopts` contains `-x` and `--cov` → CI must pass `-o addopts=""`;
  markers section is where `ci_smoke` gets registered.
- `gunicorn.conf.py` — binds plain HTTP on 5100 by default.

## Spec

### 1. `scripts/ci_bootstrap_e2e.py` (new)

With env `SECRET_KEY`, `NETCUP_FILTER_DB_PATH=$GITHUB_WORKSPACE/ci-deploy/netcup_filter.db`,
`DEPLOYMENT_TARGET=local`, `MOCK_SMTP_HOST=localhost` (+ whatever seeding needs — read it):
create the deploy dir, call `initialize_database(deploy_dir, is_local=True)` then
`create_deployment_state(...)` with its return values, writing the state JSON to the path
given by `--state-file` (the workflow passes `$RUNNER_TEMP/deployment_state_local.json`).
Fail fast with clear messages (no silent fallbacks — FAIL_FAST_PRINCIPLE.md).

### 2. `ci_smoke` marker

Register in `pytest.ini` (`ci_smoke: minimal E2E smoke subset run in GitHub Actions over plain HTTP`).
Mark: `test_route_smoke.py` (whole module), `test_admin_security_api_contracts.py`,
`test_account_sessions.py`, ONE cross-role round trip (Test 7,
`test_admin_token_revocation_immediate` — no mock-netcup dependency). **Nothing
HTTPS-dependent** (secure-cookie assertions etc.) may carry the marker.

### 3. Workflow job `e2e-smoke` in `.github/workflows/ci.yml`

1. checkout + setup-python 3.11 (pip cache).
2. `pip install -r requirements-dev.txt` plus whatever `ui_tests` imports that isn't in it —
   check `ui_tests/requirements.txt` if present (playwright, httpx, pytest-timeout…); then
   `playwright install --with-deps chromium`.
3. Mailpit as a **service container** (`axllent/mailpit`, ports 8025/1025,
   `MP_SMTP_AUTH_ACCEPT_ANY=true`); job env `MAILPIT_URL=http://localhost:8025`,
   `MAILPIT_USERNAME=ci`, `MAILPIT_PASSWORD=ci`.
4. Run the bootstrap script (step 1 env).
5. Start the app in the background:
   `PYTHONPATH=src ... python -m gunicorn -w 2 -b 127.0.0.1:5100 'netcup_api_filter.app:create_app()'`
   (env: SECRET_KEY, NETCUP_FILTER_DB_PATH, DEPLOYMENT_TARGET=local, SMTP→localhost:1025 per
   seeding contract); poll `http://127.0.0.1:5100/health` until 200 (timeout 60s).
6. Run the subset — **one serial pytest invocation** (admin password rotates on first login
   and propagates via the state file; parallelism would race it):
   ```bash
   DEPLOYMENT_TARGET=local \
   DEPLOYMENT_STATE_FILE=$RUNNER_TEMP/deployment_state_local.json \
   UI_BASE_URL=http://127.0.0.1:5100 \
   UI_PLAYWRIGHT_STORAGE_STATE_PATH=$RUNNER_TEMP/admin_auth.json \
   NAF_VERIFY_DB_PATH=$GITHUB_WORKSPACE/ci-deploy/netcup_filter.db \
   PLAYWRIGHT_HEADLESS=true \
   python -m pytest -o addopts="" --timeout=120 -m ci_smoke ui_tests/tests -v
   ```
7. `if: failure()` — upload artifacts: gunicorn log, `tmp/ui-screenshots`, a Mailpit message
   dump (`curl $MAILPIT_URL/api/v1/messages`).

Mock netcup is NOT part of the CI set (the chosen tests don't need it); if a marked test
turns out to require it, start it as a background step
(`python -m flask --app ui_tests.mock_netcup_api:app run --port 5555`) — it's dependency-light.

### 4. Branch-test protocol

Verify on a branch: push, watch the job pass; then force a failure (e.g. temporarily mark a
route in EXCLUDE as included with a bogus assertion or break a template locally) to confirm
artifacts upload; revert. Record both run URLs in your summary.

## Acceptance criteria

- [ ] `e2e-smoke` passes on a branch push from a clean checkout (no devcontainer assumptions).
- [ ] Wall-clock for the job ≤ ~10 minutes.
- [ ] Forced-failure run shows screenshots/logs artifacts.
- [ ] Unit job and lint job untouched and still green; `pytest -m "not ci_smoke"` locally is
      unaffected (marker is additive).

## Verify

```bash
cd /workspaces/netcup-api-filter
python -m pytest -o addopts="" --collect-only -m ci_smoke ui_tests/tests | tail -5   # subset collects
# then: push branch, observe Actions runs (pass + forced-fail)
```

## Guardrails (non-negotiable)

- Fail fast in the bootstrap (no cross-environment fallbacks).
- No secrets in the workflow beyond ephemeral CI-local dummies; never echo credentials.
- Don't weaken any test to make CI pass — fix the environment instead.
- Leave changes uncommitted for review unless your operator says otherwise (commit needed
  before push-to-branch verification — coordinate with the operator).
- When done: tick T13 in `docs/plans/testing-overhaul/PLAN.md` + add a worklog line.
