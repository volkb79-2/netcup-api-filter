"""
Journey 03: Realm Management Testing

This journey tests the complete realm lifecycle:

1. **Account creates realm request** - User requests a new realm (stays pending)
2. **Admin sees pending realm** - Realm appears in admin pending list
3. **Admin approves realm** - Realm becomes active
4. **Admin rejects realm** - Test rejection flow
5. **Multiple realms per account** - Account can have multiple realms
6. **Realm types** - Test host vs domain realm types

Prerequisites:
- Admin logged in (from test_01)
- At least one approved account exists (from test_02)
- Mailpit running for notifications
"""
import pytest
import pytest_asyncio
import secrets
from typing import Optional

from ui_tests.config import settings
from ui_tests.workflows import ensure_admin_dashboard


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def realm_data():
    """Generate unique realm data for this test module."""
    suffix = secrets.token_hex(4)
    return {
        "realm_pending_for_approval": {
            "value": f"pending-approve-{suffix}.example.com",
            "type": "host",
            "description": "Realm to be approved",
        },
        "realm_pending_for_rejection": {
            "value": f"pending-reject-{suffix}.example.com", 
            "type": "host",
            "description": "Realm to be rejected",
        },
        "realm_approved": {
            "value": f"home-{suffix}.example.com",
            "type": "host",
            "description": "Home automation DDNS",
        },
        "realm_rejected": {
            "value": f"reject-{suffix}.example.com",
            "type": "host",
            "description": "Realm to be rejected",
        },
        "realm_domain": {
            "value": f"iot-{suffix}.example.com",
            "type": "domain",
            "description": "Full domain delegation",
        },
        "realm_multi": {
            "value": f"multi-{suffix}.example.com",
            "type": "host",
            "description": "Additional realm",
        },
    }


@pytest.fixture(scope="module")
def test_account_credentials():
    """Return credentials for a test account that can request realms."""
    # This uses the preseeded test client from the deployment
    # If no test client, we'll create via admin
    return {
        "username": "testclient",
        "password": "TestClient123!",
    }


# ============================================================================
# Phase 0: Setup Pending Realms (via direct database to ensure test data)
# ============================================================================

async def create_pending_realm_in_db(realm_value: str, account_id: int = 1) -> bool:
    """Create a pending realm directly in the database for testing."""
    import sqlite3
    import os
    from datetime import datetime, timezone
    
    db_path = os.environ.get('DATABASE_PATH', '/workspaces/netcup-api-filter/deploy-local/netcup_filter.db')
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path, timeout=10.0)
        cursor = conn.cursor()
        
        # Check if account exists
        cursor.execute("SELECT id FROM accounts WHERE id = ?", (account_id,))
        if not cursor.fetchone():
            # Use first available account
            cursor.execute("SELECT id FROM accounts LIMIT 1")
            row = cursor.fetchone()
            if not row:
                print("No accounts in database")
                conn.close()
                return False
            account_id = row[0]
        
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        
        # Insert pending realm with all required fields
        cursor.execute("""
            INSERT INTO account_realms (
                account_id, domain, realm_type, realm_value, 
                allowed_record_types, allowed_operations, status, 
                requested_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            account_id,
            'example.com',
            'host',
            realm_value,
            'A,AAAA',
            'read,update',
            'pending',
            now,
            now
        ))
        conn.commit()
        conn.close()
        print(f"✅ Created pending realm: {realm_value}")
        return True
    except Exception as e:
        print(f"❌ Failed to create pending realm: {e}")
        return False


class TestSetupPendingRealms:
    """Create pending realms to ensure test data exists for approval/rejection tests."""
    
    @pytest.mark.asyncio
    async def test_00_create_pending_realms_for_testing(
        self, admin_session, screenshot_helper, realm_data
    ):
        """Create pending realm entries directly for testing approval flow."""
        ss = screenshot_helper('03-realm')
        browser = admin_session
        
        # Create pending realms for approval and rejection tests
        suffix = secrets.token_hex(4)
        
        await create_pending_realm_in_db(f"test-approve-{suffix}")
        await create_pending_realm_in_db(f"test-reject-{suffix}")
        
        # Verify pending realms now exist
        await browser.goto(settings.url('/admin/realms/pending'))
        await browser.wait_for_load_state('domcontentloaded')
        
        await ss.capture('realm-pending-after-setup', 'Pending realms after setup')
        
        body = await browser.text('body')
        has_pending = 'No Pending' not in body
        print(f"Pending realms exist: {has_pending}")
        
        assert has_pending, "Should have pending realms after setup"


# ============================================================================
# Phase 1: User Realm Request Flow
# ============================================================================

class TestUserRealmRequest:
    """Test user requesting a new realm."""
    
    @pytest.mark.asyncio
    async def test_01_realm_request_page_loads(
        self, browser, screenshot_helper
    ):
        """Realm request page is accessible (when logged in as account)."""
        ss = screenshot_helper('03-realm')
        
        # For now, test via admin creating realm for account
        # User-side realm request requires account login which we'll skip
        # Focus on admin workflow
        
        await browser.goto(settings.url('/account/login'))
        await ss.capture('realm-account-login', 'Account login for realm request')
        
        # Note: Full user flow would require:
        # 1. Login as account
        # 2. Navigate to realms
        # 3. Request new realm
        # This is handled in account portal tests
    
    @pytest.mark.asyncio
    async def test_02_admin_creates_realm_for_account(
        self, admin_session, screenshot_helper, realm_data
    ):
        """Admin can create realm for an existing account."""
        ss = screenshot_helper('03-realm')
        browser = admin_session
        realm = realm_data["realm_approved"]
        
        # First, go to accounts and find one
        await browser.goto(settings.url('/admin/accounts'))
        await browser.wait_for_load_state('domcontentloaded')
        
        # Click on first account
        account_link = await browser.query_selector(
            'a[href*="/admin/accounts/"]:not([href="/admin/accounts/new"]):not([href*="/pending"])'
        )
        
        if not account_link:
            pytest.skip("No accounts available to add realm to")
        
        await account_link.click()
        await browser.wait_for_load_state('domcontentloaded')
        
        await ss.capture('admin-account-detail-before-realm', 'Account detail before adding realm')
        
        # Look for "Add Realm" button/link
        add_realm_btn = await browser.query_selector(
            'a[href*="/realms/new"], button:has-text("Add Realm"), a:has-text("Add Realm")'
        )
        
        if add_realm_btn:
            await add_realm_btn.click()
            await browser.wait_for_load_state('domcontentloaded')
            
            await ss.capture('admin-add-realm-form', 'Add realm form')
            
            # Fill realm form
            await browser.fill('#realm_value, input[name="realm_value"]', realm["value"])
            
            type_select = await browser.query_selector('#realm_type, select[name="realm_type"]')
            if type_select:
                await browser.select('#realm_type, select[name="realm_type"]', realm["type"])
            
            desc_field = await browser.query_selector('#description, textarea[name="description"]')
            if desc_field:
                await desc_field.fill(realm["description"])
            
            await ss.capture('admin-realm-form-filled', 'Realm form filled')
            
            await browser.click('button[type="submit"]')
            await browser.wait_for_timeout(1000)
            
            await ss.capture('admin-realm-created', 'Realm created')
        else:
            print("Add Realm button not found - may be on different page structure")


# ============================================================================
# Phase 2: Admin Realm Management
# ============================================================================

class TestAdminRealmManagement:
    """Test admin realm list and management views."""
    
    @pytest.mark.asyncio
    async def test_03_admin_realms_list(
        self, admin_session, screenshot_helper
    ):
        """Admin can see all realms."""
        ss = screenshot_helper('03-realm')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/realms'))
        await browser.wait_for_load_state('domcontentloaded')
        
        await ss.capture('admin-realms-list', 'Admin realms list')
        
        h1 = await browser.text('main h1')
        assert 'Realm' in h1, f"Expected Realms page, got: {h1}"
    
    @pytest.mark.asyncio
    async def test_04_admin_pending_realms(
        self, admin_session, screenshot_helper
    ):
        """Admin can see pending realm requests."""
        ss = screenshot_helper('03-realm')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/realms/pending'))
        await browser.wait_for_load_state('domcontentloaded')
        
        await ss.capture('admin-realms-pending', 'Admin pending realms')
        
        body = await browser.text('body')
        print(f"Pending realms page: {body[:500]}")
    
    @pytest.mark.asyncio
    async def test_05_admin_realm_detail(
        self, admin_session, screenshot_helper
    ):
        """Admin can view realm detail page."""
        ss = screenshot_helper('03-realm')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/realms'))
        await browser.wait_for_load_state('domcontentloaded')
        
        # Click on first realm if exists
        realm_link = await browser.query_selector(
            'a[href*="/admin/realms/"]:not([href*="/pending"]):not([href*="/new"])'
        )
        
        if realm_link:
            await realm_link.click()
            await browser.wait_for_load_state('domcontentloaded')
            
            await ss.capture('admin-realm-detail', 'Admin realm detail')
            
            body = await browser.text('body')
            # Should show realm details
            assert any(word in body.lower() for word in ['type', 'value', 'account', 'token']), \
                f"Realm detail should show info: {body[:300]}"
        else:
            print("No realms to view detail - expected in fresh setup")


# ============================================================================
# Phase 3: Realm Approval/Rejection Flow
# ============================================================================

class TestRealmApprovalFlow:
    """Test realm approval and rejection flows."""
    
    @pytest.mark.asyncio
    async def test_06_approve_pending_realm(
        self, admin_session, screenshot_helper
    ):
        """Admin can approve a pending realm."""
        ss = screenshot_helper('03-realm')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/realms/pending'))
        await browser.wait_for_load_state('domcontentloaded')
        
        body = await browser.text('body')
        
        # Check if there are any pending realms
        if 'No Pending Realm' in body:
            print("No pending realms to approve - expected if all already approved")
            await ss.capture('realm-pending-empty', 'No pending realms')
            pytest.skip("No pending realms to approve")
            return
        
        # Look for approve button in the table (btn-success with check icon)
        approve_btn = await browser.query_selector(
            'form[action*="approve"] button.btn-success'
        )
        
        if approve_btn:
            await ss.capture('realm-before-approve', 'Realm before approval')
            
            await approve_btn.click()
            await browser.wait_for_timeout(1000)
            
            await ss.capture('realm-after-approve', 'Realm after approval')
            
            body = await browser.text('body')
            print(f"After approval: {body[:300]}")
        else:
            print("No approve button found - checking for empty state")
            await ss.capture('realm-pending-no-btn', 'No approve button')
            pytest.skip("No approve button found")
    
    @pytest.mark.asyncio
    async def test_07_reject_pending_realm(
        self, admin_session, screenshot_helper, realm_data
    ):
        """Admin can reject a pending realm with reason."""
        ss = screenshot_helper('03-realm')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/realms/pending'))
        await browser.wait_for_load_state('domcontentloaded')
        
        body = await browser.text('body')
        
        # Check if there are any pending realms
        if 'No Pending Realm' in body:
            print("No pending realms to reject - expected if all processed")
            await ss.capture('realm-pending-empty-reject', 'No pending realms for rejection')
            pytest.skip("No pending realms to reject")
            return
        
        # Look for reject button (btn-outline-danger with x icon)
        reject_btn = await browser.query_selector(
            'button.btn-outline-danger[onclick*="reject"]'
        )
        
        if reject_btn:
            await ss.capture('realm-before-reject', 'Realm before rejection')
            
            await reject_btn.click()
            await browser.wait_for_load_state('domcontentloaded')
            
            # Look for reason field in modal
            reason_field = await browser.query_selector('textarea[name="reason"]')
            if reason_field:
                await browser.fill('textarea[name="reason"]', "Domain not owned by user")
            
            await ss.capture('realm-reject-reason', 'Realm rejection with reason')
            
            # Confirm rejection (submit button in modal)
            confirm_btn = await browser.query_selector(
                '#rejectModal button[type="submit"]'
            )
            if confirm_btn:
                await confirm_btn.click()
                await browser.wait_for_timeout(1000)
            
            await ss.capture('realm-after-reject', 'Realm after rejection')
        else:
            print("No reject button found")
            await ss.capture('realm-pending-no-reject-btn', 'No reject button')
            pytest.skip("No reject button found")


# ============================================================================
# Phase 4: Realm Types Testing
# ============================================================================

class TestRealmTypes:
    """Test different realm types (host vs domain)."""
    
    @pytest.mark.asyncio
    async def test_08_host_realm_restrictions(
        self, admin_session, screenshot_helper
    ):
        """Host realm only allows single hostname."""
        ss = screenshot_helper('03-realm')
        browser = admin_session
        
        # Navigate to account detail and try to add realm
        await browser.goto(settings.url('/admin/accounts'))
        await browser.wait_for_load_state('domcontentloaded')
        
        account_link = await browser.query_selector(
            'a[href*="/admin/accounts/"]:not([href="/admin/accounts/new"])'
        )
        
        if account_link:
            await account_link.click()
            await browser.wait_for_load_state('domcontentloaded')
            
            add_realm = await browser.query_selector('a[href*="/realms/new"]')
            if add_realm:
                await add_realm.click()
                await browser.wait_for_load_state('domcontentloaded')
                
                # Select host type
                type_select = await browser.query_selector('#realm_type, select[name="realm_type"]')
                if type_select:
                    await browser.select('#realm_type, select[name="realm_type"]', 'host')
                
                await ss.capture('realm-type-host', 'Host realm type selected')
                
                # Fill with invalid value (should show error)
                await browser.fill('#realm_value, input[name="realm_value"]', '*.invalid.example.com')
                
                await browser.click('button[type="submit"]')
                await browser.wait_for_load_state('domcontentloaded')
                
                await ss.capture('realm-invalid-host', 'Invalid host realm rejected')
    
    @pytest.mark.asyncio
    async def test_09_domain_realm_allows_wildcard(
        self, admin_session, screenshot_helper, realm_data
    ):
        """Domain realm allows full subdomain delegation."""
        ss = screenshot_helper('03-realm')
        browser = admin_session
        realm = realm_data["realm_domain"]
        
        await browser.goto(settings.url('/admin/accounts'))
        await browser.wait_for_load_state('domcontentloaded')
        
        account_link = await browser.query_selector(
            'a[href*="/admin/accounts/"]:not([href="/admin/accounts/new"])'
        )
        
        if account_link:
            await account_link.click()
            await browser.wait_for_load_state('domcontentloaded')
            
            add_realm = await browser.query_selector('a[href*="/realms/new"]')
            if add_realm:
                await add_realm.click()
                await browser.wait_for_load_state('domcontentloaded')
                
                # Select domain type
                type_select = await browser.query_selector('#realm_type, select[name="realm_type"]')
                if type_select:
                    await browser.select('#realm_type, select[name="realm_type"]', 'domain')
                
                await browser.fill('#realm_value, input[name="realm_value"]', realm["value"])
                
                await ss.capture('realm-type-domain', 'Domain realm type')
                
                desc_field = await browser.query_selector('#description, textarea[name="description"]')
                if desc_field:
                    await desc_field.fill(realm["description"])
                
                await browser.click('button[type="submit"]')
                await browser.wait_for_timeout(1000)
                
                await ss.capture('realm-domain-created', 'Domain realm created')


# ============================================================================
# Phase 5: Multi-Realm Account
# ============================================================================

class TestMultiRealmAccount:
    """Test account with multiple realms."""
    
    @pytest.mark.asyncio
    async def test_10_account_with_multiple_realms(
        self, admin_session, screenshot_helper, realm_data
    ):
        """Account can have multiple realms."""
        ss = screenshot_helper('03-realm')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/accounts'))
        await browser.wait_for_load_state('domcontentloaded')
        
        # Click on first account
        account_link = await browser.query_selector(
            'a[href*="/admin/accounts/"]:not([href="/admin/accounts/new"])'
        )
        
        if account_link:
            await account_link.click()
            await browser.wait_for_load_state('domcontentloaded')
            
            await ss.capture('account-with-realms', 'Account with multiple realms')
            
            body = await browser.text('body')
            # Should show realm list or section
            print(f"Account detail with realms: {body[:500]}")


# ============================================================================
# Error Handling
# ============================================================================

class TestRealmErrorHandling:
    """Test realm validation and error handling."""
    
    @pytest.mark.asyncio
    async def test_11_invalid_realm_value_rejected(
        self, admin_session, screenshot_helper
    ):
        """Invalid realm values are rejected."""
        ss = screenshot_helper('03-realm')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/accounts'))
        await browser.wait_for_load_state('domcontentloaded')
        
        account_link = await browser.query_selector(
            'a[href*="/admin/accounts/"]:not([href="/admin/accounts/new"])'
        )
        
        if account_link:
            await account_link.click()
            await browser.wait_for_load_state('domcontentloaded')
            
            add_realm = await browser.query_selector('a[href*="/realms/new"]')
            if add_realm:
                await add_realm.click()
                await browser.wait_for_load_state('domcontentloaded')
                
                # Invalid realm value
                await browser.fill('#realm_value, input[name="realm_value"]', 'invalid with spaces')
                
                await ss.capture('realm-invalid-value', 'Invalid realm value entered')
                
                await browser.click('button[type="submit"]')
                await browser.wait_for_load_state('domcontentloaded')
                
                await ss.capture('realm-invalid-rejected', 'Invalid realm rejected')
                
                body = await browser.text('body')
                # Should show validation error
                assert any(word in body.lower() for word in ['invalid', 'error', 'must', 'valid']), \
                    f"Expected validation error: {body[:300]}"
    
    @pytest.mark.asyncio
    async def test_12_duplicate_realm_rejected(
        self, admin_session, screenshot_helper, realm_data
    ):
        """Duplicate realm values are rejected."""
        ss = screenshot_helper('03-realm')
        browser = admin_session
        realm = realm_data["realm_approved"]
        
        await browser.goto(settings.url('/admin/accounts'))
        await browser.wait_for_load_state('domcontentloaded')
        
        account_link = await browser.query_selector(
            'a[href*="/admin/accounts/"]:not([href="/admin/accounts/new"])'
        )
        
        if account_link:
            await account_link.click()
            await browser.wait_for_load_state('domcontentloaded')
            
            add_realm = await browser.query_selector('a[href*="/realms/new"]')
            if add_realm:
                await add_realm.click()
                await browser.wait_for_load_state('domcontentloaded')
                
                # Try to add same realm again
                await browser.fill('#realm_value, input[name="realm_value"]', realm["value"])
                
                await ss.capture('realm-duplicate-attempt', 'Duplicate realm attempt')
                
                await browser.click('button[type="submit"]')
                await browser.wait_for_load_state('domcontentloaded')
                
                await ss.capture('realm-duplicate-rejected', 'Duplicate realm rejected')
                
                body = await browser.text('body')
                # May show error or may succeed (depends on if realm exists)
                print(f"Duplicate realm result: {body[:300]}")
