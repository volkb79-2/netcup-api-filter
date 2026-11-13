---
schema_version: 1
id: naf-I04-host-traefik-exposure
project: naf
title: "Retire naf's own nginx/cert dev edge; expose via the host traefik with ciu labels"
tier: sonnet5-high
input_revision: "f912479"
depends_on: [naf-I01-ciu-adoption]
session: fresh
source: {kind: plan, ref: "nyxloom-trove/archive/INFRA-PLAN-2026-07-20.md#INFRA-4"}
status: DONE — merged (3049c49); the "changes deploy.sh" premise is obsolete (deploy.sh retired); see ../STATE.md
supersedes: [naf-P05-workspace-fqdn-unbound#O2]
scope:
  touch:
    - "tooling/reverse-proxy/**"
    - "deploy.sh"
    - ".env.services"
    - "docs/FQDN_DETECTION.md"
    - "tooling/test-runner/ciu.compose.yml.j2"
    - ".devcontainer/post-create.sh"
  forbid:
    - "src/**"
    - "passenger_wsgi.py"
    - "requirements.webhosting.txt"
oracles:
  - id: O1
    observable: "The dev app is reachable over HTTPS at the configured Host() via the running edge-traefik, with a valid cert issued by traefik's letsencrypt resolver, while naf itself ships NO nginx, NO cert material and NO /etc/letsencrypt mount."
    negative: "Today naf runs its own naf-dev-reverse-proxy nginx that terminates TLS from a host /etc/letsencrypt bind — duplicating an edge the host already provides and coupling the dev stack to PUBLIC_TLS_* paths."
    gate: trove
  - id: O2
    observable: "grep across the repo for reverse-proxy / letsencrypt / PUBLIC_TLS_ returns no live naf-owned proxy or cert handling; `env -i bash -c 'set -euo pipefail; source .env.services'` still exits 0."
    negative: "Dead proxy scaffolding and PUBLIC_TLS_* plumbing linger with no consumers, and docs still describe a reverse-DNS FQDN mechanism that no longer exists."
    gate: trove
gates: [trove]
escalate_if:
  - "the operator has not confirmed the public FQDN / that wildcard DNS resolves it to this host — the Host() rule cannot be guessed"
  - "removing the nginx edge would break a consumer other than the dev app / PowerDNS / Mailpit"
  - "PUBLIC_FQDN has a consumer beyond the session-cookie domain and the PowerDNS URL"
---

# naf-I04 — one edge, owned by the host

> **STATE (2026-07-21): ✅ DONE** — host-traefik exposure landed (`3049c49`); naf terminates no TLS. The premise's "changes deploy.sh" is obsolete (deploy.sh retired in P4). See [../STATE.md](../STATE.md).

> **PAUSED — carved for operator review.** Needs Decision A (the FQDN) confirmed and changes
> `deploy.sh`. Recorded under D-006 (REVIEW-ME).
> Base: `main` @ `f912479`. Gate: `./tooling/test-runner/testing-exec.sh trove`.

## Context — and the critical scope boundary

naf's reverse-proxy / TLS / `PUBLIC_FQDN` machinery is **exclusively a DEV/local-stack
concern**. **Production is shared webhosting under Passenger, where the hoster terminates
TLS** — naf ships no proxy and no certs there. So "reuse the host traefik" replaces **only the
dev nginx edge**; it must touch **nothing** in the production Passenger path. The app keeps its
`ProxyFix` (`app.py:75`) — it still reads `X-Forwarded-Proto`, now from traefik instead of nginx.

Verified on this host: `edge-traefik` (traefik v3.7), `edge-dockerproxy` and the
`ingress_public` network are already running. traefik's `websecure` entrypoint carries
`certResolver: letsencrypt`, so **consumers need no TLS/cert labels at all**.

## Remove (all dev-only)

- The whole `tooling/reverse-proxy/` directory — `docker-compose.yml` (`naf-dev-reverse-proxy`,
  nginx:stable-alpine, publishes 443/80, binds host `/etc/letsencrypt:ro`),
  `nginx.conf.template` (terminates TLS; fronts Flask `/`, Mailpit under its configured webroot, PowerDNS
  the retired path-based PowerDNS route), `_proxy_lib.sh`, `render-nginx-conf.sh`, `certs/`, `proxy.env`.
- `deploy.sh`: `start_tls_proxy`/`stop_tls_proxy` (`:704-809`), the
  `USE_HTTPS && DEPLOYMENT_TARGET==local` branch (`:831`), the `naf-dev-reverse-proxy` cleanup
  (`:1378-1391`), `SERVICE_REVERSE_PROXY` (`:57`).
- The host `/etc/letsencrypt` mount and all `PUBLIC_TLS_CRT_PEM` / `PUBLIC_TLS_KEY_PEM`
  handling — traefik's ACME owns certs now.
- `docs/FQDN_DETECTION.md`'s reverse-DNS detection mechanism (rewrite the doc to describe the
  config-fact model).

## Add

The exposed dev containers join the external `ingress_public` network and carry exactly four
labels (TLS inherited from the entrypoint):

```
traefik.enable=true
traefik.http.routers.<stack>-<svc>.rule=Host(`<name>.<public_fqdn>`)
traefik.http.routers.<stack>-<svc>.entrypoints=websecure
traefik.http.services.<stack>-<svc>.loadbalancer.server.port=<container-port>
```

Router/service names must be **host-unique** (convention `<stack>-<service>`). Add
`traefik.docker.network=ingress_public` for multi-homed containers. Use `expose:`, never
`ports:`. Keep backends on the internal `naf-dev-network`.

**Exposure set (Decision D):** the app (HTTPS UI/API) and the PowerDNS API edge get public
routes; **Mailpit stays internal-only**.

## FQDN — the one thing that cannot be guessed (Decision A, OPEN)

`PUBLIC_FQDN` becomes a **ciu config fact** (like dstdns's `ciu.env`), **not** a reverse-DNS
PTR lookup. It is still needed for the session-cookie domain (`app.py:144-155`) and for
re-pointing `.env.services`' `POWERDNS_API_URL`. **Confirm with the operator** the hostname and
that wildcard DNS resolves it to this host before writing any `Host()` rule. Default proposal:
a subdomain under the same wildcard base dstdns uses (`naf.<base>`).

## Supersedes naf-P05 O2

naf-P05 **O2** (make `post-create.sh` write `PUBLIC_FQDN` via reverse-DNS per
`docs/FQDN_DETECTION.md`) exists *solely* to feed the dev nginx TLS proxy and the
PowerDNS-over-public-edge URL — exactly what traefik takes over. Under this package the FQDN is
config, and `PUBLIC_TLS_*` loses all consumers. **Close naf-P05 as superseded** when this lands
(O1 already shipped). Do not implement O2.

## Gate

`./tooling/test-runner/testing-exec.sh trove` for the shell contracts, plus a manual proof that
the dev app answers over HTTPS at the configured Host() through edge-traefik with a
traefik-issued cert. Record it in the REPORT.

## BLOCKED rule

If the FQDN is unconfirmed, or a contract cannot be met, or a forbidden file must change,
STOP: write `BLOCKED: <reason>` to the LOG, commit, exit.
