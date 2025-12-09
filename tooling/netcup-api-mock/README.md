# Netcup CCP API Mock Server

Mock implementation of Netcup Customer Control Panel (CCP) API for testing DNS record management.

## Quick Start

```bash
cd tooling/netcup-api-mock

# Ensure PHYSICAL_REPO_ROOT is set (from .env.workspace)
source ../../.env.workspace

# Start mock server
docker compose up -d

# View logs
docker compose logs -f

# Stop server
docker compose down
```

## Access

- **API**: http://localhost:5555 (from host)
- **Container**: http://naf-mock-netcup-api:5555 (from containers)
- **Health check**: http://localhost:5555/health

## Configuration

All settings in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `DOCKER_NETWORK_INTERNAL` | `naf-dev-network` | Docker network |
| `NETCUP_MOCK_PORT` | `5555` | API port (host binding) |
| `FLASK_ENV` | `development` | Flask environment |
| `FLASK_DEBUG` | `false` | Enable Flask debug mode |

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

# Change port in .env
echo "NETCUP_MOCK_PORT=5554" >> .env
docker compose down && docker compose up -d
```

## Related Documentation

- [TESTING_STRATEGY.md](../../docs/TESTING_STRATEGY.md) - Overall testing architecture
- [CLIENT_USAGE.md](../../docs/CLIENT_USAGE.md) - Netcup API integration
- Mock implementation: `ui_tests/mock_netcup_api.py`
