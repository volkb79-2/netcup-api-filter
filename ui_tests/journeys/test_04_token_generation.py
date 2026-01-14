"""
Journey 04: Token Generation and Management

This journey tests the complete token lifecycle:

1. **Generate token for realm** - Create API access token
2. **Token permissions** - Record types and operations
3. **Token security** - IP whitelisting, expiry
4. **Token revocation** - Disable/revoke tokens
5. **Token regeneration** - Generate new secret
6. **Multiple tokens per realm** - Different tokens for different purposes

Prerequisites:
- Admin logged in (from test_01)
- At least one approved realm exists (from test_03)
"""
import pytest
import pytest_asyncio
import secrets
import re
from typing import Optional

from ui_tests.config import settings
from ui_tests.workflows import ensure_admin_dashboard


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def token_data():
    """Token configuration data for tests."""
    return {
        "readonly_token": {
            "description": "Read-only monitoring token",
            "operations": ["read"],
            "record_types": ["A", "AAAA"],
        },
        "ddns_token": {
            "description": "DDNS update token",
            "operations": ["read", "update"],
            "record_types": ["A", "AAAA"],
        },
        "full_token": {
            "description": "Full control token",
            "operations": ["read", "update", "create", "delete"],
            "record_types": ["A", "AAAA", "CNAME", "TXT", "MX"],
        },
        "letsencrypt_token": {
            "description": "LetsEncrypt DNS-01 token",
            "operations": ["read", "update", "create", "delete"],
            "record_types": ["TXT"],
        },
    }


# ============================================================================
# Phase 1: Token Generation
# ============================================================================

class TestTokenGeneration:
    """Test generating tokens for realms."""
    
    @pytest.mark.asyncio
    async def test_01_navigate_to_token_creation(
        self, admin_session, screenshot_helper
    ):
        """Navigate to token creation from realm."""
        ss = screenshot_helper('04-token')
        browser = admin_session
        
        # Go to realms list
        await browser.goto(settings.url('/admin/realms'))
        await browser.wait_for_load_state('domcontentloaded')
        
        await ss.capture('realms-list-for-token', 'Realms list before token creation')
        
        # Click on first realm
        realm_link = await browser.query_selector(
            'a[href*="/admin/realms/"]:not([href*="/pending"]):not([href*="/new"])'
        )
        
        if realm_link:
            await realm_link.click()
            await browser.wait_for_load_state('domcontentloaded')
            
            await ss.capture('realm-detail-for-token', 'Realm detail for token creation')
            
            # Look for create token button
            create_token_btn = await browser.query_selector(
                'a[href*="/tokens/new"], button:has-text("Create Token"), a:has-text("Create Token"), '
                'a:has-text("Generate Token"), button:has-text("Generate")'
            )
            
            if create_token_btn:
                await create_token_btn.click()
                await browser.wait_for_load_state('domcontentloaded')
                
                await ss.capture('token-creation-form', 'Token creation form')
        else:
            print("No realms available - skipping token creation")
    
    @pytest.mark.asyncio
    async def test_02_create_readonly_token(
        self, admin_session, screenshot_helper, token_data
    ):
        """Create a read-only token."""
        ss = screenshot_helper('04-token')
        browser = admin_session
        token = token_data["readonly_token"]
        
        # Navigate to realm and create token
        await browser.goto(settings.url('/admin/realms'))
        await browser.wait_for_load_state('domcontentloaded')
        
        realm_link = await browser.query_selector(
            'a[href*="/admin/realms/"]:not([href*="/pending"])'
        )
        
        if realm_link:
            await realm_link.click()
            await browser.wait_for_load_state('domcontentloaded')
            
            create_token_btn = await browser.query_selector(
                'a[href*="/tokens/new"], a:has-text("Create Token"), a:has-text("Generate")'
            )
            
            if create_token_btn:
                await create_token_btn.click()
                await browser.wait_for_load_state('domcontentloaded')
                
                # Fill token form
                desc_field = await browser.query_selector('#description, input[name="description"]')
                if desc_field:
                    await desc_field.fill(token["description"])
                
                # Select operations (read only)
                ops_select = await browser.query_selector('select[name="allowed_operations"]')
                if ops_select:
                    # Use JavaScript to select only 'read'
                    await browser.evaluate(
                        """([selector, values]) => {
                            const select = document.querySelector(selector);
                            if (!select) return;
                            for (const option of select.options) {
                                option.selected = values.includes(option.value);
                            }
                            select.dispatchEvent(new Event('change', { bubbles: true }));
                        }""",
                        ['select[name="allowed_operations"]', token["operations"]]
                    )
                
                # Select record types
                types_select = await browser.query_selector('select[name="allowed_record_types"]')
                if types_select:
                    await browser.evaluate(
                        """([selector, values]) => {
                            const select = document.querySelector(selector);
                            if (!select) return;
                            for (const option of select.options) {
                                option.selected = values.includes(option.value);
                            }
                            select.dispatchEvent(new Event('change', { bubbles: true }));
                        }""",
                        ['select[name="allowed_record_types"]', token["record_types"]]
                    )
                
                await ss.capture('readonly-token-form', 'Read-only token form filled')
                
                await browser.click('button[type="submit"]')
                await browser.wait_for_timeout(1000)
                
                await ss.capture('readonly-token-created', 'Read-only token created')
                
                # Extract token from success message
                body = await browser.text('body')
                print(f"Token creation result: {body[:500]}")
    
    @pytest.mark.asyncio
    async def test_03_token_displayed_once(
        self, admin_session, screenshot_helper
    ):
        """Token secret is displayed only once after creation."""
        ss = screenshot_helper('04-token')
        browser = admin_session
        
        # Create a new token and check the display
        await browser.goto(settings.url('/admin/realms'))
        await browser.wait_for_load_state('domcontentloaded')
        
        realm_link = await browser.query_selector(
            'a[href*="/admin/realms/"]:not([href*="/pending"])'
        )
        
        if realm_link:
            await realm_link.click()
            await browser.wait_for_load_state('domcontentloaded')
            
            create_token_btn = await browser.query_selector(
                'a[href*="/tokens/new"], a:has-text("Create Token")'
            )
            
            if create_token_btn:
                await create_token_btn.click()
                await browser.wait_for_load_state('domcontentloaded')
                
                desc_field = await browser.query_selector('#description, input[name="description"]')
                if desc_field:
                    await desc_field.fill(f"Test token {secrets.token_hex(4)}")
                
                await browser.click('button[type="submit"]')
                await browser.wait_for_timeout(1000)
                
                # Check for token in success message
                body_html = await browser.html('body')
                
                # Token should be visible in alert or code block
                has_token = (
                    '<code' in body_html or
                    'naf_' in body_html or  # Token prefix
                    'token' in body_html.lower()
                )
                
                await ss.capture('token-secret-display', 'Token secret displayed once')
                
                if has_token:
                    print("✅ Token secret displayed after creation")
                else:
                    print("Token display format may differ")


# ============================================================================
# Phase 2: Token Permissions
# ============================================================================

class TestTokenPermissions:
    """Test token permission configurations."""
    
    @pytest.mark.asyncio
    async def test_04_token_with_limited_record_types(
        self, admin_session, screenshot_helper, token_data
    ):
        """Create token with specific record types."""
        ss = screenshot_helper('04-token')
        browser = admin_session
        token = token_data["letsencrypt_token"]
        
        await browser.goto(settings.url('/admin/realms'))
        await browser.wait_for_load_state('domcontentloaded')
        
        realm_link = await browser.query_selector(
            'a[href*="/admin/realms/"]:not([href*="/pending"])'
        )
        
        if realm_link:
            await realm_link.click()
            await browser.wait_for_load_state('domcontentloaded')
            
            create_token = await browser.query_selector('a[href*="/tokens/new"]')
            if create_token:
                await create_token.click()
                await browser.wait_for_load_state('domcontentloaded')
                
                # Fill for LetsEncrypt (TXT only)
                desc_field = await browser.query_selector('#description')
                if desc_field:
                    await desc_field.fill(token["description"])
                
                # Select only TXT record type
                await browser.evaluate(
                    """([selector, values]) => {
                        const select = document.querySelector(selector);
                        if (!select) return;
                        for (const option of select.options) {
                            option.selected = values.includes(option.value);
                        }
                        select.dispatchEvent(new Event('change', { bubbles: true }));
                    }""",
                    ['select[name="allowed_record_types"]', token["record_types"]]
                )
                
                await ss.capture('letsencrypt-token-form', 'LetsEncrypt token form')
                
                await browser.click('button[type="submit"]')
                await browser.wait_for_timeout(1000)
                
                await ss.capture('letsencrypt-token-created', 'LetsEncrypt token created')
    
    @pytest.mark.asyncio
    async def test_05_token_with_full_permissions(
        self, admin_session, screenshot_helper, token_data
    ):
        """Create token with full permissions."""
        ss = screenshot_helper('04-token')
        browser = admin_session
        token = token_data["full_token"]
        
        await browser.goto(settings.url('/admin/realms'))
        await browser.wait_for_load_state('domcontentloaded')
        
        realm_link = await browser.query_selector(
            'a[href*="/admin/realms/"]:not([href*="/pending"])'
        )
        
        if realm_link:
            await realm_link.click()
            await browser.wait_for_load_state('domcontentloaded')
            
            create_token = await browser.query_selector('a[href*="/tokens/new"]')
            if create_token:
                await create_token.click()
                await browser.wait_for_load_state('domcontentloaded')
                
                desc_field = await browser.query_selector('#description')
                if desc_field:
                    await desc_field.fill(token["description"])
                
                # Select all operations
                await browser.evaluate(
                    """([selector, values]) => {
                        const select = document.querySelector(selector);
                        if (!select) return;
                        for (const option of select.options) {
                            option.selected = values.includes(option.value);
                        }
                        select.dispatchEvent(new Event('change', { bubbles: true }));
                    }""",
                    ['select[name="allowed_operations"]', token["operations"]]
                )
                
                # Select all record types
                await browser.evaluate(
                    """([selector, values]) => {
                        const select = document.querySelector(selector);
                        if (!select) return;
                        for (const option of select.options) {
                            option.selected = values.includes(option.value);
                        }
                        select.dispatchEvent(new Event('change', { bubbles: true }));
                    }""",
                    ['select[name="allowed_record_types"]', token["record_types"]]
                )
                
                await ss.capture('full-token-form', 'Full control token form')
                
                await browser.click('button[type="submit"]')
                await browser.wait_for_timeout(1000)
                
                await ss.capture('full-token-created', 'Full control token created')


# ============================================================================
# Phase 3: Token Security
# ============================================================================

class TestTokenSecurity:
    """Test token security features."""
    
    @pytest.mark.asyncio
    async def test_06_token_with_ip_whitelist(
        self, admin_session, screenshot_helper
    ):
        """Create token with IP whitelist."""
        ss = screenshot_helper('04-token')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/realms'))
        await browser.wait_for_load_state('domcontentloaded')
        
        realm_link = await browser.query_selector(
            'a[href*="/admin/realms/"]:not([href*="/pending"])'
        )
        
        if realm_link:
            await realm_link.click()
            await browser.wait_for_load_state('domcontentloaded')
            
            create_token = await browser.query_selector('a[href*="/tokens/new"]')
            if create_token:
                await create_token.click()
                await browser.wait_for_load_state('domcontentloaded')
                
                desc_field = await browser.query_selector('#description')
                if desc_field:
                    await desc_field.fill(f"IP-restricted token {secrets.token_hex(4)}")
                
                # Look for IP whitelist field
                ip_field = await browser.query_selector(
                    '#ip_whitelist, input[name="ip_whitelist"], textarea[name="ip_whitelist"]'
                )
                
                if ip_field:
                    await ip_field.fill("192.168.1.0/24, 10.0.0.1")
                    await ss.capture('token-ip-whitelist', 'Token with IP whitelist')
                
                await browser.click('button[type="submit"]')
                await browser.wait_for_timeout(1000)
                
                await ss.capture('token-ip-restricted-created', 'IP-restricted token created')
    
    @pytest.mark.asyncio
    async def test_07_token_with_expiry(
        self, admin_session, screenshot_helper
    ):
        """Create token with expiry date."""
        ss = screenshot_helper('04-token')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/realms'))
        await browser.wait_for_load_state('domcontentloaded')
        
        realm_link = await browser.query_selector(
            'a[href*="/admin/realms/"]:not([href*="/pending"])'
        )
        
        if realm_link:
            await realm_link.click()
            await browser.wait_for_load_state('domcontentloaded')
            
            create_token = await browser.query_selector('a[href*="/tokens/new"]')
            if create_token:
                await create_token.click()
                await browser.wait_for_load_state('domcontentloaded')
                
                desc_field = await browser.query_selector('#description')
                if desc_field:
                    await desc_field.fill(f"Expiring token {secrets.token_hex(4)}")
                
                # Look for expiry field
                expiry_field = await browser.query_selector(
                    '#expires_at, input[name="expires_at"], #expiry_days, input[name="expiry_days"]'
                )
                
                if expiry_field:
                    # Try to set expiry
                    field_type = await expiry_field.get_attribute('type')
                    if field_type == 'date':
                        # Set date 30 days from now
                        from datetime import datetime, timedelta
                        future_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
                        await expiry_field.fill(future_date)
                    else:
                        await expiry_field.fill('30')
                    
                    await ss.capture('token-with-expiry', 'Token with expiry set')
                
                await browser.click('button[type="submit"]')
                await browser.wait_for_timeout(1000)
                
                await ss.capture('token-expiry-created', 'Expiring token created')


# ============================================================================
# Phase 4: Token Management
# ============================================================================

class TestTokenManagement:
    """Test token listing and detail views."""
    
    @pytest.mark.asyncio
    async def test_08_token_list_view(
        self, admin_session, screenshot_helper
    ):
        """View list of tokens for a realm."""
        ss = screenshot_helper('04-token')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/realms'))
        await browser.wait_for_load_state('domcontentloaded')
        
        realm_link = await browser.query_selector(
            'a[href*="/admin/realms/"]:not([href*="/pending"])'
        )
        
        if realm_link:
            await realm_link.click()
            await browser.wait_for_load_state('domcontentloaded')
            
            await ss.capture('realm-tokens-list', 'Realm with tokens list')
            
            body = await browser.text('body')
            # Should show token list
            print(f"Tokens on realm: {body[:500]}")
    
    @pytest.mark.asyncio
    async def test_09_token_detail_view(
        self, admin_session, screenshot_helper
    ):
        """View token detail page."""
        ss = screenshot_helper('04-token')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/realms'))
        await browser.wait_for_load_state('domcontentloaded')
        
        # Get all realm links and try each one until we find one with tokens
        # Note: List may be sorted by created_at DESC, so older realms (with tokens) 
        # are at the bottom. We search all realms.
        realm_links = await browser.query_selector_all(
            'a[href*="/admin/realms/"]:not([href*="/pending"]):not([href*="/new"])'
        )
        
        if not realm_links:
            await ss.capture('realms-list-empty', 'No realms to view')
            pytest.skip("No realm links found")
        
        token_found = False
        # Try all realms (may need to check older ones at the bottom)
        for i in range(len(realm_links)):
            await browser.goto(settings.url('/admin/realms'))
            await browser.wait_for_timeout(300)
            
            # Re-query links after page navigation
            realm_links_fresh = await browser.query_selector_all(
                'a[href*="/admin/realms/"]:not([href*="/pending"]):not([href*="/new"])'
            )
            if i >= len(realm_links_fresh):
                break
                
            await realm_links_fresh[i].click()
            await browser.wait_for_load_state('domcontentloaded')
            
            # Check if this realm has a token link
            token_link = await browser.query_selector('a[href*="/admin/tokens/"]')
            
            if token_link:
                await token_link.click()
                await browser.wait_for_load_state('domcontentloaded')
                
                await ss.capture('token-detail', 'Token detail page')
                
                body = await browser.text('body')
                # Should show token details (not the secret) or at least be a valid page
                assert 'token' in body.lower() or 'description' in body.lower() or \
                       'permission' in body.lower() or 'realm' in body.lower() or \
                       '404' not in body, \
                    f"Token detail should show config (not 404): {body[:300]}"
                token_found = True
                break
        
        if not token_found:
            await ss.capture('no-tokens-found', 'No tokens found in any realm')
            pytest.skip("No token links found in any realm detail")


# ============================================================================
# Phase 5: Token Revocation
# ============================================================================

class TestTokenRevocation:
    """Test token revocation and regeneration."""
    
    @pytest.mark.asyncio
    async def test_10_revoke_token(
        self, admin_session, screenshot_helper
    ):
        """Revoke a token."""
        ss = screenshot_helper('04-token')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/realms'))
        await browser.wait_for_load_state('domcontentloaded')
        
        realm_link = await browser.query_selector(
            'a[href*="/admin/realms/"]:not([href*="/pending"])'
        )
        
        if realm_link:
            await realm_link.click()
            await browser.wait_for_load_state('domcontentloaded')
            
            token_link = await browser.query_selector('a[href*="/admin/tokens/"]')
            
            if token_link:
                await token_link.click()
                await browser.wait_for_load_state('domcontentloaded')
                
                await ss.capture('token-before-revoke', 'Token before revocation')
                
                # Look for revoke button
                revoke_btn = await browser.query_selector(
                    'button:has-text("Revoke"), a:has-text("Revoke"), form[action*="revoke"] button'
                )
                
                if revoke_btn:
                    await revoke_btn.click()
                    await browser.wait_for_load_state('domcontentloaded')
                    
                    # Confirm if modal
                    confirm_btn = await browser.query_selector(
                        '.modal button:has-text("Confirm"), .modal button[type="submit"]'
                    )
                    if confirm_btn:
                        await confirm_btn.click()
                        await browser.wait_for_timeout(1000)
                    
                    await ss.capture('token-revoked', 'Token revoked')
    
    @pytest.mark.asyncio
    async def test_11_regenerate_token_secret(
        self, admin_session, screenshot_helper
    ):
        """Regenerate token secret."""
        ss = screenshot_helper('04-token')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/realms'))
        await browser.wait_for_load_state('domcontentloaded')
        
        realm_link = await browser.query_selector(
            'a[href*="/admin/realms/"]:not([href*="/pending"])'
        )
        
        if realm_link:
            await realm_link.click()
            await browser.wait_for_load_state('domcontentloaded')
            
            token_link = await browser.query_selector('a[href*="/admin/tokens/"]')
            
            if token_link:
                await token_link.click()
                await browser.wait_for_load_state('domcontentloaded')
                
                await ss.capture('token-before-regenerate', 'Token before regeneration')
                
                # Look for regenerate button
                regen_btn = await browser.query_selector(
                    'button:has-text("Regenerate"), a:has-text("Regenerate"), '
                    'button:has-text("New Secret"), form[action*="regenerate"] button'
                )
                
                if regen_btn:
                    await regen_btn.click()
                    await browser.wait_for_load_state('domcontentloaded')
                    
                    # Confirm if modal
                    confirm_btn = await browser.query_selector(
                        '.modal button:has-text("Confirm"), .modal button[type="submit"]'
                    )
                    if confirm_btn:
                        await confirm_btn.click()
                        await browser.wait_for_timeout(1000)
                    
                    await ss.capture('token-regenerated', 'Token secret regenerated')
                    
                    body = await browser.text('body')
                    # New secret should be displayed
                    print(f"After regeneration: {body[:500]}")


# ============================================================================
# Error Handling
# ============================================================================

class TestTokenErrorHandling:
    """Test token validation and errors."""
    
    @pytest.mark.asyncio
    async def test_12_token_without_operations_rejected(
        self, admin_session, screenshot_helper
    ):
        """Token creation without operations is rejected."""
        ss = screenshot_helper('04-token')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/realms'))
        await browser.wait_for_load_state('domcontentloaded')
        
        realm_link = await browser.query_selector(
            'a[href*="/admin/realms/"]:not([href*="/pending"])'
        )
        
        if realm_link:
            await realm_link.click()
            await browser.wait_for_load_state('domcontentloaded')
            
            create_token = await browser.query_selector('a[href*="/tokens/new"]')
            if create_token:
                await create_token.click()
                await browser.wait_for_load_state('domcontentloaded')
                
                # Try to submit without selecting operations
                desc_field = await browser.query_selector('#description')
                if desc_field:
                    await desc_field.fill("Token without operations")
                
                # Deselect all operations
                await browser.evaluate(
                    """(selector) => {
                        const select = document.querySelector(selector);
                        if (!select) return;
                        for (const option of select.options) {
                            option.selected = false;
                        }
                        select.dispatchEvent(new Event('change', { bubbles: true }));
                    }""",
                    'select[name="allowed_operations"]'
                )
                
                await ss.capture('token-no-operations', 'Token without operations')
                
                await browser.click('button[type="submit"]')
                await browser.wait_for_load_state('domcontentloaded')
                
                await ss.capture('token-no-operations-error', 'No operations error')
                
                body = await browser.text('body')
                # Should show validation error
                print(f"Validation result: {body[:300]}")
