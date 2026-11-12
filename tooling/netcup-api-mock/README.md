# Netcup CCP API Mock Server

Mock implementation of Netcup Customer Control Panel (CCP) API for testing DNS record management.

## Quick Start

This stack is **ciu-managed** (naf-I01 / INFRA-PLAN-B: "migrate ALL naf containers to
ciu"). There is no hand-written `docker-compose.yml` here anymore — edit
`ciu.compose.yml.j2` / `ciu.defaults.toml.j2`; `ciu.compose.yml` is a RENDERED,
gitignored artifact and is never edited directly. See
`tooling/test-runner/README.md` for the `ciu render` / `ciu up` invocation
(same repo-root caveats apply).

```bash
# From the repo root with this checkout's generated environment loaded:
eval "$(ciu env print)"
ciu render
ciu up --dir tooling/netcup-api-mock

# View logs / stop (container_name is fixed, see ciu.defaults.toml.j2)
docker logs -f naf-<INSTANCE_ID>-mock-netcup-api
docker stop naf-<INSTANCE_ID>-mock-netcup-api
```

Normally this is not brought up standalone: it is a peer of the gating test-runner and
the other mock stacks. Use the ciu workflow above or `run-gate local-build --with-mocks`.

## Access

- **API**: http://localhost:5555 (from host)
- **Container**: http://naf-mock-netcup-api:5555 (from containers)
- **Health check**: http://localhost:5555/health

## Configuration

Runtime env vars (from `.env.workspace` / shell env, read at container start):

| Variable | Default | Description |
|----------|---------|-------------|
| `NETCUP_MOCK_PORT` | `5555` | API port (host binding) |
| `FLASK_ENV` | `development` | Flask environment |
| `FLASK_DEBUG` | `false` | Enable Flask debug mode |

The container name/image/tag and internal port are now stack scalars in
`ciu.defaults.toml.j2` (`[netcup_api_mock]`); the network is resolved by ciu at
render time (`deploy.network_name`, no longer a `DOCKER_NETWORK_INTERNAL` read
by the container itself).

## API Endpoints

### POST /
Main CCP API endpoint (all actions via POST with JSON body).

**Actions Supported**:
- `login` - Authenticate and get session ID
- `infoDnsZone` - Get zone information
- `infoDnsRecords` - List DNS records
- `updateDnsRecords` - Update DNS records

### GET /health
Health check endpoint.

**Response**:
```json
{"status": "ok"}
```

## Usage Examples

### Login

```bash
curl -X POST http://localhost:5555/ \
  -H "Content-Type: application/json" \
  -d '{
    "action": "login",
    "param": {
      "apikey": "test-key",
      "apisessionid": "",
      "customernumber": "12345",
      "apipassword": "test-password"
    }
  }'
```

### List DNS Records

```bash
curl -X POST http://localhost:5555/ \
  -H "Content-Type: application/json" \
  -d '{
    "action": "infoDnsRecords",
    "param": {
      "domainname": "example.com",
      "apikey": "test-key",
      "apisessionid": "test-session",
      "customernumber": "12345"
    }
  }'
```

### Update DNS Record

```bash
curl -X POST http://localhost:5555/ \
  -H "Content-Type: application/json" \
  -d '{
    "action": "updateDnsRecords",
    "param": {
      "domainname": "example.com",
      "apikey": "test-key",
      "apisessionid": "test-session",
      "customernumber": "12345",
      "dnsrecordset": {
        "dnsrecords": [
          {
            "id": "1",
            "hostname": "test",
            "type": "A",
            "destination": "192.0.2.1",
            "ttl": 300
          }
        ]
      }
    }
  }'
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
# Check what's using port 5555
lsof -i :5555

# Change the host binding (NETCUP_MOCK_PORT lives in .env.workspace, not a
# per-service .env — this stack has no docker-compose.yml of its own anymore)
echo "NETCUP_MOCK_PORT=5554" >> ../../.env.workspace
docker stop naf-<INSTANCE_ID>-mock-netcup-api
ciu up --dir tooling/netcup-api-mock
```

## Related Documentation

- [TESTING_STRATEGY.md](../../docs/deprecated/TESTING_STRATEGY.md) - Overall testing architecture
- [CLIENT_USAGE.md](../../docs/deprecated/CLIENT_USAGE.md) - Netcup API integration
- Mock implementation: `ui_tests/mock_netcup_api.py`
