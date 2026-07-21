# FQDN Detection (superseded)

**This document is superseded by naf-I04 (host-Traefik exposure) and no longer describes
a live mechanism.** It used to document reverse-DNS auto-detection of `PUBLIC_FQDN`
(`.devcontainer/post-create.sh` querying the external IP and doing a PTR lookup) and
certificate-path configuration.

None of that exists anymore:

- Dev services are exposed through the host-owned `edge-traefik`, which owns TLS via its
  `letsencrypt` cert resolver. naf ships no TLS material in dev (and production is Passenger
  on shared webhosting, where the hoster terminates TLS).
- `PUBLIC_FQDN` is now a **ciu config fact**
  (`topology.external.public_fqdn` in `ciu.global.defaults.toml.j2`), not a reverse-DNS
  PTR lookup. It is still used for the session-cookie domain and to derive
  `.env.services`' `POWERDNS_API_URL` (`https://naf-pdns.${PUBLIC_FQDN}`), guarded the
  same way it always was on `[ -n "${PUBLIC_FQDN:-}" ]`.
- The old detection scripts and `.env.workspace` reverse-DNS write are gone (naf-P05 O2 —
  superseded, never implemented).

For how the current dev/test stack is set up, exposed, and how `PUBLIC_FQDN` is
configured, see **`docs/DEV_INFRA_SETUP.md`**.
