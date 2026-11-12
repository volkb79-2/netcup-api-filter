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
- `ciu` 7.25.0 or newer is installed. From this repo, **always** work with the
  checkout's own generated env loaded (see §2) — the marker sets
  `standalone_root = true`, so ciu refuses to run if `$REPO_ROOT` points at a sibling
  repo.
- The host's public IP and base FQDN come from `ciu.env` (auto-detected):
  `PUBLIC_IP` and `PUBLIC_FQDN`. Read them from that environment; they are not
  committed documentation values.

## 1. Operator secrets & facts (gitignored env files)

Four env files are sourced before every ciu command; none are committed:

| File | Origin | Holds |
|---|---|---|
| `ciu.env` | `ciu env generate` (machine facts) | `REPO_ROOT`, `PHYSICAL_REPO_ROOT`, `PUBLIC_IP`, `PUBLIC_FQDN`, network name |
| `.env` | local operator environment | non-secret local overrides |
| `.env.operator` | **you create** | `NAF_DELEGATED_DNS_ZONE` — the zone PowerDNS serves |
| `.env.guard` | generated (bcrypt) | `NAF_GUARD_USER` / `NAF_GUARD_PASSWORD` / `NAF_GUARD_HTPASSWD` — the traefik basicauth credential guarding every exposed route |

**Set the delegated zone** — the single value a sysadmin must supply:

```bash
# .env.operator  (gitignored)
export NAF_DELEGATED_DNS_ZONE="<delegated-zone>"
```

The basicauth guard exists because the product is **not production-ready and must not be
publicly reachable**, while humans still reach it over real TLS. Regenerate its
credential any time (bcrypt hash for traefik + plaintext for browsing and `curl` by humans)
and re-`ciu up` the exposed stacks. The guard is for humans only: the e2e suite targets the
app over the internal docker network and never goes through traefik, so it carries no guard
credentials.

## 2. Prepare this checkout, load its env, then drive ciu

```bash
export DOCKER_HOST=unix:///run/docker-api/docker.sock   # when the cockpit exposes DooD here
export DOCKER_GID="$(stat -c '%g' /run/docker-api/docker.sock)"
ciu env generate
eval "$(ciu env print)"
export PWMCP_NETWORK="$(sed -n 's/^network_name = "\(.*\)"$/\1/p' /srv/pwmcp-instance/ciu.global.toml)"
test -n "$PWMCP_NETWORK"
set -a; . ./.env; . ./.env.operator; . ./.env.guard; . ./.env.services; set +a
ciu render                       # sanity: renders only naf's stacks
ciu up --profile full            # mocks + pwmcp + app + gate + PowerDNS
```

Each checkout owns a stable ciu `INSTANCE_ID`. Container and Compose names are
`naf-<INSTANCE_ID>-*`; the app frontend is `naf-<INSTANCE_ID>.<PUBLIC_FQDN>` and the
PowerDNS API is `naf-pdns-<INSTANCE_ID>.<PUBLIC_FQDN>`. A linked worktree does not
share the main checkout's gitignored env files: load the guard environment and the
non-secret per-stack inputs (for example `tooling/mailpit/.env`) directly from the
canonical checkout in the shell, or copy only non-secret files. Never copy the guard
hash, generated instance identity, or secret store between checkouts.

`.env.services` asks `ciu resolve --json --profile full` for each service's exact
container identity (it needs the env loaded in the order above: `ciu env print`,
`PWMCP_NETWORK`, `.env.guard`, then `.env.services`). There are no
`PROJECT_TAG`/`ENV_TAG` name formulas; delete stale shell exports of those
variables if an old session still has them.

Every checkout also runs its **own** gate runners: `ciu up --dir tooling/test-runner`
in the checkout precedes any `run-gate` there (see
[`tooling/test-runner/README.md`](../tooling/test-runner/README.md); a worktree's
runner additionally mounts the main checkout's `.git`, the git common dir).

**app-local sits behind the host traefik with zero trusted proxy hops.** Humans
reach `naf-<INSTANCE_ID>.<PUBLIC_FQDN>` through edge-traefik, but
`app_local.trusted_proxy_hops` is deliberately `0` until WP4b-2/WP5 measure the hop
chain (an unmeasured hop is never trusted; `pre_compose_validate.py` enforces it).
Consequence: every request through traefik shows traefik's address as the client,
so per-IP rate limits, login lockout, GeoIP checks and the activity log see all
human clients as one address on this dev instance.

## 3. DNS records to create UPSTREAM

Two independent things resolve to this host — set both.

### 3a. Delegate the PowerDNS zone (`NAF_DELEGATED_DNS_ZONE`)

PowerDNS on this host is **authoritative** for the operator-supplied
`NAF_DELEGATED_DNS_ZONE`. For the internet to reach it, the parent zone must
delegate that subzone here. DNS queries hit **port 53 directly — NOT traefik**
(traefik is HTTP/443 only). Create the following at the parent zone's
authoritative DNS / registrar:

| Type | Name | Value | Purpose |
|---|---|---|---|
| **NS** | `<delegated-zone>.` | `ns1.<delegated-zone>.` | delegate the subzone to this host's nameserver |
| **A** (glue) | `ns1.<delegated-zone>.` | `$PUBLIC_IP` | resolve that nameserver to this host |

So: **one NS (the delegation) + one A (glue for the nameserver name)** — your intuition was
right. If a nameserver name in the parent zone already has an A/AAAA record for this host,
point the NS at it and skip the glue.

Also required for the delegation to actually answer:
- PowerDNS must **publish port 53/udp + 53/tcp** on `$PUBLIC_IP` (the `backend-powerdns`
  stack does this; the host firewall must allow inbound 53).
- The zone inside PowerDNS carries its own SOA + NS:
  `NS ns1.<delegated-zone>.` and
  `SOA ns1.<delegated-zone>. hostmaster.<delegated-zone>. …` — both derived from
  `NAF_DELEGATED_DNS_ZONE` by the post-compose hook, never hardcoded.

### 3b. The traefik-exposed HTTPS hostnames (under `$PUBLIC_FQDN`)

These are the HTTP surfaces traefik routes + issues certs for. They must resolve to the host:

| Type | Name | Value | Serves |
|---|---|---|---|
| A | `naf-<INSTANCE_ID>.$PUBLIC_FQDN` | `$PUBLIC_IP` | the app UI/API |
| A | `naf-pdns-<INSTANCE_ID>.$PUBLIC_FQDN` | `$PUBLIC_IP` | the PowerDNS HTTP API (record management) |

If a wildcard `*.$PUBLIC_FQDN → $PUBLIC_IP` already exists, these are already
covered — **nothing to add**. The hostnames are templated from `PUBLIC_FQDN`,
never hardcoded.

> **Two PowerDNS surfaces, two paths:** the **DNS protocol** (port 53) answers zone queries
> directly on the public IP via the delegation in §3a; the **HTTP API** (record CRUD) is
> reached by naf container-to-container internally, and — if external API access is wanted —
> exposed at `naf-pdns-<INSTANCE_ID>.<FQDN>` through traefik behind basicauth (§3b). The app does **not**
> need §3b to talk to PowerDNS; it's only for outside API access. `.env.services` is the
> single source for both URLs: `POWERDNS_API_URL_INTERNAL` is the container URL and
> `POWERDNS_API_URL` is `https://naf-pdns-<INSTANCE_ID>.<FQDN>` (empty when
> `PUBLIC_FQDN` is unavailable). The PowerDNS API key is the checkout-local
> `GEN_LOCAL:naf/powerdns_api_key`; never put it in `.env` or copy it between worktrees.

## 4. Verify

```bash
# app reachable over TLS behind the guard
curl -u "$NAF_GUARD_USER:$NAF_GUARD_PASSWORD" "https://naf-${INSTANCE_ID}.$PUBLIC_FQDN/admin/login" -I
# the delegation answers on port 53
dig +short NS "$NAF_DELEGATED_DNS_ZONE" @$PUBLIC_IP
dig +short A "test.$NAF_DELEGATED_DNS_ZONE" @$PUBLIC_IP    # once a record exists
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
