---
schema_version: 1
id: naf-I03-containerized-build
project: naf
title: "Build runs under host 3.14 against cp39/cp311 vendored .so files — containerize the build"
tier: sonnet5-high
input_revision: "f912479"
depends_on: [naf-I01-ciu-adoption]
session: fresh
source: {kind: plan, ref: "nyxloom-trove/INFRA-PLAN-2026-07-20.md#INFRA-3"}
status: DONE — merged (860c825); see ../STATE.md
advances: [M3]
scope:
  touch:
    - "build_deployment.py"
    - "deploy.sh"
    - "tooling/test-runner/testing-exec.sh"
    - "docs/DEPLOYMENT_WORKFLOW.md"
  forbid:
    - "src/**"
    - "tests/**"
    - "requirements.webhosting.txt"
oracles:
  - id: O1
    observable: "build_deployment.py refuses to run initialize_database when sys.version_info[:2] != the requested --python-version, with an explicit message naming both versions. A deliberate mismatch exits non-zero."
    negative: "Today it seeds the DB under the host interpreter (3.14) with cp311/cp39 .so files first on sys.path — version-tagged extensions are silently not import candidates, pure-Python fallbacks are used instead, and the abi3 bcrypt loads a cp311 binary under 3.14. The build validates nothing about the target closure."
    gate: trove
  - id: O2
    observable: "`./deploy.sh` phase_build produces deploy-py311.zip AND deploy-py39.zip by running build_deployment.py INSIDE the matching test-runner:py311 / :py39 container (sys.executable == target interpreter), with artifacts owned by the host uid and build_info.json stamped with the builder image digest."
    negative: "The build shells out to the devcontainer's python3 (3.14), so the cockpit is the build interpreter — the exact doctrine violation the test-runner container exists to end."
    gate: trove
gates: [trove]
escalate_if:
  - "any runtime dependency lacks a cp39 OR cp311 manylinux wheel — the thin gate image has no compiler, so an --only-binary build would fail; STOP and report which dep"
  - "removing the sdist fallback breaks resolution for a dep that currently depends on it"
  - "phase_build cannot run in-container without editing a forbidden file"
---

# naf-I03 — build the deployment artifacts at their target ABI

> **STATE (2026-07-21): ✅ DONE** — the containerized build (`testing-exec.sh build <ver>`) landed (`860c825`) and now backs the cmru Passenger-tarball builder. See [../STATE.md](../STATE.md).

> **PAUSED — carved for operator review.** This modifies the production artifact pipeline
> (`deploy.sh`, `build_deployment.py`). Do not dispatch until the operator confirms. Recorded
> under D-006 (REVIEW-ME).
> Base: `main` @ `f912479`. Gate: `./tooling/test-runner/testing-exec.sh trove`.

## The bug (verified)

`deploy.sh:365` loops `PYTHON_TARGETS=(3.9 3.11)` and `deploy.sh:875-904` runs
`python3 build_deployment.py … --python-version ${pyver}` under the **host** `python3` — the
devcontainer's **3.14**.

The *download* half is cross-version-safe: `build_deployment.py:92-102` uses
`pip download --only-binary :all: --python-version <ver> --platform manylinux2014_x86_64`,
which resolves target-ABI wheels without executing them.

The *seeding* half is not. `initialize_database` (`:381-521`) puts `vendor/` **first** on
`sys.path` (`:406`) and imports the app (`:456-458`) then `db.create_all()` + seeds
(`:472-502`) — under host 3.14. The live `deploy-webhosting/vendor/` contains **35
`*.cpython-311-*.so`** files plus an abi3 bcrypt. Under 3.14:

- version-tagged cp311/cp39 `.so`s are **not import candidates at all** — packages with a
  pure-Python fallback (markupsafe, PyYAML, tomli) silently use it; C-only ones (greenlet,
  maxminddb, Pillow) would `ImportError`;
- the **abi3** bcrypt *does* load — a cp311 binary executing under 3.14, a silent mismatch;
- so seeding "works" only because it happens not to touch the hard-failing extensions. It
  proves nothing about the target closure. For the 3.9 zip the gap is wider.

Worse, the **sdist fallback** (`:104-127`) retries with *no* `--python-version/--platform`
(`:117-123`), building sdists for host 3.14 into a "3.9"/"3.11" tree, and its warning only
fires when `python_version != "3.11"` (`:109`) — so a poisoned 3.11 tree is **silent**.
(Backlog B-OPS records this verbatim.)

## Work

1. **Host-vs-target guard** in `build_deployment.py`: refuse `initialize_database` unless
   `sys.version_info[:2]` matches the requested `--python-version`; explicit message naming
   both. This is the fail-fast that makes everything below verifiable.
2. **Fix the sdist fallback** (`:104-127`): do not silently cross-build sdists for a different
   interpreter. Either drop the fallback for cross builds or gate it behind an explicit opt-in;
   fix the wrong-condition warning at `:109`.
3. **Run the build in-container.** Change `deploy.sh` phase_build (`:875-904`) to invoke
   `build_deployment.py` inside the matching image, mirroring `testing-exec.sh:run_ephemeral`
   (`:80-85`) but **adding `--user ${USER_UID}:${DOCKER_GID}`** (run_ephemeral omits it; without
   it artifacts land root/1003-owned):
   `docker run --rm -v ${PHYSICAL_REPO_ROOT}:/workspaces/netcup-api-filter -w /workspaces/netcup-api-filter --user … netcup-api-filter/test-runner:py<ver> /opt/tester-venv/bin/python build_deployment.py …`
   The version→image map already exists at `testing-exec.sh:110-114`. DooD: `-v` sources MUST be
   host paths (`PHYSICAL_REPO_ROOT`).
4. **Keep `--platform manylinux2014_x86_64 --only-binary :all:`** for wheel *resolution* even
   in-container — the container fixes the *seeding interpreter*, not the *target glibc*. A
   natively-resolved `manylinux_2_28` wheel could break the webhoster's older glibc.
5. **Provenance:** stamp the builder image digest into `build_info.json` (`:218-227` currently
   records git + host USER only).
6. Fix deprecated `datetime.utcnow()` (`:219,322,342,376`) while here.
7. Reconcile `docs/DEPLOYMENT_WORKFLOW.md` with the new flow.

## Hazards

- **No compiler in the gate image** (`Dockerfile:45-47` installs git/curl/procps only). If any
  dep lacks a cp39/cp311 wheel and `--only-binary` is relaxed, an in-container pip would try to
  *build* it and fail → escalate rather than adding build-essential silently.
- The image already provides what the build shells out to: `git` for build_info
  (`build_deployment.py:208-223`) and `/bin/bash` to source `.env.services` (`:412-432`).
- The SQLite file is interpreter-independent; the value of in-container seeding is that it
  **exercises the real target extensions** at build time.

## Gate

`./tooling/test-runner/testing-exec.sh trove`, plus a manual proof: build both zips and diff
the vendor trees against the current ones, confirming the cp39 tree really contains cp39
extensions. Record the diff in the REPORT.

## BLOCKED rule

If a contract cannot be met, or a forbidden file must change, STOP: write `BLOCKED: <reason>`
to the LOG, commit, exit.
