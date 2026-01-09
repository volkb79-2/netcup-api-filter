#!/usr/bin/env python3
"""
Test complete installation workflow (first-time setup).

This test simulates a fresh installation where admin must:
1. Login with default credentials
2. Change password and set email (forced on first login)
3. Verify SMTP configuration
4. Test 2FA login flow with email verification

This test should be run against a fresh deployment with default credentials.
"""
import os
import pytest
import time
import requests
import re
from playwright.sync_api import Page, expect


# Mailpit configuration (from tooling/mailpit/.env)
MAILPIT_URL = os.environ.get("MAILPIT_URL", "http://naf-dev-mailpit:8025")
MAILPIT_AUTH = (
    os.environ.get("MAILPIT_USERNAME", "admin"),
    os.environ.get("MAILPIT_PASSWORD", "MailpitDev123")
)


def get_2fa_code_from_mailpit(recipient_email: str) -> str | None:
    """Fetch the latest 2FA code from Mailpit API."""
    try:
        # Get messages
        response = requests.get(
            f"{MAILPIT_URL}/mailpit/api/v1/messages",
            auth=MAILPIT_AUTH,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        if not data.get('messages'):
            return None
        
        # Find latest 2FA message (look for subject containing "Verification Code")
        messages = data['messages']
        for msg in messages:
            if "Verification Code" in msg.get('Subject', ''):
                to_addrs = [addr['Address'] for addr in msg.get('To', [])]
                if recipient_email in to_addrs:
                    # Get full message
                    msg_response = requests.get(
                        f"{MAILPIT_URL}/mailpit/api/v1/message/{msg['ID']}",
                        auth=MAILPIT_AUTH,
                        timeout=10
                    )
                    msg_response.raise_for_status()
                    full_msg = msg_response.json()
                    
                    # Extract 6-digit code from text body
                    text_body = full_msg.get('Text', '')
                    match = re.search(r'\b(\d{6})\b', text_body)
                    if match:
                        return match.group(1)
        
        return None
        
    except Exception as e:
        print(f"Error fetching 2FA code from Mailpit: {e}")
        return None


@pytest.mark.installation
def test_installation_workflow(page: Page, base_url: str):
    """
    Test complete installation workflow from fresh deployment.
    
    Prerequisites:
    - Fresh deployment with default admin credentials
    - Mailpit running and configured
    - SMTP config pre-seeded in database
    """
    ADMIN_USER = "admin"
    ADMIN_PASSWORD = "admin"
    ADMIN_EMAIL = "admin@example.com"
    
    # Step 1: Login with default credentials
    page.goto(f"{base_url}/admin/login")
    page.fill("input[name='username']", ADMIN_USER)
    page.fill("input[name='password']", ADMIN_PASSWORD)
    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle")
    
    # Should redirect to initial setup (password change)
    expect(page).to_have_url(f"{base_url}/admin/change-password")
    expect(page.locator("h1")).to_contain_text("Initial Setup")
    
    # Step 2: Complete initial setup (password + email)
    # Check form fields
    page.wait_for_selector("input[name='email']")
    page.wait_for_selector("input[name='new_password']")
    page.wait_for_selector("input[name='confirm_password']")
    
    # Fill email
    page.fill("input[name='email']", ADMIN_EMAIL)
    
    # Use the generate button for strong password
    page.click("button:has-text('Generate')")
    page.wait_for_timeout(500)
    
    # Get the generated password for later use
    new_password = page.input_value("input[name='new_password']")
    assert len(new_password) >= 20, "Generated password should be at least 20 chars"
    
    # Wait for button to be enabled (form validation)
    submit_btn = page.locator("button[type='submit']")
    expect(submit_btn).to_be_enabled(timeout=3000)
    
    # Submit initial setup
    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle")
    
    # Should redirect to dashboard
    expect(page).to_have_url(f"{base_url}/admin/", timeout=10000)
    
    # Step 3: Verify SMTP configuration (should be pre-seeded)
    page.goto(f"{base_url}/admin/config/email")
    page.wait_for_load_state("networkidle")
    
    smtp_host = page.input_value("input[name='smtp_host']")
    assert "mailpit" in smtp_host.lower(), f"Expected mailpit in SMTP host, got: {smtp_host}"
    
    # Step 4: Verify email was set and 2FA enabled
    # Email should have been set during initial setup
    # 2FA should be automatically enabled when email is configured
    
    # Step 5: Test 2FA login flow
    # Logout
    page.goto(f"{base_url}/admin/logout")
    page.wait_for_load_state("networkidle")
    expect(page).to_have_url(f"{base_url}/admin/login")
    
    # Login again with new password
    page.fill("input[name='username']", ADMIN_USER)
    page.fill("input[name='password']", new_password)
    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle")
    
    # Should redirect to 2FA page
    expect(page).to_have_url(f"{base_url}/admin/login/2fa")
    expect(page.locator("h1")).to_contain_text("Verify")
    
    # Step 6: Fetch 2FA code from Mailpit and verify
    time.sleep(2)  # Wait for email to arrive
    code = get_2fa_code_from_mailpit(ADMIN_EMAIL)
    assert code is not None, "Should receive 2FA code via email"
    assert len(code) == 6, f"2FA code should be 6 digits, got: {code}"
    
    # Submit 2FA code
    page.fill("input[name='code']", code)
    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle")
    
    # Should be logged in and redirected to dashboard
    expect(page).to_have_url(f"{base_url}/admin/")
    expect(page.locator("h1")).to_contain_text("Dashboard")
    
    print(f"✅ Installation workflow completed successfully")
    print(f"   - Password changed and email configured")
    print(f"   - 2FA enabled automatically")
    print(f"   - 2FA login verified with code: {code}")
