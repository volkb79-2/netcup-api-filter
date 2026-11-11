# Follow-up work — deep review (2026-07-16) — ARCHIVED

> **RETIRED 2026-07-16 — do not treat any status here as current.** Its findings were
> carved into the nyxloom trove, which is now the source of truth:
> [`../../nyxloom-trove/handoffs/`](../../nyxloom-trove/handoffs/) (ready work),
> [`../../nyxloom-trove/backlog.md`](../../nyxloom-trove/backlog.md) (un-carved, same
> file:line detail), [`../../nyxloom-trove/decisions.md`](../../nyxloom-trove/decisions.md)
> (open calls), [`../../nyxloom-trove/roadmap.md`](../../nyxloom-trove/roadmap.md).
>
> Kept because a carved handoff is a *contract*, not an argument: this is where the
> reasoning, the evidence, and the rejected alternatives behind each finding live.
> Handoffs cite it in `source.ref` as provenance.
>
> **Already fixed since writing** (so the P0 list below is stale by design): P0-6 (the
> Telegram bot-token/chat-id log leak), P0-4/P0-5 (the phantom `ActivityLog.details`
> column and the undefined `log_activity` — audit writes), and the P1-C code-generation
> and constant-time-compare items. See `git log` for what actually landed.

Source: seven parallel read-only reviews (auth core, HTTP blueprints, DNS/backends/notifications,
app/config/data, build/deploy/tooling, docs & hygiene, test-suite health). CI was out of scope by
request. Every item below was verified by reading the code; the two "app is broken now" clusters
(§P0-4, §P0-5) were reproduced against the actual model/imports.

## How to read this

- **P0** = ship-blocker: a security boundary is bypassable, or a user-facing path 500s today. Do these first.
- **P1** = important correctness/security or a live-vs-dead-code trap that will bite the moment code moves.
- **P2** = quality, consistency, hygiene. Batchable.
- **[LHF]** = low-hanging fruit: mechanical, <15 min, low blast radius. Collected in the "Quick wins" section.
- `file:line` is where to look; effort S/M/L is a rough size for one change.

Priorities you set steer the ordering: **portal & notifications, UI usability + correctness, testing
framework, interesting features**. §P0-4/§P0-5 and §P1-A are exactly the "portal + UI correctness"
bucket, so they lead. The roadmap section at the end concretizes the feature side.

---

## ⚠️ Read before applying anything

This review ran from the **sibling `dstdns` devcontainer**, where `/workspaces/netcup-api-filter`
is mounted **read-only** and flask/pytest aren't installed. Nothing here was applied or test-run.
Apply fixes and run `pytest tests/` from **this repo's own devcontainer** (which you're keeping),
where the tree is writable and deps are present. The "aggressive, validated-by-tests" cleanup you
asked for is safe there and blocked here.

---

## P0 — fix before trusting with real or multi-tenant data

### P0-1 · Record-level DELETE authorization is not enforced (cross-tenant delete)
`api/dns_api.py:423` — `delete_record` calls `check_permission(auth, 'delete', domain, client_ip=...)`
with **no `record_name` and no `record_type`**. `check_permission` only enforces hostname scope when
`record_name is not None` (`token_auth.py:400`), so a token scoped to a single host (or `subdomain_only`)
can delete **any** record ID in the zone — apex NS/MX, another tenant's records on a shared
`ManagedDomainRoot`. The inline comment ("For now, we'll use a generic check") confirms it's known-incomplete.
**Fix:** resolve the record via `info_dns_records`, find it by `record_id`, then re-check
`check_permission` with the record's real `record_name`/`record_type`; reject if the id isn't in-zone.
Effort M. *(Flagged independently by the auth and blueprint reviews.)*

### P0-2 · Account-portal edit/delete mutate records with no hostname-scope check
`api/account.py:1563` (edit) and `:1647` (delete) find the record by `record_id` across the whole zone
and call `netcup.update_dns_records` after only a realm-level `'update'`/`'delete'` op check — never
validating the found record's hostname against `realm.matches_hostname`. Same cross-tenant exposure as
P0-1, via the UI. **Fix:** validate the resolved record's FQDN against realm scope before mutating.
Effort M. *(Also fixes P0-1's UPDATE sibling in `dns_api.py:320`, which validates the request-supplied
hostname rather than the record actually addressed by `record_id`.)*

### P0-3 · Account-portal create only scope-checks `host` realms
`api/account.py:1505` — the guard is `if realm.realm_type == 'host' and hostname != realm.realm_value`.
For `subdomain`/`subdomain_only` realms no hostname validation runs, so a subdomain-scoped realm can
create records outside its subtree (including the apex). **Fix:** use `realm.matches_hostname` for all
realm types. Effort S.

### P0-4 · The account-portal DNS UI 500s / silently mis-reports (phantom `details` column)
`api/account.py` constructs `ActivityLog(details=…)` at **1344, 1359, 1449, 1545, 1628, 1704** and
queries `ActivityLog.details.like(…)` at **1211** — but `ActivityLog` has **no `details` column**
(verified: the real column is `status_reason`, `models.py:715`). Effects, all *after* the netcup
mutation already ran:
- `realm_detail` (1211) → `AttributeError`, page 500s for any realm that has tokens.
- create/edit/delete (1449/1545/1628/1704) → `TypeError`, flash "Failed" **while the change actually
  succeeded** (users retry → duplicate creates).
- DDNS quick-update (1344/1359) → 500.
**Fix:** replace `details=` with `status_reason=` at all six sites; rewrite the 1211 stats query to
join on `token_id` (its action-name filter `('updateDnsRecords',…)` is also dead — real actions are
`api_call`/`ddns_*`/`dns_*`). Effort M; each site is [LHF] individually.

### P0-5 · Admin realm/token revoke raises `NameError` (and writes no audit row)
`api/admin.py:1538` (`realm_revoke`) and `:1595` (`token_revoke`) call `log_activity(...)`, which is
**not defined or imported in `admin.py`** (it lives in `token_auth.py:438`, never imported here —
verified). Both routes commit the revoke *first*, so the destructive action lands, the request 500s,
and **no audit-log row is written** for a sensitive action. **Fix:** write an `ActivityLog(...)` row
with real columns, matching the pattern used elsewhere in `admin.py`. Effort S.

### P0-6 · Bot token + full chat IDs can leak into logs
`telegram_service.py:189` logs the raw exception; a non-2xx response makes `raise_for_status()` raise
an `httpx.HTTPStatusError` whose message embeds the request URL — which contains the bot token
(`.../bot<TOKEN>/sendMessage`). Line 186 also logs the full `chat_id`, which AGENTS.md §4 forbids.
**Fix:** catch `HTTPStatusError` separately, log only the status code; log a chat-id prefix/hash.
Effort S. [LHF]

### P0-7 · Config double-encoding breaks DNS API + invite email on real deployments
Two verified settings-store bugs that only manifest with production (not local-seed) config:
- `passenger_wsgi.py:383` does `set_setting('netcup_config', json.dumps(...))` but `set_setting`
  JSON-encodes again → `get_setting('netcup_config')` returns a **string**; `dns_api.py:38` /
  `ddns_protocols.py:203` then call `.get(...)` on it → `AttributeError` → **500 on every DNS/DDNS
  request** until an admin re-saves config. Same double-encode hits `smtp_config`/`geoip_config`
  (they survive only via defensive `isinstance(str)` guards). **Fix:** drop the redundant `json.dumps`
  at each `set_setting` call in `passenger_wsgi.py`. Effort S.
- `password_reset.py:459,586` read only the `email_config` key, but production writes `smtp_config`
  (admin UI `admin.py:1960`, TOML import `passenger_wsgi.py:246`); only the Mailpit seeder writes
  `email_config`. So `send_account_invite_email` (live at `account_auth.py:987`) silently fails with
  "Email configuration not set" on every real deploy. **Fix:** reuse
  `notification_service._get_smtp_config()` (already handles both keys), as `send_password_reset_email`
  does. Effort S. [LHF]

### P0-8 · Devcontainer post-create drops `PUBLIC_FQDN`, which hard-aborts every `set -u` script
`.devcontainer/post-create.sh` no longer writes `PUBLIC_FQDN`/`PUBLIC_IP` into `.env.workspace`, but
`.env.services:85` unconditionally expands `${PUBLIC_FQDN}` in `POWERDNS_API_URL`. Verified:
`env -i bash -c 'set -euo pipefail; source .env.services'` → **"PUBLIC_FQDN: unbound variable"**. This
kills `deploy.sh` (sourced at line 47, *before* `--help`/`--stop`), `run-local-tests.sh`, and
`start-ui-stack.sh` after any devcontainer rebuild — it only works today because a stale pre-rework
`.env.workspace` survives on disk. Since you're keeping this devcontainer, this is a genuine P0 for the
next rebuild. **Fix:** restore FQDN detection in `post-create.sh` (per `docs/FQDN_DETECTION.md`) and/or
guard the `POWERDNS_API_URL` derivation so mock-only flows don't require a TLS FQDN. Effort M.

---

## P1 — important correctness & security

### P1-A · Portal & notifications (your priority bucket)
- **Notification preferences are stored but never honored.** The account settings UI persists
  `notify_new_ip`, `notify_failed_auth`, `notify_token_expiring`, `notification_email`
  (`api/account.py:787`, `models.py:305`), but no sender in `notification_service.py` reads them:
  `notify_failed_login` emails unconditionally, every sender uses `account.email` (never
  `notification_email`), and `notify_new_ip_login` / `notify_token_expiring` have **no callers at all**
  — two advertised alerts that never fire. **Fix:** gate senders on the preference columns +
  `notification_email`; wire or remove the two orphans (token-expiry needs a scheduler that doesn't
  exist yet). Effort M. *This is the natural seed for the "token usage analytics" and "webhook channel"
  roadmap items — the preference plumbing has to work first.*
- **User security-alert emails are a no-op stub.** `token_auth.py:507` (`_trigger_security_notification`)
  logs but the `send_security_alert` call is commented out, yet `docs/SECURITY_ERROR_TAXONOMY.md`
  documents "Immediate User Notifications (Email)" for brute-force / `ip_denied` / `token_revoked` as
  current behavior. **Fix:** implement the sender, or move the claim to "not yet implemented". Effort M.
- **Login/2FA/reset POSTs can hang up to 30s on a slow relay.** Verification, 2FA, and password-reset
  emails call the private `notifier._send_email_sync()` on the request thread with a hardcoded 30s SMTP
  timeout (`notification_service.py:300,431,638`). DNS/DDNS hot paths are clean. **Fix:** config-driven
  timeout + a public "send now"; background where UX allows. Effort M.

### P1-B · UI usability & correctness (your priority bucket)
- **Two known-broken routes are invisible to the suite.** `/account/docs` returns 500 and
  `/admin/app-logs` renders a traceback; both are permanently excluded from route-smoke
  (`test_route_smoke.py:49`) as "tracked separately" — but no tracking exists. **Fix:** repair the
  endpoints, or replace the exclusion with `xfail` tests that flip green when fixed. Effort M.
- **Read scope leaks the whole zone.** `list_records` (`dns_api.py:105`) checks `'read'` without
  `record_name`, then `filter_dns_records` (`token_auth.py:600`) filters by record **type only** — a
  `host`/`subdomain_only` token can read every record of its types across the zone. The account UI's
  `dns_records` view *does* filter by hostname, so the API is more permissive than the UI. **Fix:**
  filter returned records through `realm.matches_hostname`. Effort M.

### P1-C · Auth hardening
- **Login/2FA codes use non-cryptographic `random`.** `account_auth.py:98` (`generate_code`) uses
  `random.choices` (Mersenne Twister) for account 2FA, admin 2FA, and registration codes — while
  `recovery_codes.py`/`utils.generate_token` correctly use `secrets`. **Fix:** `secrets.choice`.
  Effort S. [LHF]
- **TOTP has no lockout.** `account_auth.py:585` — the TOTP branch of `verify_2fa` never calls
  `increment_2fa_failures`, so `method=totp` can be retried indefinitely (email/telegram branch and the
  admin path both count failures). **Fix:** increment + honor lockout on TOTP mismatch. Effort S.
- **Reset/invite bypass the password policy.** `api/account.py:220,258` gate only on
  `len(new_password) < 12` (hardcoded), and `complete_password_reset` (`password_reset.py:236`)
  validates nothing — every other path uses `validate_password()` (min 20 + 100 bits entropy). **Fix:**
  call `validate_password()` there. Effort S.
- **X-Forwarded-For spoofing defeats IP allowlists.** `admin.py:90` (`_get_client_ip`) and
  `ddns_protocols.py:62` (`get_client_ip`) take the **leftmost** XFF value (client-controlled), feeding
  the admin IP whitelist / session IP-binding and the token IP allowlist respectively. `dns_api.py`
  correctly uses `request.remote_addr` (ProxyFix-normalized). **Fix:** use `request.remote_addr`
  everywhere. Effort S.

### P1-D · Data-layer integrity (gates the "data-preserving upgrades" roadmap item)
- **Token deletion erases its own audit trail.** `models.py:611` — `APIToken.activity` uses
  `cascade='all, delete-orphan'`, contradicting `ActivityLog.token_id`'s `ondelete='SET NULL'`
  (`models.py:699`). Any ORM token delete (`regenerate_user_alias`, realm delete, account delete) wipes
  the audit history precisely during security-sensitive ops. **Fix:** drop `delete-orphan`, null out
  `token_id`. Effort M.
- **SQLite FK enforcement is never on.** No `PRAGMA foreign_keys=ON` anywhere, so every `ondelete=`
  clause is inert; deleting an Account leaves orphaned `AccountSession` rows (no ORM cascade there
  either). **Fix:** add an engine `connect` event issuing the pragma, then re-verify deletion flows —
  interacts with the item above, enable deliberately. Effort M.
- **Generated passwords/tokens logged in plaintext.** `bootstrap/platform_backends.py:348` logs
  `Generated password for {user}: {password}` into `netcup_filter.log` on the webspace (and
  `docs/TOML_CONFIGURATION.md:430` documents this as the retrieval mechanism); `database.py:437` logs a
  full demo token. Violates AGENTS.md §4. **Fix:** persist to a chmod-600 state file (you already have
  `deployment_state_*.json`), log only username + location. Effort S/M.

### P1-E · Dead/parallel code that's a live trap (DNS stack)
The codebase carries **three parallel DNS-client stacks**; the redundancy is actively dangerous:
- **`filter_proxy.py` (605 lines) is registered only in `passenger_wsgi.py`** (not `create_app()`), so
  tests never see it, and its handlers use the *old* `g.token`/`g.realm` and `check_permission`/
  `log_activity` signatures. Every route is shadowed by `dns_api` **except `GET /api/ddns/<domain>/<hostname>`**
  → in production that GET passes auth then 500s with `AttributeError`. **Fix:** delete the module and
  its registration; `dns_api`/`ddns_protocols` already cover the surface. Effort S (delete + smoke).
- **`netcup_client_mock.py` (338 lines) is imported by nothing**, yet `deploy.sh:529` and
  `build_deployment_lib.sh:123` export `MOCK_NETCUP_API=true` as if it switched to mock mode (real
  mocking is via the seeded `api_url`). If that URL ever points at prod while the flag says "mock", the
  app talks to the real API — a silent cross-env fallback. **Fix:** delete the module + the second
  orphan `MockNetcupClient` at `utils.py:403`, remove the dead exports. Effort M.
- **`backends/get_backend_for_realm()` has zero callers.** Both live DNS paths construct `NetcupClient`
  directly from the single global `netcup_config`, so a realm bound to a BYOD/PowerDNS `BackendService`
  passes `check_permission` then executes against the *platform's* Netcup account (BYOD works only for
  `test_connection`/`list_zones` in the UI). Plus `backends/netcup.py:161` `delete_record` "deletes" by
  omission → **silent no-op** against real Netcup, and the mock leaves the record too (a test would
  pass). **Fix (decision):** either wire `dns_api`/`ddns_protocols` through `get_backend_for_realm()`
  (Effort L — this is also the unlock for Cloudflare/Route53), or mark BYOD/PowerDNS not-yet-live in
  `docs/FEATURES.md` and guard realm creation (Effort S). *Sequence: delete the two dead stacks first,
  then decide backends.*

### P1-F · Testing framework (your priority bucket)
- **Route discovery silently shrank the flagship smoke suite.** `route_discovery.py:152` catches all
  exceptions, prints a swallowed warning, and falls back to a stale 21-route list — an unwritable
  `tmp/route_discovery.db` collapsed route-smoke from ~86 to 45 and `ci_smoke` from ~93 to 50, green
  the whole time. **Fix:** re-raise on discovery failure, or assert a route floor
  (`assert len(ADMIN_ROUTES) > 15`) at the top of `test_route_smoke.py`. Effort S.
- **Can-never-fail tests** (AGENTS.md test-hygiene violation): four in `nonfunctional/test_performance.py:179,295`
  and `test_accessibility.py:187,560` downgrade their only failure into `pytest.skip` (strict assert
  commented out at accessibility 190); six "skeleton" `pytest.skip`-only bodies in
  `live/test_live_email_verification.py:350-414`; unconditional skips at
  `features/test_registration_negative.py:398` and `features/test_email_notifications.py:771` (the
  latter leaves a security-notification path untested). **Fix:** restore asserts with thresholds or
  delete. Effort S–M.

---

## P2 — quality, consistency, hygiene (batchable)

**Reuse / duplication (AGENTS.md §3)**
- One shared `get_netcup_client()` factory + config-sourced default URL: it's reimplemented in
  `dns_api.py:34` and `ddns_protocols.py:199`, inlined 5× in `account.py`, and the literal endpoint URL
  is copy-pasted ~10 places. Effort M.
- `dns_api.py:555-611` (`ddns_update`) re-implements envelope handling despite importing
  `extract_dns_records`/`mutation_failed`/`mutation_message` at the top of the same file. Effort S. [LHF]
- Two parallel demo-seeding implementations with drifted defaults (`database.py:327` vs
  `bootstrap/seeding.py:459`) and two settings writers. Effort M.

**Config catalog drift (AGENTS.md §1)**
- Docs claim precedence "env > DB > .env.defaults" (`CONFIGURATION_GUIDE.md:19`) but rate limits, reset
  expiry, and IP binding implement **DB > env** while demo pages implement env > DB. Pick one, fix the
  outliers, align the three docs. Effort M.
- `.env.defaults` is missing runtime keys the code reads: `LOG_LEVEL`, `MAX_CONTENT_LENGTH`,
  `TOKEN_IP_BINDING_ENABLED` (security-relevant), `ACCOUNT_INVITE_EXPIRY_HOURS`, and more — contradicting
  the file's own "single source of truth" header. Effort S.
- Four hardcoded auth constants (`TFA_MAX_ATTEMPTS`, `TFA_LOCKOUT_MINUTES`,
  `RECOVERY_CODE_MAX_ATTEMPTS/…`) at `account_auth.py:60` are documented as env-configurable in
  `.env.defaults:237` but the overrides are dead. Effort S. [LHF]
- TOML `[session]`/`[admin]`/`[logging]`/`[notifications]` sections are validated and imported
  (`passenger_wsgi.py:274+`) into settings keys **no code reads** — worst case an operator sets
  `[admin] ip_whitelist/require_2fa` believing hardening is active. Wire them up or reject at import.
  Effort M.
- `run_lightweight_migrations` omits `NOT NULL` on additive columns even when the model declares
  `nullable=False` with a scalar default → upgraded DBs lack constraints fresh DBs have
  (`database.py:238`). Effort S. [LHF]

**Backends / DNS robustness** (latent until §P1-E backends wiring): `backends/netcup.py` update matches
by hostname+type fallback and drops priority `0`; `backends/powerdns.py:97` create is destructive
(`REPLACE`), double-suffixes hostnames, drops MX/SRV priority; `registry.py:129` skips schema validation
if `jsonschema` missing; `extract_dns_records` returns `[]` instead of raising on a malformed envelope
(`netcup_client.py:31`); `NetcupBackend`'s `finally: logout()` can turn a successful read into a
`BackendError`. Effort S each.

**GeoIP:** unauthenticated `GET /api/geoip/<ip>` proxies the paid MaxMind service for arbitrary IPs
(`dns_api.py:67`) and leaks `str(e)`; `get_geoip_status()` reads env while `lookup()` prefers DB
(status page lies); IPv4-only private-IP check sends IPv6 loopback/ULA to MaxMind
(`geoip_service.py:181`). Effort S each.

**Rate limiting:** `except ImportError` silently disables it entirely (`app.py:256`); `memory://`
storage makes limits per-gunicorn-worker (N× the configured budget); fallback literals bypass the
`.env.defaults` catalog. Effort M.

**Test-suite hygiene:** drop `-x` from `pytest.ini` `addopts` (a 400-test E2E run halts at first
failure) and scope `--cov` to the unit invocation; add `--strict-markers`; delete dead ui_tests modules
(`auth_state.py`, `conftest_mock_api.py`, the legacy "client" fixture/workflow chain,
`base_url` fixture); migrate the three telegram/2FA `tests/` modules to the shared `app`/`make_account`
fixtures; rename the `browser_session` fixture (collides with the `browser.py` context manager); fix
the `\d` SyntaxWarning at `test_validators_unit.py:272`. Effort S each.

**Ops-script rot** (see also §P0-8): delete dead `Dockerfile`/`docker-compose.yml` (reference
non-existent files), `build_deployment_lib.sh` (unsourced; AGENTS.md:89 still cites it),
`run-2fa-tests.sh` (targets a moved test file), `tooling/run-ui-validation.sh` /
`tooling/start-ui-stack.sh` (call functions/paths that don't exist), `.vscode/deploy-test-fix-loop.sh`
and the Playwright-container remnants (`PLAYWRIGHT_CONTAINER.md` says the container is removed, ~4
scripts + `.vscode/mcp.json` still `docker exec` into it); `run-local-tests.sh` swallows build failures
(`| grep … || true`) and hardcodes port 5100; `ui_tests/requirements.txt` is missing `playwright`,
`pytest-timeout`, `pytest-xdist` that the flows actually use. Effort S–M each.

---

## Quick wins — one low-risk pass (validate with `pytest tests/` in the writable container)

**Zero-risk (docs/hygiene, no code behavior change):**
1. `git rm --cached ui_tests/cookies.txt` and add it to `.gitignore` (tracked curl cookie jar).
2. `git mv "State Analysis TODO.md" docs/deprecated/` (Jan snapshot; its five cited reviews already
   moved to `docs/deprecated/`; violates the no-top-level-md rule).
3. `docs/SECURITY.md:85-88` — delete the two now-implemented items from "Not yet implemented" (DNS/DDNS
   per-blueprint rate limiting + 2FA-lockout notifications both exist); fix the blueprint list at :69
   and the `docs/README.md:38` label. (Contradicts `FEATURES.md` today.)
4. `README.md:134,136` — dead links to `docs/OPERATIONS_GUIDE.md`/`docs/CLIENT_USAGE.md` (moved to
   deprecated); add `docs/FEATURES.md` + `docs/SECURITY.md` to the map.
5. `README.md:18` — "host, subdomain, **wildcard**" → there is no wildcard realm type; it's
   `host`/`subdomain`/`subdomain_only`.
6. `docs/README.md` — add the `docs/FEATURES.md` link (AGENTS.md calls it canonical, index omits it);
   drop the dead `PLAYWRIGHT_MCP_SETUP.md` link (`:63`).
7. `AGENTS.md` — ci_smoke "(102 tests)" → 93 to match README/TESTING_INFRASTRUCTURE (recount first);
   `[../CHANGELOG.md]` → `CHANGELOG.md` (resolves outside repo); note that
   `docs/CONTAINER-DOCTRINE.md`/`CONSUMER-AI-GUIDANCE.md` live in the base-image repo, not here.
8. `docs/RATE_LIMITING.md` — delete the "Known Gap" claiming DNS/DDNS aren't rate-limited (they are,
   `app.py:291`).
9. `app-config.example.toml:100-152` — replace live-looking operator values
   (`mxe98f.netcup.net`, `dstdns@vxxu.de`, and the legacy hardcoded DDNS domain) with `example.com` placeholders and
   re-comment the blocks.
10. `CHANGELOG.md` — add an Unreleased entry for the browser-offload and Passenger 3.9/3.11 build
    commits.

**Low-risk code (each needs a `pytest tests/` run to confirm green):**
11. `dns_api.py:18-26` + `ddns_protocols.py:31` — remove unused imports (`authenticate_token`,
    `extract_bearer_token`, `validate_dns_records_update`).
12. `notification_service.py:302` — delete the duplicated `return True`.
13. `test_validators_unit.py:272` — make the `\d` docstring a raw string.
14. `account_auth.py:98` (`generate_code`) — `random.choices` → `secrets.choice` (also §P1-C).
15. `account_auth.py:620` / `verify_registration:251` / `admin.py:656` — `==`/`!=` on 2FA/verification
    codes → `hmac.compare_digest` (AGENTS.md §5).
16. The six `ActivityLog(details=…)` → `status_reason=` sites (§P0-4) — mechanical, but re-run the
    account-portal DNS flows after (that's the actual bug, not just cleanup).

Items 1–10 are pure hygiene; 11–16 change behavior and are the reason the writable container + test run
matters. Suggested commit chunking (your "logical chunks on main" choice): (a) repo hygiene 1–2;
(b) doc sync 3–10; (c) safe code cleanup 11–13; (d) auth hardening 14–15; (e) the P0 portal fix 16 as
its own commit with a note that it needs a portal smoke-run.

---

## Roadmap concretization (aligned to your priorities)

Turning the `docs/FEATURES.md` roadmap into ordered, dependency-aware work. **Bold = prerequisite that's
actually a bug above**, so you get correctness and a feature in the same change.

**Portal & notifications** (your top pick)
1. **Fix the notification-preference plumbing (§P1-A)** — without it, every notification feature below
   ships on a broken base. Gate senders on the preference columns + `notification_email`.
2. **Token usage analytics** — the account portal's own `realm_detail` already *tries* to compute
   per-token stats from `ActivityLog` (and crashes doing it, §P0-4). Fix that query into a real
   per-token activity view: last-used, call count, denied count, source IPs — all already in
   `ActivityLog`. This is the highest-leverage portal feature; the data exists.
3. **Webhook notification channel** — add a `webhook` delivery alongside email/telegram in
   `notification_service`, driven by the same (now-working) preference gate. Depends on 1.
4. **Self-service 2FA-lockout unlock** — lockout + lockout notifications exist; add a user-facing unlock
   (email-link or recovery-code gated) and a lockout-status view. Independent, medium.
5. **Background dispatch for remaining `notify_*` paths** — reuse the existing `ThreadPoolExecutor`;
   folds in the §P1-A "30s request hang" fix.

**UI usability & correctness** (your pick)
- Ship §P0-2/§P0-3/§P0-4 and §P1-B first — the portal DNS UI is the surface here and it's partly broken.
- Then a focused pass on the account portal's DNS-record management UX once it's correct.

**Testing framework** (your pick)
- §P1-F (route-discovery floor, kill can-never-fail tests) + the P2 test-hygiene batch, then recount and
  sync `docs/TESTING_INFRASTRUCTURE.md` / README / AGENTS.md in one commit (counts currently disagree:
  355 vs 373 unit, 450 vs 404 ui, 93 vs 102 ci_smoke).

**Interesting other features / larger bets**
- **More backends (Cloudflare/Route53)** — genuinely blocked on §P1-E: wire `get_backend_for_realm()`
  into the live DNS paths *first* (and fix the PowerDNS `create`/hostname/priority bugs), then adding a
  provider is a contained change. High value, but sequence it after the dead-stack cleanup.
- **Encryption at rest for TOTP seeds** — `totp_secret` is stored plaintext `String(32)`
  (`models.py:287`). The FEATURES.md filesystem-master-key approach fits the shared-webspace constraint.
  Medium; do after the P0/P1 auth items so you're not encrypting on top of a lockout gap.
- **Data-preserving (in-place) upgrades** — the big one. Gated by §P1-D (FK enforcement + the audit-wipe
  cascade must be sound first) and by replacing the additive-only `run_lightweight_migrations` with a
  real migration path (Alembic). Until then, greenfield-reseed-on-deploy is the honest posture — keep it
  documented as such.

---

## Verified clean (don't spend time here)

Auth decorators are applied consistently (only admin login/2fa/logout intentionally open); CSRF is wired
on all 49 POST-form templates and the three API blueprints are correctly `csrf.exempt`; no `|safe` on
user data; `telegram.py` callback uses constant-time compare with a chat-id conflict guard; `.gitignore`
covers all working-tree junk (zero untracked non-ignored files); hot-path indexes exist
(`token_prefix`, `session_token`, the `activity_log` composite); `run_lightweight_migrations` correctly
restricts itself to additive changes; `seed_settings_from_env` avoids the falsy-overwrite trap; secrets
are stripped from the deploy bundle; the REST `create`/`update`/`ddns` paths *do* enforce record-level
scope (making the read/delete gaps the clear outliers).
