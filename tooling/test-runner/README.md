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
(`naf-<INSTANCE_ID>-test-runner-py311`, `naf-<INSTANCE_ID>-test-runner-py314`);
run-gate `docker exec`s into them. `ciu.compose.yml` is a RENDERED, gitignored
artifact: edit `ciu.compose.yml.j2`.

**Every checkout runs its own runners.** The main checkout and each linked
worktree (`.worktrees/<name>`) has its own `INSTANCE_ID`, so run-gate execs into
`naf-<that checkout's INSTANCE_ID>-test-runner-*`, never into another checkout's
pair. Bringing them up in the checkout is therefore a **precondition of any gate
there**; it builds the checkout's own `test-runner:py3xx-<INSTANCE_ID>` images
(ciu CIU-117 tag suffix):

```bash
ciu up --dir tooling/test-runner
```

Prerequisites: the checkout's generated ciu env (`eval "$(ciu env print)"`) and
`PWMCP_NETWORK` (see AGENTS.md). A gate whose runner is missing fails with
"no such container" instead of silently using another checkout's runner.

**Why a worktree runner also mounts the main checkout's `.git`.** A linked
worktree's runner mounts only the worktree, but the worktree's `.git` is a
pointer file naming `<main checkout>/.git/worktrees/<name>`. Without that
directory every git call in the runner exits 128: assay lanes abort with
`ERROR/GIT_FAILED` before any lane work and the tracked-file hygiene tests fall
back to a filesystem walk. `ciu.compose.yml.j2` therefore adds the git common dir
for a `.worktrees/` checkout only, read-write (assay's
`snapshot_selection = "repository"` lanes run `git worktree add`, which writes
`.git/worktrees/<snap>`). Both paths are derived from ciu facts
(`PHYSICAL_REPO_ROOT`, `ciu.repo_root`), never configured. This is parity with the
main checkout's runner, which mounts its whole checkout including `.git`;
`tests/test_ciu_identity_contract.py` guards the block.
`ciu up` applies the cgroup/memory/IOPS governance overlay from `[governance]` in
`ciu.global.defaults.toml.j2`.

## Config

| Where | What |
|---|---|
| `ciu.defaults.toml.j2` | runner variants (name → Python version + cmru-pinned base image), pwmcp, state root |
| `run-gate.toml` | lanes and exec environments (SSOT) |
| `.env.workspace` | `PHYSICAL_REPO_ROOT`, `DOCKER_NETWORK_INTERNAL`, `USER_UID`, `DOCKER_GID` (auto-generated) |
