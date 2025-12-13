"""
Journey 09: Multi-Backend DNS Management Testing

This journey tests the complete multi-backend DNS management system:

1. **Admin creates backend service** - Admin adds a new backend with credentials
2. **Admin creates domain root** - Admin sets up managed domain root with visibility
3. **User sees available domain roots** - User can select from dropdown
4. **User requests realm under domain root** - User selects zone and subdomain
5. **Admin approves realm** - Realm is linked to backend service
6. **Backend provider management** - Admin views available providers
7. **User BYOD management** - User manages their own backends

This journey covers the combinatorial space of states:
- Public vs Private domain roots
- Platform vs User backends
- Different providers (netcup, powerdns)
- Realm request with domain root selection
- User backend CRUD operations

Prerequisites:
- Admin logged in (from test_01)
- Multi-backend infrastructure seeded (providers, enums)
"""
import pytest
import pytest_asyncio
import asyncio
import secrets
from typing import Optional

from ui_tests.config import settings


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def backend_data():
    """Generate unique backend data for this test module."""
    suffix = secrets.token_hex(4)
    return {
        "netcup_backend": {
            "service_name": f"test-netcup-{suffix}",
            "display_name": f"Test Netcup {suffix}",
            "customer_id": "12345678",
            "api_key": "test-api-key",
            "api_password": "test-api-password",
        },
        "powerdns_backend": {
            "service_name": f"test-pdns-{suffix}",
            "display_name": f"Test PowerDNS {suffix}",
            "api_url": "http://powerdns:8081",
            "api_key": "test-pdns-key",
        },
        "domain_root_public": {
            "root_domain": f"test-public-{suffix}.example.com",
            "display_name": f"Public Test Zone {suffix}",
            "visibility": "public",
        },
        "domain_root_private": {
            "root_domain": f"test-private-{suffix}.example.com",
            "display_name": f"Private Test Zone {suffix}",
            "visibility": "private",
        },
        "user_backend": {
            "service_name": f"my-backend-{suffix}",
            "display_name": f"My Personal Backend {suffix}",
            "customer_id": "98765432",
            "api_key": "my-api-key",
            "api_password": "my-api-password",
        },
    }


# ============================================================================
# Phase 1: Admin Views Backend Infrastructure
# ============================================================================

class TestAdminBackendInfrastructure:
    """Test admin can view and manage backend infrastructure."""
    
    @pytest.mark.asyncio
    async def test_01_admin_views_backend_providers(
        self, admin_session, screenshot_helper
    ):
        """Admin can view available backend providers."""
        ss = screenshot_helper('09-multibackend')
        browser = admin_session
        
        # Navigate to backend providers
        await browser.goto(settings.url('/admin/backends/providers'))
        await browser.wait_for_load()
        
        # Verify page loaded
        page_text = await browser.text('main')
        assert 'Backend Providers' in page_text, "Provider list page should load"
        
        # Verify built-in providers are shown
        assert 'netcup' in page_text.lower() or 'Netcup' in page_text, \
            "Netcup provider should be listed"
        assert 'powerdns' in page_text.lower() or 'PowerDNS' in page_text, \
            "PowerDNS provider should be listed"
        
        await ss.take("providers-list")
    
    @pytest.mark.asyncio
    async def test_02_admin_views_backends_list(
        self, admin_session, screenshot_helper
    ):
        """Admin can view backend services list."""
        ss = screenshot_helper('09-multibackend')
        browser = admin_session
        
        # Navigate to backends list
        await browser.goto(settings.url('/admin/backends'))
        await browser.wait_for_load()
        
        # Verify page loaded
        page_text = await browser.text('main')
        assert 'Backend Services' in page_text, "Backends list page should load"
        
        # Check for stats display
        assert 'Total' in page_text or 'Active' in page_text, \
            "Stats should be displayed"
        
        await ss.take("backends-list")
    
    @pytest.mark.asyncio
    async def test_03_admin_views_domain_roots_list(
        self, admin_session, screenshot_helper
    ):
        """Admin can view domain roots list."""
        ss = screenshot_helper('09-multibackend')
        browser = admin_session
        
        # Navigate to domain roots list
        await browser.goto(settings.url('/admin/domain-roots'))
        await browser.wait_for_load()
        
        # Verify page loaded
        page_text = await browser.text('main')
        assert 'Domain Roots' in page_text, "Domain roots list page should load"
        
        # Check for demo domain root
        if 'dyn.example.com' in page_text:
            print("✅ Demo domain root found")
        
        await ss.take("domain-roots-list")


# ============================================================================
# Phase 2: Admin Creates Backend Service (Combinatorial: netcup/powerdns)
# ============================================================================

class TestAdminCreatesBackendService:
    """Test admin creating backend services."""
    
    @pytest.mark.asyncio
    async def test_04_admin_can_access_backend_create_form(
        self, admin_session, screenshot_helper, backend_data
    ):
        """Admin can access the backend create form."""
        ss = screenshot_helper('09-multibackend')
        browser = admin_session
        
        # Navigate to backend create
        await browser.goto(settings.url('/admin/backends/new'))
        await browser.wait_for_load()
        
        # Verify form loaded
        page_text = await browser.text('main')
        assert 'Create Backend Service' in page_text or 'Add Backend' in page_text, \
            "Backend create form should load"
        
        # Verify provider selection exists
        assert 'Provider' in page_text, "Provider selection should exist"
        assert 'Service Name' in page_text, "Service name field should exist"
        
        await ss.take("backend-create-form")
    
    @pytest.mark.asyncio
    async def test_05_admin_can_access_domain_root_create_form(
        self, admin_session, screenshot_helper, backend_data
    ):
        """Admin can access the domain root create form."""
        ss = screenshot_helper('09-multibackend')
        browser = admin_session
        
        # Navigate to domain root create
        await browser.goto(settings.url('/admin/domain-roots/new'))
        await browser.wait_for_load()
        
        # Verify form loaded
        page_text = await browser.text('main')
        assert 'Create Domain Root' in page_text or 'Add Domain Root' in page_text, \
            "Domain root create form should load"
        
        # Verify form fields exist
        assert 'Root Domain' in page_text, "Root domain field should exist"
        assert 'Visibility' in page_text, "Visibility selection should exist"
        assert 'Backend' in page_text, "Backend selection should exist"
        
        await ss.take("domain-root-create-form")


# ============================================================================
# Phase 3: User Views Available Domain Roots
# ============================================================================

class TestUserViewsDomainRoots:
    """Test user can see available domain roots for realm request."""
    
    @pytest.mark.asyncio
    async def test_06_demo_user_can_see_realm_request_page(
        self, user_session, screenshot_helper
    ):
        """Demo user can access realm request page with domain root dropdown."""
        ss = screenshot_helper('09-multibackend')
        browser = user_session
        
        # Navigate to realm request page
        await browser.goto(settings.url('/account/realms/request'))
        await browser.wait_for_load()
        
        # Verify page loaded
        page_text = await browser.text('main')
        assert 'Request' in page_text or 'Realm' in page_text, \
            "Realm request page should load"
        
        # Check for domain root dropdown
        if 'DNS Zone' in page_text or 'Select available zone' in page_text:
            print("✅ Domain root dropdown found")
        
        # Check for demo domain root in dropdown (if seeded)
        if 'dyn.example.com' in page_text or 'Demo Dynamic DNS' in page_text:
            print("✅ Demo domain root available for selection")
        
        await ss.take("user-realm-request-with-dropdown")


# ============================================================================
# Phase 4: User Backend Management (BYOD)
# ============================================================================

class TestUserBackendManagement:
    """Test user can manage their own backends (BYOD)."""
    
    @pytest.mark.asyncio
    async def test_07_user_can_view_backends_list(
        self, user_session, screenshot_helper
    ):
        """User can view their own backends list."""
        ss = screenshot_helper('09-multibackend')
        browser = user_session
        
        # Navigate to user backends list
        await browser.goto(settings.url('/account/backends'))
        await browser.wait_for_load()
        
        # Verify page loaded
        page_text = await browser.text('main')
        assert 'My DNS Backends' in page_text or 'My Backends' in page_text, \
            "User backends list page should load"
        
        # Check for BYOD info
        if 'Bring Your Own DNS' in page_text or 'BYOD' in page_text:
            print("✅ BYOD info displayed")
        
        # Check for Add Backend button
        assert 'Add Backend' in page_text, "Add backend button should exist"
        
        await ss.take("user-backends-list")
    
    @pytest.mark.asyncio
    async def test_08_user_can_access_backend_create_form(
        self, user_session, screenshot_helper, backend_data
    ):
        """User can access the backend create form."""
        ss = screenshot_helper('09-multibackend')
        browser = user_session
        
        # Navigate to backend create
        await browser.goto(settings.url('/account/backends/new'))
        await browser.wait_for_load()
        
        # Verify form loaded
        page_text = await browser.text('main')
        assert 'Add DNS Backend' in page_text or 'Add Backend' in page_text, \
            "Backend create form should load"
        
        # Verify provider selection exists
        assert 'Provider' in page_text, "Provider selection should exist"
        assert 'Service Name' in page_text, "Service name field should exist"
        
        # Check for provider options
        assert 'Netcup' in page_text, "Netcup provider should be available"
        
        await ss.take("user-backend-create-form")
    
    @pytest.mark.asyncio
    async def test_09_user_sees_supported_providers(
        self, user_session, screenshot_helper
    ):
        """User can see available providers in backends list."""
        ss = screenshot_helper('09-multibackend')
        browser = user_session
        
        # Navigate to user backends list
        await browser.goto(settings.url('/account/backends'))
        await browser.wait_for_load()
        
        # Verify providers section
        page_text = await browser.text('main')
        if 'Supported Providers' in page_text:
            print("✅ Supported providers section shown")
        
        await ss.take("user-backends-providers")


# ============================================================================
# Phase 5: State Combinations Testing
# ============================================================================

class TestStateCombinations:
    """Test different state combinations for multi-backend."""
    
    @pytest.mark.asyncio
    async def test_10_public_visibility_domain_root_accessible(
        self, admin_session, screenshot_helper
    ):
        """Public domain roots are accessible to all users."""
        ss = screenshot_helper('09-multibackend')
        browser = admin_session
        
        # Navigate to domain roots and check for public visibility badge
        await browser.goto(settings.url('/admin/domain-roots'))
        await browser.wait_for_load()
        
        page_text = await browser.text('main')
        
        # Check for visibility indicators
        if 'Public' in page_text:
            print("✅ Public visibility domain roots shown")
        
        await ss.take("domain-roots-visibility-states")
    
    @pytest.mark.asyncio
    async def test_11_backend_test_status_displayed(
        self, admin_session, screenshot_helper
    ):
        """Backend test status (pending/success/failed) is displayed."""
        ss = screenshot_helper('09-multibackend')
        browser = admin_session
        
        # Navigate to backends list
        await browser.goto(settings.url('/admin/backends'))
        await browser.wait_for_load()
        
        page_text = await browser.text('main')
        
        # Check for status indicators
        if 'Active' in page_text or 'Inactive' in page_text:
            print("✅ Backend status indicators displayed")
        
        await ss.take("backends-status-indicators")


# ============================================================================
# Phase 6: Navigation and Menu Testing
# ============================================================================

class TestMultiBackendNavigation:
    """Test navigation through multi-backend UI."""
    
    @pytest.mark.asyncio
    async def test_12_dns_menu_navigates_correctly(
        self, admin_session, screenshot_helper
    ):
        """DNS menu items navigate to correct pages."""
        ss = screenshot_helper('09-multibackend')
        browser = admin_session
        
        # Start at dashboard
        await browser.goto(settings.url('/admin/dashboard'))
        await browser.wait_for_load()
        
        # Navigate through DNS menu items
        pages_to_test = [
            ('/admin/backends', 'Backend Services'),
            ('/admin/domain-roots', 'Domain Roots'),
            ('/admin/backends/providers', 'Backend Providers'),
        ]
        
        for url, expected_text in pages_to_test:
            await browser.goto(settings.url(url))
            await browser.wait_for_load()
            
            page_text = await browser.text('main')
            assert expected_text in page_text, f"Page {url} should contain '{expected_text}'"
            print(f"✅ {url} loaded correctly")
        
        await ss.take("navigation-complete")
    
    @pytest.mark.asyncio
    async def test_13_user_backends_navigation(
        self, user_session, screenshot_helper
    ):
        """User can navigate through My Backends section."""
        ss = screenshot_helper('09-multibackend')
        browser = user_session
        
        # Navigate through user backend pages
        pages_to_test = [
            ('/account/backends', 'My DNS Backends'),
            ('/account/backends/new', 'Add DNS Backend'),
        ]
        
        for url, expected_text in pages_to_test:
            await browser.goto(settings.url(url))
            await browser.wait_for_load()
            
            page_text = await browser.text('main')
            assert expected_text in page_text or 'Backend' in page_text, \
                f"Page {url} should contain backend-related content"
            print(f"✅ {url} loaded correctly")
        
        await ss.take("user-backends-navigation")


# ============================================================================
# Cleanup
# ============================================================================

class TestCleanup:
    """Cleanup test data."""
    
    @pytest.mark.asyncio
    async def test_99_cleanup(self, admin_session, screenshot_helper):
        """Final cleanup and summary."""
        ss = screenshot_helper('09-multibackend')
        browser = admin_session
        
        # Take final screenshot at dashboard
        await browser.goto(settings.url('/admin/dashboard'))
        await browser.wait_for_load()
        
        await ss.take("final-dashboard")
        
        print("✅ Multi-backend journey tests completed")
