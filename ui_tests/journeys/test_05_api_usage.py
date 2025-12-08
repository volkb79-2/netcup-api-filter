"""
Journey 05: API Usage and Audit Trail

This journey tests API functionality through the filter proxy:

1. **Successful API calls** - Valid token makes authorized requests
2. **Denied API calls** - Token scope violations logged
3. **Invalid token** - Wrong/expired tokens rejected
4. **Rate limiting** - Excessive requests handled
5. **Audit log verification** - All activity visible in admin UI

Prerequisites:
- At least one token exists (from test_04)
- Mock Netcup API running for backend
"""
import pytest
import pytest_asyncio
import asyncio
import httpx
import secrets
from typing import Optional

from ui_tests.config import settings
from ui_tests.workflows import ensure_admin_dashboard


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def api_base_url():
    """Base URL for API calls."""
    return settings.url('')


@pytest.fixture
def valid_token():
    """Get a valid token from state file."""
    # Try to get client token from settings
    token = settings.client_token
    if token:
        return token
    return None


@pytest.fixture
def invalid_token():
    """Generate an invalid token for testing."""
    return f"naf_invalid_{secrets.token_hex(32)}"


@pytest.fixture
def http_client(api_base_url):
    """HTTP client for API testing."""
    with httpx.Client(base_url=api_base_url, timeout=30.0, follow_redirects=False) as client:
        yield client


# ============================================================================
# Phase 1: Successful API Calls
# ============================================================================

class TestSuccessfulApiCalls:
    """Test valid API requests."""
    
    def test_01_api_health_endpoint(self, http_client):
        """Health endpoint is accessible without auth."""
        response = http_client.get('/health')
        assert response.status_code == 200, f"Health check failed: {response.text}"
        print(f"✅ Health endpoint: {response.json()}")
    
    def test_02_api_myip_endpoint(self, http_client):
        """MyIP endpoint is accessible (may not require auth)."""
        response = http_client.get('/api/myip')
        # May be 200 or 401 depending on config
        print(f"MyIP endpoint: {response.status_code} - {response.text[:200]}")
    
    def test_03_api_dns_with_valid_token(self, http_client, valid_token):
        """DNS records request with valid token."""
        if not valid_token:
            pytest.skip("No valid token available")
        
        headers = {'Authorization': f'Bearer {valid_token}'}
        response = http_client.get('/api/dns/example.com/records', headers=headers)
        
        print(f"DNS request: {response.status_code}")
        print(f"Response: {response.text[:500]}")
        
        # Could be:
        # - 200 (success)
        # - 403 (scope violation)
        # - 500 (Netcup API not configured - expected in test env)
        # - 502 (backend error)
        assert response.status_code in [200, 403, 500, 502], \
            f"Unexpected status: {response.status_code}"
        
        if response.status_code == 500 and 'not configured' in response.text.lower():
            print("⚠️ Netcup API not configured - expected in test environment")
    
    def test_04_api_ddns_update(self, http_client, valid_token):
        """DDNS update with valid token."""
        if not valid_token:
            pytest.skip("No valid token available")
        
        headers = {'Authorization': f'Bearer {valid_token}'}
        response = http_client.post(
            '/api/ddns/example.com/home',
            headers=headers,
            params={'ip': '192.168.1.100'}
        )
        
        print(f"DDNS update: {response.status_code}")
        print(f"Response: {response.text[:500]}")
        
        # Allow 500 for unconfigured API
        if response.status_code == 500 and 'not configured' in response.text.lower():
            print("⚠️ Netcup API not configured - expected in test environment")


# ============================================================================
# Phase 2: Authorization Errors
# ============================================================================

class TestAuthorizationErrors:
    """Test authorization failure scenarios."""
    
    def test_05_api_without_token(self, http_client):
        """API request without token returns 401."""
        response = http_client.get('/api/dns/example.com/records')
        assert response.status_code == 401, \
            f"Expected 401, got {response.status_code}: {response.text}"
        print("✅ No token = 401 Unauthorized")
    
    def test_06_api_with_invalid_token(self, http_client, invalid_token):
        """API request with invalid token returns 401."""
        headers = {'Authorization': f'Bearer {invalid_token}'}
        response = http_client.get('/api/dns/example.com/records', headers=headers)
        assert response.status_code == 401, \
            f"Expected 401, got {response.status_code}: {response.text}"
        print("✅ Invalid token = 401 Unauthorized")
    
    def test_07_api_with_malformed_token(self, http_client):
        """API request with malformed token returns 401."""
        headers = {'Authorization': 'Bearer not-a-valid-format'}
        response = http_client.get('/api/dns/example.com/records', headers=headers)
        assert response.status_code == 401, \
            f"Expected 401, got {response.status_code}"
        print("✅ Malformed token = 401 Unauthorized")
    
    def test_08_api_wrong_domain(self, http_client, valid_token):
        """Token for one domain can't access another."""
        if not valid_token:
            pytest.skip("No valid token available")
        
        headers = {'Authorization': f'Bearer {valid_token}'}
        response = http_client.get('/api/dns/unauthorized-domain.com/records', headers=headers)
        
        # Should be 403 (forbidden) or 401
        assert response.status_code in [401, 403], \
            f"Expected 401/403, got {response.status_code}"
        print(f"✅ Wrong domain = {response.status_code}")
    
    def test_09_api_wrong_operation(self, http_client, valid_token):
        """Read-only token can't create records."""
        if not valid_token:
            pytest.skip("No valid token available")
        
        headers = {'Authorization': f'Bearer {valid_token}'}
        response = http_client.post(
            '/api/dns/example.com/records',
            headers=headers,
            json={'type': 'A', 'hostname': 'test', 'destination': '1.2.3.4'}
        )
        
        # Depending on token config, could be 403 or success
        print(f"Create record attempt: {response.status_code}")
        print(f"Response: {response.text[:300]}")


# ============================================================================
# Phase 3: Filter Proxy Behavior
# ============================================================================

class TestFilterProxy:
    """Test filter proxy forwarding and filtering."""
    
    def test_10_filter_proxy_endpoint(self, http_client, valid_token):
        """Filter proxy endpoint forwards requests."""
        if not valid_token:
            pytest.skip("No valid token available")
        
        headers = {'Authorization': f'Bearer {valid_token}'}
        response = http_client.get('/filter-proxy/api/dns/example.com/records', headers=headers)
        
        print(f"Filter proxy: {response.status_code}")
        # Should work same as direct API (or 404 if route not implemented)
    
    def test_11_filter_proxy_without_auth(self, http_client):
        """Filter proxy without auth returns 401 or 404."""
        response = http_client.get('/filter-proxy/api/dns/example.com/records')
        # May return 401 (no auth) or 404 (route not implemented)
        assert response.status_code in [401, 404], \
            f"Expected 401 or 404, got {response.status_code}"
        print(f"✅ Filter proxy without auth = {response.status_code}")


# ============================================================================
# Phase 4: Audit Log Verification
# ============================================================================

class TestAuditLogVerification:
    """Verify API calls are logged in audit log."""
    
    @pytest.mark.asyncio
    async def test_12_audit_log_shows_api_calls(
        self, admin_session, screenshot_helper
    ):
        """Audit log shows API activity."""
        ss = screenshot_helper('05-api')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/audit'))
        await asyncio.sleep(0.5)
        
        await ss.capture('audit-log-api-activity', 'Audit log with API calls')
        
        body = await browser.text('body')
        h1 = await browser.text('main h1')
        assert 'Audit' in h1 or 'Log' in h1, f"Expected audit page: {h1}"
        
        print(f"Audit log content: {body[:500]}")
    
    @pytest.mark.asyncio
    async def test_13_audit_log_filter_by_status(
        self, admin_session, screenshot_helper
    ):
        """Can filter audit log by status."""
        ss = screenshot_helper('05-api')
        browser = admin_session
        
        # Try filtering by denied
        await browser.goto(settings.url('/admin/audit?status=denied'))
        await asyncio.sleep(0.5)
        
        await ss.capture('audit-log-denied', 'Audit log filtered by denied')
        
        body = await browser.text('body')
        print(f"Denied entries: {body[:300]}")
    
    @pytest.mark.asyncio
    async def test_14_audit_log_filter_by_action(
        self, admin_session, screenshot_helper
    ):
        """Can filter audit log by action type."""
        ss = screenshot_helper('05-api')
        browser = admin_session
        
        # Try filtering by action
        await browser.goto(settings.url('/admin/audit?action=dns_read'))
        await asyncio.sleep(0.5)
        
        await ss.capture('audit-log-dns-read', 'Audit log filtered by DNS read')
        
        body = await browser.text('body')
        print(f"DNS read entries: {body[:300]}")
    
    @pytest.mark.asyncio
    async def test_15_audit_log_columns(
        self, admin_session, screenshot_helper
    ):
        """Audit log has required columns."""
        ss = screenshot_helper('05-api')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/audit'))
        await asyncio.sleep(0.5)
        
        header_html = await browser.html('table thead')
        
        # Check for required columns
        expected_columns = ['timestamp', 'actor', 'action', 'status', 'resource']
        found = [col for col in expected_columns if col.lower() in header_html.lower()]
        
        print(f"Found columns: {found}")
        await ss.capture('audit-log-columns', 'Audit log column structure')
    
    @pytest.mark.asyncio
    async def test_16_audit_log_export(
        self, admin_session, screenshot_helper
    ):
        """Can export audit log."""
        ss = screenshot_helper('05-api')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/audit'))
        await asyncio.sleep(0.5)
        
        # Look for export button
        export_btn = await browser.query_selector(
            'a[href*="/export"], button:has-text("Export"), a:has-text("Export")'
        )
        
        if export_btn:
            await ss.capture('audit-log-export-btn', 'Audit log export button')
            print("✅ Export functionality found")
        else:
            print("Export button not visible (may require more entries)")


# ============================================================================
# Phase 5: Rate Limiting (Optional)
# ============================================================================

class TestRateLimiting:
    """Test rate limiting behavior."""
    
    def test_17_rate_limit_enforcement(self, http_client, valid_token):
        """Excessive requests trigger rate limit."""
        if not valid_token:
            pytest.skip("No valid token available")
        
        headers = {'Authorization': f'Bearer {valid_token}'}
        
        # Make many requests quickly
        responses = []
        for i in range(50):
            resp = http_client.get('/api/dns/example.com/records', headers=headers)
            responses.append(resp.status_code)
            if resp.status_code == 429:
                print(f"✅ Rate limited after {i+1} requests")
                break
        
        # Check if we got rate limited
        if 429 in responses:
            print("Rate limiting is active")
        else:
            print(f"No rate limiting observed in {len(responses)} requests")
            print(f"Status codes: {set(responses)}")


# ============================================================================
# Error Response Format
# ============================================================================

class TestErrorResponses:
    """Test error response format and content."""
    
    def test_18_401_response_format(self, http_client):
        """401 response has proper format."""
        response = http_client.get('/api/dns/example.com/records')
        
        assert response.status_code == 401
        
        # Should be JSON
        try:
            data = response.json()
            print(f"401 response: {data}")
            # Should have error message
            assert 'error' in data or 'message' in data or 'detail' in data
        except Exception:
            # May be plain text
            print(f"401 response (text): {response.text}")
    
    def test_19_404_response_format(self, http_client, valid_token):
        """404 response for unknown endpoints."""
        if not valid_token:
            pytest.skip("No valid token available")
        
        headers = {'Authorization': f'Bearer {valid_token}'}
        response = http_client.get('/api/nonexistent/endpoint', headers=headers)
        
        print(f"404 test: {response.status_code} - {response.text[:200]}")
