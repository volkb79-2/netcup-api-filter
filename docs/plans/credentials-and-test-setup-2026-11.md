# Credentials, setup and test-environment streamlining (2026-11)

Status: analysis + proposal (read-only review of `main` @ `618e32e`, 2026-11-05). No code changed.
Scope: how credentials are defined, seeded, stored and consumed across build, deploy and both test
suites; root cause of the 2026-11-05 e2e incident; a staged plan to make the setup deterministic.

**TL;DR.** The shipped default admin is fine to ship. What is wrong is that the e2e suite *uses the
shipped admin as its test persona*, changes its password as a side effect of logging in, and keeps
a plaintext copy of the result in `deployment_state_local.json`. The DB and that JSON file are two
sources of truth, synced by test code with no transaction, against a DB that lives across runs.
An interrupted run leaves them out of sync, and DB-persisted login lockout makes that permanent. The fix is
structural: give every e2e session a throwaway DB seeded by one function, use dedicated personas
whose credentials stay in memory, and test the forced password change once, on its own DB.

---

## A. As-is map

| # | Credential | Purpose | Defined | Generated | Read by | Mutated by |
|---|---|---|---|---|---|---|
| 1 | Shipped admin `DEFAULT_ADMIN_*` | first login on a fresh install | `.env.defaults:83-86`, overridable by gitignored `.env` | no (literal default) | build: `seeding.py:133-138` (files only, `require_default`); runtime: `database.py:262-267` (env > files) and `database.py:44-91` (`app-config.toml [[users]]`); state writer `build_deployment.py:396-419` | first login (`admin.py:2886-2899`); tests (see #13) |
| 2 | Demo user `DEFAULT_TEST_CLIENT_ID` / `DEFAULT_TEST_ACCOUNT_PASSWORD` + full-CRUD token | portal + DNS API tests | `.env.defaults:107-129`; code literal fallback `seeding.py:504-507`, `database.py:357-360` | token: `seeding.py:555` | `ui_tests/workflows.py:1167-1168` (via `ui_tests/env_defaults.py`, which reads `.env.defaults` only, not `.env`); token via state file | 2FA/lockout tests |
| 3 | Read-only demo account + token | write-denial tests | `.env.defaults:136-140` | password `seeding.py:606` (random, **recorded nowhere**); token `seeding.py:629` | `ui_tests/config.py:101-120` | — |
| 4 | "Comprehensive" demo accounts | screenshots (`--seed-demo`) | literal password in code, `seeding.py:743` | — | screenshot tooling | — |
| 5 | `app-config.toml [[users]]` | operator preseeding | gitignored `app-config.toml` (has `[[users]]`), `app-config.example.toml` | `password="generate"`: `platform_backends.py:342-345` (**logged in plaintext**) | `passenger_wsgi.py:487-541` → stored as `settings.users_config` **with plaintext passwords** (`:540`); `database.py:44-91` | one-shot import deletes the file, not the settings row |
| 6 | `SECRET_KEY` | session/CSRF signing | env; dev literal in `.env.defaults:156` | per worker `passenger_wsgi.py:75-80`; first writer persists `settings.secret_key` `:635-654` | `app.py:82-103` | `scripts/activate.py:21-42` (tries to carry it over) |
| 7 | Netcup CCP creds | upstream DNS | admin UI / `app-config.toml` / env `NETCUP_*` | — | `passenger_wsgi.py:657-659`, `seeding.py:642-667` | admin UI; e2e tests mutate `netcup_config` |
| 8 | SMTP (`email_config`) | 2FA, invites | admin UI / `app-config.toml [smtp]` | local: `seed_mock_email_config` `seeding.py:411-455` (host from `.env.services` sourced by bash, fallback literal `build_deployment.py:535-538`) | email notifier | `ci_bootstrap_e2e.py` re-seeds it because the build mutated `os.environ` |
| 9 | Telegram bot token / callback secret | linking | `.env.defaults` (placeholder), env | — | `telegram_service.py:92-99` (env only, rejects placeholder: good) | — |
| 10 | PowerDNS API key | platform backend | `.env.operator`, `tooling/backend-powerdns/.env` | operator | ciu stacks, `post_compose_seed_domain.py` (writes into the live app DB) | — |
| 11 | Traefik guard `NAF_GUARD_*` | keep dev ingress private | gitignored `.env.guard` | operator (bcrypt) | traefik label (`tooling/app-local/ciu.compose.yml.j2:73`); **tests**: `ui_tests/playwright_client.py:47-64` (silently empty if unset) | — |
| 12 | Mailpit UI/API auth | mailbox access | `tooling/mailpit/.env` | operator | `MP_UI_AUTH` (`tooling/mailpit/ciu.compose.yml.j2:30`); `ui_tests/mailpit_client.py:219-226`. A literal password sits in its docstring (`:21`) | — |
| 13 | `deployment_state_local.json` | plaintext admin password + demo tokens for tests | `build_deployment.py:356-437` | at build | `ui_tests/config.py:97-120` (import-time singleton `:293`), autouse refresh `ui_tests/conftest.py:26-34` | **5 writers**: `workflows.py:1094`, `workflows.py:1549`, `features/test_password_change_flow.py:192`, `features/test_email_notifications.py:745`, `journeys/j1_fresh_deployment.py:413,564` |
| 14 | `deployment_state_webhosting.json` | same, for the webhoster | written by the old build path (last 2026-07-21) | — | same readers | same writers. **The cmru tarball path never writes it** (`build_webhosting_tarball.py:113-140`), so its tokens never match a released DB |
| 15 | Playwright storage state `tmp/auth-states/*` | reuse admin cookies across tests *and runs* | `deployment_state.py:38-54` | at login | `ui_tests/conftest.py:40-48` | `workflows.py:1125-1135`, `:1245-1254` |
| 16 | Failed-login lockout | brute-force protection | constants `admin.py:77-78` (5 tries / 15 min, not config-driven) | — | `admin.py:141-163` | `admin.py:100-137`, stored **in the DB** via `set_system_config` |
| 17 | Unit-test app | hermetic suite | `tests/conftest.py:31-46` (tmp DB, literal test key) | — | `init_db` → `seed_admin_account` still reads repo `.env`/`.env.defaults` via `config_defaults.load_defaults` | — |

**Seeders (6, with different semantics):** `bootstrap/seeding.py:ensure_admin_account` (build: `email_2fa_enabled=0`,
`must_change_password=1`); `database.py:seed_admin_account` (every `create_app()`: `email_2fa_enabled=1`,
no forced change, recreates a missing admin from env); `database.py:seed_demo_accounts` (`SEED_DEMO_ACCOUNTS`,
token name `demo-token`, **logs the full token** `:426`); `seeding.py:seed_default_entities` (`primary-token`);
`platform_backends.py` `[[users]]`; `scripts/ci_bootstrap_e2e.py` (wraps the build seeder and then fixes
its env side effects).
**Env-file parsers (5):** `build_deployment.py:327-353` (reads `.env` *or* `.env.defaults`, never both, no
quote stripping), `config_defaults.py:12-80` (merges both, strips quotes, looks in module root + cwd),
`ui_tests/env_defaults.py` (`.env.defaults` only), `passenger_wsgi.py:59-70` (`.env.webhosting`, whose writer
`build_deployment.py:440-465` is never called), and `bash source .env.services` (`build_deployment.py:508-528`).
**Dead config:** `global-config.{defaults,active}.toml` (only referenced in docs; no `post-create.sh`
exists), `ui_tests/auth_state.py` (unused; silent `'admin'` fallback at `:56,:64`).

## B. Root causes

### B1. The 2026-11-05 incident: mechanism and evidence

1. `run-gate local-build` (`run-gate.toml:114-121`) seeds `deploy-local/netcup_filter.db` and writes
   `deployment_state_local.json`. The long-lived `app-local` container serves that DB from the bind mount.
   The e2e lane (`run-gate.toml:123-129`) is just `pytest`. Nothing resets the DB between runs.
2. The first test that logs in hits the forced change and **rotates the shipped admin's password in the
   DB**, then copies the new password into the JSON file *afterwards*:
   - `ensure_admin_dashboard`: submit `workflows.py:1081`, then a polling loop that calls
     `browser.text("main h1")` (`:1087`, which throws on pages without `main h1`), then persist at `:1094`.
   - `perform_admin_authentication_flow`: submit `:1507`, then logout, re-login and 2FA, then persist at `:1549`.
     That window is about 40 lines of fallible browser steps.
   - `test_email_notifications.py:739-746` rotates again mid-suite and persists after a fixed 1 s wait
     **without checking that the change succeeded**, so the file can also hold a password the DB never accepted.
   - `j1_fresh_deployment.py:569-570` **swallows** state-write failures.
   - `save_state` writes in place (`deployment_state.py:270-271`), so a kill during the write truncates the JSON.
3. An interruption anywhere in those windows leaves the DB holding a new password while the file says
   `admin` / `password_changed_at: null`. The interruption can be a run-gate budget kill, an exception or Ctrl-C.
   Interruption is by design: `.run-gate/profiles/e2e.jsonl` shows a run started
   02:45:15Z ending `budget_exceeded` at 3601 s (60 m budget), plus three short failed runs, all on the
   01:46 build. The budget was raised to 120 m only afterwards (`618e32e`).
4. From then on every test logs in with the stale password. With `UI_ADMIN_LOGIN_ATTEMPTS=2` (`workflows.py:941`)
   the 5-failure lockout (`admin.py:77-78`) is reached within about 3 tests and **stored in the DB**. So even a
   corrected state file would not help for 15 minutes. Only a rebuild clears both, which is why rebuilding "fixed" it.

I could not see the runner-side lane log, so I can't tell which of the windows in step 2 was hit
(see E). The design produces the observed state from any of them.

### B2. Root design causes (why this will recur)

1. **Two sources of truth for one credential.** The DB holds the bcrypt hash and is authoritative. The JSON holds
   a plaintext copy, kept in sync by five independent test call sites with no atomicity. No ordering of
   those writes is safe, because the DB change is a remote side effect of a browser click.
2. **The shipped admin is the test persona.** 29 of 45 e2e files log in as it. Every test's precondition is "the
   forced-change flow already ran and its result was recorded". So the one flow that is supposed to run once
   per install runs as a hidden side effect of whichever test comes first. And the tests meant to cover it
   (`smoke/test_installation_workflow.py`, `smoke/test_admin_ui.py`) run late, see an already-changed
   password and take the "already initialized" branch (`workflows.py:1453-1457`). The forced-change path
   is effectively **never tested in a full run**.
3. **The e2e environment has no lifecycle.** DB lifetime (local-build lane) and test lifetime (e2e lane) are
   decoupled. DB state from earlier and interrupted runs (passwords, lockouts, created accounts, settings) carries
   into the next run. Cookies in `tmp/auth-states/` carry over too (they date from June; `workflows.py:921-924`
   already works around a stale-cookie case).
4. **No detection, and failures amplify.** The suite can read the DB directly (`ui_tests/verification.py`, a
   read-only channel) but never checks it against the state file. It retries logins, which feeds the DB
   lockout. The result is a timeout flood instead of one clear error.
5. **Shared global paths.** `deployment_state.py:31` and `verification.py:13` hardcode
   `/workspaces/netcup-api-filter`. Every worktree (`.worktrees/`, nyxloom attempts) shares one state
   file, one DB and one cookie jar, which breaks the estate rule that tests never depend on shared state.
   `DEPLOYMENT_TARGET` silently defaults to `local` (`deployment_state.py:178`), and the webhosting URL is a
   literal (`:382`).

### B3. The wider tangle (not the incident, same disease)

- **Secrets in the wrong places:** full demo token logged (`database.py:426`); generated `[[users]]` password
  logged (`platform_backends.py:345`); `[[users]]` plaintext passwords stored permanently in `settings.users_config`
  (`passenger_wsgi.py:540`); `app.py:95` puts the first 20 characters of the dev default key into an exception.
- **The release tarball ships test data.** `build_webhosting_tarball.py:105` seeds `seed_demo_clients_flag=True`
  into every production DB. That means the demo account with the password published in `.env.defaults`, a full-CRUD
  token realm on `example.com`, a read-only account, demo domain roots with a mock API password
  (`seeding.py:1334`) and fake audit logs. The tarball also ships `.env.defaults` (`:132`, never removed),
  which `config_defaults` then reads at runtime on the webhoster.
- **SECRET_KEY handling is two half-mechanisms.** (a) Each gunicorn worker generates its own key
  (`passenger_wsgi.py:75-80`; the log shows 8 "temporary SECRET_KEY" lines per boot), then does
  check-then-set on `settings.secret_key` (`:640-651`). Two workers that both see "absent" end up with
  different keys, which gives random CSRF and session failures under load. This boot was clean (1 persist,
  7 loads); the race depends on timing. (b) `activate.py:32-42` "restores" the key with an `UPDATE`.
  A fresh tarball DB has no `secret_key` row (seeding never creates one), so the update hits zero rows
  and the key silently rotates on every release. That costs little, because the release is greenfield
  and wipes every session anyway. AGENTS.md:57 ("only `SECRET_KEY` carries over") is false today.
- **Each artifact gets a different "default admin".** Tarball: forced change, no 2FA. OCI image
  (`Dockerfile.release`): no DB, so `init_db` seeds from env only, with 2FA on and no forced change, or no
  admin at all if `DEFAULT_ADMIN_*` is unset. Unit tests: the runtime seeder, reading the developer's `.env`.
- **Local e2e differs from CI e2e.** CI runs `create_app()` with `FLASK_ENV=local_test` on a fresh DB
  (`.github/workflows/ci.yml:110-160`); that part is already close to the target. Local runs `passenger_wsgi`
  with no `FLASK_ENV`: production mode, rate limiting on (log: "Rate limiting enabled"), `SESSION_COOKIE_SECURE`
  auto-on. The same suite therefore tests two different apps.
- **Dev-infra guards leak into the test client.** e2e is documented to target the internal
  `http://<app>:5100` (`run-gate.toml:107-112`), which bypasses traefik. Yet `playwright_client.py` carries guard
  credentials, with a silent empty fallback. Mailpit is internal-only (no traefik labels) but still requires
  UI auth, so every test process needs `MAILPIT_*`. Those are not in run-gate `forward_env`; CI simply uses dummies.
- **Rebuilding under a running app is unsafe.** `build_deployment.py:898-900` `rmtree`s `deploy-local/` while
  `app-local` gunicorn has pooled SQLite connections open (`database.py:135-139`, pool_size 10). Old connections
  keep the unlinked inode while new ones open the new file, so requests can mix old and new DB until restart.
  `post_compose_seed_domain.py` (the delegated zone) does not re-run after a rebuild, so DB content depends
  on the order of `ciu up` and the build.

## C. Target design

**Principles.** One seeder per entity. The DB is the only store of account credentials. Test credentials
are generated per session and never written to the repo tree. Each e2e session builds its world from
scratch. Every missing input fails fast with a clear message.

### C1. Single source of truth per class

| Class | SSOT | Notes |
|---|---|---|
| (a) Shipped bootstrap admin | `.env.defaults DEFAULT_ADMIN_*` (a documented non-secret) + **one** function `bootstrap.seeding.seed_bootstrap_admin()` | Used by tarball build, local golden DB, OCI first boot, CI and unit tests. Always `must_change_password=1`, placeholder email, no 2FA until set. `database.seed_admin_account` calls it, or is removed. Tests that need it read the default from `.env.defaults`; nothing stores a rotated value. |
| (b) Per-deploy secrets | `SECRET_KEY`: env if set, else a DB row created race-free (`INSERT OR IGNORE`, then `SELECT`) inside `init_db`, once per DB, so all workers agree. Netcup/SMTP/GeoIP: DB settings via admin UI or one-shot `app-config.toml` import. | Delete `activate.py` key preservation: greenfield releases make it pointless, and today it is a no-op. Delete `.env.webhosting` loading. Never persist `[[users]]` passwords in `settings`; never log generated secrets. |
| (c) Dev-infra guards | `.env.guard` for traefik basicauth: **humans only**. Mailpit: no UI auth (internal-only network) or one forwarded pair. | e2e targets the internal URL, so the test client never needs the guard. If a run targets the public ingress, require the guard explicitly (fail fast, no silent `{}`). |
| (d) Test personas | `ui_tests/personas.py: provision(db_path) -> Personas`, called by the e2e session fixture | Random usernames, passwords, TOTP seeds and tokens per session, held in memory. Built with the product's own seeding helpers (`ensure_account` / `ensure_realm` / `ensure_token`) so the code path is the real one. |
| (e) State files | **Removed** for local. Webhosting: non-secret facts only (base URL, release version) from `.ciu.hosts.toml` / env. | Operator-held webhosting creds come from env (`DEPLOYED_ADMIN_PASSWORD`) for read-only smoke and are never rotated by tests. |

### C2. The e2e environment, created from scratch per session

1. `run-gate local-build` (unchanged builder) produces `deploy-local/` and a **golden** `netcup_filter.db`:
   shipped seed only (bootstrap admin, enums, providers; Mailpit email config for local). No demo personas.
2. A pytest **session fixture** (`ui_tests/e2e_env.py`), running inside the 3.11 runner, does:
   `mkdtemp()` → copy the golden DB → `provision()` personas → start
   `gunicorn passenger_wsgi:application` with cwd `deploy-local/` (same package, same entry point, same
   vendored closure) and `NETCUP_FILTER_DB_PATH=<tmp>/e2e.db`, `FLASK_ENV=local_test`, a random `SECRET_KEY`,
   bound to a free port on the runner (the runner is already on the pwmcp network, `tooling/test-runner/ciu.compose.yml.j2:47-49`).
   It then waits for health, yields `E2EEnv(base_url, db_path, personas)`, and on teardown kills the process
   and removes the tmp dir.
   Cost: a ~250 KB copy plus about 2 s of app start. An interrupted run leaves only an orphaned tmp dir and
   nothing that the next run reads. Parallel worktrees get separate DBs and ports.
   `verification.py` Channel A gets the session DB path from the fixture, not a literal.
3. `app-local` behind traefik stays as the **human** demo/dev surface. It is not part of the gate.
4. CI `e2e-smoke` uses the same fixture (in-process Chromium), and `scripts/ci_bootstrap_e2e.py` goes away.

Simpler alternative to step 2, if starting a server from pytest is unwanted: an e2e lane pre-step that
restores the golden DB into `app-local` with the SQLite online-backup API and restarts the container (the
runner has `docker.sock`). It is more moving parts and still serialises all worktrees on one app, so I
recommend step 2.

### C3. Personas and 2FA

- `e2e-admin`: a separate admin with `must_change_password=0`, email set, and **TOTP enabled with a
  session-generated seed**. Tests compute codes with `pyotp` (already a runtime dependency), so the common
  path has no Mailpit polling and no timing dependence. Email 2FA keeps its own dedicated tests that poll Mailpit.
- `e2e-user` (full-CRUD realm + token), `e2e-readonly` (read-only token), plus per-test throwaway accounts
  from a factory, the e2e analogue of `make_account` / `make_realm` / `make_token`.
- **The shipped admin is touched by exactly one test**, `test_first_login_forced_password_change`, on its own
  function-scoped DB copy. It covers: log in with the default, get forced to change-password, change it,
  check `must_change_password=0` in the DB, log in with the new password, see the old one rejected.
  The new password lives in a local variable.
- Tests that change a password (`test_password_change_flow`, `test_email_notifications`) do it on a
  throwaway persona, never on the session admin.
- Session cookies may be cached per session in the tmp dir, never under `tmp/auth-states/`.

### C4. What the shipped tarball contains

Code + `vendor/` + a DB seeded by `seed_bootstrap_admin()` + enums/providers + default settings. No demo
accounts, tokens, domain roots or audit logs; no `.env.defaults`; no `secret_key` row (created at first boot).
`--seed-demo` stays a local and screenshot option only.
Candid caveat: a greenfield DB with a known default on a **public** webhoster means the first visitor wins
until the operator logs in. If that matters, close it with a small `activate.py` step that sets the bootstrap
password from an operator-held host-side value before touching `restart.txt`. That is optional and does not
change the test design.

### C5. Hermetic vs live suites

- Already hermetic: `tests/` (495 tests). One leak: `init_db` reads the developer's `.env`. Fix it by having the
  `app` fixture point `config_defaults` at `.env.defaults` only, or by setting the admin defaults through env.
- **Could move to `tests/` with the Flask test client** (no browser, no server): the HTTP-only e2e files,
  i.e. `features/test_ddns_protocols.py`, `security/test_api_security.py`, `features/test_bulk_operations.py`,
  `features/test_registration_negative.py`, `roundtrip/test_ddns_quick_update.py` (where they don't need
  pwmcp), plus `mocks/*` self-tests (they test the mocks). That shortens the >60 min lane and makes those
  suites deterministic.
- Live (seeded app + pwmcp): UI journeys, cross-role round-trips, 2FA UI, route smoke.

## D. Staged migration (each stage ships alone, ordered by value/risk)

| Stage | Change | Files | Tests to add | Rollback |
|---|---|---|---|---|
| **S1. Detect, don't flood** (hours) | Session-start guard: read the admin row through Channel A; `bcrypt.checkpw(state password, DB hash)` and the lockout key. On mismatch, `pytest.exit("state/DB diverged — run run-gate local-build")`. Make `save_state` atomic (tmp + `os.replace`). Remove the swallow in j1. In `ensure_admin_dashboard`, only persist after the dashboard is confirmed, and **record the candidate password before submitting** (`pending_password`, resolved offline against the DB hash next time). | `ui_tests/conftest.py`, `ui_tests/deployment_state.py`, `ui_tests/workflows.py`, `ui_tests/tests/journeys/j1_fresh_deployment.py` | unit test for the guard against a tmp SQLite DB (good / diverged / locked) | revert the commit; no product impact |
| **S2. Product: one admin seeder, sane secrets** | `seed_bootstrap_admin()` used by build, `init_db` and the OCI first boot. Race-free `SECRET_KEY` row in `init_db`; drop the per-worker generation in `passenger_wsgi` and the key preservation in `activate.py`. Stop logging tokens/passwords (`database.py:426`, `platform_backends.py:345`, `app.py:95`). Don't store `[[users]]` passwords in `settings`. Remove the literal demo-password fallbacks in code (`seeding.py:506,743`, `database.py:359`). | `bootstrap/seeding.py`, `database.py`, `passenger_wsgi.py`, `app.py`, `platform_backends.py`, `scripts/activate.py` | `tests/`: seeder parity (same flags from every entry point); concurrent `init_db` on one file yields one key; no plaintext secret in `settings` after a TOML import; caplog contains no token | revert; DBs stay compatible (additive) |
| **S3. Per-session e2e environment** | `ui_tests/e2e_env.py` fixture (C2). `UiTestConfig` built from the fixture instead of an import-time singleton. `verification.db_path()` from the fixture. Lane: drop `UI_BASE_URL` / `DEPLOYMENT_TARGET` from `required_env`. Remove the hardcoded `/workspaces/...` paths. | `ui_tests/{conftest,config,verification,e2e_env}.py`, `run-gate.toml` | fixture self-test: two sessions get distinct DBs and ports; killing the run mid-session leaves the next run green | keep the old `deployment_state` path behind `E2E_ENV=legacy` for one release, then delete |
| **S4. Personas replace the shipped admin** | `personas.provision()`, TOTP admin, factories. `ensure_admin_dashboard` stops changing passwords. Delete `_update_deployment_state`, `update_admin_password`, `refresh_credentials` and the autouse refresh. Fold `perform_admin_authentication_flow` into the one dedicated forced-change test. | `ui_tests/{personas,workflows,conftest}.py`, `tests/smoke/test_admin_ui.py`, `smoke/test_installation_workflow.py`, `features/test_password_change_flow.py`, `features/test_email_notifications.py`, `journeys/*` | the dedicated forced-change test; a grep-guard test that no `ui_tests` module writes a password to disk | revert per file; S3 still holds |
| **S5. Clean artifacts** | Tarball and golden DB without demo data; don't ship `.env.defaults`; `build_deployment.py` stops writing `deployment_state_*.json` and `.env.webhosting`, and uses `config_defaults.load_defaults` instead of its own parser. Stop mutating `os.environ` from `.env.services` during seeding (pass the SMTP host explicitly). CI uses the S3 fixture; delete `scripts/ci_bootstrap_e2e.py`. | `scripts/build_webhosting_tarball.py`, `build_deployment.py`, `.github/workflows/ci.yml`, `scripts/ci_bootstrap_e2e.py` | release-artifact test: extracted tarball DB has exactly one account (bootstrap admin, `must_change_password=1`), no `secret_key` row, no `.env*` files | re-enable the flag; release is greenfield anyway |
| **S6. Dev-infra separation + dead code** | Drop Mailpit UI auth or forward it explicitly; guard credentials required only for public-ingress runs. Delete `ui_tests/auth_state.py`, `ui_tests/env_defaults.py`, `global-config.*.toml`, the `passenger_wsgi` `.env.webhosting` loader. Lockout thresholds read from `.env.defaults`. | `tooling/mailpit/*`, `ui_tests/{playwright_client,mailpit_client}.py`, `src/.../api/admin.py` | client fails fast when the public URL is used without guard creds | revert |
| **S7. Webhosting smoke** | `deployment_state_webhosting.json` replaced by env-supplied operator creds plus non-secret facts; webhosting runs are read-only smoke (`UI_ALLOW_WRITES=0`), never rotate the admin. Optional: bootstrap password set at activation (C4). | `ui_tests/config.py`, `scripts/activate.py`, `.ciu.hosts.toml` | smoke profile refuses mutating tests | revert |
| **S8. Shrink the browser lane** | Move the HTTP-only suites to `tests/` (C5). | listed in C5 | the moved tests themselves | keep the originals until the moves are green |

S1 alone prevents a repeat of the incident's symptoms (one clear error instead of a timeout flood). S3 and S4 remove the cause.

## E. Risks and things I could not verify

- **Exact interruption point** of the incident: I did not read the runner-side lane log (`/tmp/run-gate/lanes/e2e/...`
  inside the container) and did not touch containers. An e2e run (started 03:46Z) was in flight during this review.
- **Which base URL local e2e actually uses.** If it is the internal `http://` URL, then `app-local` without
  `FLASK_ENV=local_test` sets `Secure` session cookies over plain HTTP. How local logins succeed today is
  unexplained; the URL may in fact go through traefik over HTTPS.
- **How `MAILPIT_USERNAME/PASSWORD` reach the e2e lane**: they are not in `run-gate.toml forward_env` or the runner env.
- The **SECRET_KEY worker race** and the **unlinked-inode mixing** after a rebuild come from reading the code and
  from SQLite/POSIX semantics, not from a reproduction.
- **Whether pwmcp's gateway** may reach an arbitrary runner port. The runner shares the network, but the
  gateway policy may allow-list targets. If not, C2 needs a fixed, config-driven port or the backup-API alternative.
- `FLASK_ENV=local_test` relaxes cookies, rate limits and notifications. The e2e instance then differs from
  production in those three switches. Keep one small production-mode smoke (rate limit + secure cookie via
  traefik) so the relaxations are not the only thing ever exercised.
- Removing demo data from the tarball changes what an operator sees after a fresh deploy. If anyone relies
  on the demo realm on the webhoster, that is a product decision.

## F. Docs that become wrong (update in the same change as each stage)

- `AGENTS.md:56-58` (key carry-over; "credentials are tracked in `deployment_state_*.json`") and `:60-62`
  (local flow). The "if the state file and DB disagree, rebuild" guidance is no longer in the checked-in
  file but is still in circulation; it goes away with S3/S4.
- `docs/CONFIGURATION_GUIDE.md:47` is already wrong today (`/screenshots/.env.webhosting`).
- `docs/TESTING_LESSONS_LEARNED.md:177` (stale `ensure_admin_dashboard` line ref) and the login/2FA patterns
  (TOTP persona becomes the default; Mailpit only for email-2FA tests).
- `docs/TOML_CONFIGURATION.md` `[[users]]` sections (`:120`, `:195`, `:302`, `:340`, `:383`): generated
  passwords no longer logged; passwords not retained in `settings`.
- `docs/CONFIGURATION_SEEDING.md:20,29` (the state file as "UI test state"; one admin seeder).
- `docs/TESTING_INFRASTRUCTURE.md:157` (CI bootstrap writes the state file) and the lane table.
- `docs/DEPLOYMENT_WORKFLOW.md:60-65` (retain `SECRET_KEY`).
- `docs/DEV_INFRA_SETUP.md` (`.env.guard` used by e2e), `run-gate.toml:105-112` header comment,
  `README.md:29`, `ui_tests/README.md`, and the `.env.defaults:75-80` comment block ("credentials stored in
  `deployment_state_*.json` after password change").
