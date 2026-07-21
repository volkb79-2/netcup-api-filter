# FQDN Detection (superseded)

**This document is superseded by naf-I04 (host-traefik exposure) and no longer describes
a live mechanism.** It used to document reverse-DNS auto-detection of `PUBLIC_FQDN`
(`.devcontainer/post-create.sh` querying the external IP and doing a PTR lookup) feeding
naf's own dev nginx TLS reverse-proxy (`tooling/reverse-proxy/`, since removed) and its
`PUBLIC_TLS_CRT_PEM`/`PUBLIC_TLS_KEY_PEM` cert paths.

None of that exists anymore:

- naf's dev nginx reverse-proxy is retired. Dev services are exposed through the
  host-owned `edge-traefik`, which owns TLS via its `letsencrypt` cert resolver — naf
  ships no proxy and no certs in dev (and never did in production; production is
  Passenger on shared webhosting, where the hoster terminates TLS).
- `PUBLIC_FQDN` is now a **ciu config fact**
  (`topology.external.public_fqdn` in `ciu.global.defaults.toml.j2`), not a reverse-DNS
  PTR lookup. It is still used for the session-cookie domain and to derive
  `.env.services`' `POWERDNS_API_URL` (`https://naf-pdns.${PUBLIC_FQDN}`), guarded the
  same way it always was on `[ -n "${PUBLIC_FQDN:-}" ]`.
- `detect-fqdn.sh`, `tooling/reverse-proxy/auto-detect-fqdn.sh`, and the `.env.workspace`
  reverse-DNS write documented below are gone (naf-P05 O2 — superseded, never
  implemented).

For how the current dev/test stack is set up, exposed, and how `PUBLIC_FQDN` is
configured, see **`docs/DEV_INFRA_SETUP.md`**.
