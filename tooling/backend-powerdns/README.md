# PowerDNS Backend Tooling

This ciu stack runs PowerDNS Authoritative Server as naf's optional self-managed DNS
backend. It provides a low-TTL authoritative DNS service and an HTTP API for local
development, live DNS verification, and the product's PowerDNS backend integration.

## Current stack

The stack has two services:

- a one-shot init container using the same pinned PowerDNS image that prepares the
  SQLite data directory and loads `schema.sqlite3.sql` when the database does not
  exist (the upstream image already carries `sqlite3`, so no floating Alpine image
  is needed);
- `powerdns/pdns-auth-48`, running after initialization with the gsqlite3 backend.

Publish and exposure are deliberately different:

- DNS is published directly on host port **53/udp + 53/tcp**. Real resolvers cannot
  reach an authoritative server through an HTTP reverse proxy.
- The HTTP API listens on `backend_powerdns.ports.api` (`8081` in the committed config).
  It is not published directly. Containers use the project network; external operators
  reach it at `naf-pdns.<PUBLIC_FQDN>` through host traefik, behind the same basicauth
  guard as the app.

The source of truth is `ciu.defaults.toml.j2` plus `ciu.compose.yml.j2`. Rendered
`ciu.toml` and `ciu.compose.yml` are gitignored artifacts; do not edit or commit them.

## Zone and hooks

The delegated zone is not configured in this directory. It is the global
`[topology.dns].delegated_zone` fact from `ciu.global.defaults.toml.j2`, sourced from the
operator environment as `NAF_DELEGATED_DNS_ZONE`. The committed default is empty.

On `ciu up`, `post_compose_zone.py` creates that zone when the value is non-empty. The
first creation derives all zone-specific records from the zone itself:

```text
NS   <zone>.          ns1.<zone>.
SOA  ns1.<zone>.      hostmaster.<zone>. <serial> 10800 3600 604800 3600
```

The hook is idempotent: an existing zone is left untouched, including its SOA serial.
An empty `NAF_DELEGATED_DNS_ZONE` is a no-op. No committed default guesses a zone,
nameserver, or SOA.

## Start the stack

`POWERDNS_API_KEY` is operator-supplied and must never be committed. The tracked
`.env.defaults` entry is intentionally empty. Until B045 moves the key to a ciu
`GEN_LOCAL` secret, compose interpolation and the app-local seed hook read it from the
operator environment.

```bash
cd /workspaces/netcup-api-filter

# Generate once into the gitignored local environment.
printf 'POWERDNS_API_KEY=%s\n' "$(openssl rand -hex 32)" >> .env

set -a
. ./ciu.env
. ./.env
. ./.env.operator
. ./.env.guard
set +a

# The stack alone, or the complete development profile.
ciu up --dir tooling/backend-powerdns
ciu up --profile full
```

`.env` provides the operator-supplied `POWERDNS_API_KEY`; `.env.operator` provides the
delegated zone; and `.env.guard` provides the basicauth username/password/hash used by
the traefik route. `ciu up` fails fast when `POWERDNS_API_KEY` or the
`NAF_GUARD_HTPASSWD` required by the compose template is absent. The command prints the
location of its generated secret store; values are never printed.

## URLs

Both PowerDNS URLs are defined by `.env.services`; there are no URL defaults in
`.env.defaults`. The API key comes from the gitignored `.env`, and the public route's
basicauth username/password come from the gitignored `.env.guard`. No secret value is
shown here.

| Fact | Source | Use |
|---|---|---|
| `POWERDNS_API_URL_INTERNAL` | `.env.services` | container-to-container API traffic |
| `POWERDNS_API_URL` | `.env.services` | guarded public edge; empty when `PUBLIC_FQDN` is unavailable |

Source the files when running API commands so both credentials and the URLs are
available:

```bash
set -a
. ./.env
. ./.env.guard
. ./.env.services
set +a

curl -sf -H "X-API-Key: $POWERDNS_API_KEY" \
  "$POWERDNS_API_URL_INTERNAL/api/v1/servers/localhost" |
  python3 -m json.tool
```

External access adds the traefik basicauth guard:

```bash
curl -sf -u "$NAF_GUARD_USER:$NAF_GUARD_PASSWORD" \
  -H "X-API-Key: $POWERDNS_API_KEY" \
  "$POWERDNS_API_URL/api/v1/servers/localhost"
```

## Record API examples

Use the zone from `NAF_DELEGATED_DNS_ZONE` and the internal URL for app-side work. The
PowerDNS zone identifier ends in a dot.

```bash
ZONE="${NAF_DELEGATED_DNS_ZONE%.}."

curl -X PATCH \
  -H "X-API-Key: $POWERDNS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "rrsets": [{
      "name": "test.'"${ZONE}"'",
      "type": "A",
      "changetype": "REPLACE",
      "ttl": 60,
      "records": [{"content": "192.0.2.1", "disabled": false}]
    }]
  }' \
  "$POWERDNS_API_URL_INTERNAL/api/v1/servers/localhost/zones/$ZONE"
```

To remove the record, PATCH the same endpoint with `"changetype": "DELETE"` and omit the
`ttl` and `records` fields.

## Configuration ownership

The stack keeps non-secret daemon configuration in `[backend_powerdns]`:

- `ports.dns = 53` and `ports.api = 8081`;
- image and image tag;
- data-directory UID;
- `PDNS_AUTH_*`, `PDNS_LAUNCH`, logging, and AXFR settings;
- health-check timing and external-route toggle.

Only `POWERDNS_API_KEY` is secret. The delegated zone and public FQDN are global
topology facts. The API port is also consumed by `.env.services` to form the internal
URL; keep the shell fact and `backend_powerdns.ports.api` aligned.

The retired helpers `ensure_zone.py`, `setup-zones.sh`, and `init-db.sh` were removed.
Zone creation belongs to the ciu `post_compose` hook, and schema initialization belongs
to the PowerDNS-image init service command in `ciu.compose.yml.j2`.

## Data and lifecycle

The database is the host bind mount
`tooling/backend-powerdns/data/pdns.sqlite3`, resolved through
`PHYSICAL_REPO_ROOT`. It is not a Docker named volume.

For an idempotent stack bring-up, use ciu. For a single-stack teardown, ciu's supported
shape is a rendered compose file scoped to the same ciu project:

```bash
cd tooling/backend-powerdns
docker compose -p <PROJECT_TAG>-<ENV_TAG>-backend-powerdns -f ciu.compose.yml down
```

To rebuild the database, stop the stack, move the existing data directory aside, and
start it again through ciu. The init container recreates the schema, and the hook creates
the delegated zone when configured.

## Troubleshooting

For startup failures, inspect:

```bash
docker ps --filter name=powerdns
docker logs <project-environment-powerdns>
```

Common causes are a missing `POWERDNS_API_KEY`, port 53 already occupied, or incorrect
permissions on the bind-mounted data directory. Port 53 must remain 53 for real
delegation; do not move it to an arbitrary host port.

If the API is unreachable, verify the URL selected by `.env.services`, the network shared
by the app and PowerDNS stacks, and the guard credentials used for the public route.

## References

- [PowerDNS Authoritative documentation](https://doc.powerdns.com/authoritative/)
- [PowerDNS HTTP API](https://doc.powerdns.com/authoritative/http-api/index.html)
