# Mock Netcup API for Testing

This directory contains a complete mock implementation of the Netcup CCP API for E2E testing without requiring real Netcup credentials.

## Overview

The mock API implements all Netcup API endpoints used by the application:

- **`login`** - Authenticate and get session ID
- **`logout`** - Invalidate session
- **`infoDnsZone`** - Get DNS zone information
- **`infoDnsRecords`** - List DNS records for a domain
- **`updateDnsRecords`** - Create, update, or delete DNS records

## Features

✅ **Full API Contract** - Identical request/response format to real Netcup API  
✅ **Session Management** - Proper login/logout with session timeout (300s)  
✅ **Multi-Domain Support** - Each domain has isolated DNS records  
✅ **CRUD Operations** - Create, read, update, and delete DNS records  
✅ **Record Types** - Supports A, AAAA, MX, CNAME, TXT, etc.  
✅ **Error Handling** - Returns proper HTTP status codes (401, 400, 500)  
✅ **State Persistence** - Changes persist within test session  

## Files

- **`mock_netcup_api.py`** - Flask-based mock API server implementation
- **`conftest_mock_api.py`** - Pytest fixtures for using the mock API
- **`tests/test_mock_api_standalone.py`** - Unit tests for the mock API itself
- **`tests/test_e2e_with_mock_api.py`** - E2E tests using the mock API

## Usage

### In Tests (Recommended)

Use the pytest fixtures from `conftest.py`:

```python
def test_something(mock_netcup_api_server, mock_netcup_credentials):
    """Test with mock API."""
    from netcup_api_filter.netcup_client import NetcupClient
    
    client = NetcupClient(
        customer_id=mock_netcup_credentials['customer_id'],
        api_key=mock_netcup_credentials['api_key'],
        api_password=mock_netcup_credentials['api_password'],
        api_url=mock_netcup_api_server.url
    )
    
    # Use netcup_client normally
    client.login()
    zone = client.info_dns_zone("test.example.com")
    records = client.info_dns_records("test.example.com")
    # ...
```

### Standalone Server

Run the mock API as a standalone server for manual testing:

```bash
cd /workspaces/netcup-api-filter
python -m ui_tests.mock_netcup_api
```

Server will start on `http://localhost:5555`.

**Test credentials:**
- Customer ID: `123456`
- API Key: `test-api-key`
- API Password: `test-api-password`

## Default Test Data

Each domain is automatically seeded with default DNS records on first access:

```
@     A      192.0.2.1
www   A      192.0.2.1
@     AAAA   2001:db8::1
@     MX     mail.example.com (priority 10)
mail  A      192.0.2.10
```

## Seeding Custom Data

For tests that need specific DNS records:

```python
from ui_tests.mock_netcup_api import seed_test_domain

seed_test_domain("my-test.example.com", [
    {
        "id": "1",
        "hostname": "@",
        "type": "A",
        "priority": "",
        "destination": "192.0.2.99",
        "deleterecord": False,
        "state": "yes"
    }
])
```

## API Endpoints

### POST /run/webservice/servers/endpoint.php

**Request format:**
```json
{
    "action": "login|logout|infoDnsZone|infoDnsRecords|updateDnsRecords",
    "param": {
        // Action-specific parameters
    }
}
```

**Response format (success):**
```json
{
    "serverrequestid": "...",
    "clientrequestid": "",
    "action": "...",
    "status": "success",
    "statuscode": 2000,
    "shortmessage": "...",
    "longmessage": "...",
    "responsedata": { /* action-specific data */ }
}
```

**Response format (error):**
```json
{
    "status": "error",
    "statuscode": 4013,
    "shortmessage": "Validation Error",
    "longmessage": "..."
}
```

## Testing Strategy

### 1. Mock API Unit Tests
Validate the mock API itself works correctly:
```bash
pytest ui_tests/tests/test_mock_api_standalone.py -v
```

Tests:
- ✅ Basic CRUD operations
- ✅ Multiple domains isolation
- ✅ Invalid credentials rejection
- ✅ Session management
- ✅ Session timeout
- ✅ Session isolation

### 2. Application E2E Tests
Test complete workflows with the mock API:
```bash
pytest ui_tests/tests/test_e2e_with_mock_api.py -v
```

Tests:
- ✅ Admin creates client → client reads DNS records
- ✅ Admin creates client → client updates DNS records
- ✅ Permission enforcement (domain, operation, record type)

## Limitations

⚠️ **In-Memory Only** - State resets between test runs  
⚠️ **No DNS Validation** - Accepts any hostname/IP format  
⚠️ **Simplified Zone Info** - Returns static zone metadata  
⚠️ **No Rate Limiting** - Unlike real API  

These limitations are intentional to keep tests fast and predictable.

## Integration with Application

To use the mock API in E2E tests:

1. **Configure Netcup API settings** to point at mock server:
   ```python
   await browser.fill("#api_url", mock_netcup_api_server.url)
   ```

2. **Use normal workflow** - Application doesn't know it's a mock:
   ```python
   # Client portal will use mock API transparently
   await browser.click("text=Manage")
   # DNS records come from mock API
   ```

3. **Verify operations** - Check mock state or UI:
   ```python
   page_html = await browser.html("body")
   assert "192.0.2.99" in page_html
   ```

## Troubleshooting

**Port already in use:**
```bash
# Kill existing server
lsof -ti:5555 | xargs kill -9
```

**Dependencies missing:**
```bash
pip install Flask werkzeug requests
```

**Tests fail with connection refused:**
- Mock server may not be starting - check for Flask/werkzeug installation
- Port 5555 may be blocked by firewall

## Future Enhancements

Possible improvements:
- [ ] Persistent SQLite storage option
- [ ] DNS validation (RFC compliance)
- [ ] Rate limiting simulation
- [ ] Network latency simulation
- [ ] More realistic error scenarios
- [ ] DNSSEC operations
- [ ] Zone transfer operations
