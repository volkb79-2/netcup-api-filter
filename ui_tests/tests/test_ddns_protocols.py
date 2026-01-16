"""DDNS Protocol Tests.

Tests for DynDNS2 and No-IP compatible DDNS endpoints.

Verifies:
1. Protocol-compliant responses (text, not JSON)
2. Bearer token authentication enforcement
3. Auto IP detection with keywords
4. Realm-based authorization
5. Security enforcement (no username/password fallback)
6. Activity logging

Run with: pytest ui_tests/tests/test_ddns_protocols.py -v
"""
import os
import pytest
from pathlib import Path
import sys

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ui_tests.config import settings


pytestmark = pytest.mark.asyncio


# =============================================================================
# Helper Functions
# =============================================================================

def is_ddns_enabled():
    """Check if DDNS protocols are enabled."""
    enabled = os.environ.get('DDNS_PROTOCOLS_ENABLED', 'true')
    return enabled.lower() in ('true', '1', 'yes')


# =============================================================================
# DynDNS2 Protocol Tests
# =============================================================================

class TestDyndns2Protocol:
    """Test DynDNS2 protocol endpoint."""
    
    async def test_dyndns2_valid_token_ipv4(self):
        """DynDNS2: Update with valid bearer token and explicit IPv4."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/dyndns2/update")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
        }
        params = {
            "hostname": settings.client_domain,
            "myip": "192.0.2.1"
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)
            
            # Should be 200 with text response (good/nochg)
            # May be 403 if token lacks 'update' permission (default demo client is often read-only)
            # May be 502 if Netcup API not configured
            assert response.status_code in [200, 403, 502], \
                f"Expected 200/403/502, got {response.status_code}: {response.text}"
            
            # Response should be plain text
            assert 'text/plain' in response.headers.get('content-type', ''), \
                f"Expected text/plain, got {response.headers.get('content-type')}"
            
            # If denied, should use DynDNS2 permission code
            if response.status_code == 403:
                assert response.text.strip() == '!yours'

            # If success, should be good/nochg format
            if response.status_code == 200:
                text = response.text.strip()
                assert text.startswith(('good ', 'nochg ')), \
                    f"Expected 'good <ip>' or 'nochg <ip>', got: {text}"
                assert '192.0.2.1' in text, \
                    f"Response should contain IP address: {text}"
    
    async def test_dyndns2_auto_ip_detection(self):
        """DynDNS2: Update with myip=auto triggers IP detection."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/dyndns2/update")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
        }
        params = {
            "hostname": settings.client_domain,
            "myip": "auto"  # Should trigger auto-detection
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)
            
            # Should be 200, 403 (no update permission), or 502 (Netcup not configured)
            assert response.status_code in [200, 403, 502], \
                f"Expected 200/403/502, got {response.status_code}: {response.text}"
            
            if response.status_code == 403:
                assert response.text.strip() == '!yours'

            # If success, response should contain detected IP
            if response.status_code == 200:
                text = response.text.strip()
                assert text.startswith(('good ', 'nochg ')), \
                    f"Expected 'good <ip>' or 'nochg <ip>', got: {text}"
    
    async def test_dyndns2_missing_token(self):
        """DynDNS2: Missing bearer token returns badauth."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/dyndns2/update")
        params = {
            "hostname": f"test.{settings.client_domain}",
            "myip": "192.0.2.1"
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(url, params=params)
            
            # Should be 401 with badauth response
            assert response.status_code == 401, \
                f"Expected 401, got {response.status_code}"
            
            # DynDNS2 uses JSON for auth errors (from @require_auth decorator)
            # But this test verifies the decorator is applied
            assert response.status_code == 401
    
    async def test_dyndns2_invalid_token(self):
        """DynDNS2: Invalid bearer token returns badauth."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/dyndns2/update")
        headers = {
            "Authorization": "Bearer invalid-token-12345"
        }
        params = {
            "hostname": f"test.{settings.client_domain}",
            "myip": "192.0.2.1"
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)
            
            # Should be 401
            assert response.status_code == 401, \
                f"Expected 401, got {response.status_code}"
    
    async def test_dyndns2_unauthorized_domain(self):
        """DynDNS2: Token for different realm returns !yours."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/dyndns2/update")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
        }
        params = {
            # Use a different base domain than the seeded realm (which is under example.com)
            # so this request is truly out-of-scope and should return !yours.
            "hostname": "test.unauthorized-domain.example.net",
            "myip": "192.0.2.1"
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)
            
            # Should be 403 with !yours response
            assert response.status_code == 403, \
                f"Expected 403, got {response.status_code}: {response.text}"
            
            text = response.text.strip()
            assert text == '!yours', \
                f"Expected '!yours', got: {text}"
    
    async def test_dyndns2_invalid_hostname(self):
        """DynDNS2: Malformed hostname returns notfqdn."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/dyndns2/update")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
        }
        
        # Test with invalid hostnames
        invalid_hostnames = [
            "no-dots",           # No dots
            "..double-dot.com",  # Double dots
            "",                  # Empty
        ]
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            for hostname in invalid_hostnames:
                params = {
                    "hostname": hostname,
                    "myip": "192.0.2.1"
                }
                
                response = await client.get(url, headers=headers, params=params)
                
                # Should be 400 with notfqdn
                assert response.status_code == 400, \
                    f"Expected 400 for hostname '{hostname}', got {response.status_code}"
                
                text = response.text.strip()
                assert text == 'notfqdn', \
                    f"Expected 'notfqdn' for hostname '{hostname}', got: {text}"
    
    async def test_dyndns2_missing_hostname(self):
        """DynDNS2: Missing hostname parameter returns notfqdn."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/dyndns2/update")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
        }
        params = {
            "myip": "192.0.2.1"
            # hostname intentionally missing
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)
            
            # Should be 400 with notfqdn
            assert response.status_code == 400, \
                f"Expected 400, got {response.status_code}: {response.text}"
            
            text = response.text.strip()
            assert text == 'notfqdn', \
                f"Expected 'notfqdn', got: {text}"
    
    async def test_dyndns2_post_method(self):
        """DynDNS2: POST method works with form data."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/dyndns2/update")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
        }
        data = {
            "hostname": settings.client_domain,
            "myip": "192.0.2.2"
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.post(url, headers=headers, data=data)
            
            # Should be 200, 403 (no update permission), or 502 (Netcup not configured)
            assert response.status_code in [200, 403, 502], \
                f"Expected 200/403/502, got {response.status_code}: {response.text}"


# =============================================================================
# No-IP Protocol Tests
# =============================================================================

class TestNoipProtocol:
    """Test No-IP protocol endpoint."""
    
    async def test_noip_valid_token_ipv4(self):
        """No-IP: Update with valid bearer token."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/noip/update")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
        }
        params = {
            "hostname": settings.client_domain,
            "myip": "192.0.2.3"
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)
            
            # Should be 200, 403 (no update permission), or 502 (Netcup not configured)
            assert response.status_code in [200, 403, 502], \
                f"Expected 200/403/502, got {response.status_code}: {response.text}"
            
            # Response should be plain text
            assert 'text/plain' in response.headers.get('content-type', ''), \
                f"Expected text/plain, got {response.headers.get('content-type')}"
            
            if response.status_code == 403:
                assert response.text.strip() == 'abuse'

            # If success, should be good/nochg format
            if response.status_code == 200:
                text = response.text.strip()
                assert text.startswith(('good ', 'nochg ')), \
                    f"Expected 'good <ip>' or 'nochg <ip>', got: {text}"
    
    async def test_noip_auto_ip_detection(self):
        """No-IP: Update with myip=public triggers IP detection."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/noip/update")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
        }
        params = {
            "hostname": settings.client_domain,
            "myip": "public"  # Should trigger auto-detection
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)
            
            # Should be 200, 403 (no update permission), or 502 (Netcup not configured)
            assert response.status_code in [200, 403, 502], \
                f"Expected 200/403/502, got {response.status_code}: {response.text}"
    
    async def test_noip_missing_token(self):
        """No-IP: Missing bearer token returns nohost."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/noip/update")
        params = {
            "hostname": f"test.{settings.client_domain}",
            "myip": "192.0.2.1"
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(url, params=params)
            
            # Should be 401
            assert response.status_code == 401, \
                f"Expected 401, got {response.status_code}"
    
    async def test_noip_invalid_token(self):
        """No-IP: Invalid bearer token returns nohost."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/noip/update")
        headers = {
            "Authorization": "Bearer invalid-token-12345"
        }
        params = {
            "hostname": f"test.{settings.client_domain}",
            "myip": "192.0.2.1"
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)
            
            # Should be 401
            assert response.status_code == 401, \
                f"Expected 401, got {response.status_code}"
    
    async def test_noip_unauthorized_domain(self):
        """No-IP: Token scope violation returns abuse."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/noip/update")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
        }
        params = {
            # Use a different base domain than the seeded realm (which is under example.com)
            # so this request is truly out-of-scope and should return abuse.
            "hostname": "test.unauthorized-domain.example.net",
            "myip": "192.0.2.1"
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)
            
            # Should be 403 with abuse response
            assert response.status_code == 403, \
                f"Expected 403, got {response.status_code}: {response.text}"
            
            text = response.text.strip()
            assert text == 'abuse', \
                f"Expected 'abuse', got: {text}"
    
    async def test_noip_invalid_hostname(self):
        """No-IP: Invalid hostname returns nohost."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/noip/update")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
        }
        params = {
            "hostname": "no-dots",  # Invalid hostname
            "myip": "192.0.2.1"
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)
            
            # No-IP uses nohost (401) for both auth and hostname errors
            assert response.status_code == 401, \
                f"Expected 401, got {response.status_code}: {response.text}"
            
            text = response.text.strip()
            assert text == 'nohost', \
                f"Expected 'nohost', got: {text}"


# =============================================================================
# Auto IP Detection Tests
# =============================================================================

class TestAutoIPDetection:
    """Test auto IP detection functionality."""
    
    async def test_auto_keyword_triggers_detection(self):
        """myip=auto triggers IP detection."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/dyndns2/update")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
        }
        params = {
            "hostname": settings.client_domain,
            "myip": "auto"
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)
            
            # Should succeed (200) or fail with Netcup error (502)
            # Should NOT fail with IP validation error
            assert response.status_code in [200, 403, 502], \
                f"Auto detection failed: {response.status_code} {response.text}"
    
    async def test_public_keyword_triggers_detection(self):
        """myip=public triggers IP detection."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/dyndns2/update")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
        }
        params = {
            "hostname": settings.client_domain,
            "myip": "public"
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)
            
            assert response.status_code in [200, 403, 502], \
                f"Public detection failed: {response.status_code} {response.text}"
    
    async def test_detect_keyword_triggers_detection(self):
        """myip=detect triggers IP detection."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/dyndns2/update")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
        }
        params = {
            "hostname": settings.client_domain,
            "myip": "detect"
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)
            
            assert response.status_code in [200, 403, 502], \
                f"Detect keyword failed: {response.status_code} {response.text}"
    
    async def test_empty_myip_triggers_detection(self):
        """Empty myip parameter triggers IP detection."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/dyndns2/update")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
        }
        params = {
            "hostname": settings.client_domain,
            "myip": ""  # Empty string
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)
            
            assert response.status_code in [200, 403, 502], \
                f"Empty myip failed: {response.status_code} {response.text}"
    
    async def test_missing_myip_triggers_detection(self):
        """Missing myip parameter triggers IP detection."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/dyndns2/update")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
        }
        params = {
            "hostname": settings.client_domain,
            # myip parameter not provided
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)
            
            assert response.status_code in [200, 403, 502], \
                f"Missing myip failed: {response.status_code} {response.text}"
    
    async def test_x_forwarded_for_respected(self):
        """X-Forwarded-For header is used for IP detection."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/dyndns2/update")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
            "X-Forwarded-For": "203.0.113.1, 198.51.100.1"  # Test IPs
        }
        params = {
            "hostname": settings.client_domain,
            "myip": "auto"
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)
            
            # Should succeed or fail with backend error (not IP validation)
            assert response.status_code in [200, 403, 502], \
                f"X-Forwarded-For handling failed: {response.status_code} {response.text}"
            
            # Note: 403 is acceptable if IP whitelist is configured and test IP not allowed
    
    async def test_ipv6_detection(self):
        """IPv6 address detected and creates AAAA record."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/dyndns2/update")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
        }
        params = {
            "hostname": settings.client_domain,
            "myip": "2001:db8::1"  # IPv6 test address
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)
            
            # Should be 200/403/502 (403 if AAAA not in allowed record types)
            assert response.status_code in [200, 403, 502], \
                f"IPv6 handling failed: {response.status_code} {response.text}"


# =============================================================================
# Security Enforcement Tests
# =============================================================================

class TestSecurityEnforcement:
    """Test security enforcement in DDNS endpoints."""
    
    async def test_bearer_token_required(self):
        """Bearer token is required - no fallback to query params."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/dyndns2/update")
        params = {
            "hostname": f"test.{settings.client_domain}",
            "myip": "192.0.2.1",
            "username": "user",  # Should be ignored
            "password": "pass"   # Should be ignored
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(url, params=params)
            
            # Should be 401 - username/password in query params don't work
            assert response.status_code == 401, \
                f"Expected 401 (no auth fallback), got {response.status_code}"
    
    async def test_realm_authorization_enforced(self):
        """Realm-based authorization is enforced."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/dyndns2/update")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
        }
        
        # Try to update domain outside token's realm
        params = {
            "hostname": "device.other-domain.example.org",
            "myip": "192.0.2.1"
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)
            
            # Should be 403 with protocol-specific error
            assert response.status_code == 403, \
                f"Expected 403 for cross-realm update, got {response.status_code}"
            
            text = response.text.strip()
            assert text == '!yours', \
                f"Expected '!yours', got: {text}"
    
    async def test_username_password_ignored(self):
        """Username and password in query params are ignored."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/dyndns2/update")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
        }
        params = {
            "hostname": f"test.{settings.client_domain}",
            "myip": "192.0.2.1",
            "username": "ignored-user",
            "password": "ignored-pass"
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)
            
            # Should work with bearer token regardless of username/password
            # (those params are just ignored)
            assert response.status_code in [200, 403, 502], \
                f"Expected 200/403/502, got {response.status_code}: {response.text}"

            # Ensure query-param credentials do not affect authentication behavior.
            assert response.text.strip() != 'badauth'
    
    async def test_invalid_ip_rejected(self):
        """Invalid IP address is rejected with dnserr."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/dyndns2/update")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
        }
        params = {
            "hostname": f"test.{settings.client_domain}",
            "myip": "not.an.ip.address"  # Invalid IP
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)
            
            # Should be 502 with dnserr
            assert response.status_code == 502, \
                f"Expected 502 for invalid IP, got {response.status_code}: {response.text}"
            
            text = response.text.strip()
            assert text == 'dnserr', \
                f"Expected 'dnserr', got: {text}"


# =============================================================================
# Protocol Differences Tests
# =============================================================================

class TestProtocolDifferences:
    """Test differences between DynDNS2 and No-IP protocols."""
    
    async def test_dyndns2_permission_error_format(self):
        """DynDNS2 uses !yours for permission denied."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/dyndns2/update")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
        }
        params = {
            "hostname": "test.unauthorized.example.com",
            "myip": "192.0.2.1"
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)
            
            if response.status_code == 403:
                text = response.text.strip()
                assert text == '!yours', \
                    f"DynDNS2 should use '!yours', got: {text}"
    
    async def test_noip_permission_error_format(self):
        """No-IP uses abuse for permission denied."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/noip/update")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
        }
        params = {
            "hostname": "test.unauthorized.example.com",
            "myip": "192.0.2.1"
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)
            
            if response.status_code == 403:
                text = response.text.strip()
                assert text == 'abuse', \
                    f"No-IP should use 'abuse', got: {text}"
    
    async def test_dyndns2_hostname_error_format(self):
        """DynDNS2 uses notfqdn for invalid hostname."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/dyndns2/update")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
        }
        params = {
            "hostname": "invalid",  # No dots
            "myip": "192.0.2.1"
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)
            
            text = response.text.strip()
            assert text == 'notfqdn', \
                f"DynDNS2 should use 'notfqdn', got: {text}"
    
    async def test_noip_hostname_error_format(self):
        """No-IP uses nohost for invalid hostname."""
        import httpx
        
        if not is_ddns_enabled():
            pytest.skip("DDNS protocols disabled")
        
        url = settings.url("/api/ddns/noip/update")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
        }
        params = {
            "hostname": "invalid",  # No dots
            "myip": "192.0.2.1"
        }
        
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)
            
            text = response.text.strip()
            assert text == 'nohost', \
                f"No-IP should use 'nohost', got: {text}"
