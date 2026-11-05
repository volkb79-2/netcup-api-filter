# naf dev/test infrastructure — sysadmin setup

How to stand up the netcup-api-filter dev/test stack: ciu-governed containers, exposed
through the host-side traefik (`edge-traefik`), with a real PowerDNS-served delegated zone
so end-to-end tests exercise the true DNS path over TLS.

> **This is dev/test infra, not the product.** Production naf ships to shared webhosting
> under Passenger (the hoster terminates TLS). Nothing here is part of a naf release; the
> operator-specific values below are placeholders a sysadmin fills in.

---

## 0. Prerequisites (on the host)

- The shared **`edge-traefik`** stack (`vbpub/tls-edge`) is running, owning the external
  **`ingress_public`** docker network and the `letsencrypt` cert resolver on the
  `websecure` (443) entrypoint. Exposed naf containers only need `traefik.enable` + a
  `Host()` rule; TLS/cert is inherited.
- `ciu` is installed. From this repo, **always** work with the repo's own env loaded
  (see §2) — the marker sets `standalone_root = true`, so ciu refuses to run if
  `$REPO_ROOT` points at a sibling repo.
- The host's public IP and base FQDN come from `ciu.env` (auto-detected):
  `PUBLIC_IP` and `PUBLIC_FQDN`. On this host: **`152.53.179.117`** /
  **`gstammtisch.dchive.de`**.

## 1. Operator secrets & facts (gitignored env files)

Three env files are sourced before every ciu command; none are committed:

| File | Origin | Holds |
|---|---|---|
| `ciu.env` | `ciu env generate` (machine facts) | `REPO_ROOT`, `PHYSICAL_REPO_ROOT`, `PUBLIC_IP`, `PUBLIC_FQDN`, network name |
| `.env.operator` | **you create** | `NAF_DELEGATED_DNS_ZONE` — the zone PowerDNS serves |
| `.env.guard` | generated (bcrypt) | `NAF_GUARD_USER` / `NAF_GUARD_PASSWORD` / `NAF_GUARD_HTPASSWD` — the traefik basicauth credential guarding every exposed route |

**Set the delegated zone** — the single value a sysadmin must supply:

```bash
# .env.operator  (gitignored)
export NAF_DELEGATED_DNS_ZONE="managed.vxxu.de"
```

The basicauth guard exists because the product is **not production-ready and must not be
publicly reachable**, while humans still reach it over real TLS. Regenerate its
credential any time (bcrypt hash for traefik + plaintext for browsing and `curl` by humans)
and re-`ciu up` the exposed stacks. The guard is for humans only: the e2e suite targets the
app over the internal docker network and never goes through traefik, so it carries no guard
credentials.

## 2. Load the env, then drive ciu

```bash
set -a; . ./ciu.env; . ./.env.operator; . ./.env.guard; set +a
ciu render                       # sanity: renders only naf's stacks
ciu up --profile full            # mocks + pwmcp + app + gate + PowerDNS
```

## 3. DNS records to create UPSTREAM

Two independent things resolve to this host — set both.

### 3a. Delegate the PowerDNS zone (`managed.vxxu.de`)

PowerDNS on this host is **authoritative** for `managed.vxxu.de`. For the internet to reach
it, the **parent zone `vxxu.de`** must delegate the subzone here. DNS queries hit **port 53
directly — NOT traefik** (traefik is HTTP/443 only). Create, at the `vxxu.de` authoritative
DNS / registrar:

| Type | Name | Value | Purpose |
|---|---|---|---|
| **NS** | `managed.vxxu.de.` | `ns1.managed.vxxu.de.` | delegate the subzone to this host's nameserver |
| **A** (glue) | `ns1.managed.vxxu.de.` | `152.53.179.117` | resolve that nameserver to this host |

So: **one NS (the delegation) + one A (glue for the nameserver name)** — your intuition was
right. (If you prefer a nameserver name already under `vxxu.de` that already A-records to
this host, point the NS at it and skip the glue.)

Also required for the delegation to actually answer:
- PowerDNS must **publish port 53/udp + 53/tcp** on `152.53.179.117` (the `backend-powerdns`
  stack does this; the host firewall must allow inbound 53).
- The zone inside PowerDNS carries its own SOA + NS:
  `managed.vxxu.de SOA ns1.managed.vxxu.de. hostmaster.vxxu.de. …` and
  `managed.vxxu.de NS ns1.managed.vxxu.de.` — created from `NAF_DELEGATED_DNS_ZONE`, not
  hardcoded.

### 3b. The traefik-exposed HTTPS hostnames (under `gstammtisch.dchive.de`)

These are the HTTP surfaces traefik routes + issues certs for. They must resolve to the host:

| Type | Name | Value | Serves |
|---|---|---|---|
| A | `naf.gstammtisch.dchive.de` | `152.53.179.117` | the app UI/API |
| A | `naf-pdns.gstammtisch.dchive.de` | `152.53.179.117` | the PowerDNS HTTP API (record management) |

If a wildcard `*.gstammtisch.dchive.de → 152.53.179.117` already exists (this base is shared
with dstdns), these are already covered — **nothing to add**. The hostnames are templated
from `PUBLIC_FQDN`, never hardcoded.

> **Two PowerDNS surfaces, two paths:** the **DNS protocol** (port 53) answers zone queries
> directly on the public IP via the delegation in §3a; the **HTTP API** (record CRUD) is
> reached by naf container-to-container internally, and — if external API access is wanted —
> exposed at `naf-pdns.<FQDN>` through traefik behind basicauth (§3b). The app does **not**
> need §3b to talk to PowerDNS; it's only for outside API access.

## 4. Verify

```bash
# app reachable over TLS behind the guard
curl -u "$NAF_GUARD_USER:$NAF_GUARD_PASSWORD" https://naf.gstammtisch.dchive.de/admin/login -I
# the delegation answers on port 53
dig +short NS managed.vxxu.de @152.53.179.117
dig +short A test.managed.vxxu.de @152.53.179.117    # once a record exists
# gate still green
run-gate gate --worktree "$PWD"
```

---

## Notes / gotchas

- **ciu resolves the wrong repo from this devcontainer without the env.** The shell exports
  a sibling repo's `REPO_ROOT`; always `source ciu.env` first. `standalone_root = true`
  turns a mismatch into a loud `[S1.2]` error instead of silently operating on the wrong
  repo (ciu ≥ the CIU-11 fix).
- **The gate image doesn't rebuild on dependency drift** (`ensure_image` builds only if
  missing) — `docker rmi netcup-api-filter/test-runner:{py311,py314}` after changing
  requirements, or the gate proves a stale closure (backlog B-INFRA).
- Committed ciu sources are `.j2` templates only; `ciu.toml` / `ciu.compose.yml` / `ciu.env`
  / `.ciu/` are rendered and gitignored — never edit the rendered files.
