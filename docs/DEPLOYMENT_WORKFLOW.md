# Deployment workflow

naf has three distinct workflows. Do not use a webhosting release command to create the local
test deployment, and do not build or copy Passenger artifacts by hand.

## Local development and UI testing

`run-local-tests.sh` is the local entry point. It runs `build_deployment.py --local`, extracts
the resulting package into `deploy-local/`, starts the local Flask manager, and drives
`ui_tests/` against that deployment.

```bash
# Build deploy-local/ and run the UI suite.
./run-local-tests.sh

# Also start Mailpit, GeoIP, and Netcup API mocks.
./run-local-tests.sh --with-mocks

# Reuse an existing deploy-local/ build.
./run-local-tests.sh --skip-build
```

`build_deployment.py --local` is the only builder of `deploy-local/`. Live test and coverage
tooling depend on that directory, so it remains part of the local workflow.

The public FQDN is detected into `.env.workspace` by `.devcontainer/post-create.sh`. Local
service names and URLs are defined in `.env.services`; see [FQDN detection](FQDN_DETECTION.md)
and the individual tooling READMEs for TLS and service-stack operation.

## Release artifacts

`cmru release` creates a source-control-versioned release and publishes all release artifacts:

- the Python 3.14 OCI image for self-hosting;
- ABI-matched Passenger tarballs for Python 3.9 (`py39`) and Python 3.11 (`py311`); and
- the variant-selecting installer.

```bash
cmru release
```

CMRU invokes `scripts/build_webhosting_tarball.py` for the Passenger assets. That builder uses
`tooling/test-runner/testing-exec.sh build <version>` so dependency vendoring and database
seeding run under the target interpreter. It is separate from the local
`build_deployment.py --local` build.

## Webhosting deployment

Deploy a released Passenger variant with CIU:

```bash
ciu up --host webhoster --thin -- --variant py311
```

The `webhoster` connection inventory is `.ciu.hosts.toml`; it owns the SSH connection metadata,
remote directory, and activation command. The selected tarball is transferred to that host and
`scripts/activate.py` performs the project-specific activation:

1. extract the selected tarball;
2. retain the existing `SECRET_KEY`;
3. touch `tmp/restart.txt` to reload Passenger; and
4. health-probe `/admin/login`.

Passenger releases are greenfield: each tarball supplies a freshly seeded
`netcup_filter.db`. The database is not preserved across releases; preserving only `SECRET_KEY`
matches the retired deployment behaviour.

## Verification gate

The ship gate runs the unit suite under all shipped Python versions:

```bash
./tooling/test-runner/testing-exec.sh unit  # Python 3.9, 3.11, and 3.14
```

Use `./tooling/test-runner/testing-exec.sh e2e` for the external Playwright path and
`./tooling/test-runner/testing-exec.sh trove` for nyxloom handoff linting.

## Related documentation

- [Deployment architecture](DEPLOY_ARCHITECTURE.md)
- [FQDN detection](FQDN_DETECTION.md)
- [Testing infrastructure](TESTING_INFRASTRUCTURE.md)
