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

(appended as the session proceeds)
