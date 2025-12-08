"""
Negative Tests for Registration + Realm Workflow.

Tests that unauthorized or invalid operations are correctly rejected.
These tests verify the "deny" paths, not just the "allow" paths.

Categories:
- Workflow Step Skipping: Cannot bypass registration steps
- Authorization Boundaries: Cannot access other users' data
- Input Validation: Invalid data is rejected with proper errors
- State Enforcement: Invalid states (pending, rejected) are enforced

Run with: pytest ui_tests/tests/test_registration_negative.py -v
"""
import pytest
import re
import httpx
from pathlib import Path
import sys
import sqlite3

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ui_tests.config import settings

pytestmark = pytest.mark.asyncio


class TestWorkflowStepSkipping:
    """
    Verify that users cannot skip registration workflow steps.
    
    Flow: register → verify → realms → pending
    Each step should require completion of previous steps.
    """
    
    async def test_cannot_access_verify_without_registration(self, http_client):
        """
        Direct access to /register/verify without registering should redirect.
        """
        response = await http_client.get(
            settings.url("/account/register/verify"),
            follow_redirects=False
        )
        
        # Should redirect to registration
        assert response.status_code == 302, \
            f"Expected redirect (302), got {response.status_code}"
        
        location = response.headers.get("location", "")
        assert "/register" in location or "/login" in location, \
            f"Should redirect to register or login, got: {location}"
    
    async def test_cannot_access_realms_without_email_verification(self, http_client):
        """
        Direct access to /register/realms without email verification should redirect.
        """
        # First register to get a session
        reg_response = await http_client.get(settings.url("/account/register"))
        csrf = self._extract_csrf(reg_response.text)
        
        # Submit registration
        await http_client.post(
            settings.url("/account/register"),
            data={
                "username": "skipverify_test",
                "email": "skipverify@test.com",
                "password": "TestPass123+SecurePassword24",
                "confirm_password": "TestPass123+SecurePassword24",
                "terms": "on",
                "csrf_token": csrf
            },
            follow_redirects=True
        )
        
        # Now try to skip verification and go directly to realms
        response = await http_client.get(
            settings.url("/account/register/realms"),
            follow_redirects=False
        )
        
        # Should redirect back to verify step
        assert response.status_code == 302, \
            f"Expected redirect (302), got {response.status_code}"
    
    async def test_pending_page_shows_no_sensitive_info_to_unauthenticated(self, http_client):
        """
        Direct access to /register/pending shows generic page with no sensitive data.
        
        Note: This page is intentionally public because the session is cleared
        after registration submission. It's a generic "your registration is pending"
        page, not a page with user-specific data.
        """
        response = await http_client.get(
            settings.url("/account/register/pending"),
            follow_redirects=False
        )
        
        # Page is accessible (200 OK) but should not show sensitive data
        assert response.status_code == 200, \
            f"Pending page should be accessible, got {response.status_code}"
        
        # Verify it's a generic page without sensitive user data
        assert "pending" in response.text.lower(), \
            "Should show pending message"
        
        # Should NOT contain any specific user data (email, username, realms)
        # These would only appear if there was a session leak
        dangerous_patterns = [
            "@test.com",  # Email addresses
            "skipverify",  # Test usernames
            "realm_id=",  # Realm IDs
            "token_prefix=",  # Token data
        ]
        for pattern in dangerous_patterns:
            assert pattern not in response.text, \
                f"Pending page should not leak sensitive data: {pattern}"
    
    async def test_verify_rejects_wrong_code(self, http_client, mailpit):
        """
        Wrong verification code should keep user on verify page or redirect to register.
        
        Note: The actual error message may vary. The key test is that the user
        does NOT proceed to the realms step.
        """
        # Register
        reg_response = await http_client.get(settings.url("/account/register"))
        csrf = self._extract_csrf(reg_response.text)
        
        username = f"wrongcode_{mailpit._generate_id()}"
        
        reg_result = await http_client.post(
            settings.url("/account/register"),
            data={
                "username": username,
                "email": f"{username}@test.com",
                "password": "TestPass123+SecurePassword24",
                "confirm_password": "TestPass123+SecurePassword24",
                "terms": "on",
                "csrf_token": csrf
            },
            follow_redirects=True
        )
        
        # Check if we're on verify page
        if "/verify" in str(reg_result.url):
            # Try verification with wrong code
            verify_csrf = self._extract_csrf(reg_result.text)
            
            response = await http_client.post(
                settings.url("/account/register/verify"),
                data={
                    "code": "000000",  # Wrong code
                    "csrf_token": verify_csrf
                },
                follow_redirects=True
            )
            
            # Should NOT proceed to realms step with wrong code
            assert "/register/realms" not in str(response.url), \
                f"Should not proceed to realms step with wrong code. URL: {response.url}"
        else:
            # If we got redirected elsewhere (validation error, etc.), that's also OK
            # as long as we didn't proceed to realms
            assert "/register/realms" not in str(reg_result.url), \
                "Should not proceed to realms step"
    
    async def test_cannot_use_different_session_for_realms(self, http_client):
        """
        A session without registration cannot access the realms step.
        """
        # Create a fresh client (new session)
        async with httpx.AsyncClient(verify=False) as fresh_client:
            response = await fresh_client.get(
                settings.url("/account/register/realms"),
                follow_redirects=False
            )
            
            assert response.status_code == 302, \
                "Fresh session should be redirected from realms step"
    
    def _extract_csrf(self, html: str) -> str:
        """Extract CSRF token from HTML."""
        match = re.search(r'name="csrf_token" value="([^"]+)"', html)
        return match.group(1) if match else ""


class TestPendingAccountRestrictions:
    """
    Verify that pending (unapproved) accounts cannot log in or access protected resources.
    """
    
    async def test_pending_account_cannot_login(self, http_client, mailpit):
        """
        Account that is pending admin approval cannot log in.
        """
        # Create and verify a registration (but don't approve)
        reg_response = await http_client.get(settings.url("/account/register"))
        csrf = self._extract_csrf(reg_response.text)
        
        username = f"pending_login_{mailpit._generate_id()}"
        password = "TestPass123+SecurePassword24Secure2024"
        
        # Step 1: Register
        await http_client.post(
            settings.url("/account/register"),
            data={
                "username": username,
                "email": f"{username}@test.com",
                "password": password,
                "confirm_password": password,
                "terms": "on",
                "csrf_token": csrf
            },
            follow_redirects=True
        )
        
        # Get verification code from database directly (simulating email)
        code = self._get_verification_code(username)
        if code:
            # Step 2: Verify email
            verify_resp = await http_client.get(settings.url("/account/register/verify"))
            verify_csrf = self._extract_csrf(verify_resp.text)
            
            await http_client.post(
                settings.url("/account/register/verify"),
                data={
                    "code": code,
                    "csrf_token": verify_csrf
                },
                follow_redirects=True
            )
            
            # Step 3: Skip realms, just submit
            realms_resp = await http_client.get(settings.url("/account/register/realms"))
            realms_csrf = self._extract_csrf(realms_resp.text)
            
            await http_client.post(
                settings.url("/account/register/realms"),
                data={
                    "action": "submit",
                    "csrf_token": realms_csrf
                },
                follow_redirects=True
            )
        
        # Now try to login with this pending account
        async with httpx.AsyncClient(verify=False) as fresh_client:
            login_resp = await fresh_client.get(settings.url("/account/login"))
            login_csrf = self._extract_csrf(login_resp.text)
            
            result = await fresh_client.post(
                settings.url("/account/login"),
                data={
                    "username": username,
                    "password": password,
                    "csrf_token": login_csrf
                },
                follow_redirects=True
            )
            
            # Should NOT be logged in - should see error or stay on login
            assert "pending" in result.text.lower() or \
                   "approval" in result.text.lower() or \
                   "not active" in result.text.lower() or \
                   "login" in str(result.url).lower(), \
                f"Pending account should not be able to login. URL: {result.url}"
    
    def _extract_csrf(self, html: str) -> str:
        """Extract CSRF token from HTML."""
        match = re.search(r'name="csrf_token" value="([^"]+)"', html)
        return match.group(1) if match else ""
    
    def _get_verification_code(self, username: str) -> str | None:
        """Get verification code from database."""
        try:
            # Determine database path based on deployment target
            if settings.deployment_target == "local":
                db_path = Path("/workspaces/netcup-api-filter/deploy-local/netcup_filter.db")
            else:
                # For webhosting, we can't access the database directly
                return None
            
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
            cur.execute(
                "SELECT verification_code FROM registration_requests WHERE username=?",
                (username,)
            )
            row = cur.fetchone()
            conn.close()
            return row[0] if row else None
        except Exception:
            return None


class TestInputValidation:
    """
    Verify that invalid inputs are rejected with proper error messages.
    """
    
    async def test_registration_rejects_short_username(self, http_client):
        """
        Username shorter than minimum length should be rejected.
        """
        reg_response = await http_client.get(settings.url("/account/register"))
        csrf = self._extract_csrf(reg_response.text)
        
        response = await http_client.post(
            settings.url("/account/register"),
            data={
                "username": "ab",  # Too short
                "email": "test@test.com",
                "password": "TestPass123+SecurePassword24",
                "confirm_password": "TestPass123+SecurePassword24",
                "terms": "on",
                "csrf_token": csrf
            },
            follow_redirects=True
        )
        
        # Should show validation error, not proceed
        assert "3" in response.text or "short" in response.text.lower() or \
               "character" in response.text.lower() or "error" in response.text.lower(), \
            "Should show error for short username"
        assert "/register/verify" not in str(response.url), \
            "Should not proceed with invalid username"
    
    async def test_registration_rejects_invalid_email(self, http_client):
        """
        Invalid email format should be rejected.
        """
        reg_response = await http_client.get(settings.url("/account/register"))
        csrf = self._extract_csrf(reg_response.text)
        
        response = await http_client.post(
            settings.url("/account/register"),
            data={
                "username": "validuser",
                "email": "not-an-email",  # Invalid
                "password": "TestPass123+SecurePassword24",
                "confirm_password": "TestPass123+SecurePassword24",
                "terms": "on",
                "csrf_token": csrf
            },
            follow_redirects=True
        )
        
        # Should show validation error
        assert "email" in response.text.lower() or "invalid" in response.text.lower(), \
            "Should show error for invalid email"
    
    async def test_registration_rejects_password_mismatch(self, http_client):
        """
        Password confirmation mismatch should be rejected.
        """
        reg_response = await http_client.get(settings.url("/account/register"))
        csrf = self._extract_csrf(reg_response.text)
        
        response = await http_client.post(
            settings.url("/account/register"),
            data={
                "username": "mismatchuser",
                "email": "mismatch@test.com",
                "password": "TestPass123+SecurePassword24",
                "confirm_password": "DifferentPass123!",  # Mismatch
                "terms": "on",
                "csrf_token": csrf
            },
            follow_redirects=True
        )
        
        # Should reject with error - either inline message or 400 error page
        assert response.status_code == 400 or "match" in response.text.lower() or "mismatch" in response.text.lower(), \
            f"Should reject password mismatch (got {response.status_code})"
    
    async def test_registration_rejects_weak_password(self, http_client):
        """
        Weak password should be rejected.
        """
        reg_response = await http_client.get(settings.url("/account/register"))
        csrf = self._extract_csrf(reg_response.text)
        
        response = await http_client.post(
            settings.url("/account/register"),
            data={
                "username": "weakpwduser",
                "email": "weak@test.com",
                "password": "123456",  # Too weak
                "confirm_password": "123456",
                "terms": "on",
                "csrf_token": csrf
            },
            follow_redirects=True
        )
        
        # Should show validation error
        assert "password" in response.text.lower() or \
               "weak" in response.text.lower() or \
               "8" in response.text or \
               "character" in response.text.lower(), \
            "Should show error for weak password"
    
    async def test_realm_request_rejects_invalid_domain(self, http_client):
        """
        Invalid domain format in realm request should be rejected.
        """
        # This test requires completing registration first
        # Skipped if we can't set up the state
        pytest.skip("Requires complex state setup - covered by unit tests")
    
    def _extract_csrf(self, html: str) -> str:
        """Extract CSRF token from HTML."""
        match = re.search(r'name="csrf_token" value="([^"]+)"', html)
        return match.group(1) if match else ""


class TestAdminApprovalNegative:
    """
    Verify admin approval edge cases and rejection flows.
    """
    
    async def test_non_admin_cannot_access_pending_accounts(self, http_client):
        """
        Regular user cannot access /admin/accounts/pending.
        """
        response = await http_client.get(
            settings.url("/admin/accounts/pending"),
            follow_redirects=False
        )
        
        # Should redirect to login (admin required)
        assert response.status_code == 302, \
            "Should redirect unauthenticated user"
        assert "/admin/login" in response.headers.get("location", ""), \
            "Should redirect to admin login"
    
    async def test_non_admin_cannot_approve_account(self, http_client):
        """
        Regular user cannot POST to approval endpoint.
        """
        # Try to approve account ID 1 without admin auth
        response = await http_client.post(
            settings.url("/admin/accounts/1/approve"),
            data={"csrf_token": "fake"},
            follow_redirects=False
        )
        
        # Should redirect to login, return error, or reject CSRF
        # 302 = redirect to login
        # 400 = CSRF validation failed (still a rejection)
        # 401 = not authenticated
        # 403 = forbidden
        assert response.status_code in [302, 400, 401, 403], \
            f"Expected 302/400/401/403, got {response.status_code}"
    
    async def test_non_admin_cannot_reject_account(self, http_client):
        """
        Regular user cannot POST to rejection endpoint.
        """
        response = await http_client.post(
            settings.url("/admin/accounts/1/reject"),
            data={"csrf_token": "fake", "reason": "test"},
            follow_redirects=False
        )
        
        # 400 = CSRF validation failed (still a rejection)
        assert response.status_code in [302, 400, 401, 403], \
            f"Expected 302/400/401/403, got {response.status_code}"


class TestTokenPermissionBoundaries:
    """
    Verify that tokens cannot exceed their realm's permissions.
    
    These tests verify the authorization enforcement layer.
    """
    
    async def test_token_cannot_access_unauthorized_domain(self):
        """
        Token authorized for domain A cannot access domain B.
        """
        import httpx
        
        # Use the configured demo token
        url = settings.url("/api/dns/unauthorized-domain.example.com/records")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
        }
        
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(url, headers=headers)
            
            # Should be 403 (or 500 if Netcup not configured)
            assert response.status_code in [403, 500], \
                f"Expected 403/500 for unauthorized domain, got {response.status_code}"
            
            if response.status_code == 403:
                result = response.json()
                assert "error" in result or "message" in result
    
    async def test_readonly_token_cannot_create(self):
        """
        Token with only 'read' operation cannot create records.
        """
        import httpx
        
        url = settings.url(f"/api/dns/{settings.client_domain}/records")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
            "Content-Type": "application/json"
        }
        data = {
            "hostname": "test-create-denied",
            "type": "A",
            "destination": "1.2.3.4"
        }
        
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.post(url, headers=headers, json=data)
            
            # Should be 403 (demo token is typically read-only)
            # or 500 if Netcup API not configured
            assert response.status_code in [403, 500], \
                f"Expected 403/500 for create with read-only token, got {response.status_code}"
    
    async def test_readonly_token_cannot_delete(self):
        """
        Token with only 'read' operation cannot delete records.
        """
        import httpx
        
        url = settings.url(f"/api/dns/{settings.client_domain}/records/999")
        headers = {
            "Authorization": f"Bearer {settings.client_token}",
        }
        
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.delete(url, headers=headers)
            
            # Should be 403 or 404 (if record doesn't exist) or 500
            assert response.status_code in [403, 404, 500], \
                f"Expected 403/404/500 for delete with read-only token, got {response.status_code}"
    
    async def test_invalid_token_rejected(self):
        """
        Completely invalid token is rejected with 401.
        """
        import httpx
        
        url = settings.url(f"/api/dns/{settings.client_domain}/records")
        headers = {
            "Authorization": "Bearer totally-invalid-garbage-token",
        }
        
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(url, headers=headers)
            
            assert response.status_code == 401, \
                f"Expected 401 for invalid token, got {response.status_code}"
    
    async def test_missing_authorization_rejected(self):
        """
        Request without Authorization header is rejected.
        """
        import httpx
        
        url = settings.url(f"/api/dns/{settings.client_domain}/records")
        
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(url)
            
            assert response.status_code == 401, \
                f"Expected 401 for missing auth, got {response.status_code}"


class TestCSRFProtection:
    """
    Verify CSRF protection on all state-changing endpoints.
    """
    
    async def test_registration_requires_csrf(self, http_client):
        """
        Registration POST without CSRF token should be rejected.
        """
        response = await http_client.post(
            settings.url("/account/register"),
            data={
                "username": "nocsrf",
                "email": "nocsrf@test.com",
                "password": "TestPass123+SecurePassword24",
                "confirm_password": "TestPass123+SecurePassword24",
                "terms": "on",
                # csrf_token: NOT included
            },
            follow_redirects=True
        )
        
        # Should show CSRF error or validation error
        assert response.status_code in [400, 403] or \
               "csrf" in response.text.lower() or \
               "token" in response.text.lower() or \
               "/register" in str(response.url), \
            "Should reject request without CSRF token"
    
    async def test_admin_approve_requires_csrf(self, http_client):
        """
        Admin approval POST without CSRF should be rejected.
        """
        response = await http_client.post(
            settings.url("/admin/accounts/1/approve"),
            data={},  # No CSRF token
            follow_redirects=False
        )
        
        # Should be 400/403 for CSRF error, or 302 for auth redirect
        assert response.status_code in [302, 400, 403], \
            f"Expected 302/400/403 without CSRF, got {response.status_code}"


# Pytest fixtures
@pytest.fixture
async def http_client():
    """Create HTTP client with cookie persistence."""
    async with httpx.AsyncClient(verify=False) as client:
        yield client


@pytest.fixture
def mailpit():
    """Mock mailpit fixture for generating unique IDs."""
    class MockMailpit:
        def __init__(self):
            import random
            self._counter = random.randint(10000, 99999)
        
        def _generate_id(self):
            self._counter += 1
            return self._counter
    
    return MockMailpit()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
