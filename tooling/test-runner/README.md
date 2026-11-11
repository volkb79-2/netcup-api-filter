# test-runner — the gating container

**The devcontainer is a cockpit, not a gate.** Nothing you run in the devcontainer is a
ship signal. This container is where "green" is allowed to mean something.

## Why it exists

Two independent reasons, both load-bearing:

1. **Interpreter fidelity.** The app deploys to shared webhosting under Passenger.
   the shipped runtimes are Python **3.11** (Passenger tarball) and **3.14** (OCI image).
   A dependency that has a wheel for one but not the other fails at install/collect here,
   not as a post-deploy 500. There is one runner per version.
2. **Closure fidelity.** The image installs the repo's own
   `requirements-runtime.txt` (runtime) + `requirements-test.txt` (test toolchain).
   A dependency present in the cockpit but missing from the deployed closure fails here.

Sibling implementations of the same doctrine: dstdns `tools/test-runner` (FROM the app
base image), vbpub `tester-unified` (one container for the whole family). This one mixes
both: tester-unified's single `/opt/tester-venv` + full run-uid identity, dstdns's
runtime bind-mount + network-peer form.

## Single source of truth

The dependency closure is **derived**, never duplicated here. Change a dependency in
`requirements-runtime.txt` / `requirements-test.txt` and it flows to the gate on the
next image rebuild. (This repo has no `pyproject.toml`, unlike the vbpub family, so the
requirements files are the SSOT.)

The only thing this directory adds on top is `jsonschema`/`pyyaml`, used solely by
`lint_trove.py` to validate nyxloom handoffs — deliberately not added to the app's
requirements, because they are not app dependencies.

## No browser engine — ever

JS-rendered UI is driven through the external Playwright-as-a-Service (**pwmcp**) via
`PLAYWRIGHT_SERVER_WS`. Never install a browser engine in this image or the cockpit.
The `e2e` gate refuses to run without `PLAYWRIGHT_SERVER_WS` set, by design.

## Usage

Lanes are declared in `run-gate.toml`; judgment (what a run proves) in `assay.toml`.
Run from the repo (or a worktree) with the installed `run-gate`:

```bash
run-gate --list                      # authoritative lane list
run-gate gate --worktree "$PWD"      # unit on py311 + py314, then trove
run-gate unit-py314 --worktree "$PWD"
run-gate e2e --worktree "$PWD"       # needs app-local + mocks + pwmcp stacks up
```

Runners are ciu-managed persistent containers, one per Python version
(`naf-dev-test-runner-py311`, `naf-dev-test-runner-py314`); run-gate `docker exec`s into
them. `ciu.compose.yml` is a RENDERED, gitignored artifact: edit `ciu.compose.yml.j2`.

```bash
ciu up --dir tooling/test-runner --define-root /workspaces/netcup-api-filter
```

Prerequisites: `PWMCP_NETWORK` (see AGENTS.md) and the per-stack env: `set -a; . ./ciu.env; . ./.env.workspace; set +a`. `--define-root` is needed because this devcontainer's shell exports dstdns's `REPO_ROOT`.
`ciu up` applies the cgroup/memory/IOPS governance overlay from `[governance]` in
`ciu.global.defaults.toml.j2`.

## Config

| Where | What |
|---|---|
| `ciu.defaults.toml.j2` | runner variants (name → Python version + cmru-pinned base image), pwmcp, state root |
| `run-gate.toml` | lanes and exec environments (SSOT) |
| `.env.workspace` | `PHYSICAL_REPO_ROOT`, `DOCKER_NETWORK_INTERNAL`, `USER_UID`, `DOCKER_GID` (auto-generated) |
