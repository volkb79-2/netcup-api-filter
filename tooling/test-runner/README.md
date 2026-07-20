# test-runner — the gating container

**The devcontainer is a cockpit, not a gate.** Nothing you run in the devcontainer is a
ship signal. This container is where "green" is allowed to mean something.

## Why it exists

Two independent reasons, both load-bearing:

1. **Interpreter fidelity.** The app deploys to shared webhosting under Passenger.
   `deploy.sh` builds `deploy-py311.zip` as the primary artifact and
   `build_deployment.py` vendors wheels with `--python-version 3.11 --only-binary`. The
   devcontainer runs **3.14**. A 3.10+ syntax construct, or a dependency that has a
   cp314 wheel but no cp311 wheel, is green in the cockpit and a **post-deploy 500** in
   production. Here it fails at import/collect, which is the whole point.
2. **Closure fidelity.** The image installs the repo's own
   `requirements.webhosting.txt` (runtime) + `requirements-dev.txt` (test toolchain).
   A dependency present in the cockpit but missing from the deployed closure fails here.

Sibling implementations of the same doctrine: dstdns `tools/test-runner` (FROM the app
base image), vbpub `tester-unified` (one container for the whole family). This one mixes
both: tester-unified's single `/opt/tester-venv` + full run-uid identity, dstdns's
runtime bind-mount + network-peer form.

## Single source of truth

The dependency closure is **derived**, never duplicated here. Change a dependency in
`requirements.webhosting.txt` / `requirements-dev.txt` and it flows to the gate on the
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

```bash
./tooling/test-runner/testing-exec.sh unit            # PRIMARY gate: pytest tests/ (hermetic)
./tooling/test-runner/testing-exec.sh unit -k realm   # extra pytest args pass through
./tooling/test-runner/testing-exec.sh trove           # nyxloom handoff frontmatter lint
./tooling/test-runner/testing-exec.sh e2e ui_tests/tests/security/
./tooling/test-runner/testing-exec.sh shell           # interactive shell inside the gate
```

The image is built automatically on first use. To exercise the **secondary** Passenger
target (3.9) and its compat guards:

```bash
PYTHON_VERSION=3.9 TEST_RUNNER_IMAGE=netcup-api-filter/test-runner:py39 \
  ./tooling/test-runner/testing-exec.sh unit
```

Persistent peer (warm container on `naf-dev-network`, alongside the mock services):

The peer form is now **ciu-managed** (naf-I01). `ciu.compose.yml` is a RENDERED,
gitignored artifact — edit `ciu.compose.yml.j2`, never the output. Note the
`--define-root`: this devcontainer's shell exports dstdns's `REPO_ROOT`, so a bare
`ciu` call resolves to the wrong repo (backlog B-INFRA).

```bash
ciu render --define-root /workspaces/netcup-api-filter
ciu up --dir tooling/test-runner --define-root /workspaces/netcup-api-filter
```

`ciu up` also applies the cgroup/memory/IOPS governance overlay from `[governance]`
in `ciu.global.defaults.toml.j2` (`.ciu/ciu.compose.overlay.yml`).

## Config

| Where | What | Why |
|---|---|---|
| `runner.env` | image/container name, `PYTHON_VERSION` | identity; version-controlled |
| `.env.workspace` | `PHYSICAL_REPO_ROOT`, `DOCKER_NETWORK_INTERNAL`, `USER_UID`, `DOCKER_GID` | per-environment; auto-generated |

`testing-exec.sh` deliberately does **not** source `.env.services`: that file expands
`${PUBLIC_FQDN}` unconditionally and aborts every `set -u` consumer when post-create has
not written it (see `docs/deprecated/FOLLOWUP_REVIEW_2026-07-16.md` §P0-8). The gate must not
inherit that breakage.

`PHYSICAL_REPO_ROOT` is a **host** path: the docker socket is the host's daemon (DooD),
so `-v` sources resolve on the host, not in this container.

## Gates

| Gate id | Command | Scope |
|---|---|---|
| `unit` | `testing-exec.sh unit` | `tests/` — hermetic, no services, no browser. The default gate for nyxloom handoffs. |
| `trove` | `testing-exec.sh trove` | handoff frontmatter + L1 + gate-id resolution |
| `e2e` | `testing-exec.sh e2e` | `ui_tests/` against a deployed app + mocks + pwmcp |

These ids are the ones declared in `nyxloom-trove/nyxloom.toml [gates.*]` and referenced
by handoff `oracles[].gate`.
