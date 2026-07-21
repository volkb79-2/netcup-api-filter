# naf — project state (single point of truth)

**Last synced: 2026-07-21.** Start here. This dashboard reflects the *current* state of
netcup-api-filter; the detail lives in [roadmap.md](roadmap.md) (milestones),
[backlog.md](backlog.md) (un-carved review items), [decisions.md](decisions.md) (D-###), and
[handoffs/](handoffs/) (open carved tasks) / [archive/](archive/) (completed). When those disagree with reality, this file is corrected
first; the July-2026 review that seeded the backlog is `docs/deprecated/FOLLOWUP_REVIEW_2026-07-16.md`.

## What naf is

A Flask app that fronts DNS-provider APIs (netcup today; PowerDNS/BYOD in progress) with
**scoped, audited** token + account authorization, deployed to a Passenger shared webhoster and
(newly) self-hostable as a container. Settings live in the `settings` DB table; the gate is
`tooling/test-runner/testing-exec.sh` (the only ship signal).

- **Gate: green — `unit` 441 × {py3.11, py3.9, py3.14}** (2026-07-21).
- **Version: `naf-v0.1.0`** (cmru `scm`, first tag pending).

## Release & infra model (current)

Three tools, clean split (see `AGENTS.md` → "Build, deploy, run"):

| Concern | Tool | Detail |
|---|---|---|
| Local dev/test | `run-local-tests.sh` → `build_deployment.py --local` | builds `deploy-local/`, drives `ui_tests/` |
| Release (publish) | **cmru** (`cmru.toml`) | py3.14 OCI image + cp39/cp311 Passenger tarball variants + variant installer, `scm` versioned |
| Deploy (webhoster) | **ciu** `up --host --thin` | pushes a tarball, runs `scripts/activate.py` (extract → `SECRET_KEY` preserve → touch `tmp/restart.txt` → health-probe) |
| Dev infra | **ciu** stacks | containerized app (`app-local`), pwmcp browser (e2e), mailpit/geoip/netcup mocks, PowerDNS, host-traefik edge, cgroups+KSM governance |

Webhosting deploys are **greenfield** (fresh seeded DB each release; only `SECRET_KEY` carries
across). naf has **no Vault** — secrets are gitignored `.env.*`; `ciu` `ssh_key` is a file path.

## Handoffs — real state (files were stale; corrected here)

Done handoffs are now in [`archive/`](archive/) (with P01–P04); only the open ones (P05, P06)
remain in [`handoffs/`](handoffs/).

| Handoff | State | Evidence / note |
|---|---|---|
| naf-I03 containerized build | ✅ DONE | `860c825`; frontmatter still said "PAUSED" — corrected |
| naf-I04 host-traefik exposure | ✅ DONE | `3049c49`; premise's "changes deploy.sh" is obsolete (deploy.sh retired) |
| naf-P07 2FA lockout + dead auth | ✅ DONE | `3434659` (merged) |
| naf-P08 client-IP trust (XFF) | ✅ DONE | `521b788` (merged) |
| naf-P09 reset/invite password policy | ✅ DONE | `675a338` (merged) |
| naf-P05 workspace FQDN | 🟡 PARTIAL | O1 (`.env.services` guard) ✅; **O2 premise superseded** — PUBLIC_FQDN now comes from `ciu.env` (INFRA-4), not `post-create.sh` |
| naf-P06 test-suite integrity | 🟡 PARTIAL | O1 (route floor) ✅ part 1; **O2/O3 open** (kill can't-fail tests) — premise still valid and now **unblocked** (e2e gate + pwmcp live) |

## Implemented since the review

- **Authorization (M1/M2):** record-level REST scope (P01), portal realm scope (P02), audit
  trail no longer crashes (P03). **Read-scope leak (M1.3) still open.**
- **Auth hardening (B-AUTH — whole section):** TOTP lockout, XFF spoofing, reset/invite policy,
  dead-auth removal (P07/P08/P09).
- **Config (M3):** settings type round-trip + SMTP key (P04); FQDN guard (P05 O1).
- **Infra + release:** ciu adoption, containerized build (py3.9/3.11/3.14 gate), host-traefik
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

**Also open (see backlog.md for file:line):** B-PORTAL (webhook, self-service 2FA unlock,
background SMTP dispatch, security-alert stub), B-DEAD (`netcup_client_mock.py`, `backends/`
wiring = D-002/naf-P20), B-DATA (plaintext credential logging), B-CONFIG (hardcoded TFA
constants, example-config live values, dead TOML sections), B-QUALITY (duplicated
`get_netcup_client`, rate-limiter `memory://`), B-TESTS (`pytest.ini` strictness, naf-P06 O2/O3).

## Doc debt — ✅ reconciled (2026-07-21)

Live docs are current. **B-INFRA-DOCS** (reverse-proxy → host-traefik) and **B-DEPLOY-DOCS**
(`deploy.sh` → cmru release + ciu deploy) were swept across all live `docs/`, `tooling/`,
`ui_tests/`, and `.vscode/` markdown; `docs/CERTIFICATE_MOUNTING.md` is now a "removed in naf-I04"
stub. Only historical `docs/deprecated/` and `docs/plans/testing-{hardening,overhaul}/` keep the
old terms **by design** (read for reasoning, never as current status). **Remaining (non-doc):**
`tooling/run-ui-validation.sh` still drives the old nginx flow — delete or rewrite against
traefik/ciu (tracked in backlog B-INFRA-DOCS).

## Decisions still open

- **D-002** — wire `get_backend_for_realm()` into live paths, or guard realm creation as
  not-yet-live (naf-P20 / M6).
- **D-003** — Alembic vs. formally-documented greenfield (M7).

See [decisions.md](decisions.md) for the full D-### log.
