# P1 — Hypothesis bootstrap

**Goal:** Make property-based testing (Hypothesis) a first-class part of the unit suite so P2–P4 can drop in
test files that run locally and in the existing CI `unit-tests` job with **no new services**.

**Model/effort:** Sonnet / high. **Depends:** none. **Size:** S.

## Context
- Unit suite lives in `tests/`, run via `python -m pytest tests/`. `pytest.ini` sets `pythonpath = . src`,
  so imports are `from netcup_api_filter... import ...`. `addopts` already includes `-x --tb=short --cov=...`.
- CI `unit-tests` job (`.github/workflows/ci.yml`) runs `python -m pytest tests/` on **Python 3.11** after
  `pip install -r requirements-dev.txt`. Adding `hypothesis` to that file makes it available in CI
  automatically.
- The integration design is pre-written in [`docs/TESTING_LESSONS_LEARNED.md` §5](../../../TESTING_LESSONS_LEARNED.md)
  ("Integration plan"). Follow it.

## Do
1. Add to `requirements-dev.txt` (under "Testing frameworks"):
   ```
   hypothesis>=6.100  # Property-based testing (parsers/validators) — see TESTING_LESSONS_LEARNED §5
   ```
2. In `tests/conftest.py`, register two Hypothesis profiles and select via env so CI stays fast and local
   deep-runs are possible. Add near the top (after imports), guarded so a missing hypothesis never breaks
   collection of the non-PBT tests:
   ```python
   try:
       from hypothesis import settings, HealthCheck
       settings.register_profile("ci", max_examples=50, deadline=None,
                                 suppress_health_check=[HealthCheck.too_slow])
       settings.register_profile("dev", max_examples=500, deadline=None)
       settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci"))
   except ImportError:
       pass
   ```
   (Import `os` if not already imported. `deadline=None` avoids flaky timing failures under coverage
   instrumentation.)
3. Do **not** add `--hypothesis-*` flags to `pytest.ini` addopts. Profile selection is via
   `HYPOTHESIS_PROFILE` env (default `ci`). Document the `dev` profile in the docstring/comment.
4. Add a one-line note to `docs/TESTING_INFRASTRUCTURE.md` under "Suite layout → tests/": Hypothesis
   property tests live in `tests/test_*_property.py`, default profile `ci` (50 examples), set
   `HYPOTHESIS_PROFILE=dev` for 500.

## Verify
- `pip install -r requirements-dev.txt` then `python -m pytest tests/ -q` is green (no behavior change yet;
  this task adds no test files).
- `python -c "import hypothesis, os; from tests.conftest import *"` does not raise (profiles register).
- `grep -n hypothesis pytest.ini` returns nothing (no flags leaked into addopts).

## Out of scope
The actual property tests (P2–P4). This task only wires the dependency and profiles.
