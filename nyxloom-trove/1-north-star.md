---
kind: north-star
schema_version: 1
---

# naf north star

naf makes dynamic DNS safe to delegate. It fronts DNS-provider APIs with narrow,
record-level authority and an audit trail, so a machine can update only the DNS records
its owner explicitly granted it.

The product joins a usable account portal and admin surface with provider-independent
DNS execution: netcup is the current platform path, while PowerDNS and user-owned
backends are being made real rather than merely configurable. It should be deployable
with production parity on shared Passenger hosting or as a container, without relaxing
the authorization, configuration, or test-gate discipline that makes the boundary
trustworthy.
