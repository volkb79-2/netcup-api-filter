# Testing Against a Deployed (Webhosting) Instance

The browser suite normally owns its app: every session starts a throwaway instance with random
personas (see `docs/TESTING_INFRASTRUCTURE.md`, "`ui_tests/`"). Against a **deployed** instance only
a small, **read-only smoke** is supported. It never writes, never rotates a password and needs no
state file: the target and the operator admin come from environment variables.

## What runs remotely

Only tests marked `remote_smoke` (`ui_tests/tests/smoke/test_remote_smoke.py`):

- the public login pages render (`/admin/login`, `/account/login`) without an error body;
- the operator admin can log in (password, plus TOTP when configured);
- the admin dashboard, accounts, audit, settings and system pages return `< 400` with no error text.

With `NAF_E2E_TARGET=remote` every test **not** marked `remote_smoke` is skipped with the reason
"only tests marked remote_smoke (read-only) run against a deployed instance". The bound profile has
`deployment_target="webhosting"` and `allow_writes=False`. There is no user persona, no API token and no
database path remotely: a test that reads `settings.user_username`, `settings.client_token`,
`settings.db_path` etc. raises `TargetUnavailableError` instead of getting a placeholder.

The default (`NAF_E2E_TARGET` unset or `local`) is unchanged: throwaway local instance, nothing from the cockpit.

## Environment

| Variable | Meaning |
|----------|---------|
| `NAF_E2E_TARGET` | `remote` selects this mode; unset/`local` is the normal suite; anything else is an error |
| `NAF_REMOTE_BASE_URL` | absolute `http(s)` URL of the deployment, e.g. `https://<your-host>` (required) |
| `NAF_REMOTE_ADMIN_USERNAME` | operator admin username (required) |
| `NAF_REMOTE_ADMIN_PASSWORD_FILE` | path of a file holding the password (preferred) |
| `NAF_REMOTE_ADMIN_PASSWORD` | the password itself; **mutually exclusive** with the `_FILE` form |
| `NAF_REMOTE_ADMIN_TOTP_SECRET_FILE` / `NAF_REMOTE_ADMIN_TOTP_SECRET` | optional TOTP seed, same file-or-value rule |

A missing required value, a missing/empty file, or both forms of one secret stops the session with
exit code 3 and one message. Email-only 2FA cannot be automated remotely: give the operator admin a
TOTP seed (the login fails loudly, never skips, when 2FA is requested and no seed is configured).

## Running it

Put the secrets in files readable only by you (never on a command line, never in the repo) and run the
3.11 test runner with the files mounted read-only. Browser tests use the estate pwmcp as in the normal lane.

```bash
docker exec -w "$PWD" \
  -e NAF_E2E_TARGET=remote \
  -e NAF_REMOTE_BASE_URL=https://<your-host> \
  -e NAF_REMOTE_ADMIN_USERNAME=<operator-admin> \
  -e NAF_REMOTE_ADMIN_PASSWORD_FILE=<path-visible-in-the-runner> \
  -e NAF_REMOTE_ADMIN_TOTP_SECRET_FILE=<path-visible-in-the-runner> \
  naf-<INSTANCE_ID>-test-runner-py311 /opt/tester-venv/bin/python -m pytest -m remote_smoke ui_tests/tests/smoke/test_remote_smoke.py -v
```

The password file must exist inside the runner's filesystem (mount or copy it there; remove it afterwards).
The remote smoke never contacts the deployment unless you run it.

## Deploying first

Webhosting releases are greenfield (fresh database, pre-set admin with a forced password change, see
`AGENTS.md` and `docs/DEPLOYMENT_WORKFLOW.md`). Change that password once by hand, then use the
resulting operator credentials above; the smoke does not and must not perform the first-login change.

## Operating on the deployment otherwise

- Database / logs: mount the web root with `sshfs` from the devcontainer (read-only use for inspection).
- Cookies: the app runs behind the production TLS proxy on its public host; no cookie-domain workaround is needed.
- Adding a remote test: mark it `@pytest.mark.remote_smoke`, keep it GET-only, and use `settings.url(...)`.
  Anything that creates or changes data belongs in the local (throwaway instance) suite.
