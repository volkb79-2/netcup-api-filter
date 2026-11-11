# naf controller handoff (written 2026-11-11 ~03:40 UTC, session `netcup-api-filter-84`, Sonnet 5.5)

Purpose: near-lossless resume after context compaction. Read this file IN FULL, then the prose extract
`/tmp/naf-ctl/resume-extract.md` (about 50k tokens, `nyxloom-harness extract --preset successor --tool-calls intent`) IN FULL,
then check every job in section 4 before doing anything else. Facts here beat memory.

## 1. Role and standing rules (operator = the user; autonomy was granted for the whole migration)
- I am the CONTROLLER: I plan, brief, dispatch authors/reviewers, verify, merge, clean up. Heavy work and ALL test/product execution
  happen in containers via `run-gate` (cockpit = inspect and drive only; 8 GiB cap, one process at a time).
- Shell for gates: `source /opt/mdt/venv/bin/activate`. Gate slots: ONLY `/home/vscode/vbpub-release-program-20261027/codex/gate-run.sh <run-gate args>`
  (two-slot wrapper; vbpub controller's request 2026-11-11), ONE slot at a time, never hold a slot for hours. Authors launched
  before that request still flock `gate.lock` directly (WP1, WP2).
- Author/reviewer on DIFFERENT routes. Routes: luna = `codex-impl.sh` default (gpt-6-luna max), deepseek = `CODEX_ROUTE=deepseek`
  (deepseek-v4.1-flash high). Kit: `/home/vscode/vbpub-release-program-20261027/codex/` (`codex-impl.sh <wt> <brief> <run> [resume <thread>]`,
  `job-check.sh <run> <wt-name> <luna|deepseek|none> <ABS report>`, outputs `runs/<run>.{jsonl,err,last.txt,done}`). Reviewers never edit
  the author's worktree (scratch dir only); EVERY report path in a brief must be ABSOLUTE (luna once wrote a relative path into its cwd).
  Fix by RESUME (thread id = first `thread.started` event), not relaunch. Every merge needs an independent `VERDICT: MERGE`.
  Commit trailers: `Co-Authored-By: Codex gpt-6-luna <noreply@openai.com>` / `Co-Authored-By: Codex deepseek-v4.1-flash <noreply@openai.com>`
  on EVERY commit incl. merges by those routes; mine: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Allowed without asking: push local naf `main` to origin when gates are green (NO tags, NO `cmru release`), delete finished worktrees/branches,
  restart our own stacks (naf-dev-* only), file vbpub backlog entries (check CHANGES/backlog first; vbpub controller wants to be told before
  anything in cmru/nyxloom backlogs: cmru KI >= 152, nyxloom NL >= 65 are free for us). Remote hosts r1002/v1001 only via the documented wrapper,
  only after R1/R3 pass and review is clean, and only after telling the vbpub controller; nano1 never.
- Security: never print/copy the Docker Hub token or any secret value; no credentials in briefs/reports/commits.
- Run tests only through `run-gate` lanes (the user rejected an ad-hoc `docker exec` pytest). R2 (mutation) only on a STABLE, reviewed commit, async.
- Ciu verbs from a worktree: `env -i HOME=$HOME PATH=$PATH ciu worktree create <name> --base main --branch <b>`; delete `ciu.worktree-instance.json`
  in an R2 throwaway worktree (else DIRTY_TREE); plain `git worktree add` worktrees need `cp ciu.global.toml` from main for run-gate.
  `ciu worktree rm` refuses worktrees without generated identity: use `git worktree remove --force` + `git branch -D` after verifying merged.
- Interview/questions: ask only for decisions that are the user's; otherwise decide, record in trove decisions, proceed.

## 2. State of the repos (verify with git before acting)
- naf `main` = `482181c` (local; origin behind: NOT pushed yet). Content: migration commits, tests, survivor fixes (token_auth/utils/account_auth), shim cleanup,
  `d077df0` (assay R2 lane lists include the survivor test files), plan + trove records (F028/F029, M9, B041..B055, D-008..D-013), spike + Opus-review amendments.
  Last full gates: `release-gate` PASS and `e2e` PASS (315 passed, 37 skipped) at `e2c34cf` (the code is unchanged since; later commits are docs/assay.toml).
  R2 has NOT been confirmed: first run showed token_auth_r2 with 9 survivors only because the lane lists lacked the survivor files; fixed (d077df0); the rerun was
  stopped on purpose (WP2 changes account.py, so a rerun must wait for a stable commit).
- naf worktrees: `.worktrees/r2f` (branch `r2-final`, ab4f8c0, R2 throwaway; remove when R2 is redone from a fresh worktree), `.worktrees/wp1` (`wp1-config-hygiene`),
  `.worktrees/wp2` (`wp2-proxy-hops`).
- vbpub (shared checkout `/workspaces/vbpub`, main pushed to origin by the vbpub controller up to `f731d0437`): merged by me: backlog entries assay B525, run-gate RG-261,
  cmru KI-149 (the vbpub controller renumbers it to KI-151). Worktrees of mine: `.worktrees/naf-wp3-probe-20261111` (branch `naf-wp3-probe-20261111`, acddea785),
  `.worktrees/naf-gaps2-20261111` (branch `naf-gaps2-20261111`, 4717f1c6d).
- Peer sessions (SendMessage by name): `vbpub-controller-joint-release` (owns vbpub releases; told about all my vbpub additions; says: no ciu code in flight, I may take
  CIU-205/206/193; tell it before any ciu/cmru release is needed; it never releases while our ciu work is unmerged unless told), `dstdns-9d` (idle, untouched).
- Plan docs (read them): `docs/plans/deployed-e2e-and-modern-ciu-2026-11.md` (plan, decisions D-008..D-013, WP table WP0..WP11, spike table, risks),
  `docs/plans/deployed-e2e-opus-review-2026-11-11.md` (independent Opus review), trove: `nyxloom-trove/decisions.md`, `2-product-definition.md` (F028, F029),
  `3-roadmap.md` (M9), `4-backlog.md` (B041..B055 in section B-DEPLOY).

## 3. The plan in one paragraph
Two deployment types per checkout (`internal`, `public`) stored as a per-checkout fact (`[topology.deployment] type` + `service_profiles` in the instance overlay, with a
pre-compose change guard), `environment_tag="$INSTANCE_ID"` in every checkout with derived traefik names, two public roles (`public-edge` any checkout / `public-dns` exactly one
checkout owning `${PUBLIC_IP}:53`), frontends run the OCI release image, per-session realm labels + reaper instead of sub-zones, credentials via prompt/`ASK_FILE` mounted only into
frontend + a dedicated live runner with read-only login probes in the lane preflight, a small deployment-contract suite on the remote target (`e2e-public`, on demand),
proxy trust (`TRUSTED_PROXY_HOPS`, `PUBLIC_BASE_URL`, `x_host=0`, host-only cookies, ten raw X-Forwarded-For reads removed, static guard test; tarball keeps 1 hop until the
webhoster is measured), cmru versions covering every stack image, OCI boot smoke. The operator's directive now: DRIVE THE CIU CHANGES naf needs (CIU-193, CIU-205, CIU-206),
then migrate naf's config/test setup onto them (WP4b-1, WP4b-2, WP5...).

## 4. Jobs in flight (check each with `job-check.sh`, `.done` files, git logs) and the next action for each
| Job / run | What | State at handoff | Next action |
|---|---|---|---|
| `naf-wp1-ds1` (deepseek, thread `01a1c830-ce6a-7073-bf2c-6a4c8dcf63f1`) | WP1 PowerDNS config hygiene in `.worktrees/wp1`; brief `/tmp/naf-ctl/wp1-brief.md`, report `/tmp/naf-ctl/wp1-report.md` | running; commit 071ac59 exists; its `unit-py311` lane runs via direct flock; gate log `/tmp/naf-ctl/wp1-unit.log` (HEAD=/STATUS= first lines) | when `.done`: job-check, read report + log (PASS line), then luna review (brief like `/tmp/naf-ctl/gaps-rereview-brief.md`, ABS report path), fix by resume, merge into naf main (squash or ff keeps trailer), remove worktree/branch |
| `naf-wp2-luna2` (luna, thread `01a1c830-ce61-7bd2-9b52-489680d40a03`, resumed with `/tmp/naf-ctl/wp2-resume1.md`) | WP2 proxy trust in `.worktrees/wp2`; first run STOPPED at a design question that I answered: `PUBLIC_BASE_URL`, `x_host=0`, host-only cookies, ten XFF reads, static guard test, tarball keeps hops=1 | running; gates unit-py311 + unit-py314 to `/tmp/naf-ctl/wp2-unit.log`, `wp2-unit314.log`; report `/tmp/naf-ctl/wp2-report.md` | job-check; review by DEEPSEEK (security change: demand a careful review incl. cookie/URL regressions); merge |
| `naf-wp3-ds1` + review `naf-wp3-luna-rev1` | WP3 forwarded-headers probe, vbpub `scripts/test-webspace-forwarded-headers.php`, commit acddea785, worktree `/workspaces/vbpub/.worktrees/naf-wp3-probe-20261111` | review verdict FIX (report `/tmp/naf-ctl/wp3-review-report.md`): never recommend a hop count from an unmarked multi-entry XFF chain; no TEST-NET-3 marker => UNDETERMINED; recheck plain and forged cases incl. a plain multi-entry chain | resume the deepseek author thread `01a1c830-ce6d-7e70-8188-c91f3c0c879c` with that fix (amend, same trailer), luna re-review (delta), then merge no-ff into vbpub main with my trailer, tell the vbpub controller, remove worktree; then WP3b (Passenger WSGI probe in vbpub scripts, B054) |
| `naf-gaps2-ds1` (deepseek, thread `01a1c844-52b7-7c42-8d4e-d40ec83ca01f`) | vbpub backlog entries CIU-205, CIU-206 (ciu backlog, ~130 lines, includes a changed index/closeout line) and RG-262; commit 4717f1c6d in `/workspaces/vbpub/.worktrees/naf-gaps2-20261111`; report `/tmp/naf-ctl/gaps2-report.md` | author done, job-check green, NOT yet reviewed | luna review (check facts/ids/cross-references, current-main collisions: vbpub main moved; merge-tree), fix by resume, merge no-ff + tell vbpub controller so it can push |
| Opus research agent `a6e16fe4fac373af0` (ref e62010) | reviewed the plan (report `/tmp/naf-ctl/opus-plan-review.md`); I asked it to start ONE fresh Opus for CIU-193/205/206 if its context < 400k | message sent, reply pending | if it declined or failed: start the fresh Opus myself (Agent tool, model opus) with the full text of `/tmp/naf-ctl/ciu-impl-opus-brief.md`; track its report `/tmp/naf-ctl/ciu-impl-report.md`; its branches need Codex-route reviews and my merge; releases stay with the vbpub controller |

## 5. Queue after the jobs (in order)
1. Merge WP1, WP2 (+WP3) as reviewed. Then ONE stable naf commit: `gate-run.sh trove`, `release-gate`, `e2e` (setup as before: `set -a; . ./.env.services; set +a; export PLAYWRIGHT_SERVER_WS=ws://pwmcp:3000/`,
   `run-gate local-build --worktree "$PWD"` then `run-gate e2e --worktree "$PWD"`; scripts in the scratchpad `e2ef.sh`, `r2f.sh` are the pattern) and the four R2 lanes sequentially in a fresh ciu worktree
   (`env -i ... ciu worktree create`, delete `ciu.worktree-instance.json`, verify HEAD in `r2f-head.txt`), through `gate-run.sh`, one slot at a time. Triage survivors (tests, delete dead code, waive only provable equivalents).
2. Trove lint of the committed F028/F029/M9/B041..B055 records was never confirmed (`run-gate trove` was killed while queued): rerun it.
3. Then plan packages: WP8 (cmru versions targets; the author edits cmru.toml + tests, I run `cmru versions resolve` myself, the Docker Hub token only via env, never printed; pdns series/EOL decision),
   WP4b-1 identity (after ciu CIU-193 fix lands in a ciu release or is worked around), WP4b-2, WP5, WP6, WP9, WP7, WP11, WP10. Each with author/reviewer on different routes.
4. Final: update `nyxloom-trove/STATE.md` (not yet updated for this session's results), push naf `main` (no tags), `cmru release --dry-run`.
5. Cleanup: `.worktrees/r2f`, `wp1`, `wp2`, finished vbpub worktrees; keep the environment clean.
6. Operator-only items to remind the user about when relevant: fill `.env.live` / answer prompts, upstream delegation + A records, run the webhoster probes (WP3/WP3b) and report, provider firewall for port 53.

## 6. What worked well (repeat it)
- Brief files with: goal/non-goals, worktree, facts to verify, contract, steps, gate command with HEAD=/STATUS= log header, trailer, ABSOLUTE report path, stop conditions. Authors that hit a genuine design question stop and ask (WP2 did): answer by resume.
- Review loop: reviewer report with blocking/non-blocking, `VERDICT:` last line; fix by resume of the author thread; delta re-review; then merge. Reviews caught real faults every time (tests reading the wall clock, loose factual claims in backlog entries, wrong R2 lane lists).
- Independent Opus review of the PLAN before building: it overturned three decisions (profile-selection mechanism, shared PowerDNS, WP9) with verified evidence; keep using Opus for design review and for tool work in ciu.
- Prose extract for context hand-off: `nyxloom-harness extract <session.jsonl> --format claude-code --preset successor --tool-calls intent --max-words 26000 --redact-pattern '(?i)(token|password|secret)[=:]\s*\S+'` ≈ 50k tokens; the briefs on disk in `/tmp/naf-ctl/*.md` carry the full agent communication.
- Session transcript: `/home/vscode/.claude/projects/-workspaces-netcup-api-filter/45dce822-b55c-4024-8ee4-d8fb291fe98d.jsonl`. Scratchpad: `/tmp/claude-1003/-workspaces-netcup-api-filter/45dce822-b55c-4024-8ee4-d8fb291fe98d/scratchpad` (gate/e2e/R2 logs).
