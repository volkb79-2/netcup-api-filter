# Deployment workflow

naf has three distinct workflows. Do not use a webhosting release command to create the local
test deployment, and do not build or copy Passenger artifacts by hand.

## Local development and UI testing

`run-gate local-build` is the local entry point. It runs `build_deployment.py --local`, extracts
the resulting package into `deploy-local/`, starts the local Flask manager, and drives
`ui_tests/` against that deployment.

```bash
# Build deploy-local/ and run the UI suite.
run-gate local-build (see run-gate.toml)

# Also start Mailpit, GeoIP, and Netcup API mocks.
the local flow in run-gate.toml (mocks via ciu, then run-gate local-build, run-gate e2e)

# Reuse an existing deploy-local/ build.
run-gate local-build (see run-gate.toml)
```

`build_deployment.py --local` is the only builder of `deploy-local/`. Live test and coverage
tooling depend on that directory, so it remains part of the local workflow.

The public FQDN is detected into `.env.workspace` by `.devcontainer/post-create.sh`. Local
service names and URLs are defined in `.env.services`; see [FQDN detection](FQDN_DETECTION.md)
and the individual tooling READMEs for TLS and service-stack operation.

## Release artifacts

`cmru release` creates a source-control-versioned release and publishes all release artifacts:

- the Python 3.14 OCI image for self-hosting;
- an ABI-matched Passenger tarball for Python 3.11 (`py311`); and
- the variant-selecting installer.

```bash
cmru release
```

CMRU invokes `scripts/build_webhosting_tarball.py` for the Passenger assets. That builder uses
`docker exec` into the matching ciu runner (`naf-<INSTANCE_ID>-test-runner-py311`) so dependency vendoring and database
seeding run under the target interpreter. It is separate from the local
`build_deployment.py --local` build.

### What the artifacts contain

Neither artifact ships a secret, a demo account or `.env.defaults` (it holds the documented pre-set
admin password and test fixtures). Both ship `app-defaults.env` instead: only the allowlisted runtime keys
of `.env.defaults` (`config_defaults.RUNTIME_DEFAULT_KEYS`), rendered by `netcup_api_filter.config_defaults.write_shipped_defaults`.

- **Passenger tarball** (`naf-<variant>.tar.xz`): the runtime tree, vendored wheels, `app-defaults.env`
  and a freshly seeded `netcup_filter.db` with exactly one account, the pre-set admin
  (`is_admin=1`, `must_change_password=1`). No `secret_key` row (created at first start), no `.env*`,
  no `deployment_state_*.json`. `tests/test_release_artifacts.py` asserts this on the builder's real
  staging steps.
- **OCI image** (`Dockerfile.release`): the app, `app-defaults.env`, `NETCUP_FILTER_DB_PATH=/data/netcup_filter.db`
  and `VOLUME /data`; no database and no account. It runs as the non-root user `naf`
  (`APP_UID`/`APP_GID` build args, default 10001): `/app` is read-only for it, `/data` (DB, init lock,
  `NETCUP_FILTER_LOG_FILE`) and `/config` (`NETCUP_FILTER_APP_ROOT`, optional `app-config.toml`) are
  writable — a bind-mounted `/data` must be writable by that uid. The build context is an allowlist
  (`.dockerignore`): no `.env*` except the bind-mounted `.env.defaults`, no `.ciu/secrets`. The first start creates the database through the
  normal `init_db` path (serialized across workers by `<db>.init.lock`) and **fails fast** — gunicorn
  exits non-zero with "Worker failed to boot", the error is in the log only — unless the first admin is supplied:
  `NAF_BOOTSTRAP_ADMIN_USERNAME`, `NAF_BOOTSTRAP_ADMIN_EMAIL` and `NAF_BOOTSTRAP_ADMIN_PASSWORD_FILE`
  (a mounted secret; or an `app-config.toml` admin). Also mount `SECRET_KEY_FILE` (otherwise the app
  persists a generated key in the database) and keep `/data` on a persistent volume so the database
  and that key survive container recreation.
- **`app-config.toml` in a container**: it is a one-shot import that the app claims (renames) and
  deletes, so bind-mount a **writable directory** containing it at `NETCUP_FILTER_APP_ROOT` (the
  deploy tree on Passenger; `/config` in the image), never the file itself — a bind-mounted file or a read-only directory cannot be renamed
  and the start fails with a message saying so. `python -m netcup_api_filter.bootstrap init` (e.g.
  via `docker exec`) resolves the app root the same way as `passenger_wsgi.py` (the deploy tree that
  holds `src/netcup_api_filter`, or `NETCUP_FILTER_APP_ROOT`), so it reads the same file.

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
run-gate gate --worktree "$PWD"
```

Use `run-gate e2e` for the external Playwright path and
`run-gate trove` for nyxloom handoff linting.

## Related documentation

- [Deployment architecture](DEPLOY_ARCHITECTURE.md)
- [FQDN detection](FQDN_DETECTION.md)
- [Testing infrastructure](TESTING_INFRASTRUCTURE.md)
