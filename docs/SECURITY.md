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
- **`SECRET_KEY` and all provider credentials come from configuration** (`.env.defaults` →
  environment → DB settings), never hardcoded. Fresh deployments ship with `admin`/`admin` and
  force a password change on first login; the real password lives only in
  `deployment_state_{target}.json`.
- **Logging never includes full tokens, passwords, secrets, or chat IDs** — prefixes/IDs only.
- The Telegram link callback rejects the public placeholder secret on any non-local deployment,
  is rate-limited, and binds a `chat_id` to at most one account. See `TELEGRAM_LINKING.md`.

## Web-app hardening

- **CSRF**: Flask-WTF `CSRFProtect` protects all cookie-authenticated routes; the token-auth API
  (`dns_api`, `ddns_protocols`) and the shared-secret Telegram callback are exempt by design
  (they don't use cookies).
- **Session cookies** are config-driven (`FLASK_SESSION_COOKIE_*`); `SECURE=auto` resolves to
  Secure over HTTPS and relaxes only for explicit local HTTP testing.
- **Rate limiting** (`flask_limiter`) is applied to the admin, account, Telegram, **and the
  DNS/DDNS data API** blueprints, plus a global default. Values come from DB settings → env →
  defaults and are reloadable. Note the limiter uses in-memory storage, so limits are
  **per worker process**: N gunicorn workers allow N× the configured budget.
- **GeoIP** location checks (optional) flag logins/requests from unexpected locations.
- **Audit trail**: `ActivityLog` records authentication outcomes, grant add/revoke, Telegram
  linking, and scoped API activity; the admin **security dashboard** surfaces attack-flagged events.

## Deployment posture

The Python app lives outside the web root and is started by Passenger via `passenger_wsgi.py`.
Config is database-driven (no `.htaccess`, no secrets in the tree). Each webhosting deploy
resets to a fresh, password-change-forced state. See `DEPLOYMENT_WORKFLOW.md`.

## Not yet implemented (roadmap / known gaps)

Documented honestly so the doc and code stay in sync:

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
