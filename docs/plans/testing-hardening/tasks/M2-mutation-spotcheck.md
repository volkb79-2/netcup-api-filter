# M2 — Mutation spot-check: run, triage, fix or document

**Goal:** Use the M1 runner to prove the unit suite *detects* broken behavior on the security core — not just
executes it. Triage every surviving mutant; kill the meaningful ones with new unit tests; justify the rest.

**Model/effort:** Sonnet/high to implement → **Opus 4.8/xhigh to review the triage** (deciding "equivalent
mutant vs real gap" is the judgment that matters here). **Depends:** M1, and ideally P2–P4 (the property
tests kill many mutants for free). **Size:** M.

## Do
1. Run the full spot-check via `tooling/mutation/run.sh run` over all five target modules
   (`token_auth.py`, `models.py`, `utils.py`, `api/ddns_protocols.py`, `recovery_codes.py`). If a module is
   slow, run it module-by-module (the runner supports a single-module arg).
2. For **each surviving mutant**, classify it:
   - **Real gap** — the mutation changes behavior a correct test should catch (e.g. flipping
     `hostname != fqdn` to `==` in `matches_hostname`'s `subdomain_only` branch, or `is not None` →
     truthiness in `get_effective_operations`, or `>63` → `>=63` in `validate_hostname_format`, or removing
     the `.remove()` in `verify_recovery_code` so a code isn't consumed). **Add a focused unit test** to the
     appropriate `tests/test_*_unit.py` (or a property in P2–P4) that kills it. Re-run to confirm.
   - **Equivalent / acceptable** — the mutation cannot change observable behavior (e.g. mutating a log
     string, a `logger.debug` arg, an unreachable branch, a default that's always overridden). Record it with
     a one-line justification. Do **not** contort tests to kill equivalent mutants.
3. Prioritise by the plan's "interesting targets": the scope/permission boundaries
   (`matches_hostname`, `check_permission`, `check_ip_allowed`, `get_effective_*`), the auth check ordering
   and error codes in `authenticate_token`, and the one-time-use consumption in `verify_recovery_code`. A
   surviving mutant in any of these is high-signal — treat as a real gap unless provably equivalent.
4. Write `docs/plans/testing-hardening/MUTATION_REPORT.md`:
   - per-module table: mutants generated / killed / survived / survivors-that-were-real-gaps;
   - the list of new tests added (file + what mutant each kills);
   - the equivalent/acceptable survivors with justifications;
   - the exact command + interpreter used, and total wall-clock (so a future reader knows the cost).
5. Add a short "Mutation testing" subsection to `docs/TESTING_INFRASTRUCTURE.md` pointing at
   `tooling/mutation/` and the report, and flip the corresponding "Gaps and next steps" row to done.

## Guardrails
- **Do not** lower coverage thresholds or weaken existing assertions to make a mutant "die".
- **Do not** wire mutation into CI or `pytest.ini` (re-verify the M1 hard-constraint greps still pass after
  your changes).
- New killing tests must themselves obey the unit-suite rules: deterministic, no network/DB beyond the
  existing conftest factories, no tolerant `or`-chained assertions.

## Verify
- `python -m pytest tests/ -q` green including all new killing tests.
- `MUTATION_REPORT.md` exists with non-empty per-module numbers and a justification for every survivor left
  alive.
- A re-run of the previously-surviving "real gap" mutants now shows them killed (spot-check 2–3 by hand).
