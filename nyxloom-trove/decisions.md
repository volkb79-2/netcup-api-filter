# Decisions inbox — netcup-api-filter

Product/infra calls that block or shape handoffs. A handoff naming `depends_on: [D-NNN]`
is held by the daemon until the decision resolves. Decisions are for *product* gaps — a
mechanical gap is a BLOCKED exit, not a decision (AUTHORING.md §5/§6).

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

**Status:** OPEN · raised 2026-07-16 · blocks: naf-P20, and any Cloudflare/Route53 work

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
