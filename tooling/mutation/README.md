# Mutation testing — local runner

## What is mutation testing?

Mutation testing automatically introduces small code changes ("mutants") — flipping a `<` to `<=`,
negating a boolean, removing a `return` — and checks whether the test suite detects each change.
A mutant that is **not** caught by any test is a **survivor**: it reveals a gap where the tests
pass but an important behaviour change goes unnoticed.

For this project the tool is **[mutmut 3.6.0](https://mutmut.readthedocs.io/)**, which works on
Python 3.14 (the dev venv).

---

## Why local-only?

Mutation testing re-runs the full unit suite once per mutant.  The five target modules generate
~2,000+ mutants combined; a full pass takes **15–30 minutes**.  Running this on every push would
make CI unusable.  Instead, the runner is invoked manually when you want to verify that the test
suite actually *detects* broken behaviour — typically before a security-critical refactor, or as
part of M2 triage.

Hard rule: **this runner is never referenced from `.github/` workflows or from `pytest.ini`.**

---

## Targets (security-critical pure-logic modules)

| Module | Why |
|---|---|
| `src/netcup_api_filter/token_auth.py` | Auth chain, CIDR/IP checks, error codes |
| `src/netcup_api_filter/models.py` | `matches_hostname`, scope inheritance, `is_expired` |
| `src/netcup_api_filter/utils.py` | IP-range / domain / email validators |
| `src/netcup_api_filter/api/ddns_protocols.py` | Hostname parse/validate, auto-detect |
| `src/netcup_api_filter/recovery_codes.py` | One-time code consumption |

---

## Setup

Ensure development dependencies are installed (already done if you used `requirements-dev.txt`):

```bash
pip install -r requirements-dev.txt
```

This installs `mutmut==3.6.0`.  No further setup is required — the tool reads its config from
`setup.cfg` at the project root (the `[mutmut]` section is invisible to pytest).

---

## How to run

### Smoke check — single module (fast, ~2–5 min)

```bash
./tooling/mutation/run.sh run src/netcup_api_filter/recovery_codes.py
```

`recovery_codes.py` is the smallest target (~82 mutants) and is the recommended first smoke test
to verify the whole pipeline end-to-end.

### Full 5-module run (slow, ~15–30 min)

```bash
./tooling/mutation/run.sh run
```

### Show results from the last run

```bash
./tooling/mutation/run.sh results
# or
./tooling/mutation/run.sh show
```

### Inspect a specific surviving mutant

```bash
mutmut show netcup_api_filter.recovery_codes.x_verify_recovery_code__mutmut_3
```

This prints the diff of exactly what was changed — the mutant that the tests missed.

---

## Per-mutant test command

Each mutant is evaluated by running only the fast unit subset (no coverage, no slow tests):

```
python -m pytest -x -q -o addopts="" --rootdir=. --tb=native \
    tests/test_token_auth_unit.py \
    tests/test_realm_matching_unit.py \
    tests/test_validators_unit.py \
    tests/test_ddns_parsing_unit.py \
    tests/test_recovery_codes_unit.py \
    tests/test_password_policy_unit.py \
    tests/test_token_model_property.py \
    tests/test_ddns_property.py \
    tests/test_validators_property.py
```

The `-o addopts=""` override neutralises `pytest.ini`'s `--cov`/`-x`/`--tb=short` so each
mutant evaluates in ~2–3 s instead of the full coverage pass.

---

## How to read survivors

A **survivor** means: mutmut mutated that line and every test in the subset still passed.

Possible explanations:

1. **Real gap** — the line's behaviour is not verified by any test assertion.  Add a test that
   would fail on the mutated code.
2. **Equivalent mutant** — the mutation is semantically identical to the original in all reachable
   paths (e.g. `return x or x` vs `return x`).  Document it in the M2 triage notes.
3. **Dead code** — the line is never reached by any fast-unit test but is also never reached in
   production.  Consider removing or adding a test.

The M2 task will systematically triage every survivor and either add a killing test or record a
one-line justification in `docs/plans/testing-hardening/tasks/M2-mutation-spotcheck.md`.

---

## Config

- **`setup.cfg` `[mutmut]`** (project root) — mutmut source paths, test selection, per-mutant
  pytest flags.  Invisible to pytest (which reads `pytest.ini`).
- **`mutants/`** (project root, gitignored) — mutmut's working sandbox; recreated on each run.

---

## Verified working invocation (smoke run on recovery_codes.py)

```
./tooling/mutation/run.sh run src/netcup_api_filter/recovery_codes.py
```

Tool: mutmut 3.6.0 on Python 3.14.5 (dev venv).
mutmut 3.x installed cleanly on Python 3.14 via the `cp314` `libcst` wheel — no version
pinning workaround was needed.

Smoke run result (2026-06-14):
- 82 mutants generated for `recovery_codes.py`
- 62 killed (tests detected the mutation)
- **20 survived** — logged for M2 triage
- Wall-clock: ~127 s (~2 min)
