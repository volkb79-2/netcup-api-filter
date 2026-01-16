"""Tests for DNS API proxy authentication and authorization.

Uses the new REST API endpoints:
- GET  /api/dns/<domain>/records - List records
- POST /api/dns/<domain>/records - Create record  
- PUT  /api/dns/<domain>/records/<id> - Update record
- DELETE /api/dns/<domain>/records/<id> - Delete record
- GET  /api/myip - Get caller's public IP
"""
import pytest
from ui_tests.config import settings


pytestmark = pytest.mark.asyncio


async def test_api_myip_public_endpoint():
    """Test /api/myip public endpoint returns IP info."""
    import httpx
    
    url = settings.url("/api/myip")
    
    async with httpx.AsyncClient(verify=False) as client:
        response = await client.get(url)
        
        assert response.status_code == 200
        result = response.json()
        assert "ip" in result, f"Expected 'ip' in response: {result}"


async def test_api_dns_valid_token_authentication():
    """Test that valid token is accepted by DNS API."""
    import httpx
    
    # Use the client domain from settings
    url = settings.url(f"/api/dns/{settings.client_domain}/records")
    headers = {
        "Authorization": f"Bearer {settings.client_token}",
    }
    
    async with httpx.AsyncClient(verify=False) as client:
        response = await client.get(url, headers=headers)
        
        # If Netcup API is not configured, we'll get 500 but token was accepted
        # If permission works, we might get records or 403 depending on realm
        assert response.status_code in [200, 403, 500], \
            f"Unexpected status code: {response.status_code}, body: {response.text[:200]}"
        
        # 401 means token was rejected - that's a failure
        assert response.status_code != 401, \
            f"Token authentication failed: {response.text}"


async def test_api_dns_invalid_token_rejected():
    """Test that invalid token is rejected."""
    import httpx
    
    url = settings.url(f"/api/dns/{settings.client_domain}/records")
    headers = {
        "Authorization": "Bearer invalid-token-12345",
    }
    
    async with httpx.AsyncClient(verify=False) as client:
        response = await client.get(url, headers=headers)
        
        assert response.status_code == 401
        result = response.json()
        assert "error" in result or "message" in result, f"Expected error message: {result}"


async def test_api_dns_missing_token_rejected():
    """Test that request without token is rejected."""
    import httpx
    
    url = settings.url(f"/api/dns/{settings.client_domain}/records")
    
    async with httpx.AsyncClient(verify=False) as client:
        response = await client.get(url)
        
        assert response.status_code == 401
        result = response.json()
        assert "error" in result or "message" in result


async def test_api_dns_unauthorized_domain_rejected():
    """Test that token is restricted to allowed domain."""
    import httpx
    
    # Try to access domain not in the token's realm
    url = settings.url("/api/dns/unauthorized-domain.com/records")
    headers = {
        "Authorization": f"Bearer {settings.client_token}",
    }
    
    async with httpx.AsyncClient(verify=False) as client:
        response = await client.get(url, headers=headers)
        
        # Should be forbidden - domain not in realm
        # May get 500 if Netcup API is not configured and check happens later
        assert response.status_code in [403, 500], \
            f"Expected 403/500 for unauthorized domain, got {response.status_code}: {response.text[:200]}"


async def test_api_dns_write_operation_unauthorized():
    """Test that read-only token cannot create records."""
    import httpx
    
    # The demo token is read-only, try to create a record
    url = settings.url(f"/api/dns/{settings.client_domain}/records")
    headers = {
        "Authorization": f"Bearer {settings.readonly_client_token}",
        "Content-Type": "application/json"
    }
    data = {
        "hostname": "test-forbidden",
        "type": "A",
        "destination": "1.2.3.4"
    }
    
    async with httpx.AsyncClient(verify=False) as client:
        response = await client.post(url, headers=headers, json=data)
        
        # Read-only token should get 403 for write operations
        # Unless the Netcup API is not configured (500)
        assert response.status_code in [403, 500], \
            f"Expected 403/500 for write attempt, got {response.status_code}: {response.text[:200]}"


async def test_api_dns_malformed_bearer_rejected():
    """Test that malformed Bearer token is rejected."""
    import httpx
    
    url = settings.url(f"/api/dns/{settings.client_domain}/records")
    
    # Test various malformed auth headers
    malformed_headers = [
        {"Authorization": "Basic abc123"},  # Wrong scheme
        {"Authorization": "Bearer"},  # Missing token
        {"Authorization": "BearerTokenHere"},  # No space
    ]
    
    async with httpx.AsyncClient(verify=False) as client:
        for headers in malformed_headers:
            response = await client.get(url, headers=headers)
            # Should be 401 for auth issues
            assert response.status_code == 401, \
                f"Expected 401 for malformed auth {headers}, got {response.status_code}"


async def test_api_ddns_endpoint_exists():
    """Test that DDNS endpoint exists and handles requests."""
    import httpx
    
    # DDNS endpoint is /api/ddns/<domain>/<hostname>
    url = settings.url(f"/api/ddns/{settings.client_domain}/test")
    headers = {
        "Authorization": f"Bearer {settings.client_token}",
    }
    
    async with httpx.AsyncClient(verify=False) as client:
        response = await client.get(url, headers=headers)
        
        # Could be 200, 403 (permission), or 500 (Netcup not configured)
        # 401 means token issue, 404 means route doesn't exist
        assert response.status_code in [200, 403, 500], \
            f"Unexpected status for DDNS endpoint: {response.status_code}: {response.text[:200]}"
