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

## 2. State (updated 2026-11-12 ~00:30 UTC, after the first migration batch is merged and pushed)
- naf `main` = origin/main (pushed, NO tags): WP1 (`ed42b97`), WP8 (`c2d31a4`), WP2 (`51083e3`), fixup1 (`177bd79`, hermetic proxy defaults + fallback comparison), fixup2 (`43216d0`, direct `parse_client_address` tests), trove STATE/B056, this doc. Evidence on `43216d0`: trove PASS, release-gate PASS (unit py311/py314, R1 floors incl. utils 99.29%, R3 canaries), `cmru versions check naf` all `matches`; e2e PASS (315 passed, 37 skipped) and local-build PASS on `177bd79` (the only later change is one test file). `cmru release --dry-run`: first release would be `naf-v0.1.0`, nothing tagged or published (still operator/controller decision; NEVER run without telling the vbpub controller).
- Local note: I changed the operator's untracked `.env` line `FLASK_SESSION_COOKIE_DOMAIN=auto` to empty (the retired value is now rejected on purpose); backup `/tmp/naf-ctl/dot-env.bak-20261111`.
- vbpub main: all my merges are in; the vbpub controller pushes. ciu 7.25.0 (CIU-193/205/206) is planned by it; I must not release. Peers: `vbpub-controller-joint-release`, `dstdns-9d` (idle).
- Pending operator items: run both webhoster probes and report; `.env.live` credentials, delegation/A records, port-53 firewall; PowerDNS series (4.8 EOL, 5.1 recommended, not live-tested); decide naf-v0.1.0 release.

## 4. In flight at this checkpoint (2026-11-12 ~02:30 UTC; verify each with job-check.sh, `.done` files, git logs, gate logs)
| Job | What | Worktree / thread | Brief / report | Next action |
|---|---|---|---|---|
| `naf-fixup3-ds1` (deepseek) | B057 token form drops IP allow-list/expiry (SECURITY), B058 reset-password field mismatch, B059 form-field contract guard, real-form e2e | `.worktrees/fixup3`, branch `fixup3-form-contracts`, thread `01a1cd43-c6ac-76b0-8396-42a99764c9cc` | `/tmp/naf-ctl/fixup3-brief.md`, `fixup3-report.md`, gate logs `fixup3-unit*.log fixup3-build.log fixup3-e2e.log` | when `.done`: job-check, read report + logs (HEAD binding, counts), then LUNA review (security emphasis: route accepts commas+newlines, invalid CIDR rejected not dropped, rate-limit field removed or wired), fix by resume, merge ff/no-ff, remove worktree AND its runners/network/volumes (names `naf-<id>-test-runner*`, `<wt>-<id>-network`, `*_run-gate-state-*`; disconnect the cockpit from the network first) |
| `naf-harness1-ds1` (deepseek) | B069 one pwmcp connection per session + contract check + bounded connect/503 retry, B066 per-role storage state + anonymous context, B060 no secrets in failure output; PERFORMANCE: e2e baseline 315 passed/37 skipped in 1033 s | `.worktrees/harness1`, branch `harness1-pwmcp-connection`, thread `01a1cd4f-f9c1-7123-8f9d-cfe36bcdcda4` | `/tmp/naf-ctl/harness1-brief.md`, `harness1-report.md` | same loop; luna review; compare e2e duration and connect count |
| `naf-sweeps1-luna1` (luna) | tests/ sweeps: B061 IDOR over url_map, B062 CSRF sweep, B065 rate limits, B063 lockout; real defects go to strict-xfail + top of report | `.worktrees/sweeps1`, branch `sweeps1-authz-csrf`, thread `01a1cd4f-f97b-7042-8589-0c90ffb81428` | `/tmp/naf-ctl/sweeps1-brief.md`, `sweeps1-report.md` | DEEPSEEK review; file fix jobs for every defect found |
| R2 close-out | throwaway worktree `.worktrees/r2x` at 5e92d79, driver `/tmp/naf-ctl/r2-driver.sh`, logs `/tmp/naf-ctl/r2-<lane>.log`, marker `r2-done` | token_auth_r2 PASS, account_auth_r2 PASS, recovery_codes_r2 PASS, utils_r2 pending | | triage survivors if any; then remove `.worktrees/r2x` + branch `r2-x` + its runners |
| ciu 7.25.0 | vbpub controller releases after assay 12.2.0 and a run-gate release (its chain; ETA hours); it will message the tag | | | then upgrade naf's ciu floor, WP4b-1 etc. |
Merged this session (naf main = origin/main at `49bc2cb`): WP1, WP2, WP8, fixup1, fixup2, e2e-review backlog B057..B071 (trove). Opus e2e/pwmcp review: `/tmp/naf-ctl/e2e-coverage-review.md` (source of B057..B071). Remaining e2e-review backlog not yet started: B062 admin cookie replay after logout (product decision, server-side admin session revocation), B064 credential-invalidation controls, B067 honest skips (12 of 37 hide gaps), B068 per-test instrumentation (console/network errors, artifacts, timeout), B070 Mailpit isolation + 2-worker parallelism, B071 Telegram/GeoIP in the hermetic tier.

## 5. Queue (in order)
1. R2: throwaway ciu worktree at the final main commit, four lanes sequentially (`token_auth_r2 account_auth_r2 recovery_codes_r2 utils_r2`) via `gate-run.sh`, triage survivors (tests, delete dead code, waive only provable equivalents; fixes go through author/reviewer/gate as usual). Remove `.worktrees/r2f` (old branch `r2-final`).
2. After ciu 7.25.0 is released: WP4b-1 identity (`environment_tag="$INSTANCE_ID"`, derived names, `ciu resolve`, POWERDNS_API_KEY as GEN_LOCAL), WP4b-2 deployment type (selection record + service_profiles; templates branch on `ciu.selected_profiles`; CIU-208: topology_overrides NOT applied per stack in profile mode), WP9 OCI boot smoke, WP5 public stacks, WP6 credentials (ASK_HOST), WP7 e2e-public, WP11 e2e-remote, WP10 closeout. Authors on one route, reviewers on the other; briefs under /tmp/naf-ctl/ are the pattern (authors poll gates themselves, retry on exit 3).
3. B056 legacy filter_proxy blueprint; PowerDNS series decision; operator items above.

## 6. What worked well (repeat it)
- Brief files with: goal/non-goals, worktree, facts to verify, contract, steps, gate command with HEAD=/STATUS= log header, trailer, ABSOLUTE report path, stop conditions. Authors that hit a genuine design question stop and ask (WP2 did): answer by resume.
- Review loop: reviewer report with blocking/non-blocking, `VERDICT:` last line; fix by resume of the author thread; delta re-review; then merge. Reviews caught real faults every time (tests reading the wall clock, loose factual claims in backlog entries, wrong R2 lane lists).
- Independent Opus review of the PLAN before building: it overturned three decisions (profile-selection mechanism, shared PowerDNS, WP9) with verified evidence; keep using Opus for design review and for tool work in ciu.
- Prose extract for context hand-off: `nyxloom-harness extract <session.jsonl> --format claude-code --preset successor --tool-calls intent --max-words 26000 --redact-pattern '(?i)(token|password|secret)[=:]\s*\S+'` ≈ 50k tokens; the briefs on disk in `/tmp/naf-ctl/*.md` carry the full agent communication.
- Session transcript: `/home/vscode/.claude/projects/-workspaces-netcup-api-filter/45dce822-b55c-4024-8ee4-d8fb291fe98d.jsonl`. Scratchpad: `/tmp/claude-1003/-workspaces-netcup-api-filter/45dce822-b55c-4024-8ee4-d8fb291fe98d/scratchpad` (gate/e2e/R2 logs).
