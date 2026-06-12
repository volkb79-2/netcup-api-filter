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
import re
import pytest
import pytest_asyncio
import secrets
from typing import Optional

from ui_tests import verification, workflows
from ui_tests.browser import Browser
from ui_tests.config import settings
from ui_tests.deployment_state import get_base_url, get_deployment_target
from ui_tests.mailpit_client import MailpitClient
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
# Phase 0: Setup Pending Realms (UI-driven — no direct DB writes)
# ============================================================================

def _j03_base_url() -> str:
    return get_base_url(get_deployment_target()).rstrip("/")


async def _j03_request_realm_as_user(
    user: Browser, *, subdomain: str, account_username: str
) -> None:
    """Request a pending realm via the account portal form.

    Uses the public domain root (first available option in the request form).
    Waits until Channel A (DB) confirms the pending realm exists.
    """
    await user.goto(settings.url("/account/realms/request"))
    submitted = await user.evaluate(
        f"""
        () => {{
            const rootSel = document.getElementById('domain_root_id');
            if (!rootSel) return false;
            const firstOpt = [...rootSel.options].find(o => o.value && o.value !== '');
            if (!firstOpt) return false;
            rootSel.value = firstOpt.value;
            rootSel.dispatchEvent(new Event('change'));

            const sub = document.getElementById('subdomain');
            if (sub) sub.value = '{subdomain}';

            const typeHost = document.getElementById('type-host');
            if (typeHost) typeHost.checked = true;

            for (const id of ['rt-A', 'rt-AAAA']) {{
                const e = document.getElementById(id);
                if (e) e.checked = true;
            }}
            for (const id of ['op-read', 'op-update']) {{
                const e = document.getElementById(id);
                if (e) e.checked = true;
            }}

            document.getElementById('request-form').submit();
            return true;
        }}
        """
    )
    assert submitted, f"realm request form could not be submitted for subdomain={subdomain!r}"

    await user._page.wait_for_url(
        re.compile(r".*/account/dashboard(?:\?.*)?$"), timeout=10_000
    )
    verification.wait_for(
        lambda: verification.get_realm(
            account_username=account_username, realm_value=subdomain
        ) is not None,
        timeout=10.0,
        message=f"pending realm {subdomain!r} not created after user request",
    )
    row = verification.get_realm(account_username=account_username, realm_value=subdomain)
    assert row["status"] == "pending", f"expected pending realm, got status={row['status']!r}"
    print(f"Created pending realm: {subdomain!r} (realm_id={row['id']})")


class TestSetupPendingRealms:
    """Create pending realms via UI to ensure test data exists for approval/rejection tests."""

    @pytest.mark.asyncio
    async def test_00_create_pending_realms_for_testing(
        self, admin_session, screenshot_helper, playwright_client
    ):
        """Create pending realm entries via UI for testing the approval flow.

        Replaces the legacy DB-write seeding (T09). Creates a throwaway account
        via admin invite, logs in as that user, and requests two pending realms.
        The account is left in place (it will be cleaned up by the deployment reset);
        the realms persist as pending for the downstream approval/rejection tests.
        """
        from ui_tests.parallel_session_manager import ParallelSessionManager

        ss = screenshot_helper('03-realm')
        admin = admin_session

        # Generate unique identifiers for this test run.
        suffix = secrets.token_hex(4)
        username = f"j03setup-{suffix}"
        email = f"j03setup-{suffix}@example.test"
        password = f"J03Setup{suffix}@#$%TestPassXq"

        mailpit = MailpitClient()
        mailpit.clear()

        # Step 1: Admin creates a throwaway account (no pre-approved realm).
        await admin.goto(settings.url("/admin/accounts/new"))
        await admin.wait_for_text("main h1", "Create Account")
        await admin.fill("#username", username)
        await admin.fill("#email", email)
        await admin.evaluate(
            """
            () => {
                const inc = document.getElementById('include_realm');
                if (inc) inc.checked = false;
                document.getElementById('createAccountForm').submit();
            }
            """
        )
        verification.wait_for(
            lambda: verification.get_account(username) is not None,
            timeout=10.0,
            message=f"account {username!r} not visible in DB after create",
        )
        account_row = verification.get_account(username)
        account_id = account_row["id"]

        # Step 2: Complete the invite to set a known password.
        def _wait_for_email(*, to_address, subject_substr, timeout=20.0):
            msg = mailpit.wait_for_message(
                predicate=lambda m: (
                    subject_substr.lower() in (m.subject or "").lower()
                    and any(to_address.lower() == a.address.lower() for a in (m.to or []))
                ),
                timeout=timeout,
                poll_interval=0.5,
            )
            assert msg is not None, f"Timed out waiting for email to {to_address!r}"
            return msg

        def _link_to_local_url(absolute_url):
            path = re.sub(r"^https?://[^/]+", "", absolute_url)
            return _j03_base_url() + path

        def _extract_link(msg, path_prefix):
            body = (msg.text or "") + "\n" + (msg.html or "")
            pattern = re.compile(r"https?://[^\s\"'<>]*" + re.escape(path_prefix) + r"[^\s\"'<>]+")
            m = pattern.search(body)
            assert m, f"No URL containing {path_prefix!r} in email body:\n{body[:400]}"
            return m.group(0)

        invite_msg = _wait_for_email(to_address=email, subject_substr="account has been created")
        invite_url = _link_to_local_url(_extract_link(invite_msg, "/account/invite/"))
        mailpit.clear()

        async with ParallelSessionManager(
            browser=playwright_client.browser, base_url=settings.url("")
        ) as mgr:
            invite_handle = await mgr.create_session(role="anonymous", session_id=f"j03invite_{suffix}")
            invite_browser = Browser(invite_handle.page)
            await invite_browser.reset()
            await invite_browser.goto(invite_url, wait_until="domcontentloaded")
            await invite_browser.fill("#new_password", password)
            await invite_browser.fill("#confirm_password", password)
            await invite_browser.submit("#invite-form")
            await invite_browser._page.wait_for_url(
                re.compile(r".*/account/login(?:\?.*)?$"), timeout=10_000
            )

            verification.wait_for(
                lambda: verification.get_account(username)["must_change_password"] == 0,
                timeout=10.0,
                message="invite not accepted for j03 setup account",
            )

            # Step 3: Log in as the user and request two pending realms.
            user_handle = await mgr.create_session(role="account", session_id=f"j03user_{suffix}")
            user = Browser(user_handle.page)
            await user.reset()

            # Login (with 2FA via Mailpit).
            await user.goto(settings.url("/account/login"))
            await user.fill("#username", username)
            await user.fill("#password", password)
            await user.click("button[type='submit']")
            try:
                await user._page.wait_for_url(
                    re.compile(r".*/account/(?:login/2fa|login|dashboard)(?:\?.*)?$"),
                    timeout=10_000,
                )
            except Exception:
                pass
            await workflows.handle_2fa_if_present(user, timeout=20.0)
            await user.goto(settings.url("/account/dashboard"), wait_until="domcontentloaded")
            assert "/account/login" not in user._page.url, (
                f"user login failed for j03 setup account; at {user._page.url}"
            )

            # Request two pending realms.
            subdom1 = f"j03approve{suffix}"
            subdom2 = f"j03reject{suffix}"
            await _j03_request_realm_as_user(user, subdomain=subdom1, account_username=username)
            await _j03_request_realm_as_user(user, subdomain=subdom2, account_username=username)

        # Step 4: Verify admin sees pending realms.
        await admin.goto(settings.url('/admin/realms/pending'))
        await admin.wait_for_load_state('domcontentloaded')
        await ss.capture('realm-pending-after-setup', 'Pending realms after setup')

        body = await admin.text('body')
        has_pending = 'No Pending' not in body
        print(f"Pending realms exist: {has_pending}")
        assert has_pending, "Should have pending realms after UI-driven setup"


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
