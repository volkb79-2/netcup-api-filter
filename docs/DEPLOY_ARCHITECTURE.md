# Deployment architecture

## Separate build and deployment paths

| Concern | Entry point | Output / effect |
|---|---|---|
| Local development and UI tests | `run-gate local-build` | Calls `build_deployment.py --local`, creates `deploy-local/`, starts the local app, and runs `ui_tests/`. |
| Published release | `cmru release` | Publishes the Python 3.14 OCI image plus Passenger `py39` and `py311` tarball variants and a variant-selecting installer. |
| Passenger webhosting deployment | `ciu up --host webhoster --thin -- --variant <variant>` | Transfers a selected release tarball and runs the activation adapter on the webhoster. |

`deploy-local/` is a local-test artifact, not a webhosting release artifact. It is built only by
the `run-gate local-build` → `build_deployment.py --local` path.

## Passenger release path

CMRU owns release versioning, tagging, checksums, and publication. Its project-local build step,
`scripts/build_webhosting_tarball.py`, produces a tarball for each Passenger ABI. It invokes
`tooling/test-runner/testing-exec.sh build 3.9` or `build 3.11` so wheels are vendored and the
seed database is created with the interpreter that will load them.

CIU reads the webhoster connection and bundle settings from `.ciu.hosts.toml`. It transfers the
chosen variant and invokes `scripts/activate.py`. The adapter extracts the tarball, carries the
previous `SECRET_KEY` into the fresh database, touches `tmp/restart.txt` to reload Passenger,
and probes `/admin/login`.

The Passenger database lifecycle is greenfield: each tarball contains a newly seeded database.
No database preservation is declared or performed; `SECRET_KEY` is the sole carried-forward
value.

## Local test path

`run-gate local-build` builds and extracts `deploy-local/`, starts the Flask manager, and runs the
requested `ui_tests` target. `--with-mocks` starts Mailpit, Mock GeoIP, and Mock Netcup API; use
`--skip-build` to reuse an existing local deployment. Local tooling that consumes
`deploy-local/` must keep using this path.

## Compatibility gate

The primary ship gate executes the unit suite under Python 3.9, 3.11, and 3.14:

```bash
run-gate gate --worktree "$PWD"
```

The 3.9 and 3.11 runs cover the Passenger variants; 3.14 covers the self-hosting OCI image.
`testing-exec.sh build <version>` is used by both local `build_deployment.py` ABI work and
CMRU's `scripts/build_webhosting_tarball.py` variant builds.
