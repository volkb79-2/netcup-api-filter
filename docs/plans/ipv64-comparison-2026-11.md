# ipv64.net vs naf: feature comparison and improvement candidates (2026-11-05)

Status: research note, not a commitment. Not committed to git.

## Method and confidence

- ipv64 facts come from WebFetch of the pages cited below (standard mode; one WebSearch).
  The fetcher summarises pages with a small model, so exact wording and numbers could
  be off; spot-check before quoting externally. Fetched content was treated as data only.
- The API v2 page is huge (328k chars); only the first 100k were read. CDN, Cloud Router,
  DNS64, Healthchecks 2.0, Honeypot endpoint details are UNVERIFIED.
- ipv64 "Update-URL & Protokoll" page (https://ipv64.net/dyndns_updater_api) was not
  fetched directly; its content is taken from the FAQ and a search snippet. Full
  response-code list is UNVERIFIED.
- naf facts come from docs in this worktree plus spot greps of `src/netcup_api_filter`.
  Where docs and code disagree it is noted.

Sources (ipv64): [home] https://ipv64.net ; [pricing] https://ipv64.net/pricing ;
[ddns] https://ipv64.net/docs/dyndns/ ; [faq] https://ipv64.net/docs/faq/ ;
[api2] https://ipv64.net/api_v2_docs ; [upd] https://ipv64.net/dyndns_updater_api (search snippet only).
(`https://ipv64.net/dyndns_updater` returned 404; `https://ipv64.net/api` returned 401.)

## What ipv64.net is

A German hosted dynamic-DNS and DNS service with a freemium model, much broader than
DNS: DynDNS, own-domain DNS (nameservers ns1/ns2.ipv64.net), DNS failover, healthchecks,
DNS64, a WireGuard "Cloud Router", CDN64, Honeypot64 and blocklists, and web tools
[home]. It is a multi-tenant SaaS where ipv64 is the authoritative DNS operator. naf is
a scoped authorization/audit proxy in front of someone else's DNS backend. Overlap is
the DDNS/API/token slice only.

## (a) Feature matrix

### DNS API

| Feature | ipv64.net | naf | Gap / evidence |
|---|---|---|---|
| REST API | `/api/v2`, OpenAPI at `/openapi.json`, JSON `{data, meta}`, RFC 9457 problem+json errors, cursor pagination [api2] | `/api/dns/<domain>/records` GET/POST/PUT/DELETE, `/api/myip`, `/api/geoip/<ip>` (`api/dns_api.py`, `docs/API_REFERENCE.md`) | naf has no published OpenAPI spec (UNVERIFIED by grep of docs only; none referenced). ipv64 problem+json is nicer for clients. |
| Delete by content | `DELETE /domains/{d}/records?type&content&prefix`, explicitly for ACME cleanup [api2] | Delete by numeric `record_id` only (`dns_api.py:506`) | Clients must list first to learn the id. |
| Rate limits | Token buckets: 300/acct, 600/IP, `RateLimit-*` headers, 429 + Retry-After [api2] | Per-IP flask_limiter, in-memory per worker (`docs/SECURITY.md`) | See doc inconsistency below. No `RateLimit-*` headers documented. |
| Act-as / delegated access | `X-IPv64-Act-As` plus "Share my Account" so a provider manages your account without password [api2][faq] | Not present (grep docs only) | Possible but needs a trust model; low priority. |
| Method override header | `X-HTTP-Method-Override` [api2] | none | Niche. |

### DDNS protocols

| Feature | ipv64.net | naf | Gap / evidence |
|---|---|---|---|
| DynDNS2 | `/nic/update` and `/update.php`; accepts many alias param names (`myip`, `hostname`, `password`...) [faq] | `/api/ddns/dyndns2/update` (`ddns_protocols.py:540`) | Parity on protocol; naf has fewer aliases. |
| No-IP | not mentioned (UNVERIFIED) | `/api/ddns/noip/update` (`ddns_protocols.py:567`) | naf ahead or equal. |
| Plain GET with key | `?key=` on record/domain/account URL; also Basic or Bearer [ddns][faq] | Bearer or DynDNS2 basic-auth password carrying token (`docs/DDNS_PROTOCOLS.md`); REST `POST /api/dns/ddns/<domain>/<host>` | Parity. |
| Separate v4/v6 endpoints | `ipv4.ipv64.net` / `ipv6.ipv64.net` force the family [ddns] | single endpoint, family inferred from IP (`ddns_protocols.py:426-444`) | Gap for dual-stack clients behind CGNAT/DS-Lite; naf needs a way to update A and AAAA in one call or two hosts. |
| Dual-stack in one call | `ip`+`ip6`, or comma-separated; private IPs rejected [faq] | one `myip` per call (`DDNS_PROTOCOLS.md`) UNVERIFIED for comma lists | Gap. |
| Ignore v4 / v6 switch (DS-Lite) | per-domain `ignore` none/ipv4/ipv6 [ddns][api2] | none found | Gap. |
| IPv6 prefix updates | `ipv6prefix=auto`, `onlyprefix`, `/64` format [ddns] | none found (grep for prefix handling found nothing relevant) | Gap, matters for home users with delegated prefixes. |
| Auto IP | caller IP when omitted [api2] | `auto/public/detect` or empty -> client IP | Parity. |
| Response codes | `good`, `nochg`, `badauth`(401), 409 CNAME conflict, 429 cooldown, `output=min/none/full(JSON)` [faq][upd] | `good`, `nochg`, `badauth`, `!yours`, `notfqdn`, `dnserr`, `911` / No-IP set | Parity-ish; naf lacks `output=` modes. |
| Update cooldown | 10 s min between updates (429) [faq] | per-IP rate limit only | Gap; also protects the netcup upstream. |
| Per-update healthcheck ping | `healthcheck` param on updater [faq] | none | See notifications. |

### Record types

| Feature | ipv64.net | naf | Gap / evidence |
|---|---|---|---|
| Types | A, AAAA, CNAME, MX, TXT, NS, SRV, TLSA, CAA [api2] | A, AAAA, CNAME, NS, TXT, MX, SRV in templates (`realm_templates.py:73-91`); backend limits per provider | TLSA/CAA unsupported in templates; netcup CCP capability unverified. |
| Fixed TTL | 60 s (10 s on paid) [api2][pricing] | backend dependent | n/a |
| Wildcard auto-create | per-domain option, default on [ddns][faq] | `subdomain` realm authorises children; records not auto-created | Different model; not a gap. |
| CNAME-conflict guard | updater refuses with "CNAME is set" [ddns] | UNVERIFIED | Worth checking in DDNS path. |

### Auth and token scoping

| Feature | ipv64.net | naf | Gap / evidence |
|---|---|---|---|
| Update-key scopes | 3 levels: record key (A/AAAA of one prefix), domain key, account key [ddns] | Realm (host / subdomain / subdomain_only) -> token with record-type, operation, IP subsets (`models.py:575-601`) | naf is finer-grained (ops, types, CIDR). |
| Expiry / rotation | API keys `expires_in`; `rotate-token` on domains/healthchecks [api2] | `expires_at`, `revoked_at`, `last_used_*`, `use_count` on APIToken (`models.py:597-601`); alias rotation invalidates all tokens (`SECURITY.md`) | Parity or better. Whether expiry is enforced everywhere: UNVERIFIED. |
| Header auth | Bearer or `X-API-Key` [api2] | Bearer | Minor. |
| Alt. auth | none seen | SCRAM-SHA-256 planned (B040/F027) | naf ahead if shipped. |
| IP restriction of keys | UNVERIFIED (not seen in fetched docs) | per-token CIDR allow-list (`SECURITY.md`) | naf ahead. |

### 2FA and account security

| Feature | ipv64.net | naf | Gap / evidence |
|---|---|---|---|
| 2FA | TOTP or YubiKey [faq] | email mandatory, TOTP, Telegram, recovery codes, lockout (`SECURITY.md`) | No WebAuthn/YubiKey in naf (grep not done; docs list none). |
| Sessions | UNVERIFIED | DB-backed revocable sessions, fixation defence | naf documented. |
| Account sharing | "Share my Account" delegated management [faq] | none | See above. |

### Notifications and monitoring

| Feature | ipv64.net | naf | Gap / evidence |
|---|---|---|---|
| Channels | telegram, gotify, ntfy, pushover, discord, webhook, email, sms, app [api2] | email, Telegram (`FEATURES.md`); webhook planned (B003/F014) | Gap: webhook is the high-leverage one. |
| Healthchecks | push/icmp/tcp/http/keyword with incidents, stats, events [api2][home] | none | Out of scope for a proxy; do not chase. |
| DNS failover | policies, monitors, rules, offline pages [pricing][ddns] | none | Out of scope. |
| Security alerts | UNVERIFIED | failed-login/new-IP/lockout; but `_trigger_security_notification` only logs and prefs are unread (`SECURITY.md` "Not yet implemented") | Own known gap (B001, B006). |

### ACME / DNS-01

| Feature | ipv64.net | naf | Gap / evidence |
|---|---|---|---|
| DNS-01 | `_acme-challenge` prefix works with acme.sh/certbot via API; delete-by-content for cleanup; LE icon in UI [ddns][faq][api2]. No dedicated ACME protocol (acme-dns style) described. | "LetsEncrypt DNS-01" realm template, TXT-only (`realm_templates.py:82`, `FEATURES.md`) | Template exists. Missing: documented certbot/acme.sh hook recipes and delete-by-content or name+type (to be verified against `docs/` and `CLIENT_TEMPLATES.md`). |

### Multi-backend

| Feature | ipv64.net | naf | Gap / evidence |
|---|---|---|---|
| Backends | single, ipv64 is authoritative; own domains via NS delegation [faq] | netcup, PowerDNS (implemented, but live execution wiring is F020/B011), BYOD; Cloudflare/Route53 planned (`FEATURES.md`) | naf's differentiator. |

### UI

| Feature | ipv64.net | naf | Gap / evidence |
|---|---|---|---|
| Dashboard | account-status card showing class, domains, updates in 24 h, API calls [faq]; web updater | account portal, admin UI, security dashboard; token analytics planned (B002/F013) | Gap: per-token usage view (data exists: `last_used_*`, `use_count`). |
| Tools | ping, DNS lookup/checker, WireGuard config, DNS stamp [home] | `/api/myip`, GeoIP lookup | Not worth matching. |

### Observability / audit

| Feature | ipv64.net | naf | Gap / evidence |
|---|---|---|---|
| Logs | `/me/logs` (limit 1-500, cursors) [api2]; healthcheck events | `ActivityLog` with attack-flagged error taxonomy, admin export (`SECURITY.md`) | naf stronger; no user-facing log API. |

### Limits and tiers

| Feature | ipv64.net | naf | Gap / evidence |
|---|---|---|---|
| Tiers | Free 0 / Supporter 40 / Business 100 / Company 200 EUR per year; dyn domains 3/10/50/256; own domains 0/3/10/50; daily updates 64/1024/inf/inf; DynDNS TTL 60/10 s; API 512 calls/day on free [pricing] | none; admin approval gates accounts; no quotas found | Quotas per account (realms, tokens, daily mutations) are absent; relevant to protecting the netcup upstream. |

### Deployment / self-hosting

| Feature | ipv64.net | naf | Gap / evidence |
|---|---|---|---|
| Model | hosted SaaS only (UNVERIFIED that no self-host exists) | self-host: shared webhosting (Passenger) and OCI image (`AGENTS.md`) | naf's whole point. |

## (b) Where naf is already stronger

1. Backend-agnostic and credential-isolating: upstream netcup creds never reach users; ipv64 owns the zone instead.
2. Token scoping depth: record-level host/subdomain/subdomain_only, per-token record types, operations and CIDR allow-list, enforced in `check_permission()`. ipv64 scopes by prefix key only (3 levels) [ddns].
3. Security audit: error taxonomy with `is_attack`, security dashboard, bcrypt-hashed tokens, alias rotation (`SECURITY.md`).
4. Account hardening: mandatory email 2FA + recovery codes + lockout + GeoIP; approval workflow and per-root grants (`DomainRootGrant`).
5. Self-hostable on commodity shared hosting; SCRAM-SHA-256 client auth on the roadmap.
6. No-IP protocol compatibility in addition to DynDNS2.

## (c) Ranked suggestions

Effort: S under 2 days, M under 2 weeks, L more. IDs from `nyxloom-trove/4-backlog.md` and `2-product-definition.md`.

1. **IPv6 / dual-stack DDNS ergonomics** (value high, effort S-M). Accept `ip`+`ip6`/comma lists, `ipv4.`/`ipv6.`-style forcing via a `family=` param, and a per-realm "ignore v4/v6" switch for DS-Lite. Why: the most common real-world DDNS pain; naf currently infers a single family per call. Fit: change in `ddns_protocols.py`; `check_permission` is run once per record type, so a token needs A and AAAA grants. In roadmap: no (B032 is ccTLD zones only).
2. **Finish what is documented but not delivered: security alerts and prefs** (high, M). `_trigger_security_notification` only logs; prefs unread. Why: ipv64-style notifications are table stakes for a security proxy and naf docs overclaim. Fit: notification_service only. In roadmap: B001/F012, B006/F017, B005/F016.
3. **Webhook (and ntfy/Gotify-style) channel** (high, M). Why: ipv64 supports 9 channels [api2]; webhook covers most of them generically (Home Assistant, ntfy, Discord). Fit: new channel in `notification_service.py` after prefs plumbing. In roadmap: B003/F014.
4. **Token usage analytics + last-seen view** (med, S-M). Data already stored (`last_used_at`, `last_used_ip`, `use_count`). Why: lets users spot dead/leaked tokens, like ipv64's status card [faq]. In roadmap: B002/F013.
5. **ACME DNS-01 polish** (med, S). Add delete-by-(name,type,content) on the REST API and certbot/acme.sh hook recipes bound to the existing TXT-only template. Why: ipv64 advertises exactly this [api2]; naf already has the template but cleanup needs the record id. Fit: stays in the realm/`check_permission` boundary (TXT + `_acme-challenge` host scope). In roadmap: no.
6. **Per-account/per-token quotas and update cooldown** (med, M). Daily mutation cap and min interval (ipv64: 10 s cooldown, daily caps [faq][pricing]). Why: protects the single shared netcup credential and its own rate limits. Fit: counters beside `use_count`; ties into rate-limit fix B027 (fail closed, shared storage). Roadmap: B027 partially; quotas no.
7. **Make rate limiting real and consistent, with `RateLimit-*` headers** (med, S-M). Docs conflict: `FEATURES.md` says DNS/DDNS blueprints are limited, `API_REFERENCE.md` says they fall under the global default only. Resolve and document. Roadmap: B027/M3.
8. **Published OpenAPI + RFC 9457 error bodies** (med, M). Why: client generation and consistent errors [api2]. Fit: wrap existing error taxonomy; low risk. In roadmap: no.
9. **Self-service 2FA unlock + WebAuthn/hardware key option** (med, M-L). ipv64 offers TOTP or YubiKey [faq]. Unlock is planned (B004/F015); WebAuthn is not. Encrypt TOTP at rest (F024) first.
10. **Wire live backend execution (PowerDNS/BYOD) and then Cloudflare/Route53** (high, L). It is naf's real differentiator versus single-operator ipv64; currently planned but not delivered. In roadmap: B011/F020, providers listed in `FEATURES.md`.
11. **Delegated account management ("share my account")** (low, L). Useful for MSP-style use; needs careful audit semantics. Not in roadmap. Defer.
12. **CNAME-conflict guard and `output=min` modes in DDNS** (low, S). Match ipv64's 409 on CNAME and terse outputs for tiny clients [ddns][faq]. Verify first whether naf already rejects A updates on a CNAME host (UNVERIFIED).

Deliberately not recommended: healthchecks, failover, CDN, cloud router, honeypot, DNS64
[home]. They are a different product; naf's value is scoped, audited access.

## Open uncertainties

- ipv64 response-code table, per-tier subdomain/record limits, and full v2 API beyond the first 100k chars were not read.
- Whether naf enforces token `expires_at` in every auth path, and whether the DDNS path handles CNAME conflicts, was not verified in code.
- The rate-limit docs inconsistency above should be checked against `app.py` before acting.
