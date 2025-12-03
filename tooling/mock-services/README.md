# Mock Services for Testing

This directory contains Docker Compose configuration for mock external services used in E2E testing.

## Services

| Service | Port | Purpose | URL (from devcontainer/tests) |
|---------|------|---------|-------------------------------|
| **Mailpit** | 8025 (API/UI) / 1025 (SMTP) | SMTP testing with web UI | http://mailpit:8025 |
| **Mock GeoIP** | 5556 | MaxMind GeoIP API mock | http://mock-geoip:5556 |
| **Mock Netcup API** | 5555 | Netcup CCP API mock | http://mock-netcup-api:5555 |

> **Note:** Access services via container hostnames (e.g., `mailpit`, `mock-geoip`) since all containers
> share the `naf-dev-network` Docker network. `localhost` only works from the Docker host, not from
> inside the devcontainer.

## Quick Start

```bash
# From project root
source .env.workspace
cd tooling/mock-services

# Start all services
docker compose up -d

# Check status
docker compose ps

# View Mailpit UI
open http://localhost:8025

# Stop services
docker compose down
```

## Mailpit

**Mailpit** is a modern replacement for MailHog that provides:

- Web UI for viewing captured emails
- REST API for programmatic access
- SMTP server on port 1025
- No authentication required (test mode)

### API Examples

```bash
# List all messages
curl http://mailpit:8025/api/v1/messages

# Get message count
curl http://mailpit:8025/api/v1/messages | jq '.total'

# Delete all messages
curl -X DELETE http://mailpit:8025/api/v1/messages

# Get specific message
curl http://mailpit:8025/api/v1/message/{id}

# Search messages by subject
curl "http://mailpit:8025/api/v1/search?query=subject:verification"
```

### Flask Configuration for Testing

```python
# Use Mailpit for SMTP testing
app.config['MAIL_SERVER'] = 'mailpit'  # Docker service name
app.config['MAIL_PORT'] = 1025
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = False
```

### Pytest Fixture

```python
import httpx
import pytest

@pytest.fixture
def mailpit_client():
    """Client for Mailpit REST API."""
    with httpx.Client(base_url="http://mailpit:8025/api/v1") as client:
        # Clear mailbox before test
        client.delete("/messages")
        yield client
        # Clear mailbox after test
        client.delete("/messages")

async def test_registration_sends_verification_email(mailpit_client, page):
    # Register user...
    
    # Check email was sent
    messages = mailpit_client.get("/messages").json()
    assert messages["total"] == 1
    
    msg = messages["messages"][0]
    assert "verification" in msg["Subject"].lower()
    assert "newuser@example.com" in msg["To"][0]["Address"]
```

## Mock GeoIP Server

Mocks the MaxMind GeoIP web services API for testing IP geolocation features.

### Endpoints

- `GET /geoip/v2.1/city/{ip}` - City lookup
- `GET /geoip/v2.1/country/{ip}` - Country lookup
- `GET /geoip/v2.1/insights/{ip}` - Full insights (ISP, etc.)
- `GET /health` - Health check
- `POST /_mock/add_ip` - Add custom IP mapping
- `POST /_mock/reset` - Reset to default data

### Default Mock IPs

| IP | Country | City |
|----|---------|------|
| 8.8.8.8 | US | Mountain View |
| 1.1.1.1 | AU | Sydney |
| 203.0.113.0/24 | TEST | Test Network |

## Mock Netcup API Server

Mocks the Netcup CCP API for testing DNS operations.

### Endpoints

- `POST /` - JSON-RPC endpoint (login, logout, infoDnsZone, etc.)
- `GET /health` - Health check

### Test Credentials

```python
MOCK_CUSTOMER_ID = "123456"
MOCK_API_KEY = "test-api-key"
MOCK_API_PASSWORD = "test-api-password"
```

## Network Configuration

All services join the devcontainer network (`naf-dev-network` by default) so:

1. Flask app can reach services by hostname (e.g., `http://mailpit:1025`)
2. Playwright container can reach services for API verification
3. No port conflicts with local development

## Integration with Test Suite

The test suite can use these mock services when available:

```python
@pytest.fixture
def use_mock_services():
    """Configure Flask app to use mock services."""
    import os
    
    # Use Mailpit for SMTP
    os.environ['MAIL_SERVER'] = 'mailpit'
    os.environ['MAIL_PORT'] = '1025'
    
    # Use mock GeoIP
    os.environ['MAXMIND_API_URL'] = 'http://mock-geoip:5556'
    
    # Use mock Netcup API
    os.environ['NETCUP_API_URL'] = 'http://mock-netcup-api:5555'
    
    yield
    
    # Restore defaults...
```

## Comparison: Mailpit vs aiosmtpd

| Feature | Mailpit | aiosmtpd |
|---------|---------|----------|
| Web UI | ✅ Built-in | ❌ None |
| REST API | ✅ Comprehensive | ❌ Custom |
| Message search | ✅ Full-text | ❌ Manual |
| Message storage | ✅ SQLite | 🔶 Memory |
| TLS support | ✅ Optional | ✅ Yes |
| Docker ready | ✅ Official image | 🔶 Custom build |
| Setup complexity | ✅ Zero config | 🔶 Python code |
| Test isolation | ✅ API delete | 🔶 Restart |

**Recommendation:** Use Mailpit for all new tests. The aiosmtpd tests can be migrated incrementally.

## Troubleshooting

### Mailpit not receiving emails

1. Check Flask SMTP config points to `mailpit:1025` (not localhost)
2. Verify network connectivity: `docker exec playwright curl -s http://mailpit:8025/api/v1/info`
3. Check Mailpit logs: `docker compose logs mailpit`

### Mock GeoIP returning 404

1. Ensure mock_geoip_server.py is mounted correctly
2. Check health endpoint: `curl http://mock-geoip:5556/health`
3. Verify Basic Auth header format

### Services not on network

1. Verify network exists: `docker network ls | grep naf-dev-network`
2. Check containers are connected: `docker network inspect naf-dev-network`
3. Recreate with: `docker compose down && docker compose up -d`
