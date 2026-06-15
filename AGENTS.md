# AGENTS.md — netcup-api-filter

Orientation for AI agents and new contributors. Read this first; follow the links
for depth. Keep it accurate — if you change a workflow, update the relevant section.

## What this is

A Flask application that sits **in front of DNS provider APIs** (netcup CCP, plus
"bring your own backend" services) and exposes a **scoped, audited DNS API** so that
machines can update only the records they're authorized to. It provides:

- A **REST DNS API** and **DDNS endpoints** (DynDNS2 / No-IP compatible) authenticated by Bearer tokens.
- An **account portal** (self-service: realms, tokens, 2FA, notifications) and an **admin UI**.
- Per-account authorization, 2FA, GeoIP checks, and an activity/audit log.

It is deployed to **shared webhosting** (Passenger picks up `passenger_wsgi.py`) and runs
locally with **production parity** (same package, same DB, same entry point).

## Core architecture

**Account → Realms → Tokens.** This is the domain model; internalize it before editing auth/DNS code.

- **Account** — a human who logs into the UI. Has `user_alias` (used in tokens, *not* the username), 2FA, approval state.
- **AccountRealm** — a grant of access to a DNS scope. Fields: `domain` (the zone, e.g. `example.com`) + `realm_type` + `realm_value`.
  - `host` — exact FQDN only (`vpn.example.com`).
  - `subdomain` — apex **and** all children (whole-zone management).
  - `subdomain_only` — children only, not the apex.
- **APIToken** — a machine credential scoped to one realm. Format `naf_<user_alias>_<random>`; only a bcrypt hash + 8-char prefix are stored.

**Authorization** lives in `token_auth.check_permission()`: it verifies the zone
(`realm.matches_domain`), the **hostname scope** (`realm.matches_hostname`), the operation,
and the record type. Changing record-level auth? That's the function to reason about.

**Backends.** Realms resolve either to a platform-**managed domain root**
(`ManagedDomainRoot`, with `DomainRootGrant` controlling who may request realms under
private roots) or to a user's **own backend** (`BackendService`, BYOD).

**Auth surfaces.**
- UI: Flask session + DB-backed `AccountSession` (revocable). See `account_auth.py`.
- API: Bearer token. See `token_auth.py` (`@require_auth`).
- **2FA**: email is **mandatory** for regular accounts; TOTP and Telegram are optional; recovery codes are the fallback. A method is only *offered* if it can actually deliver.

**Entry point.** `src/netcup_api_filter/passenger_wsgi.py` → app factory `create_app()` in `app.py`.

### Source map (`src/netcup_api_filter/`)

| Area | Modules |
|------|---------|
| App / config | `app.py` (factory), `config_defaults.py` (`.env.defaults` loader), `utils.py` (shared helpers) |
| Data | `models.py` (all SQLAlchemy models), `database.py` (init, migrations, settings, seeding) |
| Auth | `account_auth.py` (UI/session/2FA), `token_auth.py` (Bearer + `check_permission`), `recovery_codes.py`, `password_reset.py` |
| DNS | `netcup_client.py` (+ `_mock`), `realm_token_service.py`, `filter_proxy.py` |
| Notifications | `notification_service.py`, `email_notifier.py`, `telegram_service.py` |
| Other | `geoip_service.py`, `bootstrap/seeding.py`, `templates/` |
| Blueprints (`api/`) | `account.py` (portal), `admin.py` (admin UI), `dns_api.py` (REST DNS), `ddns_protocols.py` (DynDNS2/No-IP), `telegram.py` (bot callback) |

Reference docs: [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md), [`docs/ADMIN_GUIDE.md`](docs/ADMIN_GUIDE.md), [`docs/DDNS_PROTOCOLS.md`](docs/DDNS_PROTOCOLS.md), [`docs/TELEGRAM_LINKING.md`](docs/TELEGRAM_LINKING.md).

## Project conventions (non-negotiable)

1. **Config-driven — no hardcoded values.** Configuration flows `.env.defaults` (version-controlled source of truth) → environment variables (per-environment override) → DB settings (runtime, via admin UI). Don't bake credentials, hosts, ports, timeouts, or cookie flags into code. Read them via `config_defaults.get_default(...)` / `os.environ` / `get_setting(...)`.

2. **Fail-fast — no silent fallbacks.** Never fall back across environments (a missing local config must *fail*, not load production config). In shell, require variables explicitly: `PORT="${PORT:?PORT not set (check .env.defaults)}"`. See [`docs/FAIL_FAST_PRINCIPLE.md`](docs/FAIL_FAST_PRINCIPLE.md).

3. **Reuse shared helpers; don't re-implement.** Before writing a utility, check `utils.py` (`parse_bool`, `sha256_hex`, `generate_token`, `hash_password`) and `netcup_client.py` (`extract_dns_records`, `mutation_failed`, `mutation_message`). Boolean-env parsing, token hashing, and Netcup response-envelope handling already have one home each — keep it that way.

4. **Logging, not `print`.** `logger = logging.getLogger(__name__)`; level from `LOG_LEVEL`. Use f-strings with context (token *prefix*, username, realm) and the right level. **Never log full tokens, passwords, secrets, or chat IDs** — log prefixes/IDs only.

5. **Security expectations** (this is a security boundary):
   - Compare secrets in constant time (`hmac.compare_digest`), never `==`.
   - Audit sensitive actions to `ActivityLog` (grants, linking, auth failures).
   - Enforce scope at the *record* level, not just the zone (see `check_permission`).
   - New POST routes need CSRF (cookie-auth) or a shared-secret/Bearer check (API); new account/admin routes need the auth decorators their siblings use.

## Database & migrations

SQLite + SQLAlchemy. There is **no Alembic**. `init_db()` calls `db.create_all()` (creates
missing *tables*) and then **`run_lightweight_migrations()`** (`database.py`), which adds
**missing columns and indexes** to existing tables so a deployment that keeps its
`netcup_filter.db` across an upgrade doesn't crash with "no such column".

- **Additive, nullable / scalar-default columns and simple indexes migrate automatically.** Just add the column to the model.
- **Anything else** — dropping/renaming columns, type changes, `NOT NULL` without a default, data backfills, new constraints — needs a **hand-written migration**; the lightweight pass will not (and must not) attempt it.

Settings live in the `settings` table via `get_setting`/`set_setting` (JSON-encoded values).

## Build, deploy, run

**`deploy.sh` is the unified deployment script** (local and webhosting). `build_deployment.py`
(+ `build_deployment_lib.sh`) builds the `deploy.zip`; `passenger_wsgi.py` is copied to the
deploy root. Do **not** scp files by hand.

```bash
./deploy.sh                     # local, mocked services (default)
./deploy.sh local --mode live   # local against real services
./deploy.sh local --tests-only  # skip build, just run tests
./deploy.sh local --https       # via the local TLS proxy
./deploy.sh webhosting           # build + upload + restart Passenger
```

Webhosting deploys **reset the database to a fresh preseeded state** (default `admin`/`admin`,
`must_change_password=true`). The Passenger app is reloaded by touching `tmp/restart.txt`.

**Credentials are tracked in `deployment_state_{local,webhosting}.json`**, never hardcoded.
Tests change the default password on first login and persist the generated value there.

```bash
jq -r '.admin.password'             deployment_state_local.json   # current password
jq -r '.admin.password_changed_at'  deployment_state_local.json   # null => fresh (use admin/admin)
```

If the state file and DB disagree, rebuild to a known state (`./deploy.sh local`) rather than
guessing. Never hardcode a password anywhere (code, tests, docs).

The webhosting target (host, remote dir, restart path) is defined by the deployment config /
`deploy.sh` — read it there rather than copying literals around.

## Testing

Two distinct layers:

- **`tests/`** — fast pytest **unit/integration** tests (no browser). Run with `pytest tests/`.
  - `tests/conftest.py` provides `app`/`client`/`db` fixtures and `make_account`/`make_realm`/`make_token` factories. New unit tests should use these rather than building their own fixtures.
- **`ui_tests/`** — **Playwright** end-to-end tests against a running deployment (`ui_tests/tests/`, plus multi-step `ui_tests/tests/journeys/`).

The standard runner builds a production-parity deployment and runs the suite:

```bash
./run-local-tests.sh                       # build + run ui_tests against deploy-local
./run-local-tests.sh --with-mocks          # also start Mailpit / GeoIP / Netcup-API mocks
./run-local-tests.sh --skip-build          # reuse existing deploy-local
./run-local-tests.sh --with-mocks ui_tests/tests/security/   # a subset
```

Playwright runs in-process by default.  To offload to an external
Playwright-as-a-Service container, set `PLAYWRIGHT_SERVER_WS`:

```bash
export PLAYWRIGHT_SERVER_WS=ws://<service-name>:3000/
pytest ui_tests/tests -v
```

**Route-smoke suite (`ui_tests/tests/smoke/test_route_smoke.py`)**: parametrized over every app
route discovered at import time — 86 tests, automatically cover new routes as they are added.
Contributors get smoke coverage for free; they must still add round-trip tests that assert
backend state changes for any new behavior (smoke only checks status codes and basic page
loading).

**CI `e2e-smoke` job** (`.github/workflows/ci.yml`): boots the app on the GitHub Actions
runner, seeds a fresh DB via `scripts/ci_bootstrap_e2e.py`, and runs all tests tagged
`@pytest.mark.ci_smoke` (102 tests). This gives PRs E2E regression coverage without needing a
full Playwright container. Tag new tests `ci_smoke` when they are fast, hermetic, and do not
require external services beyond Mailpit.

**Before writing any Playwright login / 2FA / navigation test, read
[`docs/TESTING_LESSONS_LEARNED.md`](docs/TESTING_LESSONS_LEARNED.md)** — it documents the
patterns (JS `form.submit()` for 2FA, live `browser._page.url`, verification channels,
`wait_for` poller) that prevent most flakiness.

**Test hygiene:** a test that can't fail is worse than no test. Don't downgrade a load-bearing
`assert` to `pytest.skip` to make a suite green — skip only when a feature is genuinely
disabled by config, and gate the skip on that specific condition. Restore/clean any global
state (e.g. the admin `netcup_config`) you mutate.

## Local environment

- **Dynamic FQDN.** The public hostname is auto-detected (reverse DNS) into `.env.workspace` as `PUBLIC_FQDN`. Never hardcode a hostname; `source .env.workspace` in scripts. See [`docs/FQDN_DETECTION.md`](docs/FQDN_DETECTION.md).
- **Config files (by scope):** `.env.defaults` (project defaults) → `.env.workspace` (auto-generated, environment-specific) → `.env.services` (service hostnames/URLs) → `tooling/<service>/.env` (per-service).
- **HTTPS parity** via the nginx TLS proxy in `tooling/reverse-proxy/` (real Let's Encrypt certs). The proxy container reads certs from the host `/etc/letsencrypt`; the **devcontainer cannot** see them directly (security isolation) — verify cert problems from the nginx container logs, not with `ls` in the devcontainer. See the folder README.
- **Mock services** for offline/deterministic runs — all named with the `naf-` prefix:

  | Container | Tooling dir | Purpose |
  |-----------|-------------|---------|
  | `naf-mailpit` | `tooling/mailpit/` | SMTP capture ([`docs/MAILPIT_CONFIGURATION.md`](docs/MAILPIT_CONFIGURATION.md)) |
  | `naf-mock-geoip` | `tooling/geoip-mock/` | GeoIP API mock |
  | `naf-mock-netcup-api` | `tooling/netcup-api-mock/` | Netcup CCP API mock |
  | `naf-reverse-proxy` | `tooling/reverse-proxy/` | Local TLS proxy |

- **Python**: the devcontainer installs dependencies for the `vscode` user directly (no project `venv` by design). Runtime deps: `requirements.webhosting.txt`; dev/test: `requirements-dev.txt`. See [`PYTHON_PACKAGES.md`](PYTHON_PACKAGES.md).
- **`/deploy`, `/deploy-local`, `/deploy-webhosting`** are generated (gitignored) staging trees — don't edit them by hand; they're rebuilt from `src/`.
- **FUSE/sshfs** for remote file access is available (host provides `/dev/fuse`); use `sshfs` from the devcontainer, never install `fuse` inside it.

## Documentation

[`docs/README.md`](docs/README.md) is the index of living guides; [`docs/FEATURES.md`](docs/FEATURES.md)
is the canonical capability + roadmap map. Superseded write-ups live in `docs/deprecated/` —
don't treat them as current or update them. Must-reads by task: **capabilities/roadmap** →
[`docs/FEATURES.md`](docs/FEATURES.md); **security/auth** → [`docs/SECURITY.md`](docs/SECURITY.md);
**API/DDNS** → [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md), [`docs/DDNS_PROTOCOLS.md`](docs/DDNS_PROTOCOLS.md);
**config/seeding** → [`docs/TOML_CONFIGURATION.md`](docs/TOML_CONFIGURATION.md);
**deploy** → [`docs/DEPLOYMENT_WORKFLOW.md`](docs/DEPLOYMENT_WORKFLOW.md);
**UI tests** → [`docs/TESTING_LESSONS_LEARNED.md`](docs/TESTING_LESSONS_LEARNED.md).

### Keep the canonical docs in sync (definition of done)

A change is not done until its docs match the code **in the same change**. Before finishing:

- **New/changed/removed capability** → update [`docs/FEATURES.md`](docs/FEATURES.md) (and move
  the item out of the roadmap table if you just shipped it) **and** [`../CHANGELOG.md`](../CHANGELOG.md).
- **Auth / 2FA / rate-limit / secrets** → [`docs/SECURITY.md`](docs/SECURITY.md) (incl. its
  "Not yet implemented" list — keep it honest).
- **API/DDNS endpoint, param, or response shape** → [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md) / [`docs/DDNS_PROTOCOLS.md`](docs/DDNS_PROTOCOLS.md).
- **New `.env.defaults` key or config behaviour** → [`docs/CONFIGURATION_GUIDE.md`](docs/CONFIGURATION_GUIDE.md) / [`docs/TOML_CONFIGURATION.md`](docs/TOML_CONFIGURATION.md).
- **Deploy/ops flow or script flags** → [`docs/DEPLOYMENT_WORKFLOW.md`](docs/DEPLOYMENT_WORKFLOW.md).
- **Test suite structure, type, or count change** → update [`docs/TESTING_INFRASTRUCTURE.md`](docs/TESTING_INFRASTRUCTURE.md) (table row + counts) **and** the suite-type table in the `README.md` Testing section.

Rules: don't invent doc claims the code doesn't back; if you find a doc describing something
that isn't implemented, either fix the doc or move it to the roadmap — never leave an
aspirational claim stated as current. Don't create new top-level Markdown files; extend an
existing canonical guide and link it from [`docs/README.md`](docs/README.md). Retire stale
write-ups to `docs/deprecated/` rather than deleting context.

## Running shell commands (VS Code Copilot)

To keep terminal commands auto-approvable, this repo funnels execution through a single
whitelisted script. Set the intent/command in **`.vscode/copilot-plan.sh`**
(`COPILOT_PLAN`, `COPILOT_EXEC`) and run **`bash ./.vscode/copilot-cmd.sh`** — it prints a
`[PLAN]`/`[EXEC]` line then runs the command from the repo root. Avoid compound one-liners
(`cd … && X=… cmd`) and **never put secrets on the command line** (export them or read them
inside the script). The two script files contain the full template.
