# naf — project state (single point of truth)

**Last synced: 2026-11-13 (B093 PowerDNS series decision and implementation in progress; the rest of this file is older and kept as written).** Start here. This dashboard reflects the *current* state of
netcup-api-filter; the direction spine lives in [1-north-star.md](1-north-star.md),
[2-product-definition.md](2-product-definition.md), [3-roadmap.md](3-roadmap.md), and
[4-backlog.md](4-backlog.md); decisions live in [decisions.md](decisions.md) (D-###), and
[handoffs/](handoffs/) holds open carved tasks / [archive/](archive/) completed material. When those disagree with reality, this file is corrected
first; the July-2026 review that seeded the backlog is `docs/deprecated/FOLLOWUP_REVIEW_2026-07-16.md`.

## What naf is

A Flask app that fronts DNS-provider APIs (netcup today; PowerDNS/BYOD in progress) with
**scoped, audited** token + account authorization, deployed to a Passenger shared webhoster and
(newly) self-hostable as a container. Settings live in the `settings` DB table; the gate is
`run-gate gate` (the only ship signal).

- **Gate: green (2026-11-05)** — `run-gate gate`: `unit-py311` 443 passed, `unit-py314` (assay R0), `trove`; whole-target R1 floors are the measured baseline and only ratchet up. R3 canaries and R2 mutation (token_auth, account_auth, recovery_codes, utils) are declared in `assay.toml`; results are recorded below as they land. Targets: py3.11 (Passenger) and py3.14 (OCI). e2e uses the estate pwmcp instance (`PWMCP_NETWORK`).
- **Version: `naf-v0.1.0`** (cmru `scm`, first tag pending).

## Deployed e2e and modern-ciu migration (M9, plan `docs/plans/deployed-e2e-and-modern-ciu-2026-11.md`, F028/F029)

Controller-driven by the migration session of 2026-11-11 (handoff `.controller-state/HANDOFF.md (gitignored)`); every change below was authored on one Codex route and
reviewed independently on the other, with gates through `run-gate`.

| Package | State | Evidence |
|---|---|---|
| WP1 (B042) PowerDNS config hygiene | merged (`ed42b97`) | unit-py311 1050 passed; stale keys gone, drift tests |
| WP2 (B043) proxy trust | merged (`51083e3`, plus fixes `177bd79`, `43216d0`) | `TRUSTED_PROXY_HOPS`, `PUBLIC_BASE_URL`, host-only cookies, ten raw XFF reads removed, default-deny static guard; unit-py311 1175, unit-py314 PASS on the branch head |
| WP3/WP3b (B044/B054) webhoster probes | merged in vbpub (`scripts/test-webspace-forwarded-headers.php`, `scripts/test-webspace-passenger-forwarded-headers/`) | **operator action pending:** run both probes against the webhoster, then decide the tarball hop count (shipped default stays 1, unverified) |
| WP8 (B050) cmru versions cover every image | merged (`c2d31a4`) | series decision made 2026-11-13: move naf's backend to PowerDNS 5.1 (`pdns-auth-51`); B093 updates the target and stack; resolver records landed in `9847b7b`, final gates pending |
| B093 PowerDNS 5.1 migration | implementation on `pdns51`; final gates pending | stack and zone bootstrap target 5.1.5; cmru resolution recorded in `9847b7b`; B095 tracks real-start verification |
| ciu CIU-193/205/206 | merged in vbpub main, unreleased (ciu 7.25.0 planned by the vbpub controller) | worktree-safe `ciu down`, selection facts + selection record under `ciu up --dir`, `ASK_HOST` host-wide secret |
| WP4b-1/WP4b-2, WP5, WP6, WP7, WP9, WP11 | open | wait for ciu 7.25.0 (identity, deployment type, public stacks, credentials, `e2e-public`) |
| Final gates | green | release-gate PASS on `43216d0` (unit py311/py314, R1 floors, R3 canaries), e2e PASS on `177bd79`, `cmru versions check naf` matches, pushed to origin (no tags) |
| R2 close-out (B041/WP0) | open | lane lists fixed (`d077df0`); rerun the four lanes on one stable commit |
| E2E/pwmcp review backlog (B057..B071) | filed `2026-11-12`; B057/B058 in progress on `fixup3-form-contracts` | [4-backlog § B-E2E-REVIEW](4-backlog.md#b-e2e-review-2026-11-12-independent-e2epwmcp-review) |

Open items for the operator: probes on the webhoster, `.env.live` credentials and delegation/A records for the public tier, provider firewall for port 53, and B095 PowerDNS real-start verification.

## Release & infra model (current)

Three tools, clean split (see `AGENTS.md` → "Build, deploy, run"):

| Concern | Tool | Detail |
|---|---|---|
| Local dev/test | `run-local-tests.sh` → `build_deployment.py --local` | builds `deploy-local/`, drives `ui_tests/` |
| Release (publish) | **cmru** (`cmru.toml`) | py3.11+py3.14 OCI images + cp311 Passenger tarball variant + variant installer, `scm` versioned |
| Deploy (webhoster) | **ciu** `up --host --thin` | pushes a tarball, runs `scripts/activate.py` (extract → `SECRET_KEY` preserve → touch `tmp/restart.txt` → health-probe) |
| Dev infra | **ciu** stacks | containerized app (`app-local`), pwmcp browser (e2e), mailpit/geoip/netcup mocks, PowerDNS, host-traefik edge, cgroups+KSM governance |

Webhosting deploys are **greenfield** (fresh seeded DB each release; only `SECRET_KEY` carries
across). naf has **no Vault** — secrets are gitignored `.env.*`; `ciu` `ssh_key` is a file path.

## Handoffs — real state (files were stale; corrected here)

Done handoffs are in [`archive/`](archive/); only P06 remains open in [`handoffs/`](handoffs/).

| Handoff | State | Evidence / note |
|---|---|---|
| naf-I03 containerized build | ✅ DONE | `860c825`; frontmatter still said "PAUSED" — corrected |
| naf-I04 host-traefik exposure | ✅ DONE | `3049c49`; premise's "changes deploy.sh" is obsolete (deploy.sh retired) |
| naf-P07 2FA lockout + dead auth | ✅ DONE | `3434659` (merged) |
| naf-P08 client-IP trust (XFF) | ✅ DONE | `521b788` (merged) |
| naf-P09 reset/invite password policy | ✅ DONE | `675a338` (merged) |
| naf-P05 workspace FQDN | ✅ ARCHIVED | O1 merged; O2 superseded by naf-I04 because PUBLIC_FQDN now comes from `ciu.env`; no residual work |
| naf-P06 test-suite integrity | 🟡 PARTIAL | O1 (route floor) ✅ part 1; **O2/O3 open** (kill can't-fail tests) — premise still valid and now **unblocked** (e2e gate + pwmcp live) |

## Implemented since the review

- **Authorization (M1/M2):** record-level REST scope (P01), portal realm scope (P02), audit
  trail no longer crashes (P03). **Read-scope leak (M1.3) still open.**
- **Auth hardening (B-AUTH — whole section):** TOTP lockout, XFF spoofing, reset/invite policy,
  dead-auth removal (P07/P08/P09).
- **Config (M3):** settings type round-trip + SMTP key (P04); FQDN guard (P05 O1).
- **Infra + release:** ciu adoption, containerized build (py3.11/3.14 gate), host-traefik
  edge, pwmcp e2e container, KSM, and the full cmru release model (P2/P3/P4 — `deploy.sh`
  retired). B-BUILD demo-seed fix.

## Open work — by priority

**Top priorities (highest value):**
1. **B-PORTAL notification-preference plumbing** (`notification_service.py`) — operator's #1; the base the rest of the portal sits on. M
2. **B-PORTAL token-usage analytics view** — highest-leverage; data already in `ActivityLog`; P03 dep landed. M
3. **B-UI read-scope leak** (`token_auth.py:600` filter by hostname, not type) — real cross-tenant read exposure, verified present. M
4. **B-DEAD delete `filter_proxy.py`** — still registered in `passenger_wsgi.py`; the un-shadowed DDNS `GET` is a live prod 500. S
5. **B-DATA audit-cascade + FK enforcement** (`models.py:611` + `PRAGMA foreign_keys=ON`) — token delete silently wipes audit history. M
6. **B-UI two broken routes** (`/account/docs` 500, `/admin/app-logs` traceback) — user-visible, invisible to the suite. M

**Also open (see [4-backlog.md](4-backlog.md) for file:line):** B-PORTAL (webhook, self-service 2FA unlock,
background SMTP dispatch, security-alert stub), B-DEAD (`netcup_client_mock.py`, `backends/`
wiring = D-002/naf-P20), B-DATA (plaintext credential logging), B-CONFIG (hardcoded TFA
constants, example-config live values, dead TOML sections), B-QUALITY (duplicated
`get_netcup_client`, rate-limiter `memory://`), B-TESTS (`pytest.ini` strictness, naf-P06 O2/O3),
and B-API-AUTH (HTTP SCRAM-SHA-256 for scoped DNS API clients; added 2026-10-15).

## Doc debt — ✅ reconciled (2026-07-21)

Live docs are current. **B-INFRA-DOCS** (reverse-proxy → host-traefik) and **B-DEPLOY-DOCS**
(`deploy.sh` → cmru release + ciu deploy) were swept across all live `docs/`, `tooling/`,
`ui_tests/`, and `.vscode/` markdown; `docs/CERTIFICATE_MOUNTING.md` is now a "removed in naf-I04"
stub. Only historical `docs/deprecated/` and `docs/plans/testing-{hardening,overhaul}/` keep the
old terms **by design** (read for reasoning, never as current status). **Remaining (non-doc):**
(`tooling/run-ui-validation.sh` was deleted 2026-11-05; the e2e lane replaces it.) Historically it drove the old nginx flow — superseded by
traefik/ciu (tracked in backlog B-INFRA-DOCS).

## Decisions still open

- **D-002** — wire `get_backend_for_realm()` into live paths, or guard realm creation as
  not-yet-live (naf-P20 / M6).
- **D-003** — Alembic vs. formally-documented greenfield (M7).

See [decisions.md](decisions.md) for the full D-### log. The superseded CMRU release plan and
both INFRA plans were archived on 2026-07-21 because their recorded work is merged.
