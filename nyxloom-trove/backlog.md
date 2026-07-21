# Backlog — un-carved ideas

Everything from the deep review (`docs/deprecated/FOLLOWUP_REVIEW_2026-07-16.md`, declared in
`nyxloom.toml [refs]`) that is **not yet a handoff**. Each entry is specific enough that
carving is mechanical: the file:line and the intended change are already named.

Carve order is roughly top-down. `nyxloom.toml` sets `ready_queue_target = 5` /
`max_active_tasks = 3`, so this is deliberately a queue, not a dump — carve as slots free.

**Already landed (not backlog, for orientation):** the Telegram bot-token/chat-id log
leak (P0-6), `generate_code` → `secrets`, `hmac.compare_digest` on 2FA/registration
codes, four dead imports, a duplicate `return True`, and a `\d` SyntaxWarning were fixed
directly in commit `3fd6357` and validated in the gate (373 passed on python 3.11).

---

## B-AUTH — auth hardening (review §P1-C)

- **TOTP has no lockout.** `account_auth.py:585` — the TOTP branch of `verify_2fa` never
  calls `increment_2fa_failures`, so `method=totp` retries indefinitely. The
  email/telegram branch and the admin path (`admin.py:624`) both count. Mirror them. S.
- **Reset/invite bypass the password policy.** `api/account.py:220,258` gate only on
  `len(new_password) < 12` (a hardcoded literal); `password_reset.py:236`
  (`complete_password_reset`) validates nothing. Every other path uses
  `validate_password()` (min 20 + 100 bits entropy, env-configurable). S.
- **X-Forwarded-For spoofing defeats IP allowlists.** `admin.py:90` (`_get_client_ip`)
  and `ddns_protocols.py:62` (`get_client_ip`) take the **leftmost** XFF value, which is
  client-controlled behind `$proxy_add_x_forwarded_for`. These feed the admin IP
  whitelist, admin session IP-binding, and the token IP allowlist. `dns_api.py` already
  does it right (`request.remote_addr`, ProxyFix-normalized). S.
- **Dead second reset path.** `account_auth.py:848` `request_password_reset` (plaintext
  6-digit code onto the Account row, `random`-generated) has no callers; the live flow is
  the `ResetToken` model. Its columns `models.py:323-324` are written nowhere else.
  Removing the function is S; dropping the columns needs a hand-written migration. S-M.
- **`generate_secure_password`** (`account_auth.py:121`) — imported in `admin.py:31`,
  never called, and uses `random.choices`. Remove or fix. S.

## B-PORTAL — portal & notifications (review §P1-A; the user's top priority)

- **Notification preferences are stored but never honored.** The settings UI persists
  `notify_new_ip`, `notify_failed_auth`, `notify_token_expiring`, `notification_email`
  (`api/account.py:787`, `models.py:305`), but no sender in `notification_service.py`
  reads them: `notify_failed_login` emails unconditionally, every sender uses
  `account.email` (never `notification_email`), and `notify_new_ip_login` /
  `notify_token_expiring` have **zero callers** — two advertised alerts that never fire.
  **Carve this first**; the features below sit on it. M.
- **Token usage analytics.** `realm_detail` already tries to compute per-token stats from
  `ActivityLog` and crashes doing it (naf-P03 fixes the crash). Turn that into a real
  view: last-used, call count, denied count, source IPs — the data already exists in
  `ActivityLog`. Highest-leverage portal feature. Depends on naf-P03. M.
- **Webhook notification channel.** A `webhook` delivery alongside email/telegram, gated
  by the (repaired) preference plumbing. Depends on the preferences item. M.
- **Self-service 2FA-lockout unlock + status view.** Lockout and lockout notifications
  exist; user-driven unlock does not. M.
- **Background dispatch for the remaining `notify_*` paths.** Verification, 2FA, and
  reset emails call the private `notifier._send_email_sync()` on the request thread with
  a hardcoded 30s SMTP timeout (`notification_service.py:300,431,638`), so login and
  registration POSTs can hang 30s on a slow relay. Reuse the existing
  `ThreadPoolExecutor`. DNS/DDNS hot paths are already clean. M.
- **Security alert stub.** `token_auth.py:507` `_trigger_security_notification` only
  logs — the `send_security_alert` call is commented out — while
  `docs/SECURITY_ERROR_TAXONOMY.md` documents user emails for brute-force / `ip_denied` /
  `token_revoked` as current. Implement it, or move the claim to "not yet implemented".
  `notification_service.py:2230` `send_security_alert_email` (~170 lines) has zero
  callers and is the natural body. M.

## B-UI — UI usability & correctness (review §P1-B; user priority)

- **Two known-broken routes.** `/account/docs` returns 500; `/admin/app-logs` renders a
  traceback. Both are permanently excluded from route-smoke (`test_route_smoke.py:49`)
  as "tracked separately" — with no tracking. Fix, or replace the exclusion with `xfail`
  that flips when repaired. M. *(id: B-ROUTES, referenced by naf-P06)*
- **Read scope leaks the whole zone.** `list_records` (`dns_api.py:105`) checks `'read'`
  without `record_name`, then `filter_dns_records` (`token_auth.py:600`) filters by record
  **type only**. A `host`/`subdomain_only` token reads every record of its types across
  the zone. The account UI's `dns_records` view *does* filter by hostname — so the API is
  more permissive than the UI. Documented as intentional; inconsistent with the
  record-level guarantee AGENTS.md states. M.

## B-DEAD — three parallel DNS stacks (review §P1-E)

Sequence: delete the two dead stacks first, then resolve **D-002** (backends).

- **`filter_proxy.py` (605 lines)** is registered ONLY in `passenger_wsgi.py:85,99`, not
  in `create_app()`, so tests never see it. Its handlers use the old `g.token`/`g.realm`
  and old `check_permission`/`log_activity` signatures. Every route is shadowed by
  `dns_api` **except `GET /api/ddns/<domain>/<hostname>`** — in production that GET
  passes auth then 500s with `AttributeError`. Delete the module + its registration. S.
- **`netcup_client_mock.py` (338 lines)** is imported by nothing, yet `deploy.sh:529` and
  `build_deployment_lib.sh:123` export `MOCK_NETCUP_API=true` as if it switched modes
  (real mocking is via the seeded `api_url`). If that URL points at prod while the flag
  says mock, the app talks to the real API — a silent cross-env fallback. Delete it, the
  second orphan `MockNetcupClient` at `utils.py:403`, and the dead exports. M.
- **`backends/` correctness** (latent until D-002 resolves): `backends/netcup.py:161`
  `delete_record` deletes by *omission* → a silent no-op against the real API that
  reports success (the mock hides it too); `update_record` (~120) falls back to
  hostname+type matching and drops priority `0`; `backends/powerdns.py:97` `create_record`
  uses `REPLACE` with only the new value → **wipes the rest of the RRset**, double-suffixes
  hostnames, drops MX/SRV priority; `registry.py:129` skips schema validation when
  `jsonschema` is missing. S each, but do them together with D-002(a).

## B-DATA — data-layer integrity (review §P1-D; gates D-003)

- **Token deletion erases its own audit trail.** `models.py:611` `APIToken.activity` uses
  `cascade='all, delete-orphan'`, contradicting `ActivityLog.token_id`'s
  `ondelete='SET NULL'` (`models.py:699`). Any ORM token delete wipes history during
  security-sensitive ops. M.
- **SQLite FK enforcement is never on.** No `PRAGMA foreign_keys=ON` anywhere, so every
  `ondelete=` is inert; deleting an Account orphans `AccountSession` rows. Add an engine
  `connect` event, then re-verify deletion flows — interacts with the item above; enable
  deliberately, not casually. M.
- **Plaintext credential logging.** `bootstrap/platform_backends.py:348` logs
  `Generated password for {user}: {password}` into `netcup_filter.log` on the webspace,
  and `docs/TOML_CONFIGURATION.md:430` documents that as the retrieval mechanism;
  `database.py:437` logs a full demo token. Violates AGENTS.md §4. Persist to a
  chmod-600 state file (`deployment_state_*.json` already exists for this). S-M.
- **Lightweight migration omits NOT NULL** even when the model declares `nullable=False`
  with a scalar default (`database.py:238`), so upgraded DBs lack constraints fresh ones
  have. S.

## B-CONFIG — config catalog drift (review §P2)

- **Precedence is inconsistent.** `docs/CONFIGURATION_GUIDE.md:19` says "env > DB >
  defaults"; rate limits, reset expiry, and IP binding implement **DB > env**; demo pages
  implement env > DB; AGENTS.md describes a third order. Pick one, fix outliers, align
  three docs. M.
- **`.env.defaults` catalog gaps.** Read at runtime but absent: `LOG_LEVEL`,
  `MAX_CONTENT_LENGTH`, `SEND_FILE_MAX_AGE_DEFAULT`, `TEMPLATES_AUTO_RELOAD`, `BASE_URL`,
  `PASSWORD_RESET_EXPIRY_HOURS`, `REGISTRATION_VERIFY_EXPIRY_HOURS`,
  `ACCOUNT_INVITE_EXPIRY_HOURS`, `TOKEN_IP_BINDING_ENABLED` (security-relevant),
  `SEED_DEMO_ACCOUNTS`, `DEMO_PAGES_ENABLED`, `NETCUP_*`. Contradicts the file's own
  "single source of truth" header. S.
- **Dead documented env knobs.** `TFA_MAX_ATTEMPTS`, `TFA_LOCKOUT_MINUTES`,
  `RECOVERY_CODE_MAX_ATTEMPTS/_LOCKOUT_MINUTES` are hardcoded at `account_auth.py:60`
  but documented as configurable in `.env.defaults:237`. S.
- **Dead TOML sections.** `[session]`/`[admin]`/`[logging]`/`[notifications]` are
  validated and imported (`passenger_wsgi.py:274+`) into settings keys **no code reads**.
  Worst case: an operator sets `[admin] ip_whitelist/require_2fa` believing hardening is
  on. Wire up or reject at import. M.
- **Invite expiry ignores its DB setting.** `password_reset.py:567` reads only the env
  var while the admin UI seeds/edits/displays `invite_expiry_hours`. S.
- **Startup credential check reads keys nobody writes.** `passenger_wsgi.py:670` checks
  `netcup_customer_id`/`api_key`/`api_password`; config lives in the `netcup_config`
  blob, so DB-configured deploys always log a misleading "not fully configured". S.
- **`app-config.example.toml:100-152`** ships uncommented live-looking operator values
  (`mxe98f.netcup.net`, `dstdns@vxxu.de`, `powerhosts.vxxu.de`) against its own
  "leave commented" instruction. S.

## B-QUALITY — reuse & robustness (review §P2)

- **One `get_netcup_client()` factory.** Reimplemented in `dns_api.py:34` and
  `ddns_protocols.py:199`, inlined 5× in `account.py`; the literal endpoint URL is
  copy-pasted ~10 places instead of coming from config. M.
- **`ddns_update` re-implements envelope handling** (`dns_api.py:555-611`) despite
  importing `extract_dns_records`/`mutation_failed`/`mutation_message` at the top of the
  same file. S.
- **`extract_dns_records` promises to fail loudly** but returns `[]` for a dict without
  the envelope keys (`netcup_client.py:31`). S.
- **`NetcupBackend.finally: logout()`** can turn a successful read into a `BackendError`
  (`netcup_client.py:114`). S.
- **GeoIP:** unauthenticated `GET /api/geoip/<ip>` proxies the paid MaxMind service for
  arbitrary IPs and leaks `str(e)` (`dns_api.py:67`); `get_geoip_status()` reads env
  while `lookup()` prefers DB (status page lies); IPv4-only private-IP check sends IPv6
  loopback/ULA to MaxMind (`geoip_service.py:181`); dead `lru_cache` import + `urllib`
  fallback. S each.
- **Rate limiting:** `except ImportError` silently disables it entirely (`app.py:256`);
  `memory://` storage makes limits per-worker (N× the budget); fallbacks bypass the
  `.env.defaults` catalog. M.
- **`realm_token_service`:** `regenerate_token` (~559) appends a 15-char timestamp and
  then fails `create_token`'s 64-char validation for long names; re-requesting a rejected
  realm doesn't update `domain_root_id`/`user_backend_id`; `create_realm_by_admin` fires
  a spurious `notify_realm_pending`. S each.
- **`notification_service` small items:** lockout email refs aren't in `EMAIL_TYPE_CODES`
  so they degrade to `NAF-GEN-*`; `_get_base_url()` silently falls back to a hardcoded
  `https://naf.example.com`, putting a dead link in every email on an unconfigured
  deploy; `notify_realm_approved` interpolates the raw JSON column instead of
  `get_allowed_record_types()`. S each.
- **Duplicate demo-seeding** implementations with drifted defaults (`database.py:327` vs
  `bootstrap/seeding.py:459`) and two settings writers. M.
- **`bootstrap/seeding.py:368`** `create_default_test_client_options` dereferences the
  `_ENV_DEFAULTS` global instead of `_get_env_defaults()` → `AttributeError`; dead but
  exported. S.
- **`ddns_protocols.py:118` `parse_hostname`** takes the last two labels as the zone, so
  `device.example.co.uk` → `co.uk` and DDNS silently cannot serve ccTLD zones. M.

## B-TESTS — test hygiene beyond naf-P06

- **`pytest.ini`:** drop `-x` from `addopts` (a 400-test run halts at the first failure)
  and scope `--cov` to the unit invocation (it measures nothing for ui_tests, whose app
  runs in another process); add `--strict-markers` so a typo'd bucket marker can't
  silently escape `-m`. Its own carve: it changes every run. S.
- **Dead ui_tests modules:** `auth_state.py` (256 lines, zero importers, a third parallel
  login/2FA impl), `conftest_mock_api.py` (99 lines, zero importers, duplicated by the
  `mock_netcup_api_server` fixture), the legacy "client" fixture/workflow chain
  (`conftest.py:319-349` + four `workflows.py` functions + five `test_admin_*` helpers),
  and the unused `base_url` fixture. S-M.
- **`browser_session` name collision:** a conftest fixture and a `browser.py` async
  context manager share the name with different semantics. S.
- **Hand-rolled fixtures** in `tests/test_telegram_linking.py:25`,
  `test_2fa_security_functional.py:24`, `test_telegram_2fa.py:23` re-implement the
  conftest `app` fixture (omitting its `SEED_DEMO_ACCOUNTS`/`NETCUP_FILTER_APP_ROOT`
  neutralization) and roll private `_create_account()` instead of `make_account`; a
  fixture is also named `test_account`. M.
- **Assert-free tests:** `journeys/test_journey_master.py:133` (print-only summary) and
  `smoke/test_screenshot_capture_and_ux.py:486` (docstring promises a 7-step journey;
  body screenshots 3 public pages with zero assertions). M.
- **`mock_smtp_server` fixture** hardcodes port 1025, colliding with Mailpit; its only
  consumer is its own self-test and it duplicates Mailpit's role. M.

## B-OPS — script rot (review §P2)

- **Delete (dead):** root `Dockerfile` + `docker-compose.yml` (COPY files that don't
  exist; pre-Passenger `filter_proxy` entrypoint), `build_deployment_lib.sh` (unsourced;
  AGENTS.md:89 still cites it; hardcodes SECRET_KEY/port/admin), `run-2fa-tests.sh`
  (targets a moved test file), `tooling/run-ui-validation.sh` (requires a `proxy.env` and
  a `tooling/local_proxy/` that don't exist), `tooling/start-ui-stack.sh` (imports
  `create_app` from `database`, runs a nonexistent `wsgi:app`), `tooling/run-tests.sh`
  (redundant wrapper), `.vscode/deploy-test-fix-loop.sh` (needs the removed Playwright
  container + `./build-and-deploy.sh`).
- **Playwright-container remnants:** `PLAYWRIGHT_CONTAINER.md` says the container is
  removed, but `run-2fa-security-tests.sh:84` still `docker exec`s into
  `naf-dev-playwright` (with a hardcoded personal hostname fallback), and
  `.vscode/ensure-mcp-connection.sh:38` and `.vscode/mcp.json:5` disagree on the MCP URL.
- **`run-local-tests.sh`:** swallows build failures (`| grep … || true`) then extracts a
  stale zip; hardcodes port 5100 despite `LOCAL_FLASK_PORT`; under `set -e` a pytest
  failure skips the Flask-stop cleanup (lines 133-147 are dead) — use a `trap`.
- **`deploy.sh:1133`:** `local exit_code=$?` after a failed `if run_in_playwright…; then`
  always captures 0, so failure logs say "exit code 0" and the FATAL branch is dead.
- **Fail-fast violations:** `deploy.sh:682` `${SERVICE_POWERDNS:-naf-dev-powerdns}`,
  `:1391` hardcoded `naf-dev-reverse-proxy`, `:1437` `${PDNS_AUTH_WEBSERVER_PORT:-8081}`,
  `build_deployment.py:441` `MOCK_SMTP_HOST='naf-dev-mailpit'`, `post-create.sh:74`
  Docker-GID `'118'`, `gunicorn.conf.py:93` `GUNICORN_BIND` defaults to `0.0.0.0:5100`
  and deploy.sh never sets it (so changing `LOCAL_FLASK_PORT` silently breaks the health
  check).
- **`post-create.sh:117`** picks the FIRST container with a `devcontainer.local_folder`
  label — with two devcontainers up (the actual setup) it can write the *sibling* repo's
  host path into `.env.workspace`, corrupting every `${PHYSICAL_REPO_ROOT}` bind.
- **`build_deployment.py`:** `initialize_database` puts the target-version `vendor/`
  (cp311-only `.so`s) first on `sys.path` and imports the app under the **host**
  interpreter (3.14 in the cockpit) with no host-vs-target guard; the sdist-fallback
  warning triggers on the wrong condition; `create_initial_env_webhosting` is dead; four
  listed root docs don't exist; `datetime.utcnow()` is deprecated on 3.12+.
- **`ui_tests/requirements.txt`** is missing `playwright`, `pytest-timeout`,
  `pytest-xdist` that the flows actually use, and `PYTHON_PACKAGES.md:24` falsely claims
  it contains them. Pins also conflict with `requirements-dev.txt` (pytest >=8.3 vs >=9).
- **`tooling/flask-manager.sh`:** exports `DATABASE_PATH`, which the app never reads
  (it's `NETCUP_FILTER_DB_PATH`); defaults to `deploy/` not `deploy-local/`; runs the
  Flask dev server while deploy.sh runs gunicorn — undermining the parity claim.
- **Mock composes** hardcode `naf-dev-*` names despite `.env.services` declaring itself
  the source of truth, and `pip install flask` at every container start (so the
  "offline/deterministic" mocks need PyPI to boot).

## B-DOCS — doc sync (review "Quick wins" 3-10, mostly not yet applied)

- `docs/SECURITY.md:85-88` — two items in "Not yet implemented" ARE implemented
  (DNS/DDNS per-blueprint rate limiting, `app.py:291`; 2FA-lockout notifications,
  `notification_service.py:1233` ← `account_auth.py:1149`). It contradicts FEATURES.md.
  Also `:69` blueprint list and `docs/README.md:38` label.
- `README.md:134,136` — dead links to `docs/OPERATIONS_GUIDE.md` / `docs/CLIENT_USAGE.md`
  (moved to deprecated); the map omits FEATURES.md and SECURITY.md.
- `README.md:18` — "host, subdomain, **wildcard**": no wildcard realm type exists
  (`host`/`subdomain`/`subdomain_only`).
- `docs/README.md` — never links `docs/FEATURES.md` (AGENTS.md calls it canonical); `:63`
  links a deleted `PLAYWRIGHT_MCP_SETUP.md` (also `PARALLEL_SESSION_STRATEGY.md:321`).
- `AGENTS.md:162` — ci_smoke "(102 tests)" vs 93 elsewhere; `:209`
  `[../CHANGELOG.md]` resolves outside the repo; `:134` points at
  `docs/CONTAINER-DOCTRINE.md` / `CONSUMER-AI-GUIDANCE.md`, which live in the base-image
  repo, not here; `:89` still says `build_deployment_lib.sh` is part of the build.
- `docs/RATE_LIMITING.md:59,99-104` — "Known Gap" says DNS/DDNS aren't rate-limited; they
  are.
- `docs/TESTING_INFRASTRUCTURE.md:14,20,24,27` — 355 unit (actual **373**), 450 ui
  (404 collected), ~20 journey (4 collected), 93 ci_smoke vs AGENTS.md's 102.
- `docs/TOML_CONFIGURATION.md` — every multi-line inline-table example is invalid TOML
  (`tomllib` rejects it, verified); `:248` claims a PowerDNS URL fallback that actually
  raises; `:139` lists a `custom` provider that `create_backend_service` rejects.
- `docs/DEPLOYMENT_WORKFLOW.md` — claims Phase 0 starts a Playwright container and
  auto-detects PUBLIC_FQDN (neither implemented); says builds create `deploy.zip` (actual:
  `deploy-local.zip`, `deploy-py39/py311.zip`); documents none of `--failfast/--profile/
  --pytest-workers/--pytest-durations/--skip-journey-tests/--preserve-secret-key/
  --bundle-app-config`.
- `PYTHON_PACKAGES.md:106,162` — contradicts itself on where Playwright lives.
- `AGENTS.md:189` says "no project venv by design"; `post-create.sh:299` creates a
  uv-managed 3.11 `.venv` and `devcontainer.json:61` points VS Code at it;
  `PYTHON_PACKAGES.md` describes a third scheme (pip --user).
- `CHANGELOG.md` — no entry for `dfe4b92` (browser offload) or `f170a7f` (Passenger
  3.9/3.11 builds).
- `.vscode/REVIEW_PROMPT_*.md` (7 files) — one-shot prompts whose reports were all
  retired to `docs/deprecated/`. Retire alongside them, or say why they stay.

## B-INFRA — findings from the ciu/pwmcp adoption (naf-I01/I02, 2026-07-20)

- **The gate never rebuilds on dependency drift.** `tooling/test-runner/testing-exec.sh`
  `ensure_image()` (~:68) builds ONLY `if ! image_present`. So editing
  `requirements.webhosting.txt` / `requirements-dev.txt` leaves the existing image in
  place and the gate silently keeps proving things about a **stale closure** — the exact
  class of false-green the container exists to prevent. (Hit live: adding `playwright` to
  requirements-dev.txt required a manual `docker rmi` before the gate saw it.) Fix: tag the
  image with a hash of the two requirements files (+ the Dockerfile) so a drifted closure
  is a cache miss, or add an explicit `--rebuild` that CI/gates always pass. S-M.
- **ciu resolves to the WRONG REPO from this devcontainer — RESOLVED (partly) via SPEC S1.2.**
  Cause: `~/.bashrc` auto-sources `${REPO_ROOT}/ciu.env` and dstdns is this devcontainer's
  primary workspace, so every shell starts `REPO_ROOT=/workspaces/dstdns`; S1.1 resolves
  `--define-root → $REPO_ROOT → cwd walk-up`, so the stale env beat naf's marker and a bare
  `ciu render` produced **17 dstdns stacks**. Fixed by declaring `standalone_root = true`
  under `[ciu]` in `ciu.global.defaults.toml.j2`, plus the `source ciu.env` workflow.
  (ciu's related **CIU-10**, `PHYSICAL_REPO_ROOT` contamination, is already FIXED upstream —
  hence `env generate` self-correcting via `/proc/self/mountinfo`.)
- **UPSTREAM ciu BUG — `standalone_root` does not guard `ciu render`.** Measured: with
  `REPO_ROOT=/workspaces/dstdns`, `ciu up --dir …` correctly aborts
  (`[S1.2] … Expected: /workspaces/netcup-api-filter, got: /workspaces/dstdns`), but
  `ciu render` still renders all 17 dstdns stacks, rc=0. Reason: `deploy.py:1633` calls
  `detect_standalone_root(repo_root)` on the **already-resolved** root, so it inspects
  dstdns's marker (which has no `standalone_root`) and passes; `engine.py:1033` gets it right
  by walking from `working_dir`. The guard therefore misses precisely the cross-repo
  contamination it exists for. Mitigation here: the mutating path (`up`) IS protected, and
  `source ciu.env` is the documented workflow. **Report to the ciu project** — the one-line
  fix is to pass the working dir, not the resolved root. S.
- **`ciu env generate` derives its own network and creates it.** It produced
  `DOCKER_NETWORK_INTERNAL="netcup-api-filter-7716ce-network"` (repo-path hash) and
  **created that docker network + attached the devcontainer**, which is NOT naf's
  `naf-dev-network`. `ciu.global.defaults.toml.j2` now pins `network_name` explicitly to
  avoid the split, but the stray ciu-created network is unused clutter — decide whether to
  reconcile naf on the ciu-derived name or teach ciu.env the existing one. S.
- **`infra/pwmcp/` is hand-written compose, not a ciu stack.** Valid (`ciu up --shipped`
  supports it, and ciu's own gitignore notes a hand-written compose stays committed), but it
  is the one piece of the adoption not under the `.j2` convention. Templating it
  (`ciu.compose.yml.j2` + `ciu.defaults.toml.j2`) would bring it under governance too. S.
- **Compose project-name collision clobbered dstdns's shared pwmcp (hit live, FIXED).**
  naf's `infra/pwmcp/` and dstdns's `infra/pwmcp/` both default their compose project name
  to the directory basename `pwmcp`, so `docker compose -f infra/pwmcp/docker-compose.yml
  up -d` from naf adopted dstdns's `pwmcp-local-pwmcp` as its own service and **recreated
  then removed it** — taking down shared browser infra. Restored with
  `docker compose -f /workspaces/dstdns/infra/pwmcp/ciu.compose.yml up -d --pull never`.
  Fixed permanently by pinning `name: naf-pwmcp` at the top of naf's compose (committed).
  Lesson: any hand-written compose stack that shares a basename with a sibling repo MUST set
  an explicit `name:`. Also: `pull_policy: always` fails in this devcontainer (the docker
  credential helper errors even on anonymous ghcr pulls), so naf's compose uses `missing`
  (the governed image is already local). ciu templating (item above) would make the project
  name deterministic and remove this footgun. S. **UPDATE 2026-07-21:** the credential-helper
  claim is stale — anonymous ghcr pulls of the PUBLIC image now succeed (config.json carries an
  explicit empty `ghcr.io` auth that bypasses the broken credsStore), so `infra/pwmcp` was moved
  to `pull_policy: always` like every other stack. **Validation strengthened:** beyond the
  co-worker's `http://pwmcp:3000/health`=200 peer check, the gate image (with the pinned
  `playwright==1.61.*` client) was proven to `chromium.connect(ws://pwmcp:3000/)`, drive a
  real Chromium (149.x), set + read page content — the full browser-offload path, live.

## B-INFRA-DOCS — stale reverse-proxy references after naf-I04

naf-I04 deleted `tooling/reverse-proxy/` and the dev nginx TLS edge (app + PowerDNS now go
through the host traefik). These LIVE (non-deprecated) files still describe the removed proxy
and need reconciling with `docs/DEV_INFRA_SETUP.md`: `docs/CERTIFICATE_MOUNTING.md`,
`docs/DEPLOYMENT_WORKFLOW.md`, `docs/FAIL_FAST_PRINCIPLE.md`, `docs/MAILPIT_CONFIGURATION.md`,
`docs/CONFIGURATION_GUIDE.md`, `AGENTS.md`. Also `tooling/run-ui-validation.sh` existed only to
drive the old nginx TLS flow — it now fails fast (its `tooling/reverse-proxy/proxy.env` is gone);
delete it or rewrite it against the traefik/ciu path. S-M.

## B-BUILD — demo-seed double-insert breaks every `--seed-demo` build (✅ FIXED 9d632c5)

**RESOLVED:** `seed_comprehensive_demo_data` now get-or-creates accounts (reuses an existing
username instead of blind-inserting). Validated end-to-end via `testing-exec.sh build 3.11 --
build_deployment.py … --seed-demo` (completes + produces the zip); unit gate 441 on 3.11+3.9.
Original write-up kept below for the record.


`build_deployment.py:486` `seed_default_entities(seed_demo_clients_flag=True)` creates the
`demo-readonly` account (from `.env.defaults` `DEFAULT_READONLY_TEST_CLIENT_ID=demo-readonly`),
then `:495` `seed_comprehensive_demo_data()` (`bootstrap/seeding.py:713`) creates a
`demo-readonly` account AGAIN → `sqlite3.IntegrityError: UNIQUE constraint failed:
accounts.username`. The webhosting build always passes `--seed-demo` (`deploy.sh:800`), so a
fresh `deploy.sh webhosting` (and `deploy.sh local`) **cannot complete DB seeding**.

**Surfaced by INFRA-3** (the containerized build runs seeding to completion in a clean env and
fails loudly). **Confirmed pre-existing**: reproduces identically under host Python 3.14, so it
is NOT an ABI/interpreter issue — the current `deploy-webhosting/` zip predates the collision or
was built without `--seed-demo`. **Fix:** make the two demo-account seed paths reconcile — either
`seed_comprehensive_demo_data` get-or-creates `demo-readonly` instead of inserting, or
`seed_default_entities`'s demo-client seed shouldn't create the account the comprehensive path
owns. Needs a `--seed-demo` build to actually complete afterward (validate in the test container
via `testing-exec.sh build`). Relates to B-QUALITY "duplicate demo-seeding implementations". S-M.
