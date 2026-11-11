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

## 2. State (updated 2026-11-11 ~14:30 UTC, after the first migration batch)
- naf `main` (local, NOT pushed): merged WP1 (`ed42b97`), WP8 (`c2d31a4`), WP2 (`51083e3`), trove STATE/B056 and this doc. All via independent MERGE verdicts; branches/worktrees removed
  except `.worktrees/r2f` (branch `r2-final`, R2 throwaway: remove when R2 is redone from a fresh worktree).
- vbpub main (pushed by the vbpub controller up to 6a37e3b87; CIU-208/209 merge `cc4fb8fd3` and the probes `51ed5fdfa`, `6f02577d4` may still be unpushed): merged by me: backlog CIU-205/206/RG-262, CIU-208/209, PHP and Passenger probes (WP3/WP3b), and the Opus-built ciu changes CIU-193/205/206 (merged `2de80e124`, `345afffad`, `0d40aefbd`, status `6a37e3b87`; merged-head ciu-gate PASS). ciu 7.25.0 will be cut by the vbpub controller; it never releases without telling me. I never run cmru release.
- Peer sessions (SendMessage by name): `vbpub-controller-joint-release`, `dstdns-9d` (idle). Its R2/instances Opus implementer has my constraints.
- Pending operator items: run both webhoster probes and report; `.env.live` credentials, delegation/A records, port-53 firewall, PowerDNS series (4.8 is EOL; 5.1 recommended, not live-tested).

## 4. In flight at this checkpoint
Final gates on the current naf main HEAD via `/tmp/naf-ctl/final-gates.sh` (trove, release-gate, local-build, e2e; logs `/tmp/naf-ctl/fg-<lane>.log`, `fg-done` marker). Trove lint was the only failure of the first attempt (handoff frontmatter): fixed by moving this file to docs/plans. Do not commit to main while they run (gate label must equal HEAD). Docker Hub authenticated pulls are limited to 200/hour: run `cmru versions resolve|check` at most once per hour; `cmru versions check naf` (release-gate step) has not yet been run against the new targets.

## 5. Queue (in order)
1. Finish the final gates above; read verdict lines in a SEPARATE step. Then R2: fresh ciu worktree (`env -i HOME=$HOME PATH=$PATH ciu worktree create r2x --base main --branch r2-x`, delete `ciu.worktree-instance.json`), the four lanes (`token_auth_r2 account_auth_r2 recovery_codes_r2 utils_r2`) sequentially via `gate-run.sh`, triage survivors; clean `.worktrees/r2f`.
2. Push naf main (no tags) once release-gate + e2e + trove PASS; `cmru release --dry-run`.
3. After ciu 7.25.0: WP4b-1 identity (`environment_tag="$INSTANCE_ID"`, derived names, `ciu resolve`, POWERDNS_API_KEY as GEN_LOCAL), WP4b-2 deployment type (selection record + service_profiles, templates branch on `ciu.selected_profiles`; CIU-208 means topology_overrides are NOT applied per stack in profile mode), WP9 OCI boot smoke, WP5 public stacks, WP6 credentials (ASK_HOST), WP7 e2e-public, WP11 e2e-remote, WP10 closeout (docs, STATE, R2 evidence). Authors on one route, reviewers on the other (deepseek author -> luna reviewer, luna author -> deepseek reviewer); briefs under /tmp/naf-ctl/wp*-brief.md are the pattern; ask authors to poll gates themselves and retry on exit 3.
4. B056 legacy filter_proxy blueprint (remove or fix; delete the stubs in tests/test_proxy_hops.py); PowerDNS series decision.

## 6. What worked well (repeat it)
- Brief files with: goal/non-goals, worktree, facts to verify, contract, steps, gate command with HEAD=/STATUS= log header, trailer, ABSOLUTE report path, stop conditions. Authors that hit a genuine design question stop and ask (WP2 did): answer by resume.
- Review loop: reviewer report with blocking/non-blocking, `VERDICT:` last line; fix by resume of the author thread; delta re-review; then merge. Reviews caught real faults every time (tests reading the wall clock, loose factual claims in backlog entries, wrong R2 lane lists).
- Independent Opus review of the PLAN before building: it overturned three decisions (profile-selection mechanism, shared PowerDNS, WP9) with verified evidence; keep using Opus for design review and for tool work in ciu.
- Prose extract for context hand-off: `nyxloom-harness extract <session.jsonl> --format claude-code --preset successor --tool-calls intent --max-words 26000 --redact-pattern '(?i)(token|password|secret)[=:]\s*\S+'` ≈ 50k tokens; the briefs on disk in `/tmp/naf-ctl/*.md` carry the full agent communication.
- Session transcript: `/home/vscode/.claude/projects/-workspaces-netcup-api-filter/45dce822-b55c-4024-8ee4-d8fb291fe98d.jsonl`. Scratchpad: `/tmp/claude-1003/-workspaces-netcup-api-filter/45dce822-b55c-4024-8ee4-d8fb291fe98d/scratchpad` (gate/e2e/R2 logs).
