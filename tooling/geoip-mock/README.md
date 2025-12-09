# GeoIP Mock Server

Mock implementation of MaxMind GeoIP API for testing IP geolocation features.

## Quick Start

```bash
cd tooling/geoip-mock

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

- **API**: http://localhost:5556 (from host)
- **Container**: http://naf-mock-geoip:5556 (from containers)
- **Health check**: http://localhost:5556/health

## Configuration

All settings in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `DOCKER_NETWORK_INTERNAL` | `naf-dev-network` | Docker network |
| `GEOIP_MOCK_PORT` | `5556` | API port (host binding) |
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

# Change port in .env
echo "GEOIP_MOCK_PORT=5557" >> .env
docker compose down && docker compose up -d
```

## Related Documentation

- [TESTING_STRATEGY.md](../../docs/TESTING_STRATEGY.md) - Overall testing architecture
- Mock implementation: `ui_tests/mock_geoip_server.py`
