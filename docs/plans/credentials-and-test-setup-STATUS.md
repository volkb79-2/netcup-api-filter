# Credentials & test setup — implementation STATUS

Plan: [`credentials-and-test-setup-2026-11.md`](credentials-and-test-setup-2026-11.md) (stages S1–S8).
Branch: `cred-integration` (worktree `.worktrees/cred`), based on `main@654aa0e`. Not merged to main and
not pushed. Track branches were merged with `--no-ff`: `cred-s2`, `cred-s3`, `cred-s5`, `cred-s6`,
`cred-s7` and `cred-s8`.

Operator decisions applied:
- Only the Passenger tarball ships an account: `admin`/`admin` with `must_change_password`. There are
  no demo accounts and no `.env.defaults`.
- The OCI image ships no account: first boot needs a bootstrap admin from env or TOML, or it refuses to
  start.
- The SECRET_KEY design is kept.
- e2e uses a per-session throwaway app inside the py311 runner.
- Our containers are ciu projects with idempotent `post_compose` hooks and `GEN_LOCAL` secrets.

## Per-stage status

| Stage | Commit(s) | Done | Broken / deferred |
|---|---|---|---|
| **S1** detect, don't flood | folded into S3 `e711487` | The state file it guarded is gone. The session fixture refuses a missing deploy tree, a non-pristine golden DB (only the shipped admin with `must_change`, no lockout row) and an app that is not ready. It exits once (`pytest.exit`, rc 3) with one message. | — |
| **S2** one init entry point | `2330096` | `bootstrap.init_instance` (CLI `python -m netcup_api_filter.bootstrap init`) is used by the tarball build, the local golden DB, the app start (`init_db`), the app-local `post_compose` hook and, through deploy-local, the e2e golden DB.<br>The OCI image has no default admin: it needs `NAF_BOOTSTRAP_ADMIN_*` (`*_PASSWORD_FILE` preferred) or a TOML admin, otherwise it fails fast.<br>`SECRET_KEY` comes from `SECRET_KEY_FILE`/`SECRET_KEY`, else an `INSERT OR IGNORE` DB row.<br>The TOML `[[users]]`/`[[backends]]`/`[[domain_roots]]` double-decode is fixed.<br>app-local uses `GEN_LOCAL` secrets, a `/data` hostdir and the hook. | The hook is unit-tested only (fake ctx, CIU-176). Its live run is the coordinator's `ciu up --dir tooling/app-local` (below). |
| **S3** per-session e2e app | `e711487` | Each session gets a golden-DB copy (SQLite backup API) and runs gunicorn `passenger_wsgi:application` from the deploy tree on a free port in the py311 runner.<br>`FLASK_ENV=local_test` and `FLASK_SESSION_COOKIE_SECURE=false` are stated explicitly; pwmcp connects to `http://$NAF_E2E_ADVERTISE_HOST:<port>`.<br>The run-gate e2e lane no longer needs `UI_BASE_URL`/`DEPLOYMENT_TARGET`.<br>`deployment_state.py`/`env_defaults.py`/`refresh_credentials` are removed. | The runners must be re-created to get `NAF_E2E_ADVERTISE_HOST`. |
| **S4** personas, one forced-change test | `ccfb70c`, `3d4fe78` | Personas are random and in memory:<br>• `e2e-admin`: TOTP<br>• `e2e-mail-admin`: email 2FA, used by the lockout tests<br>• `e2e-user01`: email 2FA, CRUD realm and token<br>• `e2e-readonly`<br>The shipped admin's forced change is a single test on its own instance; voluntary password changes use a throwaway-admin instance.<br>**Product fix:** portal TOTP login (`/account/login/2fa?method=totp` never recorded the method).<br>Legacy literal test persona inputs were removed. | See "Known breakage": the Mailpit-dependent paths could not be proven green yet. |
| **S5** clean artifacts | `87d4241`, `e46072f` | `.env.defaults` never ships; every shipped tree (tarball, deploy-local, OCI image) carries the generated runtime-only `app-defaults.env`.<br>OCI image: `NETCUP_FILTER_DB_PATH=/data/netcup_filter.db` and `VOLUME /data`.<br>`build_deployment.py` writes no state file or `.env.webhosting` and is ruff-clean.<br>CI `e2e-smoke` uses the session fixture; `scripts/ci_bootstrap_e2e.py` is deleted.<br>Release-artifact test: one account, no `secret_key` row, no `.env*`. | The OCI image was not built (`docker build` not run). The CI workflow has not run on GitHub. |
| **S6** dev-infra separation | `11bda64d` | Mailpit has no UI/API auth; the guard is for humans only; admin lockout is config-driven (`ADMIN_LOGIN_LOCKOUT_*`); dead code is removed. | The running `naf-dev-mailpit` still has auth until it is re-upped (below). |
| **S7** remote smoke | `6ce9ad4` | `NAF_E2E_TARGET=remote` with `NAF_REMOTE_BASE_URL`, `NAF_REMOTE_ADMIN_USERNAME`, `NAF_REMOTE_ADMIN_PASSWORD[_FILE]` and `NAF_REMOTE_ADMIN_TOTP_SECRET[_FILE]`.<br>Read-only (`allow_writes=False`); only `-m remote_smoke` runs, everything else is skipped by an explicit condition. | Never run against the real webhoster. |
| **S8** HTTP suites hermetic | `04a3e36` | The six HTTP-only e2e suites moved to `tests/`. | `ui_tests/tests/mocks/*` stay (they need fixed-port loopback servers or the live DB). |
| **docs (F)** | in each stage, plus `a8f3849` | AGENTS.md, TESTING_INFRASTRUCTURE, TESTING_LESSONS_LEARNED (new §4 Credentials), JOURNEY_CONTRACTS, CONFIGURATION_GUIDE/SEEDING, SECURITY, DEPLOYMENT_WORKFLOW, WEBHOSTING_TESTING_GUIDE, PLAYWRIGHT-TESTING, ui_tests/README, CHANGELOG. | `docs/UI_REQUIREMENTS.md` mock-ups still show `demo-user` (illustrative, left alone). `.vscode/REVIEW_PROMPT_*.md` still mention the state file (stale prompts). |

## Known breakage (at the time of hand-back)

1. **Everything that needs Mailpit fails until Mailpit is re-upped.** The running `naf-dev-mailpit` was started
   with UI/API auth, and the S6 test clients no longer send credentials, so they get a 401.
   - Affected: user-persona logins (email 2FA is mandatory for regular accounts), the email-2FA and lockout tests, the email-notification tests and J2/J3.
   - Measured on the e2e sample (smoke, 2FA security, password change, email notifications, journeys): 131 passed, 39 failed and 21 skipped. Every failure traced to that 401, except two real bugs that are now fixed in `3d4fe78`.
   - The TOTP/admin paths are green: the installation test, admin UI, J1, the password-change flow and the throwaway-admin password-changed path.
   - Fix: coordinator step 1 below, then re-run `run-gate e2e`.
2. **Not executed:** the OCI image build, the GitHub CI job, the app-local hook against real ciu, and the remote smoke against the webhoster.
3. The full browser suite has not been run end to end on the integration HEAD; only the sample above was.
4. The assay R1 coverage lanes were not run. `token_auth`, `account_auth`, `recovery_codes` and `utils` are unchanged by these stages;
   the changed product code is `api/account.py` (covered by `tests/test_portal_totp_login.py`).

Unit results on the integration HEAD: py314 and py311 `tests/` each give **942 passed**. `ui_tests` collects 364 tests.


## How to verify (exact commands)

Unit tests always run in a runner and never in the cockpit. Use `<wt>` = the integration worktree path:

```bash
W=/workspaces/netcup-api-filter/.worktrees/cred
docker exec -w $W naf-dev-test-runner-py311 /opt/tester-venv/bin/python -m pytest tests -q -p no:cacheprovider -o addopts=
docker exec -w $W naf-dev-test-runner-py314 /opt/tester-venv/bin/python -m pytest tests -q -p no:cacheprovider -o addopts=
docker exec -w $W naf-dev-test-runner-py311 /opt/tester-venv/bin/python -m pytest ui_tests/tests --collect-only -q -p no:cacheprovider -o addopts=
```

Focused proofs per stage:

| Stage | Test files |
|---|---|
| S2 | `tests/test_bootstrap_instance.py`, `tests/test_app_local_init_hook.py` (the hook, with a fake ctx; CIU-176) |
| S1/S3 | `tests/test_e2e_env.py` (golden-DB guard, copy isolation, fail-fast settings) |
| S4 | `tests/test_portal_totp_login.py` (product fix) |
| S5 | `tests/test_shipped_defaults.py`, release-artifact test (see S5 row) |
| S6 | `tests/test_admin_login_lockout_config.py` |
| S7 | see S7 row |
| S8 | the moved `tests/test_*_http.py` suites |

## Coordinator: commands to run from main after the merge

Do not run `ciu up` inside a worktree (CIU-176). These commands run in the main checkout after
`cred-integration` has been merged:

```bash
cd /workspaces/netcup-api-filter
set -a; . ./ciu.env; . ./.env.services; set +a      # plus PWMCP_NETWORK (estate pwmcp network_name)

# 1. Mailpit lost its UI auth (S6). First delete MAILPIT_USERNAME / MAILPIT_PASSWORD from
#    tooling/mailpit/.env (gitignored; delete the two lines, do not copy their values anywhere).
ciu up --dir tooling/mailpit

# 2. Re-create the test runners so they get NAF_E2E_ADVERTISE_HOST (their own container name).
ciu up --dir tooling/test-runner

# 3. Build deploy-local/ and its GOLDEN DB (shipped admin only, must_change_password=1).
run-gate local-build --worktree "$PWD"

# 4. e2e: each session starts its own app in the runner; no app-local, UI_BASE_URL or DEPLOYMENT_TARGET.
run-gate e2e --worktree "$PWD"

# 5. app-local is now a ciu-initialized instance: GEN_LOCAL secrets (secret_key,
#    bootstrap_admin_password), its own /data hostdir DB, post_compose hooks
#    (init_instance, then seed_domain). The hook prints the PATH of the admin password file.
ciu up --dir tooling/app-local
```

Expected on step 5: the hook output names `.ciu/secrets/naf/app_local_bootstrap_admin_password`. It
never prints the value. Log in as `admin` with the contents of that file; `must_change_password` is
off for an operator-supplied bootstrap admin. The first `ciu up` creates the DB under the hostdir.
Later runs are idempotent and change nothing: the hook does not pass `--enforce-admin` (an explicit
operator command that would re-apply the username, email and password from the secret and clear a lockout).

Order matters: run step 3 before step 4. The e2e session refuses a missing or non-pristine golden DB
with a single message (exit code 3). If the golden DB was ever served or modified, run step 3 again.

## Decisions taken (recommended defaults; confirm or override)

1. **OCI bootstrap contract.** The admin comes from env (`NAF_BOOTSTRAP_ADMIN_USERNAME`/`_EMAIL`/`_PASSWORD_FILE`, or
   `_PASSWORD`; setting both the value and the file is an error) or from an `app-config.toml` admin.
   - An operator-supplied bootstrap admin gets `must_change_password` **off**: the operator chose that secret.
   - Email 2FA is off until SMTP is configured.
   - Only the tarball's documented `admin`/`admin` is forced to change.
2. **The user persona uses email 2FA only.** Email is mandatory for regular accounts, and
   `test_account_2fa_disable` enables and disables TOTP on that persona. This keeps the user paths
   dependent on Mailpit.
   - Alternative: also give the persona TOTP and log in with TOTP. That needs the 2FA-disable test to use its own persona.
   - Recommended: keep the current design.
3. **Mailpit has no auth** (it is internal-only, a mock). The basicauth guard is for humans; e2e never goes through traefik.
4. **app-local `cookie_secure = "true"`.** It is served over TLS by the host edge. e2e uses its own plain-HTTP instance with
   `FLASK_SESSION_COOKIE_SECURE=false` stated explicitly.
5. **No `--enforce-admin` in the app-local hook (changed by the operator, 2026-11-05).** `ciu up` must not change an
   initialized instance: the hook only initializes what is missing. To rotate the bootstrap credential, `ciu clean` the
   stack's volumes and `up` fresh. `--enforce-admin` remains an explicit operator command of the CLI, used by no hook.
6. **The shipped catalog is an allowlist** (changed by review #5): `config_defaults.RUNTIME_DEFAULT_KEYS`, never a
   credential-like name. `tests/test_shipped_defaults.py` fails if runtime code reads a key the allowlist lacks.
7. **S7 names:** the `NAF_E2E_TARGET=remote` switch, the `NAF_REMOTE_*` variables and the `remote_smoke` marker. The remote admin must
   have a TOTP seed; email-only 2FA on the remote target fails loudly.
8. **Left in place on purpose:** the `.gitignore` entry for `deployment_state_*.json` (it guards old checkouts) and
   `DEPLOYMENT_MODE=live` gating `ui_tests/tests/live/` (it means "real external dependencies", not the remote target).

## Worktrees created (for the coordinator to remove)

`cred` (integration), `cred-s2`, `cred-s3`, `cred-s5`, `cred-s6`, `cred-s7`, `cred-s8` under `.worktrees/`. No stack was
started from any of them. Their `deploy-local/` trees are gitignored build output.

## Review fixes (branch `cred-fixes`, 2026-11-05)

Blind review of the merged S1–S8 (`main@0b020b4`). Fixed on `cred-fixes` (based on `main@697f5a0`), one commit per
finding. Unit tests only (pwmcp slots were in use): the browser paths are for the coordinator to verify from main.

| # | Finding | Commit | Fix | Test |
|---|---|---|---|---|
| 1 | first-boot init raced between gunicorn workers | `aef3f66` | exclusive `fcntl.flock` on `<db>.init.lock` around `init_db` and the bootstrap CLI (`bootstrap/init_lock.py`, `NAF_INIT_LOCK_TIMEOUT_SECONDS`). Chosen over an entrypoint / gunicorn `on_starting`: one mechanism for the OCI image, the ciu stack (incl. the hook's concurrent CLI) and Passenger | `tests/test_init_concurrency.py`: 4 processes boot one fresh DB at once (fails 3/3 without the lock with UNIQUE errors) |
| 2 | "fails fast" untrue; error page rendered `str(e)` | `aef3f66` | `passenger_wsgi` logs and re-raises; no stand-in WSGI app. gunicorn: "Worker failed to boot", master exits non-zero | start without bootstrap config exits non-zero |
| 3 | weak configured bootstrap password accepted; 2FA doc wrong | `9fc1d31` | `validate_password` on configured specs (shipped `admin/admin` exempt). Doc corrected: a configured admin starts without 2FA (banner) and enrolls TOTP; email 2FA is not auto-enabled (broken SMTP would lock out the only admin) | `test_bootstrap_instance.py` |
| 5 | `SECRET_KEY=local-dev-…` shipped; denylist | `8e79e1f` | line deleted; shipped catalog = allowlist `RUNTIME_DEFAULT_KEYS`, credential-like names never ship | `test_shipped_defaults.py` |
| 6 | success reported without an admin; IntegrityError on email | `eadf599` | non-admin/deactivated username or taken email → `BootstrapAdminError`; an initialized DB needs an **active** admin | `test_bootstrap_instance.py` |
| 7 | hook overwrote `email_config` every up | `b03fbd0` | mock email config create-only | `test_bootstrap_instance.py` |
| 8 | e2e lane lost `required_env` | `744a76d` | `required_env = ["PLAYWRIGHT_SERVER_WS"]`; forward_env reviewed (mock URLs reach tests and the session app; `PUBLIC_FQDN` is harmless because `local_test` leaves the cookie domain unset) | `test_run_gate_pointers.py` |
| 9 | bind-mounted `app-config.toml` → EBUSY; CLI ignored TOML | `c896a34` | unclaimable file fails the start with "mount the directory"; CLI resolves the app root like `passenger_wsgi`; image uses `NETCUP_FILTER_APP_ROOT=/config` (#15) | `tests/test_app_config_claim.py` |
| 10 | `finally` commit saved partial `[[users]]` | `d602035` | rollback on any error, plaintext row still purged | `test_bootstrap_instance.py` |
| 11 | old `users_config` plaintext never purged | `76bf459` | `init_instance` purges it every start | `test_bootstrap_instance.py` |
| 12 | stale docs/comments | `72226f3`, `f3fd090` | hook/enforce wording, no hard test counts, README e2e text, `.env.defaults` comment, unused `base_url` fixture removed, historical banners on `.vscode/REVIEW_PROMPT_*.md` | — |
| 14 | conftest not exception-safe; port race; admin/admin on pwmcp net | `f3fd090` | `ExitStack` session fixture; bounded retry on "Address already in use"; `retire_shipped_admin()` in every session DB except `app_instance(keep_shipped_admin=True)` (installation test) | `test_e2e_env.py` |
| 15 | image ran as root; no `.dockerignore` | `d72d170` | user `naf` (10001), `/data` + `/config` writable, log to `/data`; `.dockerignore` allowlist | `tests/test_image_hardening.py` (static) |
| 16 | CI mailpit floating tag | `11da3ca` | `ghcr.io/axllent/mailpit:v1.33.0` (current exact pin; WP8 advanced it) | — |
| 17 | PowerDNS key on `docker exec` argv | `2d72216` | `-e NAME`, value in the hook's env | `tests/test_seed_domain_hook_secret.py` |
| 18 | `_restore_secret` swallowed errors | `e3de4f7` | raises for a non-empty preserved secret (`timezone.utc` kept) | `tests/test_activate_secret.py` |
| 19 | `/account/2fa/resend` unchecked method | `2a3bb6b` | rejected unless offered (`_offered_2fa_methods`) | `test_portal_totp_login.py` |

**Unit results on `cred-fixes`:** py311 `tests/`: 999 passed, R1 coverage token_auth/account_auth/recovery_codes 100%
lines+branches, utils 98%. py314 `tests/`: 981 passed + 18 setup errors in one run made while two other agents' pytest
runs shared the py314 runner; the five affected files (`test_recovery_codes_edge`, `test_registration_negative_http`,
`test_settings_encoding`, `test_token_auth_activity_and_decorator`, `test_token_auth_unit`) re-run on py314: 166 passed.
Not reproduced; re-run the py314 lane on an idle runner to close it.

**Backlog (not fixed, per the brief):** #13 the regex heuristic in `test_shipped_defaults.py` (now also covers the
int-setting helper and `*_KEY` constants, still a heuristic); #17 remainder: `post_compose_seed_domain` falls back to the
cwd DB when `NETCUP_FILTER_DB_PATH` is unset.

**Needs a running stack (coordinator, from main):**
- OCI image: build it (`cmru`/bake), then first boot with and without `NAF_BOOTSTRAP_ADMIN_*` → healthy vs. exit non-zero
  with "Worker failed to boot"; non-root user can write `/data` (named volume) and `/config`.
- `ciu up --dir tooling/app-local` twice: second run changes nothing (admin, `email_config`), hook prints the secret path.
- `run-gate e2e`: lane refuses without `PLAYWRIGHT_SERVER_WS`; installation test still logs in with `admin/admin` on its own
  instance; other sessions reject it.
- CI `e2e-smoke` with the pinned Mailpit image.
- Passenger (webhoster): a failed start shows Passenger's generic page, details only in `netcup_filter.log`.

