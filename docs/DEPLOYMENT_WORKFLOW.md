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

The public FQDN is a CIU fact (`PUBLIC_FQDN` in the generated `ciu.env`, surfaced as `topology.external.public_fqdn`). Local
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

The configured CMRU build step invokes `cmru handler bundle-build` using `bundle.toml`; the
`[[project.variants]]` entries in `cmru.toml` are the shared build and publish list. Before the
handler runs, naf resolves this
checkout's test-runner identity through CIU, verifies that the runner is running and sees the same
Git `HEAD`, and supplies its root and identity through the environment variables named by
`[exec].env`. CMRU downloads target-ABI wheels; `tooling/passenger_bundle_stage.py` expands those
wheels, seeds the database, and renders shipped defaults inside the matching runner. This is
separate from the local `build_deployment.py --local` build.

CMRU 7.3.0 appends `-v` to the project prefix while generating the manifest tag. Naf's release
config already uses `naf-v`, so the preflight passes the handler a temporary config copy with only
that value normalized to `naf`; it preserves the variant list and removes the copy when the step
ends. The canary report records this cmru handler finding for vbpub.

The Passenger bundle is supported only inside a tagged `cmru release`: its build preflight requires
`CMRU_RELEASE_TAG` and rejects `NAF_VERSION` by itself. Use `cmru release` when the tagged Passenger
artifact is ready; `cmru build` and `cmru publish --build-output` do not produce this project's
Passenger bundle. The untagged version-source gap is filed with vbpub as KI-163 (see B101).

Each build step removes old `dist/naf-v*.tar.xz` files before calling the handler so the publisher
and activation adapter cannot select multiple release versions. After a successful handler run, it
removes `dist/app` only when the current version's archive exists. The equivalence procedure compares
the archives, so it does not need the staged tree afterward.

**Current canary blocker:** CMRU 7.3.0 hard-excludes both the staged `app-defaults.env` and vendored
`certifi/cacert.pem`; manifest generation therefore refuses this bundle tree. This branch remains
parked until a CMRU release fixes vbpub KI-162 and the controller completes B101's old/new data comparison.

### Artifact contents

The Passenger stage replaces `.env.defaults` (which holds the documented pre-set admin password and
test fixtures) with `app-defaults.env`: only the allowlisted runtime keys of `.env.defaults`
(`config_defaults.RUNTIME_DEFAULT_KEYS`), rendered by
`netcup_api_filter.config_defaults.write_shipped_defaults`. The OCI artifact has its own generated
runtime catalog. Neither release artifact is intended to ship a secret or demo account.

- **Passenger tarball contract (not yet produced by this branch)** (`naf-v<version>-<variant>.tar.xz`):
  a CMRU bundle with `manifest.json`, the runtime tree, extracted vendored packages, `app-defaults.env`, and a freshly seeded
  `netcup_filter.db` with exactly one account, the pre-set admin
  (`is_admin=1`, `must_change_password=1`). No `secret_key` row (created at first start), no `.env*`,
  no `deployment_state_*.json`. The archive has a single top-level `app/` directory; CIU activation
  strips it into the Passenger application root, as CMRU's generated installer does for its bundles.
  This is the configured artifact contract; CMRU 7.3.0 currently refuses to archive it for the
  hard-exclude conflict above, so this branch has not produced a Passenger tarball.
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
remote directory, and activation command. The selected versioned tarball is transferred to that
host and `scripts/activate.py` performs the project-specific activation. It strips CMRU's single
top-level bundle directory before extraction:

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
