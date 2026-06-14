# M1 — Mutation tooling (toggleable, local-only, no CI)

**Goal:** A **toggleable, opt-in** mutation-testing runner over the security-critical pure-logic core.
**Local only.** It must be invoked **explicitly** and be referenced by **no** CI workflow and **no**
`pytest.ini` — running `pytest` or pushing must never trigger it.

**Model/effort:** Sonnet / high. **Depends:** none (but pairs with P2–P4). **Size:** M.

## Hard constraints (verify each at the end)
- `grep -rn mutmut .github/ pytest.ini` → **no matches** (not in CI, not in pytest addopts).
- The only way to run mutation is the new runner script (or the documented command in its README).
- Adding the dep must not change `python -m pytest tests/` behavior at all.

## Do
1. **Dependency.** Add a pinned mutation tool to `requirements-dev.txt` under a clearly-commented
   "Mutation testing (manual/local only — see tooling/mutation/)" block. Prefer `mutmut` (the tool named in
   the overhaul gaps table). **Pin a version that actually installs and runs on the local interpreter** — the
   dev `.venv` is Python 3.14; if the chosen `mutmut` release won't run there, either pin one that does, or
   document running it under a Python 3.11 venv (the deploy/CI target). If `mutmut` proves unworkable on the
   available interpreter, fall back to `cosmic-ray` and adjust the runner accordingly — record the decision in
   the README. The deliverable is a *working, documented, toggleable* runner, not a specific tool.
2. **Config.** Configure the tool to mutate exactly these modules (the targets from the plan):
   - `src/netcup_api_filter/token_auth.py`
   - `src/netcup_api_filter/models.py`
   - `src/netcup_api_filter/utils.py`
   - `src/netcup_api_filter/api/ddns_protocols.py`
   - `src/netcup_api_filter/recovery_codes.py`

   Use the tool's native config mechanism for the pinned version, kept isolated so it does **not** affect the
   normal pytest run. The test runner used per-mutant must run only the relevant **fast unit subset** with
   pytest's repo addopts neutralised (no `--cov`, keep fail-fast). Concretely the per-mutant command should be
   shaped like:
   ```
   python -m pytest -x -o addopts="" \
     tests/test_token_auth_unit.py tests/test_realm_matching_unit.py \
     tests/test_validators_unit.py tests/test_ddns_parsing_unit.py \
     tests/test_recovery_codes_unit.py tests/test_password_policy_unit.py \
     tests/test_token_model_property.py tests/test_ddns_property.py \
     tests/test_validators_property.py
   ```
   (`-o addopts=""` drops the repo's `--cov`/`-x`/`--tb` so each mutant evaluates fast; include the P2–P4
   property files if they exist at run time — they sharpen mutant-killing.)
3. **Runner.** Create `tooling/mutation/run.sh` (executable) that:
   - is a no-op unless explicitly run (it's a script, not a hook);
   - supports `run` (full spot-check), `results`/`show` (summary), and an optional single-module argument so
     an expensive full run can be narrowed (`./tooling/mutation/run.sh run src/netcup_api_filter/token_auth.py`);
   - prints the surviving-mutant count and where to see details;
   - activates `.venv` if present, else uses the documented interpreter.
4. **README.** `tooling/mutation/README.md`: what it is, why it is local-only (re-runs the suite per mutant —
   too slow for CI), the exact commands, how to read survivors, and a pointer to the report M2 will produce.
5. **gitignore.** Add the tool's cache/work dir (e.g. `.mutmut-cache`, `mutants/`, `.cosmic-ray/`) to
   `.gitignore`.

## Verify
- `./tooling/mutation/run.sh run src/netcup_api_filter/recovery_codes.py` completes and reports a survivor
  count (smallest module = fast smoke of the whole pipeline). Capture the command's working invocation in the
  README.
- The three "Hard constraints" greps pass.
- `python -m pytest tests/ -q` unchanged and green.

## Out of scope
Triaging/killing survivors and the full-core run — that is M2.
