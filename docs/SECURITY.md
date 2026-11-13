# Security Overview

How netcup-api-filter protects credentials, scopes access, and audits activity — and
the design choices behind each control. This is a reference for the current
implementation; see `SECURITY_IMPROVEMENTS_2FA.md`, `SECURITY_ERROR_TAXONOMY.md`, and
`CHARSET_VALIDATION.md` for depth on specific areas.

## Threat model

The app is a **scoped authorization layer in front of DNS provider APIs**. The provider
credentials (netcup CCP key/password, BYOD backend secrets) are far more powerful than any
individual user should be. The core job is therefore: let a machine change *only* the records
its token is authorized to change, prove who did what, and keep the powerful upstream
credentials out of reach. Primary adversaries: a stolen/guessed API token, a malicious or
buggy client trying to reach out of scope, and credential probing/brute force.

## Identity & authentication

- **Two surfaces, two mechanisms.** Humans use the **portal/admin UI** (Flask session +
  a DB-backed `AccountSession` row, so sessions are individually **revocable** and audited —
  `account_auth.py`). Machines use **Bearer API tokens** (`token_auth.py`, `@require_auth`).
- **Token format `naf_<user_alias>_<random>`** (`models.py`). Only a **bcrypt hash** plus an
  8-char lookup prefix are stored — the raw token is shown once. Tokens carry a per-account
  `user_alias`, *not* the username, so a leaked token never exposes login credentials and an
  account can rotate its alias to invalidate every token at once.
- **2FA**: email is **mandatory** for regular accounts; TOTP and Telegram are optional;
  recovery codes are the fallback. A method is only *offered* if it can actually deliver (e.g.
  Telegram is hidden unless notifications are configured). Repeated failures trigger a
  **lockout** (`TFA_MAX_ATTEMPTS` / `TFA_LOCKOUT_MINUTES`); recovery-code attempts are
  rate-limited too. The session token is **regenerated on login** (fixation defence). See
  `SECURITY_IMPROVEMENTS_2FA.md`.
- **Admin login lockout**: after `ADMIN_LOGIN_LOCKOUT_THRESHOLD` (default 5) consecutive failed
  password logins for a username, the admin account is locked for `ADMIN_LOGIN_LOCKOUT_MINUTES`
  (default 15). Both are config-driven (`.env.defaults`, env override); invalid values fail loudly.

## Authorization (the heart of it)

Every record-level API call runs through `token_auth.check_permission()`, which enforces, in order:

1. **IP allow-list** (optional, per token, CIDR-aware).
2. **Zone** — the target domain must equal the realm's domain (`realm.matches_domain`).
3. **Hostname scope** — the target FQDN must be inside the realm's scope
   (`realm.matches_hostname`): `host` (exact FQDN), `subdomain` (apex + children), or
   `subdomain_only` (children, not apex). **This is enforced at the record level, not just the
   zone** — a token scoped to one host cannot touch its siblings.
4. **Operation** (read/create/update/delete) and **record type** must be in the token's grant.

Failures resolve to a **granular error taxonomy** (`invalid_format`, `token_hash_mismatch`,
`domain_denied`, `hostname_denied`, `ip_denied`, …) with a severity and an `is_attack` flag,
recorded in `ActivityLog`. This makes probing and brute force *attributable* rather than an
undifferentiated "401". See `SECURITY_ERROR_TAXONOMY.md`.

## Secrets handling

- **Secret comparisons are constant-time** (`hmac.compare_digest`) — e.g. the Telegram bot
  callback secret. Passwords and tokens use bcrypt.
- **`SECRET_KEY` and all provider credentials come from configuration**, never hardcoded and
  with no published default: `SECRET_KEY_FILE`/`SECRET_KEY`, else a random key created once,
  race-free, in the database (`docs/CONFIGURATION_GUIDE.md`).
- **Only the Passenger tarball ships an account**: the pre-set admin (`DEFAULT_ADMIN_*`) with
  `must_change_password`. The OCI image ships none; a fresh container needs an operator-supplied
  bootstrap admin (`NAF_BOOTSTRAP_ADMIN_*`, password as a mounted secret file) or refuses to start
  (the process exits non-zero; first-start initialization is serialized by a lock file, so
  concurrent workers cannot race on it).
- **Configured bootstrap admin passwords obey the password policy** (`validate_password`); only
  the documented tarball default (`admin`/`admin`, forced change on first login) is exempt. A
  configured bootstrap admin starts **without 2FA** (warning banner) until it enrolls TOTP.
- **Start-up errors are never shown to clients**: `passenger_wsgi` logs the traceback and
  re-raises; there is no stand-in WSGI app rendering the exception text (which could contain row
  values such as an email or a password hash).
  The database is the only credential store: no password is copied into state files.
- **`.env.defaults` never ships** (it documents the pre-set admin password and holds test
  fixtures). Shipped trees carry `app-defaults.env`, the runtime-only subset
  (`config_defaults.render_shipped_defaults`): an allowlist of runtime keys that never contains a
  credential-like name, checked by `tests/test_shipped_defaults.py`. There is no `SECRET_KEY` default.
- **Known window:** a freshly deployed tarball on a public host accepts the documented default
  admin password until someone completes the forced change. Deploy and log in immediately.
- `[[users]]` imports never log or retain passwords (the imported list is deleted from the
  settings table after the accounts exist); `"generate"` yields an unknown password (non-admin only).
- **Logging never includes full tokens, passwords, secrets, or chat IDs** — prefixes/IDs only.
- The Telegram link callback rejects the public placeholder secret on any non-local deployment,
  is rate-limited, and binds a `chat_id` to at most one account. See `TELEGRAM_LINKING.md`.

## Web-app hardening

- **CSRF**: Flask-WTF `CSRFProtect` protects all cookie-authenticated routes; the token-auth API
  (`dns_api`, `ddns_protocols`) and the shared-secret Telegram callback are exempt by design
  (they don't use cookies).
- **Session cookies** are config-driven (`FLASK_SESSION_COOKIE_*`). `SECURE=auto` is true outside
  `FLASK_ENV=local_test` and false in that explicitly stated local HTTP mode; it does not infer
  transport security from request headers. Cookie `Domain` is empty by default, so the browser
  keeps the session host-only. An explicit `FLASK_SESSION_COOKIE_DOMAIN` is validated and may
  widen the cookie to sibling hosts.
- **Rate limiting** (`flask_limiter`) is applied to the admin, account, Telegram, **and the
  DNS/DDNS data API** blueprints, plus a global default. Values come from DB settings → env →
  defaults and are reloadable. Note the limiter uses in-memory storage, so limits are
  **per worker process**: N gunicorn workers allow N× the configured budget.
- **GeoIP** location checks (optional) flag logins/requests from unexpected locations.
- **Audit trail**: `ActivityLog` records portal and admin login outcomes, including password
  failures, lock-rejected attempts, successful logins, and invalid or lock-rejected second
  factors. Unknown usernames are recorded with a null `account_id`; audit reasons never contain
  submitted passwords or 2FA codes. Grant add/revoke, Telegram linking, and scoped API activity
  are also audited; the admin **security dashboard** surfaces attack-flagged events.

### Proxy trust, public URLs, and cookies

`TRUSTED_PROXY_HOPS` controls which forwarding headers can affect the request. The repository
default in `.env.defaults` is `0`: no proxy headers influence the client address or scheme. For a
positive value `N`, `ProxyFix` trusts the `N` rightmost values for client address and scheme;
`X-Forwarded-Host` is never trusted. Every client-address use reads the middleware-resolved
`request.remote_addr`. Invalid, empty, and negative hop counts stop startup. If a zero-hop app
receives forwarded headers, it emits one warning per process and explains how to set the hop count.
Automatic DDNS address detection accepts parsed IPv4/IPv6 values, including unambiguous `IPv4:port`
and `[IPv6]:port` forms; malformed or ambiguous addresses fail closed instead of selecting a record
type from the presence of a colon.

Set `PUBLIC_BASE_URL` to the public HTTP(S) origin when links must not depend on request Host or
scheme. It accepts only `http[s]://host[:port]`, with no credentials, path, query, or fragment.
When set, it is the origin for reset, verification, invitation, notification, redirect, and UI
example links. When empty, existing URL generation remains in place: Flask external URLs and UI
examples use the request origin, and notification emails keep their existing configured-base
behavior. Startup warns because reset, verification, and invitation links can use an untrusted
request Host. The app does not reject request Host values.

`tooling/app-local` explicitly sets zero trusted proxy hops and builds `PUBLIC_BASE_URL` from its configured
external subdomain and CIU's public FQDN. The per-session e2e app connects directly over HTTP, so it
explicitly sets `TRUSTED_PROXY_HOPS=0` and `PUBLIC_BASE_URL` to empty, using its request-derived
origin regardless of inherited runner environment values.

The Passenger webhosting tarball ships `app-defaults.env` with `TRUSTED_PROXY_HOPS=0`, inherited
from `.env.defaults`, so no forwarding headers affect the request by default. On 2026-11-13,
probes from two clients against one shared Passenger webhoster showed forged `X-Forwarded-For`
arriving unchanged as the only chain entry, `X-Forwarded-Proto` passing through unchanged while
the server reported HTTPS, and `REMOTE_ADDR` remaining the actual client address. A deployment
behind a real proxy must set `TRUSTED_PROXY_HOPS` explicitly to the measured count and verify
`GET /api/myip` with both a plain request and one carrying forged `X-Forwarded-For` and
`X-Forwarded-Proto` values; confirm the returned `ip` is not changed by the forged values. With
zero trusted hops behind a real proxy, every client appears under the proxy's address, so per-IP
rate limits, login lockouts, GeoIP checks, the activity log and the admin IP whitelist all see one
client; that is why the count must be measured and set, not guessed.

## Deployment posture

The Python app lives outside the web root and is started by Passenger via `passenger_wsgi.py`.
Config is database-driven (no `.htaccess`, no secrets in the tree). Each webhosting deploy
resets to a fresh, password-change-forced state. See `DEPLOYMENT_WORKFLOW.md`.

## Not yet implemented (roadmap / known gaps)

Documented honestly so the doc and code stay in sync:

- **Closing the first-login window of the tarball** (setting the pre-set admin's password from an
  operator-held value at activation) is not implemented.
- **Self-measuring proxy calibration** for other webhosters (B092 part 2): the Passenger catalog
  ships zero trusted hops and nothing measures or proposes a hop count at activation; operators
  set `TRUSTED_PROXY_HOPS` by hand.
- **TOTP secret encryption at rest**, **password-history reuse checks**, and response
  **`Content-Security-Policy` / `Strict-Transport-Security`** headers.
- **SCRAM-SHA-256 HTTP authentication for scoped DNS API clients** (B040/F027). Machine
  DNS requests currently authenticate with Bearer tokens only.
- **User-facing security alerts** — `token_auth._trigger_security_notification` only
  logs; the `send_security_alert` call is commented out, so brute-force / `ip_denied` /
  `token_revoked` events never reach the account owner despite
  `SECURITY_ERROR_TAXONOMY.md` describing them as current.
- **Notification preferences** — `notify_new_ip` / `notify_failed_auth` /
  `notify_token_expiring` / `notification_email` are stored by the settings UI but no
  sender reads them.

Report a vulnerability privately to the maintainer rather than via a public issue.
