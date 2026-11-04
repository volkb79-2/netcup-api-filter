# AGENTS.md — netcup-api-filter (naf)

naf's delta on top of the estate rules. **Read vbpub's `AGENTS.md` first**
(`/workspaces/vbpub/AGENTS.md`): cockpit doctrine, defaults-are-hazards, worktrees,
cgroup placement, supported-workflow rule, exit-status rule. Nothing from it is repeated here.
Current state, gate status and handoffs: [`nyxloom-trove/STATE.md`](nyxloom-trove/STATE.md).

**Hand-started (not nyxloomd-dispatched)?** Before work, read `nyxloom-trove/README.md`,
`nyxloom-trove/STATE.md`, every `nyxloom-trove/*.md` sibling of a canonical doc, and the
canonical doctrine in vbpub `nyxloom/reference/{AUTHORING,STANDARD,DOCTRINE}.md`. The sibling
refines the canonical file, never replaces it; keep siblings to the delta.

## What this is

A Flask app in front of DNS provider APIs (netcup CCP, plus bring-your-own backends) that exposes
a **scoped, audited DNS API**: REST + DDNS (DynDNS2/No-IP) via Bearer tokens, an account portal
and an admin UI, with 2FA, GeoIP checks and an activity log. Deployed to shared webhosting
(Passenger → `src/netcup_api_filter/passenger_wsgi.py` → `create_app()` in `app.py`) and as a
container.

## Domain model (internalize before touching auth/DNS code)

**Account → Realms → Tokens.**

- **Account** — a human with UI login. `user_alias` (used in tokens, not the username), 2FA, approval state.
- **AccountRealm** — grant of a DNS scope: `domain` + `realm_type` + `realm_value`.
  `host` = exact FQDN; `subdomain` = apex and all children; `subdomain_only` = children only.
- **APIToken** — machine credential scoped to one realm, `naf_<user_alias>_<random>`; only a bcrypt hash and 8-char prefix are stored.
- **Backends** — a realm resolves to a platform `ManagedDomainRoot` (`DomainRootGrant` gates private roots) or a user's own `BackendService`.
- **Authorization** is `token_auth.check_permission()`: zone, hostname scope, operation, record type. Reason about that function for any record-level change.
- **2FA** — email mandatory for regular accounts; TOTP/Telegram optional; recovery codes are the fallback. A method is offered only if it can deliver.

Module map: read `src/netcup_api_filter/` (blueprints in `api/`). Reference docs: [`docs/README.md`](docs/README.md).

## Conventions (non-negotiable)

1. **Config-driven.** `.env.defaults` → environment → DB settings (`get_setting`). No hardcoded credentials, hosts, ports, timeouts or cookie flags. Fail fast, never fall back across environments ([`docs/FAIL_FAST_PRINCIPLE.md`](docs/FAIL_FAST_PRINCIPLE.md)); shell: `PORT="${PORT:?...}"`.
2. **Reuse helpers** — `utils.py` (`parse_bool`, `sha256_hex`, `generate_token`, `hash_password`), `netcup_client.py` (`extract_dns_records`, `mutation_failed`, `mutation_message`).
3. **Logging, not `print`.** `logging.getLogger(__name__)`, f-strings with context. Never log full tokens, passwords, secrets or chat IDs; prefixes/IDs only.
4. **Security boundary.** `hmac.compare_digest` for secrets; audit sensitive actions to `ActivityLog`; enforce scope per record, not just per zone; new POST routes need CSRF (cookie auth) or Bearer/shared-secret (API) and the auth decorators their siblings use.
5. **Database.** SQLite, no Alembic. `init_db()` → `create_all()` + `run_lightweight_migrations()` adds missing nullable/scalar-default columns and simple indexes. Drops, renames, type changes, NOT NULL without default, backfills, new constraints need a hand-written migration.
6. **Python floor.** Webhosting variants run **3.9 and 3.11**; the OCI image is 3.14. No 3.10+ syntax or cp314-only deps in shipped code.

## Run, test, release — never in the cockpit

The devcontainer only inspects and drives. **App and test execution happen in containers**, through
the supported verbs:

| Concern | Verb |
|---|---|
| Gate (unit per Python version, trove, e2e) | `run-gate <lane>` |
| Local app, mocks, pwmcp | `ciu` stacks (`tooling/*/`) |
| Release (OCI image + Passenger tarballs, `scm` version) | `cmru release` |
| Deploy to webhoster | `ciu up --host webhoster --thin -- --variant py311` |

Webhoster inventory, pinned host key and activation contract: `.ciu.hosts.toml`. Webhosting releases are
greenfield (fresh seeded DB, default `admin`/`admin`, `must_change_password`); only `SECRET_KEY` carries over.
Credentials are tracked in `deployment_state_*.json` (never hardcode a password); browser tests use pwmcp via
`PLAYWRIGHT_SERVER_WS`, never an engine installed here.

> **Migration pending** (trove backlog): the gate is still `tooling/test-runner/testing-exec.sh` and
> `nyxloom-trove/nyxloom.toml` `[gates.*]`; `run-local-tests.sh` / `build_deployment.py --local` still build
> and drive `deploy-local/` from the cockpit. They are being replaced by `run-gate.toml` lanes and ciu stacks;
> until then they are the only available gate, not the target.

**Testing:** `tests/` (pytest unit/integration; use the `make_account`/`make_realm`/`make_token` fixtures in
`tests/conftest.py`) and `ui_tests/` (Playwright; read [`docs/TESTING_LESSONS_LEARNED.md`](docs/TESTING_LESSONS_LEARNED.md)
before writing login/2FA/navigation tests). Layout and counts: [`docs/TESTING_INFRASTRUCTURE.md`](docs/TESTING_INFRASTRUCTURE.md).
A test that can't fail is worse than none: never downgrade a load-bearing `assert` to `skip`; skip only on a
specific config condition. Restore global state you mutate.

## Local environment

Public hostname is auto-detected into `.env.workspace` (`PUBLIC_FQDN`); never hardcode one
([`docs/FQDN_DETECTION.md`](docs/FQDN_DETECTION.md)). Config layers: `.env.defaults` → `.env.workspace` →
`.env.services` → `tooling/<service>/.env`. HTTPS comes from the host `edge-traefik`; naf holds no TLS material
([`docs/DEV_INFRA_SETUP.md`](docs/DEV_INFRA_SETUP.md)). Mock services (`naf-` prefix: mailpit, geoip, netcup-api, app-local) each have a ciu stack under `tooling/<name>/`.
`deploy*/` trees are generated and gitignored. Python deps: `requirements.webhosting.txt` (runtime),
`requirements-dev.txt`; see [`PYTHON_PACKAGES.md`](PYTHON_PACKAGES.md).

## Docs are part of the change

A change is done only when its docs match the code in the same change: [`docs/FEATURES.md`](docs/FEATURES.md) +
[`CHANGELOG.md`](CHANGELOG.md) for capabilities, [`docs/SECURITY.md`](docs/SECURITY.md) for auth/2FA/secrets
(keep "Not yet implemented" honest). Other areas: find the guide via [`docs/README.md`](docs/README.md).
Never state an aspiration as current; no new top-level Markdown files; retire stale write-ups to `docs/deprecated/`.
