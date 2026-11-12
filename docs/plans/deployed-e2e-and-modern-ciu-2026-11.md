# Deployed e2e tier, deployment types and modern-ciu configuration (plan, 2026-11-11)

Status: PLAN, amended 2026-11-11 after an independent Opus review ([`deployed-e2e-opus-review-2026-11-11.md`](deployed-e2e-opus-review-2026-11-11.md), findings folded in below).
Origin: investigation of the e2e deployment workflow (2026-11-10) and the operator interview of 2026-11-11.

## 1. Where we are

| Tier | What it runs | What it proves | What it does NOT cover |
|---|---|---|---|
| hermetic unit (`tests/`, gate lanes) | in-process app + fakes | logic | any process/network boundary |
| hermetic e2e (`run-gate e2e`) | throwaway gunicorn in the py311 runner, golden-DB copy, random personas, mailpit + mocks, pwmcp browser | UI/API journeys on the shipped package | TLS, traefik, the app container, ProxyFix/client IP, PowerDNS, real mail, real netcup |
| human instance (`tooling/app-local`) | container behind `tls-edge`, guard, ciu secrets | manual use | nothing runs tests against it |
| `ui_tests/tests/live/*` | needs `DEPLOYMENT_MODE=live` + bare env vars | DNS propagation, IMAP mail | no lane, no credential home, PowerDNS never started here |

The deployed tier the product needs (frontend behind the host `tls-edge`, our PowerDNS as authoritative backend for a delegated
zone, real SMTP/IMAP and netcup accounts) exists only as unconnected pieces.

## 2. Decisions

- **D-008 deployment types.** `internal` (instance network, mocks, nothing published, frontend reached by container name) and `public`
  (frontend behind `tls-edge`, real SMTP/IMAP/netcup). The type is a PER-CHECKOUT FACT, not a per-invocation selection: ciu 7.24
  gives `ciu up --dir` (the documented verb) no selection context (`engine.py` main_execution call), so templates cannot read
  `ciu.selected_profiles` there, and nothing is persisted between invocations (SPEC S3.12). Therefore: the per-checkout overlay
  `ciu.global.instance.toml.j2` carries `[ciu.instance] service_profiles` and `[topology.deployment] type`; templates read
  `topology.deployment.type` (renders under `--dir` too); a `pre_compose` guard records the type in the instance data dir and
  refuses a change until `ciu clean` (emulates v8 S9.4). Flags use v8 names: `[topology.realness] mail|netcup|dns = live|simulated`,
  endpoint `publish = host|proxy|instance`. Selection context under `--dir` is filed as a ciu request.
- **D-009 identity.** `deploy.environment_tag = "$INSTANCE_ID"` in EVERY checkout (dstdns precedent, v8 S4.2-shaped; no special
  primary). Traefik router, service and middleware names and the frontend subdomain derive from the instance identity (today they
  are global: `naf-app`, `naf-guard`, so a second frontend's router collides and traefik drops it). Hooks and tests READ identities
  (`ciu resolve --json [--live]`, ciu status), they do not form container names; `.env.services` stops building names. This lands
  first: ciu CIU-193 is open (`ciu down` in a worktree stops other checkouts that share tags).
- **D-010 two public roles, one port-53 owner.** `public-edge` (any checkout): frontend behind `tls-edge` with its own backing
  PowerDNS (no host port 53, its own key). `public-dns` (exactly ONE checkout): PowerDNS published on `${PUBLIC_IP}:53` (not
  0.0.0.0; IPv6 decided explicitly), the delegated zone, the live tier. No shared-infra join, no cross-checkout key sharing.
  The app cannot create zones, so sessions isolate by REALM LABEL `e2e-<utc>-<rand>.<delegated_zone>` (exercises naf's own
  scoping, needs no master key in tests) and a reaper one-shot in the PowerDNS stack deletes stale `e2e-*` rrsets; the public
  PowerDNS API route on `ingress_public` is dropped (tests use the instance network). Frontend names: stable per checkout
  (`naf-<instance>.<PUBLIC_FQDN>`, never per session: Let's Encrypt rate limits are shared estate-wide); the preflight waits until
  the served certificate's SAN matches.
- **D-011 credentials.** `GEN_LOCAL` for generated secrets (owned by their checkout, never shared). Operator-supplied real
  credentials: `ASK_FILE`/prompt only, never exported into the cockpit environment (every agent subprocess inherits it, and env
  overwrites the stored value); mounted only into the frontend and a dedicated live runner, not the shared exec runners. Non-secret
  facts in gitignored `.env.live`. `ASK_EXTERNAL` hard-fails only on first materialisation, so the lane PREFLIGHT proves each
  credential with a real, read-only login (SMTP auth, IMAP login, netcup read call; the CCP key controls every domain of the
  account: no writes). Failures are classified (prerequisite / provider timeout / product); retry once on provider timeouts only.
- **D-012 frontends run the OCI release image.** `app-local` today runs the test-runner image with the whole repo mounted
  read-write (a public app could write `.ciu/secrets`, `.env.guard`, git hooks that run in the cockpit). Public and internal
  frontends use the release image (non-root, data volume only, `NAF_BOOTSTRAP_ADMIN_*_FILE`).
- **D-013 proxy trust.** `TRUSTED_PROXY_HOPS` (default 0), `x_host` never trusted, canonical `PUBLIC_BASE_URL` for every emailed
  link (reset-link host poisoning), host-only session cookies (the old `auto` shared one cookie with every sibling under
  `.PUBLIC_FQDN`), every client address from `request.remote_addr`, a static test forbids raw forwarded-header reads in `src/`.
  The shipped tarball keeps today's behaviour (1 hop) until the operator has measured the webhoster (WP3); both 0 and 1 can
  fail there, so the default is a measured decision.
- **Tier split.** Hermetic e2e stays. The deployed tier is a small DEPLOYMENT-CONTRACT suite on the existing remote target
  (`NAF_E2E_TARGET=remote`), not the full UI suite (which seeds personas into SQLite and needs pristine installs): TLS chain,
  Secure and host-only cookies, forged forwarded headers through the edge, https email links, the guard, the app-to-PowerDNS wire,
  live mail / netcup read / DNS. The deployed lane is on-demand, not part of `release-gate`.

## 3. Work packages

Routes: author on one route, independent review on the other; every merge needs a MERGE verdict; gates only via `run-gate`.
"A=ds" = author deepseek (review luna); "A=luna" = author luna (review deepseek).

| WP | Backlog | Content | Route | Depends |
|---|---|---|---|---|
| WP0 | B041 | R2 close-out: lane lists include the survivor files (main `d077df0`), rerun the four lanes on the stable commit, triage | controller + ds | - |
| WP1 | B042 | Config hygiene: one source for the PowerDNS URLs, remove the retired proxy-path variables, invented SOA default and dead helpers from the defaults, drift tests (the API-key move to `GEN_LOCAL` is WP4b-1/WP5, not here) | A=ds | - |
| WP2 | B043 | Proxy trust (D-013): `TRUSTED_PROXY_HOPS`, `x_host=0`, `PUBLIC_BASE_URL`, host-only cookies, ten raw forwarded-header reads removed + static guard test, tarball keeps 1 until WP3 | A=luna | - |
| WP3 | B044 | Webhoster probe: run the EXISTING `test-webspace-php-environment.php` now (it already reports XFF/XFP/REMOTE_ADDR); new `test-webspace-forwarded-headers.php` (forged-header verdict) | A=ds | - |
| WP3b | B054 | Passenger probe: a standalone WSGI app dir (vbpub scripts) that dumps what a Passenger app sees for a forged header (PHP-FPM may sit behind a different front than Passenger); operator runs it, decides the tarball default | A=ds | WP3 |
| WP4a | B045 | DONE (section 6; corrected by the Opus review) | controller | - |
| WP4b-1 | B046 | Identity: `environment_tag="$INSTANCE_ID"` everywhere, derived traefik router/service/middleware/subdomain, `ciu resolve` instead of name building (`.env.services`, hooks, run-gate env), `.gitignore` ciu entries, `ciu.user_tables`, re-run the CIU-176 repro (fixed in 7.23.0), `PUBLIC_BASE_URL`/hops in stack config; `POWERDNS_API_KEY` becomes a checkout-local `GEN_LOCAL` secret. Gates all worktree stack work | A=ds | WP1 |
| WP4b-2 | B053 | Deployment type: overlay fact + `service_profiles`, `topology.deployment.type`, v8-named realness/publish keys, the pre-compose change guard, templates branch on the fact | A=ds | WP4b-1 |
| WP5 | B047 | Public stacks: frontends on the OCI release image (no repo mount), `public-dns` role (`${PUBLIC_IP}:53`, IPv6 decision, delegated zone, realm-label reaper), `public-edge` role, drop the public PowerDNS API route, seed hook tested end to end | A=luna | WP4b-2, WP2 |
| WP6 | B048 | Credentials: prompt/`ASK_FILE` secrets for SMTP/IMAP/netcup, `.env.live.example`, mounts only into the frontend and a dedicated live runner, applied at first boot only | A=ds | WP4b-2 |
| WP7 | B049 | Deployment-contract suite on the remote target + endpoint manifest (`endpoints.json` written by a post-compose hook from `ciu resolve --json --live`), lane `e2e-public` with preflight (login probes, certificate SAN wait, failure classes), DNS assertions (fresh-name creation via public resolvers, deletion at the authoritative server), scrubbing of secrets/traces, per-instance guard credential instead of the human `.env.guard` | A=luna | WP5, WP6 |
| WP8 | B050 | cmru versions: every stack image a target, floating tags gone, `cmru versions check` in the release gate; decide the pdns series/EOL (`pdns-auth-48` constraint `<4.9.0` can never advance); delete or pin the alpine init | A=ds | - |
| WP9 | B051 | OCI boot smoke: build the release image, boot with and without `NAF_BOOTSTRAP_ADMIN_*`, non-root `/data`,`/config`; closes the open OCI verification item (replaces the former internal-profile UI e2e). Also owns release-builder readiness (WP4b-1 review M4): since WP4b-1 every checkout runs its own runners, so `cmru release` building in `.worktrees/cmru-release-*` needs that worktree's runner up (`ciu up --dir tooling/test-runner` there, with the linked-worktree `.git` mount; `ciu down --dir` after). Decide whether cmru's `build` step starts it; `scripts/build_webhosting_tarball.py` stops with that instruction when the runner is absent or stopped. Proof step: a cmru dry run or `cmru tester-gate` building the Passenger tarball | A=ds | WP4b-1 |
| WP11 | B055 | On-demand `e2e-remote` lane: remote smoke against the real public target, the Passenger tarball on the webhoster | A=ds | WP3b |
| WP10 | B052 | Docs + closeout: `DEV_INFRA_SETUP.md`, `TESTING_INFRASTRUCTURE.md`, `SECURITY.md`, `FEATURES.md`/`CHANGELOG.md`, `STATE.md`, release-gate + e2e on the final HEAD, R2 evidence, push | controller | all |

Order: WP3 -> WP2's tarball default; WP4b-1 -> {WP4b-2, WP9} -> WP5/WP6 -> WP7 -> WP11 -> WP10. Parallel from the start: WP0, WP1, WP2,
WP3, WP8.

## 4. Tool gaps (filed in vbpub backlogs, see the list at the end)

Each gap names evidence from this repo and a "close when". Until a gap is closed naf uses the workaround stated.

## 5. Things the operator must supply (nothing here is committed)

- Fill `.env.live` and answer the `ASK_EXTERNAL` prompts (SMTP, IMAP, netcup CCP) once per store.
- Upstream: the delegation for the zone (NS + glue, `DEV_INFRA_SETUP.md` 3a) and a wildcard/individual A record for the public
  frontend names under `PUBLIC_FQDN` (verify what already exists; WP5 documents the exact records).
- Run the webhoster probe (WP3) and report the result; until then the tarball trusts no proxy.

## 6. WP4a spike result (2026-11-11, reading ciu 7.24 docs + `ciu check` on main)

| Question | Finding |
|---|---|
| (a) per-deployment-type switches | CORRECTED by the Opus review: `ciu.selected_profiles` is NOT available under `ciu up --dir` and is not persisted, so it cannot carry the type (see D-008). Original finding: templates and hooks can read the selection: `ciu.selected_profiles` / `ciu.deployed_stacks` (CONSUMERS section 10, S3.12), e.g. `external.enabled = {{ 'public' in ciu.selected_profiles }}`. This replaces the `topology_overrides` idea of D-008: profiles pick the stacks and the flags derive from the selection; nothing global is overridden. |
| (b) worktree joins the primary's PowerDNS | CORRECTED: `--shared-infra` is a `ciu worktree create` flag (fixed at creation), and D-010 avoids the join altogether. Original finding: it joins the reference instance's network; `--shared-infra-ref-services <alias>` writes a CIU-derived, re-authenticated `[topology.services.<alias>] internal_host/internal_port` (CONFIG S16.1a, CONSUMERS section 17). Use it for `powerdns`; never hand-type the primary's container name. |
| (c) one generated key across stacks | `GEN_LOCAL:<name>` lives in the PROJECT store `<repo-root>/.ciu/secrets/<name>` (S4.9): shared by all stacks of ONE checkout. A joined worktree has its own store, so it cannot read the primary's PowerDNS key from there; supply it with `ASK_EXTERNAL`/`ASK_FILE` in the worktree (WP5 decides; a backlog entry is filed once tested, since stacks cannot be brought up from managed worktrees yet, CIU-176). |
| (d) `ASK_EXTERNAL` non-interactive | CORRECTED: aborts only on FIRST materialisation; afterwards the stored value is reused silently and an env value overwrites it (`materialize.py`). The hard-fail is a lane preflight with real login probes (D-011). |
| (e) `ciu check` | PASS on main. One WARN: `.gitignore` lacks the ciu worktree artifacts (`ciu.worktree-instance.json`, `*.tmp` instance files). Fixed in WP4b-1. CIU-176 (stacks from managed worktrees) was fixed in ciu 7.23.0: re-run the repro instead of treating it as a blocker. |
| names | `container_name` stays explicit; every checkout isolates via `deploy.environment_tag = "$INSTANCE_ID"` (CONSUMERS section 26, dstdns does this); ciu 7.24 refuses to start on a name owned by another checkout (CIU-104). v8 derives names (`SPEC-V8` S4.2) and forbids `container_name` in templates; moving there later means deleting the line. |

## 7. Risks and unverified points (from the review; need host access or the operator)

Host port 53 occupancy, provider firewall and IPv6 (glue AAAA without a v6 publish breaks intermittently; Docker publishes bypass ufw);
live tls-edge overrides (only the template was read); traefik duplicate-router and forwarded-header stripping (from knowledge, test
through the edge); the source IP traefik sees for same-host clients (hairpin); Let's Encrypt limits (about 50 certificates per
registered domain per week, estate-wide: stable names, wait for the SAN); whether the pdns image self-initialises sqlite (alpine init
removable); `ASK_FILE` under DooD; the webhoster front end (WP3/WP3b, operator only).

## 8. Requests to the tools (filed in vbpub backlogs)

ciu: selection context under `ciu up --dir`; host-wide secrets (v8 S10.4). run-gate: RG-261 (stack prerequisite and per-instance
endpoints), per-lane secret mounts. cmru: KI-149 (floating tags, apply). assay: B525 (R2 test selection).
