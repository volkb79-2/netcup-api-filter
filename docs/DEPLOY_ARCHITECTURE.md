# Deployment architecture

## Separate build and deployment paths

| Concern | Entry point | Output / effect |
|---|---|---|
| Local development and UI tests | `run-gate local-build` | Calls `build_deployment.py --local`, creates `deploy-local/`, starts the local app, and runs `ui_tests/`. |
| Published release | `cmru release` | Publishes the Python 3.14 OCI image plus Passenger `py311` tarball variants and a variant-selecting installer. |
| Passenger webhosting deployment | `ciu up --host webhoster --thin -- --variant <variant>` | Transfers a selected release tarball and runs the activation adapter on the webhoster. |

`deploy-local/` is a local-test artifact, not a webhosting release artifact. It is built only by
the `run-gate local-build` → `build_deployment.py --local` path.

## Passenger release path

CMRU owns release versioning, tagging, checksums, and publication. Its configured project-local
build step calls `cmru handler bundle-build` using `bundle.toml`; `cmru.toml` is the single variant list for
both building and publishing. Naf's preflight resolves this checkout's runner identity through
CIU, confirms the runner is running and sees the same Git `HEAD`, then passes its root and resolved
identity through the environment names configured in `bundle.toml`. CMRU vendors the wheels for
the target ABI. `tooling/passenger_bundle_stage.py` runs inside that runner to expand wheels into
Passenger's importable layout, seed the release database, and write the filtered runtime defaults.

This bundle requires CMRU **7.3.1 or newer**, declared in the `cmru.toml` header. The bundle test
checks the installed parser version when available and otherwise checks its structural contract.
CMRU 7.3.1 canonicalizes the `naf-v` manifest prefix and uses a Git-bound `.devN+g<hash>` version
when `NAF_VERSION` is unset; the naf preflight only resolves the matching
checkout runner identity and conditionally passes an explicit release version through. The temporary
prefix config workaround is gone.

Naf's exact `[archive].keep` paths preserve `app-defaults.env` and the wheel-extracted
`vendor/certifi/cacert.pem`. `.env.defaults` is copied by the stage helper for seeding only and is
removed before manifest creation. CMRU cleans the staged bundle after success (`keep_tree = false`);
naf retains the stale-archive prune because CMRU only deletes the current archive and leaves sibling
versions in `dist/`. The real Passenger bundle has not been built by this implementer; KI-126
acceptance and the old/new data comparison remain open in B106.

The configured bundle uses the canonical name, `naf-v<version>-<variant>.tar.xz`, and carries a
`manifest.json` under one top-level `app/` directory. The CIU adapter strips that directory while
extracting; CMRU's generated installer follows the same single-directory bundle contract.

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

The primary ship gate executes the unit suite under Python 3.11 and 3.14:

```bash
run-gate gate --worktree "$PWD"
```

The 3.11 run covers the Passenger variant; 3.14 covers the self-hosting OCI image. Local
`run-gate local-build` and the Passenger bundle's ABI-dependent stage both run inside the
matching runner.
