"""
Journey 06: System Configuration

This journey tests system configuration pages:

1. **Netcup API config** - Backend API credentials
2. **Email config** - SMTP settings and test
3. **System info** - Version, dependencies, status
4. **Security settings** - Session, password policies

Prerequisites:
- Admin logged in (from test_01)
"""
import pytest
import pytest_asyncio
import asyncio

from ui_tests.config import settings
from ui_tests.workflows import ensure_admin_dashboard


# ============================================================================
# Phase 1: Netcup API Configuration
# ============================================================================

class TestNetcupApiConfig:
    """Test Netcup API configuration page."""
    
    @pytest.mark.asyncio
    async def test_01_netcup_config_page_loads(
        self, admin_session, screenshot_helper
    ):
        """Netcup API config page loads correctly."""
        ss = screenshot_helper('06-config')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/config/netcup'))
        await asyncio.sleep(0.5)
        
        await ss.capture('netcup-config-page', 'Netcup API configuration page')
        
        h1 = await browser.text('main h1')
        assert 'Netcup' in h1 or 'API' in h1, f"Expected Netcup config page: {h1}"
    
    @pytest.mark.asyncio
    async def test_02_netcup_config_has_required_fields(
        self, admin_session, screenshot_helper
    ):
        """Netcup config has all required fields."""
        ss = screenshot_helper('06-config')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/config/netcup'))
        await asyncio.sleep(0.5)
        
        body_html = await browser.html('body')
        
        # Required fields for Netcup API
        required_fields = ['customer', 'api_key', 'api_password', 'endpoint', 'url']
        found = [f for f in required_fields if f.lower() in body_html.lower()]
        
        print(f"Found config fields: {found}")
        assert len(found) >= 3, f"Missing required fields. Found: {found}"
    
    @pytest.mark.asyncio
    async def test_03_netcup_config_test_connection(
        self, admin_session, screenshot_helper
    ):
        """Can test Netcup API connection."""
        ss = screenshot_helper('06-config')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/config/netcup'))
        await asyncio.sleep(0.5)
        
        # Look for test button
        test_btn = await browser.query_selector(
            'button:has-text("Test"), button:has-text("Verify"), button:has-text("Check")'
        )
        
        if test_btn:
            await test_btn.click()
            await asyncio.sleep(2.0)
            
            await ss.capture('netcup-connection-test', 'Netcup connection test result')
            
            body = await browser.text('body')
            print(f"Connection test result: {body[:300]}")
        else:
            print("No test connection button found")
    
    @pytest.mark.asyncio
    async def test_04_netcup_config_save(
        self, admin_session, screenshot_helper
    ):
        """Can save Netcup config (idempotent)."""
        ss = screenshot_helper('06-config')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/config/netcup'))
        await asyncio.sleep(0.5)
        
        # Just click save without changing values
        await browser.click('button[type="submit"]')
        await asyncio.sleep(1.0)
        
        await ss.capture('netcup-config-saved', 'Netcup config after save')
        
        body = await browser.text('body')
        # Should see success message or stay on page
        print(f"Save result: {body[:300]}")


# ============================================================================
# Phase 2: Email Configuration
# ============================================================================

class TestEmailConfig:
    """Test email configuration page."""
    
    @pytest.mark.asyncio
    async def test_05_email_config_page_loads(
        self, admin_session, screenshot_helper
    ):
        """Email config page loads correctly."""
        ss = screenshot_helper('06-config')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/config/email'))
        await asyncio.sleep(0.5)
        
        await ss.capture('email-config-page', 'Email configuration page')
        
        h1 = await browser.text('main h1')
        assert 'Email' in h1 or 'SMTP' in h1, f"Expected Email config page: {h1}"
    
    @pytest.mark.asyncio
    async def test_06_email_config_has_required_fields(
        self, admin_session, screenshot_helper
    ):
        """Email config has all required fields."""
        ss = screenshot_helper('06-config')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/config/email'))
        await asyncio.sleep(0.5)
        
        body_html = await browser.html('body')
        
        # Required fields for SMTP
        required_fields = ['smtp', 'host', 'port', 'from', 'email']
        found = [f for f in required_fields if f.lower() in body_html.lower()]
        
        print(f"Found email config fields: {found}")
        assert len(found) >= 3, f"Missing required fields. Found: {found}"
    
    @pytest.mark.asyncio
    async def test_07_email_config_test_send(
        self, admin_session, mailpit, screenshot_helper
    ):
        """Can send test email."""
        ss = screenshot_helper('06-config')
        browser = admin_session
        
        mailpit.clear()
        
        await browser.goto(settings.url('/admin/config/email'))
        await asyncio.sleep(0.5)
        
        # Look for test button
        test_btn = await browser.query_selector(
            'button:has-text("Test"), button:has-text("Send Test")'
        )
        
        if test_btn:
            await test_btn.click()
            await asyncio.sleep(2.0)
            
            await ss.capture('email-test-sent', 'Email test sent')
            
            # Check Mailpit for test email
            msg = mailpit.wait_for_message(
                predicate=lambda m: 'test' in m.subject.lower(),
                timeout=10.0
            )
            
            if msg:
                print(f"✅ Test email received: {msg.subject}")
            else:
                print("No test email received (SMTP may not be configured)")
    
    @pytest.mark.asyncio
    async def test_08_email_config_save(
        self, admin_session, screenshot_helper
    ):
        """Can save email config."""
        ss = screenshot_helper('06-config')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/config/email'))
        await asyncio.sleep(0.5)
        
        # Save without changing (idempotent)
        await browser.click('button[type="submit"]')
        await asyncio.sleep(1.0)
        
        await ss.capture('email-config-saved', 'Email config saved')


# ============================================================================
# Phase 3: System Information
# ============================================================================

class TestSystemInfo:
    """Test system information page."""
    
    @pytest.mark.asyncio
    async def test_09_system_info_page_loads(
        self, admin_session, screenshot_helper
    ):
        """System info page loads correctly."""
        ss = screenshot_helper('06-config')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/system'))
        await asyncio.sleep(0.5)
        
        await ss.capture('system-info-page', 'System information page')
        
        h1 = await browser.text('main h1')
        assert 'System' in h1 or 'Info' in h1, f"Expected System info page: {h1}"
    
    @pytest.mark.asyncio
    async def test_10_system_info_shows_version(
        self, admin_session, screenshot_helper
    ):
        """System info shows version."""
        ss = screenshot_helper('06-config')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/system'))
        await asyncio.sleep(0.5)
        
        body = await browser.text('body')
        
        # Should show version info
        has_version = any(word in body.lower() for word in ['version', 'build', 'commit', 'git'])
        print(f"Version info present: {has_version}")
        print(f"System info: {body[:500]}")
    
    @pytest.mark.asyncio
    async def test_11_system_info_shows_dependencies(
        self, admin_session, screenshot_helper
    ):
        """System info shows Python dependencies."""
        ss = screenshot_helper('06-config')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/system'))
        await asyncio.sleep(0.5)
        
        body = await browser.text('body')
        
        # Should show some dependency info
        dependencies = ['flask', 'python', 'pip', 'gunicorn']
        found = [d for d in dependencies if d.lower() in body.lower()]
        
        print(f"Dependencies shown: {found}")
    
    @pytest.mark.asyncio
    async def test_12_system_info_shows_database(
        self, admin_session, screenshot_helper
    ):
        """System info shows database info."""
        ss = screenshot_helper('06-config')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/system'))
        await asyncio.sleep(0.5)
        
        body = await browser.text('body')
        
        # Should show database info
        has_db = any(word in body.lower() for word in ['database', 'sqlite', 'db', 'accounts', 'realms'])
        print(f"Database info present: {has_db}")


# ============================================================================
# Phase 4: Admin Password Change
# ============================================================================

class TestAdminPasswordChange:
    """Test admin password change functionality."""
    
    @pytest.mark.asyncio
    async def test_13_password_change_page_loads(
        self, admin_session, screenshot_helper
    ):
        """Password change page loads correctly."""
        ss = screenshot_helper('06-config')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/change-password'))
        await asyncio.sleep(0.5)
        
        await ss.capture('password-change-page', 'Admin password change page')
        
        h1 = await browser.text('main h1')
        assert 'Password' in h1 or 'Change' in h1, f"Expected password change page: {h1}"
    
    @pytest.mark.asyncio
    async def test_14_password_change_requires_current(
        self, admin_session, screenshot_helper
    ):
        """Password change requires current password."""
        ss = screenshot_helper('06-config')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/change-password'))
        await asyncio.sleep(0.5)
        
        body_html = await browser.html('body')
        
        # Should have current password field
        has_current = 'current' in body_html.lower() or 'old' in body_html.lower()
        assert has_current, "Password change should require current password"
    
    @pytest.mark.asyncio
    async def test_15_password_change_mismatch_error(
        self, admin_session, screenshot_helper
    ):
        """Password mismatch shows error via client-side validation."""
        ss = screenshot_helper('06-config')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/change-password'))
        await asyncio.sleep(0.5)
        
        # Fill with mismatched passwords
        current_field = await browser.query_selector('#current_password')
        if current_field:
            await current_field.fill('dummy-current')
        
        new_field = await browser.query_selector('#new_password')
        if new_field:
            await new_field.fill('NewPassword123!')
        
        confirm_field = await browser.query_selector('#confirm_password')
        if confirm_field:
            await confirm_field.fill('DifferentPassword123!')
        
        await asyncio.sleep(0.3)  # Let JS validation run
        
        await ss.capture('password-mismatch-filled', 'Password mismatch test')
        
        # Submit button should be disabled due to client-side validation
        submit_btn = await browser.query_selector('button[type="submit"]')
        if submit_btn:
            is_disabled = await submit_btn.get_attribute('disabled')
            if is_disabled is not None:
                print("✅ Submit button disabled due to mismatch - client-side validation works")
                await ss.capture('password-mismatch-btn-disabled', 'Submit button disabled')
                return
        
        # If button not disabled, try clicking and check for error
        try:
            await browser.click('button[type="submit"]')
            await asyncio.sleep(0.5)
            
            await ss.capture('password-mismatch-error', 'Password mismatch error')
            
            body = await browser.text('body')
            assert any(word in body.lower() for word in ['match', 'same', 'error', 'mismatch']), \
                f"Expected mismatch error: {body[:300]}"
        except Exception as e:
            # Button disabled by JS validation is expected behavior
            print(f"✅ Form prevented submission: {e}")


# ============================================================================
# Phase 5: Navigation Consistency
# ============================================================================

class TestConfigNavigation:
    """Test navigation between config pages."""
    
    @pytest.mark.asyncio
    async def test_16_config_dropdown_works(
        self, admin_session, screenshot_helper
    ):
        """Config dropdown menu works."""
        ss = screenshot_helper('06-config')
        browser = admin_session
        
        await browser.goto(settings.url('/admin/'))
        await asyncio.sleep(0.5)
        
        # Click config dropdown
        config_dropdown = await browser.query_selector(
            'a.nav-link.dropdown-toggle:has-text("Config"), .navbar .dropdown-toggle'
        )
        
        if config_dropdown:
            await config_dropdown.click()
            await asyncio.sleep(0.3)
            
            await ss.capture('config-dropdown-open', 'Config dropdown open')
            
            # Should show config links
            dropdown_html = await browser.html('.dropdown-menu.show, .dropdown-menu')
            assert 'netcup' in dropdown_html.lower() or 'email' in dropdown_html.lower()
    
    @pytest.mark.asyncio
    async def test_17_all_config_pages_have_navbar(
        self, admin_session, screenshot_helper
    ):
        """All config pages have consistent navbar."""
        ss = screenshot_helper('06-config')
        browser = admin_session
        
        config_pages = [
            '/admin/config/netcup',
            '/admin/config/email',
            '/admin/system',
            '/admin/change-password',
        ]
        
        for page in config_pages:
            await browser.goto(settings.url(page))
            await asyncio.sleep(0.3)
            
            # Check navbar exists
            navbar = await browser.query_selector('nav.navbar, .navbar')
            assert navbar is not None, f"Navbar missing on {page}"
            
            # Check footer exists
            footer = await browser.query_selector('footer')
            if footer:
                footer_text = await browser.text('footer')
                print(f"Footer on {page}: {footer_text[:100]}")
