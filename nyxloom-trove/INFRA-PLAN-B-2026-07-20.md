# Infra plan B — ciu root fix, network migration, containerized build, host traefik

Supersedes the sequencing in `INFRA-PLAN-2026-07-20.md` (INFRA-1/2 are landed). Operator
decisions this round: **execute INFRA-3 + INFRA-4**, adopt the **ciu-derived network name**,
FQDN = `naf.<PUBLIC_FQDN>` with a combined `naf-pdns.<PUBLIC_FQDN>` for PowerDNS, and
**never hardcode the FQDN**. Plan presented for review before execution.

## EXECUTION STATUS 2026-07-20 (live)

**Done + committed:**
- Phase A — `standalone_root = true`. **Measured caveat:** it guards `ciu up` (the mutating
  path) but NOT `ciu render` — upstream bug, `deploy.py:1633` checks the already-resolved
  root instead of the working dir. Recorded in B-INFRA; report to the ciu project.
- Phase B — network migrated to the ciu-derived name; `post-create.sh` hardcoded fallback
  removed (it would have silently split ciu's network from the containers').
- App containerized as the `tooling/app-local` ciu stack + traefik ingress + basicauth;
  `Host()` templated from `topology.external.public_fqdn` (never hardcoded).
  Verified: `ciu up --dir tooling/app-local --dry-run` → 17 steps, governance injected.
- Playwright `_guard_credentials()` + gate env forwarding, so the guard does not kill e2e.
- Stack conversions merged: `infra/pwmcp`, `tooling/geoip-mock`, `tooling/netcup-api-mock`.

**In flight:** conversions for `tooling/backend-powerdns` + `tooling/mailpit`; and a fix for
the deploy.sh call sites below.

**REMAINING — in order:**
1. **deploy.sh silently no-ops the mocks.** ~10 sites do
   `(cd tooling/<svc> && docker compose up -d 2>/dev/null) || log_warning`. The compose files
   are now deleted, and the calls are *doubly* silenced (`2>/dev/null` AND `|| true`), so the
   mocks simply never start and nothing errors. Must become ciu calls with the error-hiding
   removed on the *start* path.
2. Merge the last two conversions; register nothing new (registry already lists all stacks).
3. `naf-pdns` traefik exposure on `tooling/backend-powerdns` (labels + guard), mirroring
   `tooling/app-local`.
4. INFRA-4 surgery in `deploy.sh`: delete `tooling/reverse-proxy/`, remove
   `start_tls_proxy`/`stop_tls_proxy` (:704-809), the `USE_HTTPS && local` branch (:831), the
   `naf-dev-reverse-proxy` cleanup (:1378-1391), `SERVICE_REVERSE_PROXY` (:57), the
   `/etc/letsencrypt` mount and `PUBLIC_TLS_*`. Re-point `.env.services` `POWERDNS_API_URL`.
   Close **naf-P05 O2** as superseded.
5. **Stop the old containers and redeploy under ciu** (`ciu up --profile full`), then verify:
   app answers HTTPS at `naf.<fqdn>` through edge-traefik behind basicauth; pwmcp healthy;
   `testing-exec.sh unit` still 433 on 3.11+3.9; e2e passes the guard.
6. INFRA-3 containerized build (separate, `handoffs/naf-I03-containerized-build.md`).

**Nothing has been torn down yet** — the running environment is still intact.

## Phase A — fix ciu root resolution properly (replaces the `--define-root` workaround)

**Root cause (confirmed in ciu's own handoff docs):** the devcontainer's `~/.bashrc`
auto-sources `${REPO_ROOT}/ciu.env`, and dstdns is this devcontainer's primary workspace, so
every shell starts with `REPO_ROOT=/workspaces/dstdns`. Per **SPEC S1.1** the resolution order
is `--define-root` → `$REPO_ROOT` → cwd walk-up, so the stale env beat naf's marker and a bare
`ciu render` rendered **17 dstdns stacks**.

**The supported fix — SPEC S1.2 `standalone_root = true`:** declared under `[ciu]` in the
repo-root marker (exactly as `vbpub/pwmcp` and `topos/pwmcp` do). ciu then *refuses* to run when
`REPO_ROOT` doesn't match:

    [S1.2] standalone_root is true but REPO_ROOT does not match.
    Expected: /workspaces/netcup-api-filter, got: /workspaces/dstdns

That converts a **silent wrong-repo render** into a loud failure — the repo's fail-fast
doctrine. The working invocation becomes `source ciu.env` (it exports the correct `REPO_ROOT`),
not `--define-root` on every call.

*Related, already fixed upstream:* ciu **CIU-10** (a sibling's `PHYSICAL_REPO_ROOT` leaking into
`ciu env generate`) is FIXED in the installed build — which is why `env generate` self-corrected
via `/proc/self/mountinfo`.

- [ ] Add `standalone_root = true` under `[ciu]`.
- [ ] Drop `--define-root` from README/docs; document `source ciu.env`.
- [ ] Mark the B-INFRA "wrong repo root" finding RESOLVED, citing S1.2.
- **Verify:** with `REPO_ROOT=/workspaces/dstdns` exported, `ciu render` **fails** with S1.2;
  after `source ciu.env` it succeeds and renders only naf's stack.

## Phase B — migrate to the ciu-derived network

Operator chose the ciu-native name. Migration is cheap: **every mock compose already uses
`${DOCKER_NETWORK_INTERNAL:?...}`**; only one functional literal exists (the pin I added).
The devcontainer is **already attached** to `netcup-api-filter-7716ce-network`.

- [ ] `.env.workspace`: `DOCKER_NETWORK_INTERNAL` → the ciu-derived name.
- [ ] Marker: `network_name = "$DOCKER_NETWORK_INTERNAL"` (un-pin).
- [ ] `.devcontainer/post-create.sh:226`: drop the `:-naf-dev-network` fallback (fail-fast).
- [ ] Refresh stale comments (testing-exec.sh, pwmcp README/compose).
- [ ] Stop naf containers, recreate on the new network, remove the orphaned `naf-dev-network`.
- **Known risk (accepted):** the ciu name embeds a repo-path hash, so moving the checkout
  changes it. Recorded in B-INFRA.

## Phase C — INFRA-3 containerized build

Per `handoffs/naf-I03-containerized-build.md`. The build seeds the DB under the **host 3.14**
interpreter while vendoring 35 `cpython-311` `.so` files, so it validates nothing about the
target ABI (and abi3 bcrypt loads cross-version).

- [ ] `build_deployment.py`: host-vs-target guard on `initialize_database`; fix the sdist
      fallback + its wrong-condition warning; drop deprecated `utcnow()`.
- [ ] `deploy.sh phase_build`: run inside `test-runner:py311` / `:py39`
      (DooD, `--user ${USER_UID}:${DOCKER_GID}`, mount `PHYSICAL_REPO_ROOT`).
- [ ] Keep `--platform manylinux2014_x86_64 --only-binary :all:` (container fixes the *seeding
      interpreter*, not the *target glibc*).
- [ ] Stamp the builder image digest into `build_info.json`.
- **Verify:** both zips build in-container; diff the vendor trees to prove the py39 tree really
      carries cp39 extensions. Escalate if any dep lacks a cp39/cp311 wheel (the thin image has
      no compiler).

## Phase D — INFRA-4 host traefik, retire naf's own edge

Per `handoffs/naf-I04-host-traefik-exposure.md`. **Production (Passenger) is untouched** — this
is the dev edge only.

**Remove:** all of `tooling/reverse-proxy/`; `deploy.sh` `start_tls_proxy`/`stop_tls_proxy`
(:704-809), the `USE_HTTPS && local` branch (:831), the `naf-dev-reverse-proxy` cleanup
(:1378-1391), `SERVICE_REVERSE_PROXY` (:57); the `/etc/letsencrypt` mount and all
`PUBLIC_TLS_*`; the reverse-DNS mechanism in `docs/FQDN_DETECTION.md`.

**Add:** `ingress_public` (external) membership + four labels; TLS/cert inherited from the
`websecure` entrypoint (traefik owns ACME).

**FQDN — never hardcoded.** `ciu.env` already carries `PUBLIC_FQDN` (auto-detected). So:
`[topology.external] public_fqdn = "$PUBLIC_FQDN"`, and rules template it:
``Host(`naf.{{ topology.external.public_fqdn }}`)`` and
``Host(`naf-pdns.{{ topology.external.public_fqdn }}`)``.

**Password protection (operator asked):** yes — a config-gated traefik `basicauth` middleware,
the pattern dstdns already uses on pwmcp:

    traefik.http.routers.<r>.middlewares=<n>-guard
    traefik.http.middlewares.<n>-guard.basicauth.users=<user>:<htpasswd>   # "$" -> "$$"

Gated by `external.guard_enabled`; the htpasswd hash comes from a **ciu secret**, never
committed. Scope = OPEN QUESTION 2.

- [ ] Re-point `.env.services` `POWERDNS_API_URL` to the traefik route.
- [ ] Mailpit stays internal-only (D-006 decision D).
- [ ] Close **naf-P05 O2** as superseded.

## ANSWERED 2026-07-20 (operator) — scope expanded

- **App routing → containerize the local app, AS A CIU STACK** (no hand-written compose).
  `deploy.sh`'s host `gunicorn` becomes a container on the project network so traefik can
  label-discover it. Implementation note: reuse the **test-runner py311 image** (it already
  carries the runtime closure at the primary Passenger ABI) running
  `gunicorn -c gunicorn.conf.py passenger_wsgi:application` over the mounted `deploy-local/`,
  rather than building a second app image. The dead root `Dockerfile`/`docker-compose.yml`
  (backlog B-OPS) are removed as part of this.
- **Migrate ALL naf containers to ciu** — `tooling/{mailpit,geoip-mock,netcup-api-mock,
  backend-powerdns}`, `infra/pwmcp` (currently hand-written), plus the new app stack.
  `tooling/test-runner` is already converted. Every hand-written `docker-compose.yml` goes.
- **basicauth: wire ALL services and ENABLE it.** Rationale: the product is not production
  ready and must not be publicly reachable, but e2e has to run through real TLS.
- **PowerDNS = the dev container** (`tooling/backend-powerdns`), exposed as
  `naf-pdns.<PUBLIC_FQDN>`.

### Consequence that must be designed in, not discovered

Guarding **every** route with basicauth breaks e2e unless the browser authenticates. Playwright
must receive the credentials — `browser.new_context(http_credentials=...)` in
`ui_tests/playwright_client.py`, fed from the same ciu secret that generates the htpasswd hash.
Without this, enabling the guard silently kills the e2e gate it exists to protect.

## RESOLVED QUESTIONS (were blocking Phase D)

1. **The dev app is not a container.** `deploy.sh:535` runs `gunicorn` as a **host process in
   the devcontainer** on `LOCAL_FLASK_PORT=5100`; the old nginx reached it as
   `${LOCAL_APP_HOST}:${LOCAL_APP_PORT}`. traefik's docker provider discovers routes from
   **container labels**, so there is nothing to label. Options: (a) label the devcontainer and
   join it to `ingress_public`; (b) a traefik file-provider entry pointing at the devcontainer
   host:port — but that edits the shared `vbpub/tls-edge` stack; (c) containerize the local app
   so it is label-discoverable (aligns with the "off the cockpit" doctrine, largest change);
   (d) expose only containerized services (PowerDNS) and keep the app on its dev port.
2. **Which services get basicauth**, and is the exposed PowerDNS the dev `tooling/backend-powerdns`
   container or a real authoritative server (changes the hardening bar)?

## Verification gates

`testing-exec.sh unit` (433 on 3.11+3.9) after each risky phase; `e2e` via pwmcp on the new
network; both deploy zips built in-container with correct ABI; app+PowerDNS answering over
HTTPS through edge-traefik.

## REVIEW HOLD — `wt/ciu-powerdns` NOT merged (2026-07-20)

The `tooling/backend-powerdns` conversion is committed on `wt/ciu-powerdns` but **deliberately
not merged**. The agent disclosed (to its credit) that it converted the stack's mandatory
`${VAR:?must be set}` environment variables into **committed TOML defaults with invented
values** — SOA `ns1.vxxu.de` / `hostmaster.vxxu.de`, the API port, and the `PDNS_*` server
settings — because the real values live in gitignored `.env` files it could not read.

That is the wrong trade for this repo: it replaces fail-fast required-vars with
cross-environment default fallbacks on a DNS server's SOA and API configuration, which
`docs/FAIL_FAST_PRINCIPLE.md` / AGENTS.md §2 explicitly forbid. A wrong-but-plausible SOA is
exactly the kind of value that silently produces bad zone data rather than an error.

**Resolution needed before merge:** keep the `${VAR:?...}` guards (sourced from the operator's
`.env`) and let the ciu marker carry only genuinely static identity (image, tag, container
name, internal ports), or have the operator supply the real values. Everything else in that
branch (2 services, init one-shot + depends_on, healthcheck fidelity, UID 953, port 53
udp/tcp) verified clean and is worth keeping.
