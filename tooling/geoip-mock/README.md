# GeoIP Mock Server

Mock implementation of MaxMind GeoIP API for testing IP geolocation features.

## Quick Start

This stack is **ciu-managed** (naf-I01 follow-on). `ciu.compose.yml` is a RENDERED,
gitignored artifact — edit `ciu.compose.yml.j2` / `ciu.defaults.toml.j2`, never the
output. Note the `--define-root`: this devcontainer's shell exports dstdns's
`REPO_ROOT`, so a bare `ciu` call resolves to the wrong repo (backlog B-INFRA).

```bash
# Ensure GEOIP_MOCK_PORT is set (host port binding); PHYSICAL_REPO_ROOT and
# DOCKER_NETWORK_INTERNAL come from .env.workspace / ciu.env.
ciu render --define-root /workspaces/netcup-api-filter
ciu up --dir tooling/geoip-mock --define-root /workspaces/netcup-api-filter

# View logs
docker logs -f naf-dev-mock-geoip

# Stop server
ciu down --dir tooling/geoip-mock --define-root /workspaces/netcup-api-filter
```

`ciu up` also applies the cgroup/memory/IOPS governance overlay from `[governance]`
in `ciu.global.defaults.toml.j2` (`.ciu/ciu.compose.overlay.yml`).

## Access

- **API**: http://localhost:5556 (from host)
- **Container**: http://naf-dev-mock-geoip:5556 (from containers on `naf-dev-network`;
  matches `HOSTNAME_MOCK_GEOIP` / `MOCK_GEOIP_API_URL` in `.env.services`. The short
  service alias `mock-geoip` also resolves, via Docker's automatic per-service DNS.)
- **Health check**: http://localhost:5556/health

## Configuration

| Where | What | Why |
|---|---|---|
| `ciu.defaults.toml.j2` | stack scalars: `name`, `image`, `image_tag`, `port` | identity; version-controlled |
| `.env.workspace` / `ciu.env` | `PHYSICAL_REPO_ROOT`, `DOCKER_NETWORK_INTERNAL`, `USER_UID`, `DOCKER_GID` | per-environment; auto-generated |

Env vars still read at compose time (host-side, not templated — see `ciu.compose.yml.j2`):

| Variable | Default | Description |
|----------|---------|-------------|
| `GEOIP_MOCK_PORT` | *(required)* | API port (host binding) |
| `FLASK_ENV` | `development` | Flask environment |
| `FLASK_DEBUG` | `false` | Enable Flask debug mode |

## API Endpoints

### GET /health
Health check endpoint.

**Response**:
```json
{"status": "ok"}
```

### GET /country/{ip}
Get country information for IP address.

**Response**:
```json
{
  "country": {
    "iso_code": "DE",
    "name": "Germany"
  }
}
```

### GET /city/{ip}
Get city information for IP address.

**Response**:
```json
{
  "city": {
    "name": "Berlin"
  },
  "country": {
    "iso_code": "DE",
    "name": "Germany"
  }
}
```

## Usage Examples

```bash
# Check health
curl http://localhost:5556/health

# Get country for IP
curl http://localhost:5556/country/8.8.8.8

# Get city for IP
curl http://localhost:5556/city/8.8.8.8
```

## Troubleshooting

### Container fails to start

```bash
# Check if PHYSICAL_REPO_ROOT is set
echo $PHYSICAL_REPO_ROOT

# Source from .env.workspace
source ../../.env.workspace
echo $PHYSICAL_REPO_ROOT
```

### Port already in use

```bash
# Check what's using port 5556
lsof -i :5556

# Change the host port binding, then re-render + re-up
export GEOIP_MOCK_PORT=5557
ciu down --dir tooling/geoip-mock --define-root /workspaces/netcup-api-filter
ciu render --define-root /workspaces/netcup-api-filter
ciu up --dir tooling/geoip-mock --define-root /workspaces/netcup-api-filter
```

## Related Documentation

- [TESTING_STRATEGY.md](../../docs/deprecated/TESTING_STRATEGY.md) - Overall testing architecture
- Mock implementation: `ui_tests/mock_geoip_server.py`
