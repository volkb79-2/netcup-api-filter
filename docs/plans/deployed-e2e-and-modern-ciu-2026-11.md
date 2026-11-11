# Deployed e2e tier, deployment types and modern-ciu configuration (plan, 2026-11-11)

Status: PLAN (decisions D-008..D-011 in `nyxloom-trove/decisions.md`; work packages are backlog B041..B052).
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

- **D-008 deployment types.** Two ciu deployment types selected at `ciu up --profile`: `internal` (everything on the instance
  network, mailpit + mocks, nothing published, frontend reached by container name) and `public` (frontend behind `tls-edge`,
  PowerDNS public on port 53, real SMTP/IMAP/netcup). Realised on ciu 7.24 with `[deploy.profiles]` and the `ciu.selected_profiles` template/hook facts
  (templates branch on `ciu.selected_profiles`); shaped so ciu v8 layouts/realness (SPEC-V8 S7.6, S9) replace them
  without template changes.
- **D-009 identity.** Worktrees get per-instance container names by `deploy.environment_tag = "$INSTANCE_ID"` in the worktree
  overlay (ciu CONSUMERS section 26); the primary keeps `dev`. No code forms a container name except from config
  (`deploy.project_name`/`environment_tag`/service name); hooks and run-gate already follow this.
- **D-010 one public DNS singleton.** Exactly one PowerDNS owns host port 53 (long-lived, owned by the primary checkout, `public`
  profile). Worktree/session stacks never publish 53; they use the primary's PowerDNS API over a shared network and create their
  own sub-zone `e2e-<id>.<delegated_zone>` per session (the delegation covers the subtree; deleted on teardown). Public frontends
  are many: `naf-<instance>.<PUBLIC_FQDN>`, each with its own traefik Host rule and dynamic certificate. The internal e2e
  needs no DNS name.
- **D-011 credentials.** No credential is tracked. Generated instance secrets use `GEN_LOCAL` (secret key, bootstrap admin
  password, PowerDNS API key). Operator-supplied real credentials use `ASK_EXTERNAL:<KEY>` (env `<KEY>`, else `CIU_SECRET_<NAME>`,
  else prompt; cached in the ciu store) and are mounted as files; non-secret operator facts live in the gitignored `.env.live`
  (committed `.env.live.example`, empty values). Live-tier tests hard-fail on a missing value, never skip. The deployed lane is
  on-demand (not part of `release-gate`).

## 3. Work packages

Routes: author on one route, independent review on the other; every merge needs a MERGE verdict; gates only via `run-gate`.
"A=ds" = author deepseek (review luna); "A=luna" = author luna (review deepseek).

| WP | Backlog | Content | Route | Depends |
|---|---|---|---|---|
| WP0 | B041 | R2 close-out: R2 lane test lists include the survivor files (done in `assay.toml`), rerun all four R2 lanes on the stable commit, triage survivors | controller + ds | - |
| WP1 | B042 | Config hygiene: one source for the PowerDNS URLs (internal URL derived from stack config, public URL from topology); delete `POWERDNS_PROXY_*`, the `/backend-powerdns` path and `POWERDNS_SOA` from `.env.defaults`; `POWERDNS_API_KEY` becomes a `GEN_LOCAL` ciu secret (compose + seed hook read it through ciu, not the shell); `.env.operator` keeps only operator facts; drift tests | A=ds | - |
| WP2 | B043 | Trusted-proxy hops: `TRUSTED_PROXY_HOPS` setting (fail-fast, default 0 in `.env.defaults`, 1 in app-local/public via stack config); `ProxyFix` built from it; every raw `request.headers.get('X-Forwarded-For')` read in `api/account.py` replaced by `request.remote_addr`; unit tests through the real middleware (forged header, 0/1/2 hops); docs/SECURITY.md | A=luna | - |
| WP3 | B044 | Webhoster probe: `scripts/test-webspace-forwarded-headers.php` in vbpub (sibling of the existing `test-webspace-*` scripts) that reports the headers/remote address a PHP request sees behind the hoster's front end, and a short runbook; the tarball default (`app-defaults.env`) stays 0 until the operator has run it | A=ds (vbpub worktree) | - |
| WP4a | B045 | DONE (section 6). ciu spike (read-only, no code): confirm on 7.24 (a) profile-derived switches for publish/labels flags, (b) shared-infra join of a worktree to the primary's PowerDNS, (c) one `GEN_LOCAL` key shared by two stacks, (d) `ASK_EXTERNAL` non-interactive behaviour, (e) `ciu check` clean on the current config; write findings to the plan, file backlog entries for every gap | controller | - |
| WP4b | B046 | Modern ciu config: `environment_tag` from instance id for worktrees, profiles `internal`/`public` with flags under `[topology.*]`, templates branch on them (port 53 publish, traefik labels, guard, cookie secure), hooks and compose without hand-formed names, `ciu check` clean, dead rendered artifacts removed | A=ds | WP4a, WP1 |
| WP5 | B047 | `public` stack: PowerDNS singleton (data dir not inside the repo checkout, pinned image, port 53, API behind traefik+guard), sub-zone create/delete helper, app container with `TRUSTED_PROXY_HOPS=1`, `naf-<instance>.<PUBLIC_FQDN>` Host rule, seeding of the delegated-zone backend via the hook (end-to-end tested, not only unit) | A=luna | WP4b, WP2 |
| WP6 | B048 | Credentials: `ASK_EXTERNAL` secrets for SMTP/IMAP and netcup CCP, `.env.live.example`, delivery as files into the app container (mail/netcup configuration from the secret files at first boot, not from the DB seed on every `up`), docs in `DEV_INFRA_SETUP.md` | A=ds | WP4b |
| WP7 | B049 | Deployed e2e lane `e2e-public` (on-demand): preflight (stack up, credentials present, zone delegated) that fails with one message each; the existing UI suite pointed at the public frontend through `tls-edge` (guard credentials from `.env.guard`); live tests wired and hard-failing: DNS propagation through the public resolver path, TLS chain, real mail round trip (SMTP out, IMAP in), real netcup CCP read; session sub-zone create/delete | A=luna | WP5, WP6 |
| WP8 | B050 | cmru versions: targets for `alpine` (pdns init), the `python` bases of the geoip/netcup mocks and the runners, `cmru versions check` in the release gate, the drift test covers every stack image, no floating tag remains | A=ds | - |
| WP9 | B051 | Internal-profile e2e variant: the same suite against the app container on the instance network by container name (no TLS, no DNS), proving the container image path; replaces nothing in the hermetic tier | A=ds | WP4b |
| WP10 | B052 | Docs + closeout: `DEV_INFRA_SETUP.md`, `TESTING_INFRASTRUCTURE.md`, `SECURITY.md` (proxy trust), `FEATURES.md`/`CHANGELOG.md`, `STATE.md`, release-gate + e2e on the final HEAD, R2 evidence, push | controller | all |

Order: WP0, WP1, WP2, WP3, WP8 in parallel (no shared files except `.env.defaults`; WP1/WP2 touch different keys, reviewed
separately); WP4a immediately; then WP4b -> WP5/WP6/WP9 -> WP7 -> WP10.

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
| (a) per-deployment-type switches | Templates and hooks can read the selection: `ciu.selected_profiles` / `ciu.deployed_stacks` (CONSUMERS section 10, S3.12), e.g. `external.enabled = {{ 'public' in ciu.selected_profiles }}`. This replaces the `topology_overrides` idea of D-008: profiles pick the stacks and the flags derive from the selection; nothing global is overridden. |
| (b) worktree joins the primary's PowerDNS | `ciu up --shared-infra` joins the reference instance's network; `--shared-infra-ref-services <alias>` writes a CIU-derived, re-authenticated `[topology.services.<alias>] internal_host/internal_port` (CONFIG S16.1a, CONSUMERS section 17). Use it for `powerdns`; never hand-type the primary's container name. |
| (c) one generated key across stacks | `GEN_LOCAL:<name>` lives in the PROJECT store `<repo-root>/.ciu/secrets/<name>` (S4.9): shared by all stacks of ONE checkout. A joined worktree has its own store, so it cannot read the primary's PowerDNS key from there; supply it with `ASK_EXTERNAL`/`ASK_FILE` in the worktree (WP5 decides; a backlog entry is filed once tested, since stacks cannot be brought up from managed worktrees yet, CIU-176). |
| (d) `ASK_EXTERNAL` non-interactive | Aborts when no value is supplied (S4.13), which is the hard-fail the live tier wants; the answer is cached in the store. |
| (e) `ciu check` | PASS on main. One WARN: `.gitignore` lacks the ciu worktree artifacts (`ciu.worktree-instance.json`, `*.tmp` instance files). Fixed in WP4b. |
| names | `container_name` stays explicit; worktrees isolate via `deploy.environment_tag = "$INSTANCE_ID"` (CONSUMERS section 26); ciu 7.24 refuses to start on a name owned by another checkout (CIU-104). v8 derives names (`SPEC-V8` S4.2) and forbids `container_name` in templates; moving there later means deleting the line. |

## 7. Risks

Rate limits of the certificate authority when many frontends are created, host firewall for 53, behaviour of the webhoster front end
(WP3 probe), whether `ciu status --json` exposes enough endpoint facts for a lane preflight (filed as run-gate RG-261).
