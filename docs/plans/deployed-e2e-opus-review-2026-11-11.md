# Opus review: deployed e2e tier and modern-ciu plan (2026-11-11)

Checked against the repo, ciu 7.24.0 source (`/opt/mdt/venv/.../ciu`), SPEC/CONFIG/CONSUMERS, SPEC-V8 draft.12, tls-edge and dstdns. Read-only.

## 1. Verdict

**Sound with changes.** The tier split, the single port-53 owner and the credential model are right. But the deployment-type mechanism, frontend identity, WP7's premise and WP9 are wrong as written; re-scope them before WP4b. WP0..WP3 and WP8 may continue.

## 2. Findings

### Blocking

**B1. Profile-derived flags break `ciu up --dir` and are not persistent.**
- Engine mode passes no selection context (`engine.py:3131-3147`). Any template reading `ciu.selected_profiles` therefore fails (UndefinedError, SPEC S3.12 cl.1) under the documented verb `ciu up --dir tooling/<stack>` (AGENTS.md, `run-gate.toml:107-108`).
- S3.12 cl.4: "Nothing is persisted". A later plain `ciu up` re-renders a public instance as internal, which drops its traefik labels while the first-boot init keeps its public mail/netcup config.
- **Fix:**
  - Per-checkout overlay `ciu.global.instance.toml.j2`: `[ciu.instance] service_profiles=["public"]` (the default selection, `deploy.py:236-250`) plus `[topology.deployment] type="public"`, which templates read and which also renders under `--dir`.
  - A `pre_compose` guard that records the type in the instance data dir and refuses a change until `ciu clean`. This emulates v8 S9.4.
- Spike row (a) is wrong in practice.

**B2. Traefik names are global.** The router and service are `naf-app`/`naf-powerdns`, the middleware `naf-guard`, and the Host `naf.<fqdn>` (`app-local/ciu.compose.yml.j2:76-87`, `backend-powerdns/ciu.compose.yml.j2:263-273`). A worktree frontend defines the same router with another rule. Traefik flags the conflict and drops the router, taking the human instance down. **Fix:** derive the router, service and middleware names and the subdomain from the instance identity.

**B3. `$INSTANCE_ID` for every checkout, not "primary keeps dev".**
- dstdns, the reference consumer, commits `environment_tag="$INSTANCE_ID"` for all checkouts (`dstdns/ciu.global.defaults.toml.j2:74-75`). That is v8 S4.2-shaped and removes the special case.
- CIU-193 is OPEN: while tags are shared, `ciu down` in a worktree stops the main checkout's `naf-dev-*` containers. Land this first.

**B4. WP7's premise fails.**
- The UI suite provisions personas directly into the session SQLite (`e2e_env.py`, `NAF_VERIFY_DB_PATH`) and needs pristine installs. That is impossible against a long-lived container.
- A remote target already exists (`NAF_E2E_TARGET=remote`, `ui_tests/config.py:21-35,155+`; one `remote_smoke` file).
- **Fix:** build a small deployment-contract suite on that target, with personas provisioned through the admin UI/API (the admin password comes from the GEN_LOCAL file). It covers only what the hermetic tier cannot:
  - TLS chain
  - Secure and host-only cookies
  - a forged XFF
  - https email links
  - the guard
  - the app-to-PowerDNS wire
  - live mail, netcup read and DNS

**B5. WP9 tests nothing new, and the public app is unsafe.**
- `app-local` runs the test-runner image and serves `deploy-local/` from a read-write mount of the whole repo (`app-local/ciu.compose.yml.j2:20,28,55`). WP9 duplicates the hermetic lane: same image, tree and gunicorn.
- Publicly, a compromised app could write `.ciu/secrets`, `.env.guard` and git hooks, which execute in the cockpit.
- **Fix:** frontends run the OCI release image (`Dockerfile.release`): non-root, data volume only, `NAF_BOOTSTRAP_ADMIN_*_FILE`. WP9 becomes the OCI boot smoke, which closes the backlog item "OCI image build/boot verification".

**B6. Cookie domain `auto` = `.<PUBLIC_FQDN>`** (`app.py:137-152`). Frontends would overwrite each other's `session` cookie, and every sibling estate service would receive it. **Fix:** host-only by default; the public profile sets `""` explicitly. Belongs to F029.

### Proxy trust (WP2/WP3)

- **The inventory is incomplete.** There are also raw left-most-entry XFF reads at `account.py:1851,2148,2192` and `filter_proxy.py:505,597`. Acceptance should be a test forbidding `headers.get('X-Forwarded-For'` anywhere in `src/`.
- **The edge is probably not forgeable.** The tls-edge `websecure` entrypoint has no `forwardedHeaders` (`tls-edge/ciu-stack/traefik.yml.j2:50-66`), and traefik's default strips client `X-Forwarded-*` headers. The exposure is the webhoster and direct access. Keep a forged-header test through the edge to prove it.
- **Hops 0 behind TLS** keeps the Secure flag, which comes from config (`app.py:111-116`). It does break two things:
  - `url_for(_external=True)` produces `http://` reset, verify and invite links (`password_reset.py:347,477,603`), which are dead without port 80.
  - Every client collapses to the proxy IP for rate limits, lockouts, `ADMIN_SESSION_BIND_IP` and GeoIP, so one abuser locks everyone out.
- **x_host=1 without a host-validating proxy allows reset-link host poisoning.** Fix: `x_host=0`, a fail-fast canonical external URL (or Flask `TRUSTED_HOSTS`), and a one-time WARN when forwarded headers arrive untrusted.
- **WP3 must precede the tarball default.** Both 0 and 1 can fail on the webhoster, and today ships 1.
- **The probe.** `vbpub/scripts/test-webspace-php-environment.php:411-424` already reports HTTPS/XFP/XFF/REMOTE_ADDR, so run it now. PHP-FPM may sit behind a different front than Passenger, so add a WSGI environ dump via `passenger_wsgi.py`, requested with a forged header.

### ciu 7.24 claims

- **`ciu up --shared-infra`:** wrong verb. These are `ciu worktree create` flags (CONFIG S16.1), fixed at creation.
- **`ASK_EXTERNAL` hard-fail:** only on first materialization.
  - `materialize.py:423-450`: env `<key>` wins and overwrites the store; afterwards the store is reused silently.
  - The store is per stack, so worktrees re-ask.
  - The live-tier "fail on missing" must therefore be a lane preflight with real login probes.
- **`GEN_LOCAL` per checkout, CIU-104, §26 `environment_tag`:** correct.
- **CIU-176:** fixed in 7.23.0 (CHANGES.md:178-180). Re-run the repro.
- **D-009 "no code forms names":** false. `.env.services:20-57` and the hooks (`post_compose_zone.py:90-93`) form names. Use `ciu resolve --json --live`, which mirrors v8 `resolved.identities`.

### Non-blocking

- **Sub-zones.** The app cannot create zones (`seeding.py:1114`), so per-session sub-zones need the master key plus parent NS records.
  - Use per-session realm labels `e2e-<utc>-<rand>.<zone>` instead. They exercise naf's own scoping and need no key in tests.
  - A crash-reaper one-shot in the PowerDNS stack deletes stale `e2e-*` rrsets.
  - Keep the SOA negative TTL low.
- **DNS assertions.** `test_live_dns_verification.py` polls 8.8.8.8 for deletion, which is cache-bound and flaky. Assert fresh-name creation via public resolvers (that proves :53 is reachable externally) and deletion at the authoritative server. Same-host tests hairpin and prove nothing about firewalls.
- **Port 53.** Bind `${PUBLIC_IP}:53`, not `0.0.0.0` (`backend-powerdns/ciu.compose.yml.j2:217-220`), to avoid stub-resolver clashes. Decide IPv6 (glue AAAA without a v6 publish breaks intermittently). Docker publishes bypass ufw; the provider firewall is what matters.
- **PowerDNS API.** It is exposed at `naf-pdns.<fqdn>` with `webserver_allow_from=0.0.0.0/0` on `ingress_public`, so every estate container reaches the master API. Drop the route; tests use the instance network.
- **CA limits.** tls-edge `acme-tls` issues one certificate per name. Let's Encrypt allows about 50 per registered domain per week, shared with the whole estate. Use stable per-worktree names (never per session), and have the preflight wait until the served SAN matches; traefik's default certificate is served until then.
- **Guard.** WP7 reuses the human `.env.guard`, contrary to `ciu.global.defaults.toml.j2:232-233`. Use a generated per-instance test credential, or an `ipAllowList` for same-host clients (measure the hairpin source IP first).
- **Secrets.**
  - Never pass live credentials as env in the cockpit: every agent subprocess inherits them, and env wins. Use the prompt or `ASK_FILE`.
  - Mount them only into the app and a dedicated live runner, not the shared exec runners.
  - No screenshots or traces of the netcup config page; a masked-repr secret type in tests.
  - Ensure R2 cowtree excludes `.ciu/`.
- **netcup CCP credentials control every domain on the account:** read-only calls only.
- **External flakiness.** Report failure classes (prerequisite / provider timeout / product) and retry once only on provider timeouts. Plus-addressing per session.
- **WP8.** The `pdns-auth-48` constraint `<4.9.0` (`cmru.toml:106-127`) can never advance, because new series are new repositories. The latest 4.8 resolution is from 2025-02, so decide the series and EOL. The alpine init (`:134`, `pull_policy: missing` contradicts its comment) may be removable if the pdns image self-initialises sqlite.
- **Inconsistencies.**
  - The plan and B042 say the WP1 key becomes `GEN_LOCAL`; the controller told the WP1 author otherwise.
  - B041 cites `ab4f8c0`, which is only on `r2-final`; main has `d077df0`.

## 3. Better alternatives and missing pieces

- **Two public roles.**
  - `public-edge`: any checkout. Frontend behind tls-edge, its own internal PowerDNS without :53, its own key.
  - `public-dns`: exactly one checkout. :53, the delegated zone and the live tier.

  This removes the shared-infra join, master-key sharing, `powerdns`/`app` alias collisions and cross-checkout zone leaks. It matches the operator's statement that only one checkout goes public with DNS.
- **Endpoint manifest.** A `post_compose` hook writes `endpoints.json` (URLs and secret file paths, no values) from `ciu resolve --json --live` plus the Host rule; the preflight reads it. This replaces sourcing `.env.services` and stands in for v8 gate `binds` and RG-261.
- **Webhoster lane.** The real public target is the Passenger tarball. Add an on-demand `e2e-remote` lane (remote_smoke against the webhoster) after WP3.
- **Declare `ciu.user_tables`** now (S3.13, as dstdns does).

## 4. v8 to v7 adoption

v8 implementation has barely started (ciu8 trove: one P001 handoff).

| v8 feature | Buys | v7.24 expression | Cost | Recommendation |
|---|---|---|---|---|
| Derived identity S4.2 | Worktree-safe names, routers, hosts | `environment_tag="$INSTANCE_ID"` everywhere; routers and subdomain from it | S | **Adopt now.** v8 only deletes `container_name`. |
| Read, never form identities S4.4 | Rename-proof hooks and tests | `ciu resolve --json [--live]`; retire `.env.services` names | S | **Adopt now.** |
| Layouts and realness, immutable record S7.6/S9 | Deployment types | Overlay fact plus `service_profiles`; `[topology.realness] mail/netcup/dns="simulated"/"live"` using v8 level names; `pre_compose` guard | S-M | **Adopt the shape.** The guard and Jinja branches become waste; no bundles. **ciu request:** selection context under `--dir`. |
| Publish `host`/`proxy`/`instance` S7.4 | :53 vs edge vs internal | Per-endpoint `publish` key in templates | S | **Adopt the names.** |
| Join presets S9.5 | Borrow primary PowerDNS | `worktree create --shared-infra` | M | **Avoid** (two roles); wait. |
| Secrets generate/ask/file/ephemeral S10.1 | No tracked credentials | `GEN_LOCAL`/`ASK_EXTERNAL`/`ASK_FILE`/`GEN_EPHEMERAL` | S | **Adopt now**; the mapping is mechanical. |
| Host-scoped secrets S10.4 | One operator credential for all checkouts | None; `ASK_FILE` outside the checkout under DooD unverified | n/a | **File a ciu request.** |
| External realization `probe` S5.4 | Early failure on dead SMTP/CCP | Preflight probes | S | **Adopt.** |
| `ciu gate` binds and preconditions S16 | Lane gets endpoints, requires stack up | run-gate (v8 ports it, so not waste); RG-261 | M | **run-gate request.** |
| Leases and reap S14.6 | Crash cleanup | `ciu worktree reap`, `ciu run reap`, rrset reaper | S | **Use what exists.** |
| Admission S21 | Memory-based concurrency | n/a | L | **Wait.** |

## 5. Amended work packages (deltas only)

- **WP0:** cite `d077df0`.
- **WP1:** the key becomes `GEN_LOCAL`, owned by its checkout and never shared. Drop the public PowerDNS route and leave `ingress_public`.
- **WP2 (re-scope):** all XFF reads plus a guard test; `x_host=0`; canonical URL; host-only cookies; untrusted-header WARN. The tarball value comes from WP3, so WP2 depends on WP3.
- **WP3 (first):** run the PHP probe now, then add a Passenger WSGI probe.
- **WP4b-1 identity:** `$INSTANCE_ID` everywhere; derived routers, middleware and subdomain; `ciu resolve` in hooks; retire `.env.services` names; re-run CIU-176. Gates all worktree stack work (CIU-193).
- **WP4b-2 deployment type:** overlay fact plus `service_profiles`, the guard, realness and publish keys. Not `ciu.selected_profiles`.
- **WP5:** OCI release image with no repo mount; `${PUBLIC_IP}:53` and an IPv6 decision; `public-dns` role only; realm labels plus a reaper instead of sub-zones.
- **WP6:** prompt or `ASK_FILE`, never cockpit env; mounted only into the app and a dedicated live runner; preflight login probes.
- **WP7 (re-scope):** contract suite on the remote target with API-provisioned personas; `endpoints.json`; certificate wait; DNS rules; failure classes; scrubbing.
- **WP8:** add the pdns series/EOL decision; delete or pin the alpine init.
- **WP9 (replace):** OCI boot smoke. Depends on WP4b-1 only.
- **WP11 (new):** on-demand `e2e-remote` against the webhoster.
- **Requests:** ciu (`--dir` selection context, host secrets); run-gate (RG-261, per-lane secret mounts).
- **Order:** WP3 → WP2; WP4b-1 → {WP4b-2, WP9} → WP5/WP6 → WP7 → WP11 → WP10.

## 6. Not verified

- Host :53 occupancy, provider firewall, IPv6: needs host access.
- The live tls-edge overrides: only the template was read.
- Traefik's duplicate-router and header-stripping behaviour: from knowledge of traefik, not a test.
- The hairpin source IP traefik sees.
- Let's Encrypt limit numbers: from memory.
- pdns sqlite self-init.
- Whether shared-infra joins add service aliases.
- `ASK_FILE` under DooD.
- Delegation state and the webhoster front end: operator only.
