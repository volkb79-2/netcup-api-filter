# Configuration Guide

This guide is the single source of truth for the repository's environment-file layout. It records
each file's owner, reader, scope and content boundary. Runtime setting precedence remains
consumer-specific: inspect the named reader instead of assuming a universal environment/database
order.

## Environment-file layout

| File | Role | Tracked? | Who writes it | Who reads it | What must never be in it |
|---|---|---|---|---|---|
| `.env.defaults` | Policy defaults, local test fixtures and the Passenger build seed | Yes | naf maintainers | `src/netcup_api_filter/config_defaults.py`, `bootstrap/admin.py`, and `build_deployment.py` during database seeding | Operator host facts or real provider credentials |
| `.env.services` | Shell resolver for service URLs and checkout-local service identities | Yes | naf maintainers | Sourced by shell workflows; calls `ciu resolve --json` and `tooling/ciu_resolve_env.py`; its exports are read by `build_deployment.py`, `bootstrap/platform_backends.py`, `ui_tests/workflows.py`, and `ui_tests/tests/live/test_live_dns_verification.py` | Hand-entered URLs, service names or credential values |
| `.env.workspace` | Generated devcontainer facts: `ENV_TYPE`, `USER_*`, `DOCKER_GID`, `REPO_ROOT`, `PHYSICAL_REPO_ROOT`, `DOCKER_NETWORK_INTERNAL`, `DEVCONTAINER_NAME` (no `PUBLIC_FQDN`/`PUBLIC_IP`: those are in `ciu.env`) | No | `.devcontainer/finalize.post.d/10-netcup-setup.sh` | `.vscode/ensure-mcp-connection.sh` and the manual `source` steps in `tooling/*/README.md`; CIU does not read it (its render context uses `ciu.env`, see `ciu.global.defaults.toml.j2` `workspace_env_file`) | Credentials or hand-maintained overrides |
| `ciu.env` | Generated CIU identity and machine facts, including `PUBLIC_IP` and `PUBLIC_FQDN` | No | `ciu env generate` (`ciu env print` only prints it for `eval`) | CIU Compose templates, including `tooling/test-runner/ciu.compose.yml.j2` and `tooling/app-local/ciu.compose.yml.j2` | Hand-edited values or credentials outside CIU's secret mechanism |
| `.env.operator` | Operator-supplied local infrastructure facts, including the delegated zone | No | Operator | Sourced before CIU; `ciu.global.defaults.toml.j2` consumes `NAF_DELEGATED_DNS_ZONE`, then the PowerDNS/app seed hooks use the rendered fact | `POWERDNS_API_KEY` or guard credentials; CIU generates the PowerDNS key |
| `.env.webhoster` | Human webhoster URL and SSHFS route | No | Operator | Sourced by the operator; the `sshfs` and `curl` commands below read its keys. `.ciu.hosts.toml` is a separate CIU deployment input | Netcup CCP, mailbox, app or guard credentials |
| `.env.live` | Inputs for live mailbox/DNS checks and the on-demand deployed-instance smoke | No | Operator / later CIU secret delivery | No current `run-gate` lane consumes it; its live-test keys are read by `ui_tests/tests/live/*`, app settings by `passenger_wsgi.py` / `geoip_service.py`, and remote smoke keys by `ui_tests/config.py` | Credentials copied into tracked files or the webhoster SSH route |
| `.env.guard` | Local Traefik basic-auth credentials for human access | No | Operator | the operator sources it in the setup sequence documented in `run-gate.toml`; `ciu.global.defaults.toml.j2` and the `app-local` / PowerDNS Compose templates consume the user/hash; documented human `curl` commands use the user/password | Any tracked credential value or live application login |
| `.env` | Optional local override layer for `.env.defaults`; absent/empty by default | No | Local developer | `src/netcup_api_filter/config_defaults.py` reads it after `.env.defaults`; `build_deployment.py` uses that loader while seeding and removes it from the artifact | Live-tier credentials, deployment route facts or anything intended to ship |
| `app-defaults.env` | Generated allowlist of runtime defaults in a staged tree | No | `config_defaults.write_shipped_defaults()` called by `build_deployment.py` and `tooling/passenger_bundle_stage.py`; CMRU 7.3.1+ includes this exact protected path through `[archive].keep` (B108) | `src/netcup_api_filter/config_defaults.py` | Credential-like values or build/test-only settings |
| `.env.operator.example` | Placeholder-only template for `.env.operator` | Yes | naf maintainers | A human copies it; `tests/test_env_layout.py` guards its shape; the resulting file is read as `.env.operator` above | Real zones, hosts, accounts or credentials |
| `.env.webhoster.example` | Placeholder-only template for `.env.webhoster` | Yes | naf maintainers | A human copies it; `tests/test_env_layout.py` guards its shape; the resulting file is read by the documented `sshfs` / `curl` commands | Real hosts, account names or credentials |
| `.env.live.example` | Placeholder-only template for `.env.live` | Yes | naf maintainers | A human copies it; `tests/test_env_layout.py` guards its shape; the resulting file is read by the live tests and app readers above | Real domains, mailbox/provider credentials or IPs |
| `.env.guard.example` | Placeholder-only template for `.env.guard` | Yes | naf maintainers | A human copies it; `tests/test_env_layout.py` guards its shape; the resulting file is read by CIU / Compose above | Real basic-auth values or hashes |

The real `.env.operator`, `.env.webhoster`, `.env.live`, `.env.guard`, `.env.workspace`, `ciu.env`
and root `.env` files are gitignored. The four `*.example` files are tracked and contain only
empty values or obvious placeholders. To use one, copy it to the corresponding real filename, fill
that local file, then source the real file when the workflow calls for it:

```bash
set -a; . ./.env.live; set +a
```

Sourcing a file only exports its keys into the current shell. `run-gate.toml` `forward_env` does not
forward the `.env.live` keys (`IMAP_*`, `DNS_*`, `DEPLOYMENT_MODE`, `NETCUP_*`, `MAXMIND_*`, or
`NAF_E2E_TARGET` / `NAF_REMOTE_*`) into the test runners, and no `run-gate` lane runs
`ui_tests/tests/live/*` or the remote smoke. The on-demand deployed lane and credential delivery
remain B048 part 2 / B049. Until that supported workflow exists, `.env.live` is a template for
explicitly selected test processes, not an input consumed by a current gate.

For the local CIU flow, `run-gate.toml` records the setup sequence: load CIU's generated facts,
provide `PWMCP_NETWORK`, source `.env.guard`, then source `.env.services`. The exact file need
depends on the workflow; these files are not a universal source chain.

### Webhoster route

`.env.webhoster` is for manual SSHFS and URL access. CIU deployment uses `.ciu.hosts.toml` and its
own declared inputs. `ciu up --host webhoster --thin` pushes the checkout minus the inventory's `bundle_excludes`
(plus CIU's mandatory `.git`, `.ciu`, `ciu.env`), so every private env file is named there;
`tests/test_env_layout.py` fails when one is missing. After loading the local route file, the human commands consume its keys:

```bash
sshfs "${WEBHOSTING_SSH_USER}@${WEBHOSTING_SSH_HOST}:${WEBHOSTING_REMOTE_DIR}" "$WEBHOSTING_MOUNT_POINT"
curl --fail --output /dev/null "${WEBHOSTING_URL}/admin/login"
```

`WEBHOSTING_MOUNT_POINT` is supplied by the caller; it is not a key in the env file.

### Keys in `.env.live.example`

The live example's DNS and mailbox keys have readers in the live DNS/email tests; its Netcup/GeoIP
keys have app readers; and its deployed target keys are read by `ui_tests/config.py` when the
on-demand remote smoke is selected (also documented in `WEBHOSTING_TESTING_GUIDE.md`).
`POWERDNS_API_URL` and `POWERDNS_API_URL_INTERNAL` belong to `.env.services`, which derives them;
neither belongs in `.env.defaults` or `.env.webhoster`. The live DNS lifecycle test also needs
`POWERDNS_API_KEY`, but that key is intentionally absent from `.env.live.example`: CIU generates a
checkout-local `GEN_LOCAL` value in `tooling/backend-powerdns/ciu.defaults.toml.j2` and supplies it
to the backend Compose container and seed hook, not to a pytest process. There is no supported
tracked manual delivery path today; a person could manually export the generated value into a
selected test process, but the repository has no lane that does so. The CIU-resolved / `ASK_FILE`
handoff to a live runner remains B048 part 2 / B049. The app's SMTP host and credentials are
Settings UI/database values, not environment variables.

The keys below also appear in the `.env.defaults` catalog. Their readers (live tests, `geoip_service.py`)
read `os.environ` with their own in-code fallbacks and do not consult the catalog, so the catalog
values are documentation of the intended defaults, not values that `.env.live` overrides. The
structural test checks that every name below still exists in `.env.defaults`:

```env-default-overrides
DNS_TEST_DOMAIN
DNS_TEST_SUBDOMAIN_PREFIX
DNS_PROPAGATION_TIMEOUT
DNS_PROPAGATION_POLL_INTERVAL
DNS_CHECK_SERVERS
IMAP_HOST
IMAP_PORT
IMAP_USER
IMAP_PASSWORD
IMAP_USE_TLS
IMAP_MAILBOX
IMAP_MAILBOXES
IMAP_TIMEOUT
IMAP_MESSAGE_LOOKBACK
MAXMIND_ACCOUNT_ID
MAXMIND_LICENSE_KEY
MAXMIND_API_URL
```

Reader evidence for the example keys:

- `DEPLOYMENT_MODE`, `DNS_TEST_*`, `DNS_PROPAGATION_*` and `DNS_CHECK_SERVERS` are read by
  `ui_tests/tests/live/test_live_dns_verification.py`.
- `IMAP_*` values are read by `ui_tests/tests/live/test_live_email_verification.py` and
  `ui_tests/workflows.py`.
- `NETCUP_CUSTOMER_ID`, `NETCUP_API_KEY` and `NETCUP_API_PASSWORD` are read by
  `src/netcup_api_filter/passenger_wsgi.py` (with the database Settings values as fallback).
- `MAXMIND_*` values are read by `src/netcup_api_filter/geoip_service.py` and the GeoIP admin
  configuration in `src/netcup_api_filter/api/admin.py`.
- `NAF_E2E_TARGET`, `NAF_REMOTE_BASE_URL`, `NAF_REMOTE_ADMIN_USERNAME`, and both remote admin
  password/TOTP value-or-file pairs are read by `ui_tests/config.py`; their on-demand remote smoke
  setup is described in `docs/WEBHOSTING_TESTING_GUIDE.md`.
- `NAF_DELEGATED_DNS_ZONE` is consumed by `ciu.global.defaults.toml.j2`; `NAF_GUARD_USER` and
  `NAF_GUARD_HTPASSWD` are consumed by that template and local Compose guard labels. The documented
  human `curl` commands read `NAF_GUARD_USER` and `NAF_GUARD_PASSWORD`.
- `WEBHOSTING_*` values are read by the `sshfs` and `curl` commands above.

## Configuration behavior

`config_defaults.load_defaults()` reads `app-defaults.env`, then `.env.defaults`, and overlays
root `.env`; explicit environment values win at the call sites that consult `get_default()` or
`require_default()`. Settings stored in the database have their own precedence at consumers such
as the GeoIP and Netcup integrations. `.env` is not automatically exported into arbitrary shell
commands.

Builds use `.env.defaults` and optional `.env` while creating the Passenger database, then write
the allowlisted `app-defaults.env` and remove both source files. A `.env` override is therefore a
build-time input, not a runtime file shipped to the webhoster. `tests/test_release_artifacts.py`
checks that sensitive env files do not appear in the resulting tree.

`SECRET_KEY` has runtime readers in `app.py` and `passenger_wsgi.py`, with `SECRET_KEY_FILE` as a
file-backed option. It belongs nowhere in `.env.defaults` or `.env.webhoster`, and it is not a
`.env.live` input. If neither runtime source is set, the app creates and persists a key in the
database; `scripts/activate.py` carries the persisted value across greenfield webhosting releases.

## Session and security settings

- `FLASK_SESSION_COOKIE_SECURE=auto` sets Secure cookies outside `FLASK_ENV=local_test`; it does
  not inspect forwarded scheme headers.
- `FLASK_SESSION_COOKIE_HTTPONLY`, `FLASK_SESSION_COOKIE_SAMESITE` and `FLASK_SESSION_LIFETIME`
  control browser session handling.
- `FLASK_SESSION_COOKIE_DOMAIN` is empty by default, keeping the session cookie host-only. Set a
  validated DNS domain only when sibling hosts must share a cookie; `auto` is not accepted.
- `TRUSTED_PROXY_HOPS` is a non-negative integer. `0` ignores forwarded headers; `N > 0` trusts the rightmost `N` `X-Forwarded-For` and `X-Forwarded-Proto` values. `X-Forwarded-Host` is never trusted. The repository and Passenger `app-defaults.env` defaults are `0`; invalid, empty, and negative values fail startup. Deployments behind a real proxy must explicitly set the measured hop count and verify `GET /api/myip` with plain and forged forwarding-header requests; see [`SECURITY.md`](SECURITY.md).
- `PUBLIC_BASE_URL` is empty by default. Set an HTTP(S) origin with no path, query, fragment or
  credentials to make externally generated links use that scheme and host. `tooling/app-local`
  derives it from the configured public topology; the per-session e2e app clears it for its direct
  HTTP topology.
- `ADMIN_LOGIN_LOCKOUT_THRESHOLD` and `ADMIN_LOGIN_LOCKOUT_MINUTES` control admin brute-force
  lockout. They are read at call time; a non-integer or value below `1` raises an error.

## Bootstrap admin and first start

`bootstrap.instance.init_instance()` owns schema setup, lightweight migrations, default settings,
administrator creation and (local stack only) Mailpit configuration.

| Caller | Administrator source | Result |
|---|---|---|
| Passenger tarball | `DEFAULT_ADMIN_USERNAME`, `DEFAULT_ADMIN_PASSWORD` and `DEFAULT_ADMIN_EMAIL` from `.env.defaults` | One pre-set admin with `must_change_password`; first login changes the password |
| Local golden DB (`run-gate local-build`) | Same pre-set admin plus Mailpit values | `deploy-local/netcup_filter.db`; e2e copies it per session |
| OCI image / fresh container | `NAF_BOOTSTRAP_ADMIN_*` runtime environment or an `app-config.toml` admin entry | First start fails if no admin source exists; no account is reset on later starts |
| `tooling/app-local` | CIU `GEN_LOCAL` secret passed to the bootstrap hook | Admin is created once; the hook prints the secret store path, never the value |

First-start initialization is serialized by `<db>.init.lock`; failures are fatal to startup and
never rendered to clients. Configured bootstrap passwords must satisfy the product password
policy.

### Bootstrap inputs, init lock and SECRET_KEY

For a container first start, set `NAF_BOOTSTRAP_ADMIN_USERNAME` and
`NAF_BOOTSTRAP_ADMIN_EMAIL`, plus exactly one of `NAF_BOOTSTRAP_ADMIN_PASSWORD_FILE` (preferred,
pointing to a mounted secret) or `NAF_BOOTSTRAP_ADMIN_PASSWORD`. The password value and password
file are mutually exclusive. Instead of environment inputs, `app-config.toml` may define an
`[[users]]` entry with `is_admin = true` and an explicit password. These inputs create the first
admin only; they do not reset an existing account. The explicit operator command
`python -m netcup_api_filter.bootstrap init --enforce-admin` reasserts the configured admin;
startup hooks do not use this option.

Initialization uses an exclusive `<db>.init.lock`; other processes wait up to
`NAF_INIT_LOCK_TIMEOUT_SECONDS` and startup fails if that wait expires. `SECRET_KEY_FILE` and
`SECRET_KEY` are mutually exclusive. A supplied key must be at least 16 characters; when neither
is supplied, the app creates and persists one in the database.

Local builds take the Mailpit host from `MAILPIT_HOST` and the mock Netcup URL from
`MOCK_NETCUP_API_URL`, both exported by `.env.services` after `ciu resolve`. Mailpit's SMTP port,
sender and admin recipient come from `.env.defaults` keys `LOCAL_MAILPIT_SMTP_PORT`,
`LOCAL_MAIL_FROM` and `LOCAL_MAIL_ADMIN_EMAIL`. The local Netcup mock uses the
`LOCAL_MOCK_NETCUP_CUSTOMER_ID`, `LOCAL_MOCK_NETCUP_API_KEY`, `LOCAL_MOCK_NETCUP_API_PASSWORD`
and `LOCAL_MOCK_NETCUP_TIMEOUT` defaults. These local build values are test-fixture configuration,
not webhosting or OCI credentials. `tooling/app-local` takes its Mailpit settings from
`[app_local.mail]` in `tooling/app-local/ciu.defaults.toml.j2`.

## Adding configuration

Put a new key in the file whose scope owns it. Add a `.env.defaults` entry only when the value is
a repository-wide policy default or a test/build fixture. Keep operator host facts in
`.env.operator`, human deploy routes in `.env.webhoster`, live credentials in `.env.live` / CIU
secret delivery, and basic-auth values in `.env.guard`. Document the reader and failure behavior,
then add a gate-backed guard when the layout or key registry changes.
