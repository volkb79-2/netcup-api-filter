"""Tests for API proxy authentication and authorization."""
import pytest
import json
from ui_tests.config import settings


pytestmark = pytest.mark.asyncio


async def test_api_proxy_valid_token_authentication():
    """Test that valid token is accepted by API proxy."""
    import httpx
    
    url = settings.url("/api")
    headers = {
        "Authorization": f"Bearer {settings.client_token}",
        "Content-Type": "application/json"
    }
    data = {
        "action": "infoDnsRecords",
        "param": {"domainname": settings.client_domain}
    }
    
    async with httpx.AsyncClient(verify=False) as client:
        response = await client.post(url, headers=headers, json=data)
        
        # Should not return "Invalid authentication token"
        result = response.json()
        assert result.get("message") != "Invalid authentication token", \
            f"Token authentication failed: {result}"
        
        # May fail with "Internal server error" if Netcup API not configured,
        # but that means authentication passed
        assert response.status_code in [200, 403, 500], \
            f"Unexpected status code: {response.status_code}"


async def test_api_proxy_invalid_token_rejected():
    """Test that invalid token is rejected."""
    import httpx
    
    url = settings.url("/api")
    headers = {
        "Authorization": "Bearer invalid-token-12345",
        "Content-Type": "application/json"
    }
    data = {
        "action": "infoDnsRecords",
        "param": {"domainname": settings.client_domain}
    }
    
    async with httpx.AsyncClient(verify=False) as client:
        response = await client.post(url, headers=headers, json=data)
        
        assert response.status_code == 401
        result = response.json()
        assert result.get("message") == "Invalid authentication token"


async def test_api_proxy_missing_token_rejected():
    """Test that request without token is rejected."""
    import httpx
    
    url = settings.url("/api")
    headers = {"Content-Type": "application/json"}
    data = {
        "action": "infoDnsRecords",
        "param": {"domainname": settings.client_domain}
    }
    
    async with httpx.AsyncClient(verify=False) as client:
        response = await client.post(url, headers=headers, json=data)
        
        assert response.status_code == 401
        result = response.json()
        assert "token" in result.get("message", "").lower()


async def test_api_proxy_domain_authorization():
    """Test that token is restricted to allowed domain."""
    import httpx
    
    url = settings.url("/api")
    headers = {
        "Authorization": f"Bearer {settings.client_token}",
        "Content-Type": "application/json"
    }
    
    # Try to access unauthorized domain
    data = {
        "action": "infoDnsRecords",
        "param": {"domainname": "unauthorized.com"}
    }
    
    async with httpx.AsyncClient(verify=False) as client:
        response = await client.post(url, headers=headers, json=data)
        
        assert response.status_code == 403
        result = response.json()
        assert result.get("message") == "Permission denied"


async def test_api_proxy_operation_authorization():
    """Test that token is restricted to allowed operations."""
    import httpx
    
    url = settings.url("/api")
    headers = {
        "Authorization": f"Bearer {settings.client_token}",
        "Content-Type": "application/json"
    }
    
    # Test token is read-only, try to perform write operation
    data = {
        "action": "updateDnsRecords",
        "param": {
            "domainname": settings.client_domain,
            "dnsrecordset": {
                "dnsrecords": [
                    {
                        "hostname": "test",
                        "type": "A",
                        "destination": "1.2.3.4"
                    }
                ]
            }
        }
    }
    
    async with httpx.AsyncClient(verify=False) as client:
        response = await client.post(url, headers=headers, json=data)
        
        assert response.status_code == 403
        result = response.json()
        assert "permission" in result.get("message", "").lower()


async def test_api_proxy_invalid_json():
    """Test that invalid JSON is rejected."""
    import httpx
    
    url = settings.url("/api")
    headers = {
        "Authorization": f"Bearer {settings.client_token}",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient(verify=False) as client:
        response = await client.post(url, headers=headers, content="not json")
        
        assert response.status_code == 400
        result = response.json()
        assert "format" in result.get("message", "").lower()


async def test_api_proxy_unsupported_action():
    """Test that unsupported action is rejected."""
    import httpx
    
    url = settings.url("/api")
    headers = {
        "Authorization": f"Bearer {settings.client_token}",
        "Content-Type": "application/json"
    }
    data = {
        "action": "unsupportedAction",
        "param": {"domainname": settings.client_domain}
    }
    
    async with httpx.AsyncClient(verify=False) as client:
        response = await client.post(url, headers=headers, json=data)
        
        assert response.status_code == 400
        result = response.json()
        assert "unsupported" in result.get("message", "").lower()


async def test_api_proxy_missing_domainname():
    """Test that missing domainname parameter is rejected."""
    import httpx
    
    url = settings.url("/api")
    headers = {
        "Authorization": f"Bearer {settings.client_token}",
        "Content-Type": "application/json"
    }
    data = {
        "action": "infoDnsRecords",
        "param": {}
    }
    
    async with httpx.AsyncClient(verify=False) as client:
        response = await client.post(url, headers=headers, json=data)
        
        assert response.status_code == 400
        result = response.json()
        assert "domainname" in result.get("message", "").lower()
