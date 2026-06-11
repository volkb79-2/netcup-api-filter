# Features & Roadmap

The canonical map of what netcup-api-filter can do today and what's planned. This is
the single source for product capabilities — keep it in sync with the code (see the
sync rule in [`../AGENTS.md`](../AGENTS.md)). For how-to depth, follow the linked guides.

## What it is

A **scoped, audited authorization layer in front of DNS provider APIs**. It lets machines
update *only* the DNS records they're authorized to, proves who did what, and keeps the
powerful upstream provider credentials out of reach. It ships an account portal, an admin
UI, and token-authenticated REST/DDNS APIs, and runs on shared webhosting under Passenger.

## Current capabilities

### DNS access control (the core)
- **Account → Realms → Tokens** model. A realm grants a DNS scope; a token is a machine
  credential scoped to one realm (`naf_<user_alias>_<random>`, bcrypt-hashed).
- **Record-level authorization** (`token_auth.check_permission`): enforces zone, **hostname
  scope** (`host` / `subdomain` / `subdomain_only`), operation, record type, and an optional
  per-token IP allow-list. A host-scoped token cannot touch its siblings.
- **Realm templates** — pre-configured presets (DDNS single host, subdomain delegation,
  read-only monitoring, LetsEncrypt DNS-01, full management, CNAME delegation) defined once
  in `realm_templates.py` and surfaced in both portals. See [`../CLIENT_TEMPLATES.md`](../CLIENT_TEMPLATES.md).

### API surfaces
- **REST DNS API** — `GET/POST/PUT/DELETE /api/dns/<domain>/records`, `/api/myip`. See [`API_REFERENCE.md`](API_REFERENCE.md).
- **DDNS** — DynDNS2 and No-IP compatible endpoints (routers, ddclient, inadyn), auto-IP
  detection, IPv6→AAAA. See [`DDNS_PROTOCOLS.md`](DDNS_PROTOCOLS.md).
- **Per-IP rate limiting** on the admin, account, Telegram, **and DNS/DDNS** blueprints,
  config-driven (DB → env → default). See [`RATE_LIMITING.md`](RATE_LIMITING.md).

### Backends (multi-provider)
- **netcup CCP** managed domain roots, and **bring-your-own** backend services per account.
- **PowerDNS** backend implemented; a provider abstraction (`backends/`) makes adding more
  providers a contained change.

### Accounts, authentication & 2FA
- Self-service **registration with admin approval**; revocable DB-backed sessions.
- **2FA**: email mandatory, **TOTP** and **Telegram** optional, **recovery codes** fallback;
  a method is offered only if it can actually deliver.
- **Lockout** after repeated failed 2FA/recovery attempts, **with notifications** to the user
  (and optionally an operator) when an account is locked.
- **Telegram linking** via deep-link + bot callback (constant-time secret, one-chat-per-account,
  rate-limited, audited). See [`TELEGRAM_LINKING.md`](TELEGRAM_LINKING.md).

### Admin UI
- Account management + approval/rejection; **realm request approval**; **domain-root** and
  per-account **grant** management; **backend-service CRUD** (create/edit/test/enable/delete);
  settings (SMTP, GeoIP, netcup, rate limits); **audit log** with export; **security dashboard**
  surfacing attack-flagged events. See [`ADMIN_GUIDE.md`](ADMIN_GUIDE.md).

### Notifications
- **Email** (async) and **Telegram** channels. Security alerts: failed-login, new-IP login,
  password change, **2FA lockout**. Delivery is **backgrounded** so a slow email/Telegram
  endpoint never blocks a request (`NOTIFICATIONS_SYNC` forces synchronous delivery for tests).

### Configuration & deployment
- **Config-driven, no hardcoded values**: `.env.defaults` → environment → DB settings.
- **First-start seeding** from `app-config.toml` (`[[users]]`, `[[backends]]`, `[[domain_roots]]`).
  See [`TOML_CONFIGURATION.md`](TOML_CONFIGURATION.md).
- **Passenger deployment** via `deploy.sh` with production-parity local testing.
- **Greenfield deploys** (see roadmap): each deploy provisions a fresh, freshly-seeded database.

### Security
Constant-time secret comparisons, bcrypt password/token hashing, scoped audit trail, optional
GeoIP checks, CSRF on cookie routes. Full posture and known gaps: [`SECURITY.md`](SECURITY.md).

## Roadmap (planned / not yet implemented)

| Area | Planned capability | Notes |
|------|--------------------|-------|
| Backends | **Cloudflare, Route53** providers | The `backends/` abstraction is ready; these are not yet implemented. |
| Deploy / data | **Data-preserving (in-place) upgrades** | Today deploys are intentionally **greenfield** — each deploy wipes and reseeds the DB, so schema/app can change freely. A real migration path (e.g. Alembic) is required before production data must survive an update. A lightweight additive-column migration (`run_lightweight_migrations`) already guards accidental data retention; it is **not** a substitute for full migrations. |
| Security | **Encryption at rest for sensitive secrets** (TOTP seeds) | Candidate approach for the shared-webspace constraint: a **filesystem-stored master key** on the webspace used to encrypt/decrypt sensitive DB fields. We control the webspace filesystem even on shared hosting; **TLS termination is the webhoster's responsibility**, so transport-layer hardening (HSTS/CSP) is out of scope here. |
| Security | **Self-service 2FA-lockout unlock** & lockout visibility | Lockout + lockout notifications exist; user-driven unlock and a status view do not. |
| Notifications | **Background dispatch for the remaining notify_\* paths** & a **webhook channel** | Request-hot-path security notifications are already backgrounded; admin/cron-triggered ones still send inline. |
| Portal | **Token usage analytics** | Surface per-token activity from the audit log in the account portal. |

Have an idea or a gap to file? Add it here (kept in sync with `CHANGELOG.md` and the code).
