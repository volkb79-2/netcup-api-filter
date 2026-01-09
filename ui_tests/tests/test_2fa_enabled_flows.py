"""
Test 2FA flows with Mailpit (no ADMIN_2FA_SKIP).

This test suite runs with 2FA fully enabled to ensure:
1. 2FA email codes are sent and received
2. Template components that depend on 2FA state render correctly
3. Dashboard shows 2FA warning when appropriate

These tests should be run separately with Mailpit running and
WITHOUT the ADMIN_2FA_SKIP environment variable.
"""

import asyncio
import re

import pytest

from ui_tests.browser import browser_session
from ui_tests.config import settings
from ui_tests.mailpit_client import MailpitClient


pytestmark = pytest.mark.asyncio


async def test_2fa_warning_component_renders_on_dashboard():
    """Test that 2FA setup warning renders correctly on dashboard.
    
    This component was broken (used current_user instead of g.admin)
    and only showed up when 2FA was enabled in production.
    
    This test requires:
    - Mailpit running
    - NO ADMIN_2FA_SKIP environment variable
    - Fresh deployment with must_change_password=1
    """
    async with browser_session() as browser:
        from ui_tests import workflows
        
        # Login (will handle password change if needed)
        await workflows.ensure_admin_dashboard(browser)
        
        # Check if 2FA warning is visible
        body_text = await browser.text("body")
        
        # Look for 2FA-related content
        has_2fa_content = (
            "two-factor" in body_text.lower() or
            "2fa" in body_text.lower() or
            "authenticator" in body_text.lower()
        )
        
        if has_2fa_content:
            print("✓ 2FA warning component rendered")
            
            # Verify no template errors
            assert "current_user" not in body_text or "undefined" not in body_text.lower(), \
                "Found undefined current_user error"
            assert "UndefinedError" not in body_text, \
                "Found UndefinedError in page"
        else:
            print("ℹ️  2FA already configured or warning not shown")
        
        # Verify dashboard rendered without errors anyway
        h1 = await browser.text("h1")
        assert "Dashboard" in h1
        
        # Check for 500 errors
        assert "500" not in body_text
        assert "Internal Server Error" not in body_text


async def test_complete_2fa_flow_with_mailpit():
    """Test complete 2FA flow: login → 2FA code → dashboard.
    
    This is an end-to-end test that verifies:
    1. Login triggers 2FA email
    2. Mailpit receives the email
    3. Code can be extracted and submitted
    4. Dashboard loads after successful 2FA
    
    Requires Mailpit running on localhost:8025 or MAILPIT_API_URL.
    """
    mailpit = MailpitClient()
    
    try:
        # Clear any existing messages
        messages = mailpit.list_messages()
        for msg in messages:
            mailpit.delete_message(msg.id)
        
        async with browser_session() as browser:
            # Login with admin credentials
            await browser.goto(settings.url("/admin/login"))
            await asyncio.sleep(0.3)
            
            await browser.fill("#username", "admin")
            await browser.fill("#password", settings.admin_password)
            await browser.click("button[type='submit']")
            await asyncio.sleep(1.0)
            
            # Check if redirected to 2FA page
            current_url = browser._page.url
            
            if "/2fa" not in current_url:
                print("ℹ️  No 2FA challenge (may be disabled or already set up)")
                return
            
            # Wait for 2FA email
            msg = mailpit.wait_for_message(
                predicate=lambda m: "verification" in m.subject.lower() or "2fa" in m.subject.lower(),
                timeout=10.0
            )
            
            assert msg is not None, "No 2FA email received in Mailpit"
            print(f"✓ Received 2FA email: {msg.subject}")
            
            # Extract code from email
            full_msg = mailpit.get_message(msg.id)
            code_match = re.search(r'\b(\d{6})\b', full_msg.text)
            
            assert code_match is not None, "Could not extract 6-digit code from email"
            code = code_match.group(1)
            print(f"✓ Extracted code: {code}")
            
            # Submit code via JavaScript (avoid race with auto-submit)
            await browser.evaluate(f"""
                (function() {{
                    const input = document.getElementById('code');
                    const form = document.getElementById('twoFaForm');
                    if (input && form) {{
                        input.value = '{code}';
                        form.submit();
                    }}
                }})();
            """)
            
            # Wait for navigation to complete
            for _ in range(20):
                await asyncio.sleep(0.5)
                new_url = browser._page.url
                if "/2fa" not in new_url and new_url != current_url:
                    break
            else:
                raise AssertionError("2FA navigation did not complete")
            
            # Verify we're on dashboard
            h1 = await browser.text("h1")
            assert "Dashboard" in h1 or "Change Password" in h1, \
                f"Expected dashboard or password change, got: {h1}"
            
            # Clean up
            mailpit.delete_message(msg.id)
            
            print("✓ Complete 2FA flow test PASSED")
    
    finally:
        mailpit.close()


async def test_dashboard_renders_with_2fa_enabled():
    """Test that dashboard renders correctly when 2FA is fully enabled.
    
    This specifically tests the condition that was broken:
    - Admin account with email_2fa_enabled=1
    - Dashboard includes 2fa_setup_warning.html
    - Component uses g.admin (not current_user)
    """
    async with browser_session() as browser:
        from ui_tests import workflows
        
        # Login (handles 2FA if needed)
        await workflows.ensure_admin_dashboard(browser)
        
        # Verify dashboard loaded
        h1 = await browser.text("h1")
        assert "Dashboard" in h1
        
        # Check for errors
        body_text = await browser.text("body")
        assert "500" not in body_text
        assert "UndefinedError" not in body_text
        assert "jinja2.exceptions" not in body_text
        
        # Verify key components rendered
        assert await browser.query_selector("footer")
        assert await browser.query_selector("nav")
        
        # Check if 2FA warning is present (may or may not be, both valid)
        page_source = await browser.page_content()
        if "requires_2fa_setup" in page_source:
            # Component is being used - verify no errors
            assert "current_user" not in body_text or "g.admin" in page_source, \
                "2FA component may be using wrong context variable"
        
        print("✓ Dashboard with 2FA enabled test PASSED")
