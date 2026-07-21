# Decisions inbox — netcup-api-filter

Product/infra calls that block or shape handoffs. A handoff naming `depends_on: [D-NNN]`
is held by the daemon until the decision resolves. Decisions are for *product* gaps — a
mechanical gap is a BLOCKED exit, not a decision (AUTHORING.md §5/§6).

---

## D-004 — P01/P02 record-resolution helpers stay per-module (not shared)

**Status:** DECIDED (orchestrator, 2026-07-20) · shapes: naf-P01, naf-P02

naf-P01 (REST DNS API) and naf-P02 (account portal) both need the same shape: resolve a
`record_id` to the stored record within a zone, then validate that record's hostname
against `realm.matches_hostname`. The tempting move is one shared helper.

**Decision: keep them per-module** (`api/dns_api.py` and `api/account.py` each get their
own small helper). Reasons: (1) they run in different auth contexts — token-auth vs
session-auth — and resolve config/clients differently; (2) a shared helper forces both
parallel agents to edit one file, creating a merge conflict and premature coupling for
~10 lines of duplication. Both MUST use `realm.matches_hostname` as the predicate so the
*semantics* are identical even though the code is duplicated. A later unifying refactor
(once both have landed and the real shared surface is visible) is a backlog candidate,
not part of this batch.

---

## D-005 — B-AUTH batch partition (2026-07-20b): three disjoint packages

**Status:** DECIDED (orchestrator, 2026-07-20) · shapes: naf-P07, naf-P08, naf-P09

The five B-AUTH items span overlapping files, so the fan-out is partitioned by **file
ownership** to keep parallel worktrees mergeable:

- **naf-P07** owns `account_auth.py` (TOTP-branch lockout, remove dead
  `request_password_reset`, remove dead `generate_secure_password`) **plus** the single
  dead-import line `api/admin.py:31`. Item 5 (`generate_secure_password`) must be **atomic**
  — its definition and its lone import live in one worktree, else the package fails its own
  gate on an `ImportError`.
- **naf-P08** owns the client-IP sites in `api/admin.py` (`_get_client_ip:90`, audit sites
  :1207/:1291) and `api/ddns_protocols.py:get_client_ip`. Fix = trust `request.remote_addr`
  (ProxyFix `x_for=1`, `app.py:75`), mirroring what `dns_api.py` already does.
- **naf-P09** owns `api/account.py` (reset/invite password policy :220/:258 **and** the
  leftmost-XFF reset-token IP-binding site :210) and `password_reset.py`
  (`complete_password_reset` validates nothing today).

Only P07∩P08 share a file (`api/admin.py`) at disjoint hunks (line 31 vs 90/1207/1291) —
git auto-merges. **Merge P07 first, then P08**, re-gating between; P09 is fully disjoint and
merges in any order.

---

## D-006 — infra plan decisions (decided autonomously; interview was hook-blocked)

**Status:** DECIDED (orchestrator, 2026-07-20) · shapes: INFRA-1..4 · **REVIEW-ME**

I tried to interview the operator on the five open infra decisions; the interactive
question was **denied by a hook** (background session, operator away). Per standing
instruction ("make decisions on your own, don't wait for signoff; write them down for later
review"), I decided them with the plan's recommended options. **All are open to reversal on
review** — flagged REVIEW-ME. See `INFRA-PLAN-2026-07-20.md`.

- **E · sequencing:** execute **INFRA-1 (ciu adoption) + INFRA-2 (pwmcp e2e) now** (additive,
  validatable on this host); **carve INFRA-3 (containerized build) + INFRA-4 (host traefik) as
  handoffs and PAUSE for operator review** before touching `deploy.sh`/`build_deployment.py`.
  Rationale: 3+4 change the production artifact pipeline and dev edge and can't be validated by
  the unit gate — they get a checkpoint; 1+2 don't touch the deploy path.
- **A · traefik FQDN (INFRA-4):** deferred into the INFRA-4 handoff for operator confirmation;
  default proposal = a subdomain under the **same wildcard base dstdns uses** (read from
  dstdns `ciu.env` `PUBLIC_FQDN`), i.e. `naf.<base>`. Not committed until INFRA-4 review.
- **B · pwmcp (INFRA-2):** **vendor naf's own `infra/pwmcp/` ciu stack** on `naf-dev-network`
  (declarative, matches dstdns, self-contained) rather than attaching the dstdns-owned shared
  `dstdns-shared-local-pwmcp` (which sits on dstdns's network and would couple naf's e2e to a foreign
  runtime container).
- **C · ciu depth (INFRA-1):** **full `.j2` template convention** (repo-root marker + stack
  templates + gitignore rendered outputs), matching dstdns — not the minimal `--shipped` path,
  which would leave the rendered-`ciu.toml`-as-source confusion in place.
- **D · exposure (INFRA-4):** app (HTTPS UI/API) + PowerDNS API edge get public traefik routes;
  Mailpit stays internal-only.

---

## D-007 — cross-stack config: the delegated DNS zone lives in `[topology.dns]`

**Status:** DECIDED (orchestrator, 2026-07-20) · shapes: backend-powerdns, app-local ·
**resolves the `wt/ciu-powerdns` review hold**

For e2e/public tests naf needs a real DNS backend: the operator delegates a public
(sub)domain whose NS points at this host's `PUBLIC_IP` where PowerDNS runs. That zone is
consumed by **two** stacks — `backend-powerdns` (must be authoritative for it) and
`app-local` (seeds a domain-root/backend so a user owns the zone and can create hosts under
it). It is app-level in *meaning* but **cross-stack** in *scope*, and for a released product
it is a placeholder a sysadmin fills in, not shipped data. So a per-stack `config.toml.j2`
(like dstdns `applications/worker-io`) is the wrong home.

**Decision (ciu precedent = `topology.external.public_fqdn`, read cross-stack by authentik +
reverse-proxy):** it lives in the GLOBAL marker as `[topology.dns] delegated_zone` — a
reserved-namespace topology fact that is a Jinja global in every stack template. Committed as
an env-ref placeholder `{{ env.get('NAF_DELEGATED_DNS_ZONE') or '' }}` (empty default so
render never hard-fails); the operator supplies the real value via `NAF_DELEGATED_DNS_ZONE`
in the environment (`ciu.env` / an `.env`), editing no committed file. **Not** a secret (a
zone name is public), **not** `[deploy.env.shared]` (that is for raw container env), **not**
`[registry.*]` (that is provisioning metadata).

**How each stack reads it (all plumbing already exists):**
- **backend-powerdns:** flatten `{{ topology.dns.delegated_zone }}` into a stack-local key; a
  `configfile` or `post_compose` hook creates/serves the zone via the pdns API, guarded on
  non-empty. This **replaces the invented SOA/zone defaults** that put `wt/ciu-powerdns` on
  hold — the values come from the operator, not guesses.
- **app-local:** read `{{ topology.dns.delegated_zone }}`; a `post_compose`/init step (DB/API
  seed, **not** writing into the RO app container) inserts the `ManagedDomainRoot`/
  `BackendService` row for the zone. DB-seed-from-a-global-fact has no dstdns precedent but
  reuses the existing hook plumbing (hooks receive the full merged config incl. `topology`).

`[topology.dns]` placeholder is added to the marker now; the two consuming implementations
(pdns zone-create hook + app backend-seed hook) are the remaining work. Exposure of the pdns
API is `naf-pdns.<public_fqdn>` behind the same basicauth guard as the app.

---

## D-001 — nyxloomd cannot reach this repo (blocks ALL dispatch)

**Status:** CARVED UPSTREAM · raised 2026-07-16 · blocks: every handoff in this trove
**Fix in flight:** `nyxloom-P27-project-mount-reachability` (vbpub commit `49abcaa`) —
carved into nyxloom's own trove, since this is a defect in nyxloom's infrastructure, not
ours. nyxloom is self-hosting (registry: dstdns, nyxloom, topos), so its daemon should
dispatch P27 itself. Follow-up B11 there covers the principled fix: derive the daemon's
project binds from the registry so `project add` cannot produce an unreachable project.

**Still an operator step after P27 merges:** `ciu up --dir nyxloom/nyxloomd` to rebuild
(the self-hosting caveat — a merge to daemon-core does not take effect until rebuild),
then `nyxloom project add` for this trove. P27 explicitly forbids the agent from doing
either, since it would be restarting the daemon that dispatches it.

The running `nyxloom-prod-nyxloomd` container mounts only:

    /home/vb/volkb79-2/vbpub    -> /workspaces/vbpub
    /home/vb/volkb79-2/dstdns   -> /workspaces/dstdns
    /home/vb/mdt--mounted-folders -> /home/vscode
    /var/run/docker.sock

There is **no mount for `/home/vb/volkb79-2/netcup-api-filter`**, so the daemon cannot
read this trove, lint it, or dispatch from it. This is exactly the access check
STANDARD.md says `init` performs.

Two sub-calls for the operator (both need a **prod daemon restart**, which is why this
is a decision and not a handoff):

1. Add the netcup mount to the nyxloomd container (its ciu/compose definition in the
   vbpub checkout) and restart it.
2. Register the project: `nyxloom project add` with this trove's `nyxloom.toml`.

Note `exec-nyxloom.py` matches a container whose name contains both `nyxloom` **and**
`controller`; the running one is `nyxloom-prod-nyxloomd`, so the wrapper silently falls
back to host mode. Either rename, set `NYXLOOM_CONTAINER=nyxloom-prod-nyxloomd`, or
widen the match — otherwise `exec-nyxloom` and the daemon disagree about which state is
authoritative.

**Until this resolves:** handoffs are authored and validated locally with
`./tooling/test-runner/testing-exec.sh trove` (a documented subset of `nyxloom lint`).

---

## D-002 — the `backends/` abstraction is dead code on the live DNS path

**Status:** DECIDED (a) — WIRE IT UP · resolved 2026-07-20 (operator) · raised 2026-07-16

**Resolution (operator, 2026-07-20):** Option **(a) — wire it up now.** Route
`dns_api`/`ddns_protocols` through `get_backend_for_realm()` so a realm bound to a
BYOD/PowerDNS backend actually executes against that backend rather than silently against
the platform netcup account. This is an **L-effort milestone**, carved as
`naf-P20-backends-wireup`, and it **sequences AFTER the B-AUTH batch (2026-07-20b)**: it
touches `dns_api.py` + `ddns_protocols.py`, colliding with naf-P08 (XFF client-IP), so it
cannot share the same parallel worktree wave. Prerequisite correctness fixes fold into it —
`backends/netcup.py:161` delete-by-omission (a silent no-op the mock hides), the
`update_record` priority-`0` drop, and `backends/powerdns.py:97` REPLACE-wipes-the-RRset /
hostname double-suffix / priority-drop. `docs/FEATURES.md` becomes true once it lands. See
roadmap M6.3.



`backends/registry.get_backend_for_realm()` — the documented core of realm→backend
resolution (AGENTS.md "Backends") — has **zero callers**. Both live DNS paths build a
`NetcupClient` directly from the single global `netcup_config` setting. So a realm bound
to a BYOD/PowerDNS `BackendService` passes `check_permission` and is then executed
against the *platform's* Netcup account. BYOD/PowerDNS work only for
`test_connection`/`list_zones` in the UI.

`docs/FEATURES.md` currently claims PowerDNS as a current capability and Cloudflare /
Route53 as "the abstraction is ready" — neither is true of the request path.

The product call — which way to close the honesty gap:

- **(a) Wire it up.** Route `dns_api`/`ddns_protocols` through `get_backend_for_realm()`.
  Effort L. Unlocks Cloudflare/Route53 (they become contained changes) and makes BYOD
  real. Must fix `backends/netcup.py:161` first (delete-by-omission is a silent no-op
  against the real API) and the PowerDNS create/hostname/priority bugs.
- **(b) Mark it not-yet-live.** Correct `docs/FEATURES.md`, guard realm creation against
  BYOD/PowerDNS backends so nobody can create a realm that silently targets the wrong
  account. Effort S. Honest, but leaves the abstraction dead.

Recommendation: **(b) now, (a) as a scoped milestone** — (b) removes an active
mis-routing footgun in one small change; (a) is real work that deserves its own carve.

---

## D-003 — greenfield deploys vs. data-preserving upgrades

**Status:** OPEN · raised 2026-07-16 · blocks: any "production data" milestone

Every webhosting deploy wipes and reseeds the DB. `run_lightweight_migrations` is
additive-only by design and explicitly not a migration system. Before real data can live
here, someone must decide: adopt Alembic (and freeze the additive-only escape hatch), or
formally keep greenfield and document it as the product's posture.

Gated by naf-P16 (FK enforcement + the audit-wipe cascade) — migrating a schema whose
cascades are wrong just preserves the wrong data faithfully.
