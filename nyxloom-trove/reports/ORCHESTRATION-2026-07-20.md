# Manual orchestration session — 2026-07-20

nyxloom is down for development, so the `naf` trove is driven by hand: the orchestrator
(Opus) refreshes carves, fans out **sonnet** implementation agents in isolated worktrees,
and does review-merge. This log records the decisions taken autonomously so they can be
reviewed later. Base: `main` @ `488ac2d`.

## Reassertion against current `main` (all five carves still valid)

The carves were written at `adcba7d`; `main` has since moved (P03 audit fix, the security
LHF commit, the gate container, the doc sync). Re-verified each defect is **still present**
and refreshed the line numbers:

| Pkg | Defect | Verified at | Line drift |
|-----|--------|-------------|-----------|
| naf-P01 | `delete_record` calls `check_permission` with no `record_name`; `update_record` validates request body not stored record | `dns_api.py:420` (delete), `:317` (update), `:110` (list) | 423→420 etc. |
| naf-P02 | portal create scope-checks only `host` realms; edit/delete mutate by id with no hostname check | `account.py:1513` (create), `:1574` (edit), `:1659` (delete) | 1505→1513 etc. |
| naf-P04 | `passenger_wsgi` double-JSON-encodes 10 `set_setting` sites; `password_reset` reads only `email_config` | `passenger_wsgi.py:246..568`, `password_reset.py:459,586` | — |
| naf-P05 | `.env.services:85` unconditional `${PUBLIC_FQDN}` | `.env.services:85` | — |
| naf-P06 | `route_discovery.py:153` bare `except` → stale static fallback | `route_discovery.py:153` | — |

"current dstdns state" in the request is read as **current `naf` main** — the packages
don't depend on dstdns; they only share the gate *pattern* (mirrored from dstdns/vbpub),
which is unchanged. Flag if that reading is wrong.

## Cross-cutting concerns (fix B's assumptions before starting B)

- **CC-1 · P02 vs P03 (landed).** P03 already fixed the `ActivityLog` writes in the same
  `account.py` routes P02 edits (they now pass `source_ip` + `status_reason`). **P02 must
  NOT touch the audit writes** — only insert a hostname-scope check *before* each netcup
  mutation. Baked into the P02 refresh + agent prompt.
- **CC-2 · P01 vs P02 (parallel).** Both add "resolve record_id → stored record, then
  validate its hostname against the realm." They live in different modules (token-auth
  `dns_api.py` vs session-auth `account.py`). **Decision D-004:** each implements its own
  local helper; do NOT introduce a shared cross-module helper now — it would force both
  agents to touch one file (merge conflict + premature coupling). Both MUST use
  `realm.matches_hostname` as the scope predicate for consistency. A later unifying
  refactor is a backlog item, not this batch.
- **CC-3 · P04 scope.** All 10 `set_setting(json.dumps(...))` sites double-encode, not
  just `netcup_config`. Four of them (`session/admin_security/logging/notifications`
  _config) are read by nobody (backlog B-CONFIG) — fixing their encoding is harmless and
  keeps the file consistent, so fix all 10.
- **CC-4 · file-set disjointness.** The parallel batch touches disjoint files
  (`dns_api.py` / `account.py` / `passenger_wsgi.py`+`password_reset.py` + one new test
  each), so worktree branches merge without conflict.

## Batch selection

**Parallel now (worktree fan-out, gate=unit, sonnet):** naf-P01, naf-P02, naf-P04. All
are code + a new unit test, fully validated by the `unit` gate.

**Deferred (this orchestrator, after the batch):** naf-P05 (shell/docs; gate=trove; O2
needs a post-create run I can only partially exercise without a devcontainer rebuild) and
naf-P06 (mostly `ui_tests`; full validation needs the `e2e` gate = deployed app + pwmcp,
not available inline). These get done with their validation gaps documented, not hidden.

## Execution model (validated)

Manual worktrees under `.worktrees/<pkg>` branched from `main` HEAD (NOT origin — local
main carries all the above). Agents are pinned to their worktree by absolute path, edit +
write tests there, and **self-gate** with the now worktree-aware
`./tooling/test-runner/testing-exec.sh unit` (runs 3.11 + 3.9 against the worktree). The
orchestrator reviews each worktree diff, merges to `main`, and re-gates on `main` before
the next merge. Proven: a worktree gate emits `[gate] worktree: … -> …/.worktrees/<pkg>`
and runs pytest against the worktree's own files.

## Decisions filed this session

- **D-004** (below, decisions.md): P01/P02 record-resolution helpers stay per-module.

## Dispatch / review / merge log

### Batch 1 — P01/P02/P04 fanned out (sonnet, worktrees), P06-part-1 by orchestrator

Dispatched 3 sonnet agents in parallel worktrees; each self-gated. Reviewed against git
state, not the reports (AUTHORING §7).

- **naf-P02** (`46990c1`, wt/naf-p02) — ACCEPTED. `matches_hostname` for all realm types
  on create; resolve-by-id + scope check before mutation on edit/delete; `ActivityLog`
  writes left untouched (CC-1 honored). `_realm_fqdn_for` correctly maps apex→bare zone.
  15 backend-truth tests incl. the subtle subtree-apex inclusion (`subdomain`) vs
  exclusion (`subdomain_only`). Agent gate: 398 passed on 3.11 + 3.9.
- **naf-P04** (`121b23b`, wt/naf-p04) — ACCEPTED. Found and fixed **12** double-encode
  sites, not the 10 I named (2 had drifted in since the carve — `free_domains_config`,
  `platform_backends_config`); good grep discipline. Shared `_get_smtp_config()` helper;
  all three senders now read `smtp_config` then `email_config`; None-on-invalid matches
  the old False early-returns. O1/O2 exercised via a real `passenger_wsgi` exec_module in
  a subprocess (not just round-trip). Agent gate: 394 passed on 3.11 + 3.9.
- **naf-P01** (wt/naf-p01) — ACCEPTED WITH ORCHESTRATOR FIX. The agent did NOT commit
  (report truncated mid-gate); code was sound: resolve-by-id, authorize against the
  STORED record's hostname/type, and re-check the TARGET on a move (better than the
  carve spec). 7 backend-truth tests, incl. move-out-of-scope.
  **Review finding (regression) — FIXED by orchestrator before merge:** the agent
  removed the upfront zone-level `check_permission` and fetched the record FIRST. That
  let an out-of-scope caller (a) trigger an upstream fetch for any zone and (b) tell
  404 (no such id) from 403 (id exists, not yours) — a cross-zone record-existence
  oracle. Restored a cheap zone/op gate before the fetch in both `update_record` and
  `delete_record` (this is what the original delete path had; the agent dropped it).
  Documented here for later discussion — it's the kind of subtle security regression a
  cheap-model implement + fast merge can introduce, which is exactly why review-merge
  re-derives rather than trusts the report.
- **naf-P06 part 1** (`2f298a2`, wt/naf-p06, orchestrator) — route discovery now raises
  loudly instead of the stale-static fallback; `discover_routes_static()` deleted; smoke
  suite asserts an admin/client route floor; new `tests/test_route_discovery_unit.py`
  proves the contract under the UNIT gate (added beyond scope.touch so O1 is provable
  without e2e). Gate: 386 on 3.11. Part 2 (ui_tests can't-fail cleanup, needs e2e) TBD.

Cross-cutting check passed: the four branches touch strictly disjoint files (dns_api.py /
account.py / {passenger_wsgi,password_reset}.py / {route_discovery,test_route_smoke}.py +
four disjoint new test files), so they merge without conflict and a single combined gate
on `main` is a valid signal for the batch.

### Batch 1 merged + confirmed

Merged `--no-ff` per package (ebffa4e P02, 2d0d35e P04, 49d1711 P06, 2035480 P01).
**Combined dual-interpreter gate on `main`: 419 passed on python 3.11 AND 3.9** (373
baseline + 7 + 15 + 11 + 3). Handoffs P01/P02/P04 archived with reports; roadmap updated.

### naf-P05 (O1) — orchestrator, partial

The critical half of the "rebuild bomb" is fixed and merged: `.env.services` guards the
`${PUBLIC_FQDN}` derivation, so `set -u` sourcing no longer aborts every consumer. Test
`tests/test_env_services_sourcing.py` (shells out) runs in the unit gate. My first test
assertion was buggy (`${VAR:-<unset>}` masked empty-vs-unbound) — caught by the gate, not
merged; the underlying `.env.services` fix was correct throughout (rc 0). **O2 deferred**
(post-create reverse-DNS write; needs a real rebuild to validate) — handoff left open.

## Session outcome & what remains

Landed this session (all gated 3.11 + 3.9): **naf-P01, P02, P04, P05-O1, P06-part-1**.
The authorization boundary is closed on every mutation path (REST + portal); the settings
double-encode that 500'd the DNS API on real config is fixed; the devcontainer rebuild
bomb is defused; route discovery can no longer silently shrink the suite.

Open, ready for the next session or the daemon once it can reach this repo (D-001):
- **naf-P05 O2** — post-create writes PUBLIC_FQDN (reverse-DNS).
- **naf-P06 part 2** — delete/restore the can't-fail ui_tests (needs the e2e gate).
- Backlog buckets B-AUTH … B-DOCS and decisions D-002 (backends abstraction) / D-003
  (data-preserving upgrades) — all file:line-specific in backlog.md.

Process notes worth keeping (also in project memory): worktree fan-out + review-merge
works well; trust git state over agent receipts (one agent didn't commit; one introduced
a security regression its report omitted); the worktree-aware gate makes per-package
isolated self-gating cheap.
