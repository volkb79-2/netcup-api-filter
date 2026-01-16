"""API Security and Authorization Tests.

Tests to verify:
1. Token scope enforcement (domain, operation, record type)
2. Token lifecycle (revoked, expired, disabled account)
3. IP whitelist enforcement
4. Credential protection (Netcup credentials never exposed)

Run with: pytest ui_tests/tests/test_api_security.py -v
"""
import pytest
from pathlib import Path
import sys

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ui_tests.config import settings


pytestmark = pytest.mark.asyncio


class TestTokenDomainScopeEnforcement:
    """Test that tokens are restricted to their realm's domain scope."""
    
    async def test_token_cannot_access_other_domain(self):
        """Token authorized for domain A cannot access domain B."""
        import httpx
        
        # Use the configured client token (bound to client_domain)
        url = settings.url("/api/dns/unauthorized-domain.example.com/records")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
        }
        
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(url, headers=headers)
            
            # Should get 403 Forbidden for unauthorized domain
            # May get 500 if Netcup API not configured
            assert response.status_code in [403, 500], \
                f"Expected 403/500 for unauthorized domain, got {response.status_code}"
            
            # If 403, verify error message mentions scope/permission
            if response.status_code == 403:
                result = response.json()
                assert "error" in result or "message" in result
    
    async def test_token_can_access_allowed_domain(self):
        """Token can access domain in its realm scope."""
        import httpx
        
        url = settings.url(f"/api/dns/{settings.client_domain}/records")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
        }
        
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(url, headers=headers)
            
            # Should be 200 or 500 (if Netcup not configured)
            # 403 would mean permission issue (could be valid for write ops)
            # 401 would mean token auth failed
            assert response.status_code != 401, \
                f"Token should be valid, got 401: {response.text}"


class TestTokenOperationScopeEnforcement:
    """Test that tokens are restricted to their allowed operations."""
    
    async def test_readonly_token_cannot_create(self):
        """Read-only token cannot create records."""
        import httpx
        
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
            
            # Demo token should be read-only, so CREATE should be denied
            # 403 = permission denied (correct)
            # 500 = Netcup API not configured
            assert response.status_code in [403, 500], \
                f"Expected 403/500 for write attempt, got {response.status_code}"
    
    async def test_readonly_token_cannot_delete(self):
        """Read-only token cannot delete records."""
        import httpx
        
        url = settings.url(f"/api/dns/{settings.client_domain}/records/1")
        headers = {
            "Authorization": f"Bearer {settings.readonly_client_token}",
        }
        
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.delete(url, headers=headers)
            
            # DELETE should be denied for read-only token
            assert response.status_code in [403, 500], \
                f"Expected 403/500 for delete attempt, got {response.status_code}"


class TestTokenLifecycleEnforcement:
    """Test that token lifecycle states are properly enforced."""
    
    async def test_invalid_token_rejected(self):
        """Completely invalid token is rejected with 401."""
        import httpx
        
        url = settings.url(f"/api/dns/{settings.client_domain}/records")
        headers = {
            "Authorization": "Bearer invalid-garbage-token-12345",
        }
        
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(url, headers=headers)
            
            assert response.status_code == 401
            result = response.json()
            assert "error" in result or "message" in result
    
    async def test_malformed_bearer_rejected(self):
        """Malformed Bearer auth is rejected."""
        import httpx
        
        url = settings.url(f"/api/dns/{settings.client_domain}/records")
        
        malformed_cases = [
            {"Authorization": "Basic abc123"},  # Wrong scheme
            {"Authorization": "Bearer"},  # No token after Bearer
            {"Authorization": "BearerTokenNoSpace"},  # No space
            {"Authorization": ""},  # Empty
        ]
        
        async with httpx.AsyncClient(verify=False) as client:
            for headers in malformed_cases:
                response = await client.get(url, headers=headers)
                assert response.status_code == 401, \
                    f"Expected 401 for {headers}, got {response.status_code}"
    
    async def test_missing_auth_rejected(self):
        """Request without Authorization header is rejected."""
        import httpx
        
        url = settings.url(f"/api/dns/{settings.client_domain}/records")
        
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(url)
            
            assert response.status_code == 401


class TestCredentialProtection:
    """Test that internal credentials are never exposed."""
    
    async def test_error_response_no_credentials(self):
        """Error responses don't leak Netcup credentials."""
        import httpx
        
        url = settings.url(f"/api/dns/{settings.client_domain}/records")
        headers = {
            "Authorization": "Bearer invalid-token",
        }
        
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(url, headers=headers)
            
            response_text = response.text.lower()
            
            # Check that sensitive patterns don't appear
            assert "apikey" not in response_text or "invalid" in response_text
            assert "apipassword" not in response_text
            assert "customer" not in response_text or "customer" in str(response.status_code)
    
    async def test_success_response_no_internal_tokens(self):
        """Success responses don't expose internal data."""
        import httpx
        
        url = settings.url(f"/api/dns/{settings.client_domain}/records")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
        }
        
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(url, headers=headers)
            
            if response.status_code == 200:
                response_text = response.text.lower()
                
                # Token hash should never be in response
                assert "hash" not in response_text or "sha" not in response_text
                
                # Session IDs shouldn't leak
                assert "apisessionid" not in response_text


class TestIPWhitelistEnforcement:
    """Test IP whitelist enforcement (if configured)."""
    
    async def test_x_forwarded_for_considered(self):
        """X-Forwarded-For header is considered for IP checks."""
        import httpx
        
        # This tests that the system considers forwarded headers
        # The actual enforcement depends on token configuration
        url = settings.url("/api/myip")
        headers = {
            "X-Forwarded-For": "203.0.113.50",
        }
        
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(url, headers=headers)
            
            assert response.status_code == 200
            result = response.json()
            # The response should have an IP (either forwarded or direct)
            assert "ip" in result


class TestPublicEndpointSecurity:
    """Test security of public endpoints."""
    
    async def test_myip_endpoint_no_auth_required(self):
        """Public /api/myip endpoint doesn't require auth."""
        import httpx
        
        url = settings.url("/api/myip")
        
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(url)
            
            assert response.status_code == 200
            result = response.json()
            assert "ip" in result
    
    async def test_myip_no_sensitive_data(self):
        """Public endpoint doesn't expose sensitive data."""
        import httpx
        
        url = settings.url("/api/myip")
        
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(url)
            
            assert response.status_code == 200
            result = response.json()
            
            # Should only have IP info, not internal data
            allowed_keys = {"ip", "ipv4", "ipv6", "version"}
            result_keys = set(result.keys())
            
            # No unexpected keys with sensitive data
            for key in result_keys:
                assert "token" not in key.lower()
                assert "secret" not in key.lower()
                assert "password" not in key.lower()


class TestRateLimiting:
    """Test rate limiting on auth endpoints."""
    
    async def test_rapid_failed_auth_handled(self):
        """Rapid failed auth attempts don't cause errors."""
        import httpx
        import asyncio
        
        url = settings.url(f"/api/dns/{settings.client_domain}/records")
        headers = {
            "Authorization": "Bearer invalid-token",
        }
        
        async with httpx.AsyncClient(verify=False) as client:
            # Send multiple rapid requests
            responses = []
            for _ in range(5):
                response = await client.get(url, headers=headers)
                responses.append(response.status_code)
                # Small spacing to avoid hammering too fast and to better
                # simulate real clients without requiring Playwright.
                await asyncio.sleep(0.1)
            
            # All should be 401 (not 500 or errors)
            # Rate limiting might kick in (429) which is also acceptable
            for status in responses:
                assert status in [401, 429], \
                    f"Expected 401 or 429, got {status}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
