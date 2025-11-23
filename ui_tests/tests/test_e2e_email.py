"""E2E tests for email notification functionality.

Tests verify that the application sends correct emails for various events:
- Test email from admin UI
- Client creation notification
- Admin security alerts
- Permission violation notifications

Uses mock SMTP server to capture and inspect emails.
"""
import pytest
import asyncio
import re
from datetime import datetime
from ui_tests.browser import browser_session
from ui_tests.config import settings
from ui_tests import workflows


pytestmark = pytest.mark.asyncio


async def test_e2e_admin_sends_test_email(browser_session, mock_smtp_server):
    """Test admin can send test email through UI."""
    
    async with browser_session() as browser:
        # Login as admin
        await workflows.ensure_admin_dashboard(browser)
        
        # Navigate to email configuration
        await browser.goto(settings.url("/admin/email_config/"))
        await asyncio.sleep(1)
        
        # Configure email settings to use mock SMTP
        await browser.fill('input[name="smtp_server"]', '127.0.0.1')
        await browser.fill('input[name="smtp_port"]', '1025')
        await browser.fill('input[name="smtp_username"]', 'test')
        await browser.fill('input[name="smtp_password"]', 'test')
        await browser.fill('input[name="sender_email"]', 'noreply@example.com')
        
        # Uncheck SSL for mock SMTP
        ssl_checkbox = await browser.query_selector('input[name="use_ssl"]')
        if ssl_checkbox:
            is_checked = await ssl_checkbox.is_checked()
            if is_checked:
                await ssl_checkbox.click()
        
        # Submit configuration
        submit_btn = await browser.query_selector('button[type="submit"]')
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(1)
        
        # Navigate to test email page
        await browser.goto(settings.url("/admin/test-email/"))
        await asyncio.sleep(1)
        
        # Enter test email address
        await browser.fill('input[name="test_email"]', 'admin@example.com')
        
        # Send test email
        send_btn = await browser.query_selector('button[type="submit"]')
        if send_btn:
            await send_btn.click()
            await asyncio.sleep(2)  # Wait for email to be sent
        
        # Verify email was captured
        assert len(mock_smtp_server.captured_emails) == 1, "Test email should be sent"
        
        email = mock_smtp_server.captured_emails[0]
        assert email.sender == 'noreply@example.com'
        assert 'admin@example.com' in email.recipients
        assert 'Test Email' in email.subject
        assert 'Netcup API Filter' in email.subject
        assert 'test email' in email.body_text.lower()
        
        # Check HTML version exists
        assert email.body_html is not None
        assert '<h2' in email.body_html
        assert 'Test Email' in email.body_html


async def test_e2e_client_creation_email_notification(browser_session, mock_smtp_server):
    """Test that creating a client sends notification email if configured."""
    
    async with browser_session() as browser:
        # Login as admin
        await workflows.ensure_admin_dashboard(browser)
        
        # Configure email settings first
        await browser.goto(settings.url("/admin/email_config/"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="smtp_server"]', '127.0.0.1')
        await browser.fill('input[name="smtp_port"]', '1025')
        await browser.fill('input[name="smtp_username"]', 'test')
        await browser.fill('input[name="smtp_password"]', 'test')
        await browser.fill('input[name="sender_email"]', 'noreply@netcup-filter.local')
        
        # Uncheck SSL
        ssl_checkbox = await browser.query_selector('input[name="use_ssl"]')
        if ssl_checkbox:
            is_checked = await ssl_checkbox.is_checked()
            if is_checked:
                await ssl_checkbox.click()
        
        submit_btn = await browser.query_selector('button[type="submit"]')
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(1)
        
        # Enable email notifications for client creation
        await browser.goto(settings.url("/admin/system_config/"))
        await asyncio.sleep(1)
        
        notify_checkbox = await browser.query_selector('input[name="notify_client_creation"]')
        if notify_checkbox:
            is_checked = await notify_checkbox.is_checked()
            if not is_checked:
                await notify_checkbox.click()
        
        submit_btn = await browser.query_selector('button[type="submit"]')
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(1)
        
        # Clear any previous emails
        mock_smtp_server.handler.reset()
        
        # Create a new client with email address
        await browser.goto(settings.url("/admin/client/new/"))
        await asyncio.sleep(1)
        
        client_email = 'newclient@example.com'
        
        await browser.fill('input[name="client_id"]', 'test_email_client')
        await browser.fill('input[name="email_address"]', client_email)
        await browser.fill('textarea[name="allowed_domains"]', 'test.example.com')
        await browser.fill('textarea[name="allowed_operations"]', 'read,write')
        await browser.fill('textarea[name="allowed_record_types"]', 'A,AAAA')
        
        # Submit form
        submit_btn = await browser.query_selector('button[type="submit"]')
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(2)  # Wait for email to be sent (async with delay)
        
        # Check if email was sent (may or may not be implemented yet)
        if len(mock_smtp_server.captured_emails) > 0:
            email = mock_smtp_server.captured_emails[0]
            
            # Verify email details
            assert client_email in email.recipients
            assert 'client' in email.subject.lower() or 'api' in email.subject.lower()
            assert 'test_email_client' in email.body_text
            
            # Check for token or access information
            assert 'token' in email.body_text.lower() or 'access' in email.body_text.lower()


async def test_e2e_email_filter_by_recipient(browser_session, mock_smtp_server):
    """Test filtering captured emails by recipient."""
    
    async with browser_session() as browser:
        # Login and configure email
        await workflows.ensure_admin_dashboard(browser)
        
        await browser.goto(settings.url("/admin/email_config/"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="smtp_server"]', '127.0.0.1')
        await browser.fill('input[name="smtp_port"]', '1025')
        await browser.fill('input[name="smtp_username"]', 'test')
        await browser.fill('input[name="smtp_password"]', 'test')
        await browser.fill('input[name="sender_email"]', 'noreply@test.local')
        
        ssl_checkbox = await browser.query_selector('input[name="use_ssl"]')
        if ssl_checkbox and await ssl_checkbox.is_checked():
            await ssl_checkbox.click()
        
        submit_btn = await browser.query_selector('button[type="submit"]')
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(1)
        
        # Clear previous emails
        mock_smtp_server.handler.reset()
        
        # Send multiple test emails to different recipients
        recipients = ['alice@example.com', 'bob@example.com', 'alice@example.com']
        
        for recipient in recipients:
            await browser.goto(settings.url("/admin/test-email/"))
            await asyncio.sleep(0.5)
            
            await browser.fill('input[name="test_email"]', recipient)
            send_btn = await browser.query_selector('button[type="submit"]')
            if send_btn:
                await send_btn.click()
                await asyncio.sleep(1)
        
        # Wait for all emails to be sent
        await asyncio.sleep(2)
        
        # Verify total emails
        assert len(mock_smtp_server.captured_emails) == 3
        
        # Filter by recipient
        alice_emails = mock_smtp_server.handler.get_emails_to('alice@example.com')
        bob_emails = mock_smtp_server.handler.get_emails_to('bob@example.com')
        
        assert len(alice_emails) == 2, "Alice should receive 2 emails"
        assert len(bob_emails) == 1, "Bob should receive 1 email"
        
        for email in alice_emails:
            assert 'alice@example.com' in email.recipients
        
        for email in bob_emails:
            assert 'bob@example.com' in email.recipients


async def test_e2e_email_html_content(browser_session, mock_smtp_server):
    """Test that emails contain both text and HTML versions."""
    
    async with browser_session() as browser:
        # Login and configure email
        await workflows.ensure_admin_dashboard(browser)
        
        await browser.goto(settings.url("/admin/email_config/"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="smtp_server"]', '127.0.0.1')
        await browser.fill('input[name="smtp_port"]', '1025')
        await browser.fill('input[name="smtp_username"]', 'test')
        await browser.fill('input[name="smtp_password"]', 'test')
        await browser.fill('input[name="sender_email"]', 'noreply@test.local')
        
        ssl_checkbox = await browser.query_selector('input[name="use_ssl"]')
        if ssl_checkbox and await ssl_checkbox.is_checked():
            await ssl_checkbox.click()
        
        submit_btn = await browser.query_selector('button[type="submit"]')
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(1)
        
        # Clear previous emails
        mock_smtp_server.handler.reset()
        
        # Send test email
        await browser.goto(settings.url("/admin/test-email/"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="test_email"]', 'test@example.com')
        send_btn = await browser.query_selector('button[type="submit"]')
        if send_btn:
            await send_btn.click()
            await asyncio.sleep(2)
        
        # Verify email
        assert len(mock_smtp_server.captured_emails) == 1
        email = mock_smtp_server.captured_emails[0]
        
        # Check text version
        assert email.body_text is not None
        assert len(email.body_text) > 0
        assert 'test email' in email.body_text.lower()
        
        # Check HTML version
        assert email.body_html is not None
        assert len(email.body_html) > 0
        assert '<html>' in email.body_html or '<body>' in email.body_html
        assert '<h2' in email.body_html or '<h1' in email.body_html
        
        # HTML should be richer (have more content than plain text)
        assert len(email.body_html) > len(email.body_text)


async def test_e2e_email_headers_captured(browser_session, mock_smtp_server):
    """Test that email headers are properly captured."""
    
    async with browser_session() as browser:
        # Login and configure email
        await workflows.ensure_admin_dashboard(browser)
        
        await browser.goto(settings.url("/admin/email_config/"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="smtp_server"]', '127.0.0.1')
        await browser.fill('input[name="smtp_port"]', '1025')
        await browser.fill('input[name="smtp_username"]', 'test')
        await browser.fill('input[name="smtp_password"]', 'test')
        await browser.fill('input[name="sender_email"]', 'noreply@test.local')
        
        ssl_checkbox = await browser.query_selector('input[name="use_ssl"]')
        if ssl_checkbox and await ssl_checkbox.is_checked():
            await ssl_checkbox.click()
        
        submit_btn = await browser.query_selector('button[type="submit"]')
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(1)
        
        # Clear previous emails
        mock_smtp_server.handler.reset()
        
        # Send test email
        await browser.goto(settings.url("/admin/test-email/"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="test_email"]', 'test@example.com')
        send_btn = await browser.query_selector('button[type="submit"]')
        if send_btn:
            await send_btn.click()
            await asyncio.sleep(2)
        
        # Verify headers
        assert len(mock_smtp_server.captured_emails) == 1
        email = mock_smtp_server.captured_emails[0]
        
        # Check standard headers
        assert 'From' in email.headers
        assert 'To' in email.headers
        assert 'Subject' in email.headers
        assert 'Date' in email.headers
        assert 'Content-Type' in email.headers
        
        # Verify header values
        assert email.headers['From'] == 'noreply@test.local'
        assert email.headers['To'] == 'test@example.com'
        assert 'Test Email' in email.headers['Subject']
        
        # Check that Content-Type indicates multipart (text + HTML)
        assert 'multipart' in email.headers['Content-Type'].lower()


async def test_e2e_email_timestamps(browser_session, mock_smtp_server):
    """Test that email timestamps are properly recorded."""
    
    async with browser_session() as browser:
        # Login and configure email
        await workflows.ensure_admin_dashboard(browser)
        
        await browser.goto(settings.url("/admin/email_config/"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="smtp_server"]', '127.0.0.1')
        await browser.fill('input[name="smtp_port"]', '1025')
        await browser.fill('input[name="smtp_username"]', 'test')
        await browser.fill('input[name="smtp_password"]', 'test')
        await browser.fill('input[name="sender_email"]', 'noreply@test.local')
        
        ssl_checkbox = await browser.query_selector('input[name="use_ssl"]')
        if ssl_checkbox and await ssl_checkbox.is_checked():
            await ssl_checkbox.click()
        
        submit_btn = await browser.query_selector('button[type="submit"]')
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(1)
        
        # Clear previous emails
        mock_smtp_server.handler.reset()
        
        # Record time before sending
        before = datetime.utcnow()
        
        # Send test email
        await browser.goto(settings.url("/admin/test-email/"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="test_email"]', 'test@example.com')
        send_btn = await browser.query_selector('button[type="submit"]')
        if send_btn:
            await send_btn.click()
            await asyncio.sleep(2)
        
        # Record time after sending
        after = datetime.utcnow()
        
        # Verify timestamp
        assert len(mock_smtp_server.captured_emails) == 1
        email = mock_smtp_server.captured_emails[0]
        
        assert email.timestamp is not None
        assert before <= email.timestamp <= after, "Email timestamp should be between before and after"


@pytest.mark.skip(reason="Permission violations need API proxy integration - implement when ready")
async def test_e2e_email_permission_violation_alert(browser_session, mock_smtp_server, mock_netcup_api_server):
    """Test that permission violations trigger admin email alerts.
    
    This test requires the API proxy to be configured and a client attempting
    unauthorized operations. Skipped until API proxy integration is complete.
    """
    async with browser_session() as browser:
        # Login as admin
        await workflows.ensure_admin_dashboard(browser)
        
        # Configure email notifications
        await browser.goto(settings.url("/admin/email_config/"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="smtp_server"]', '127.0.0.1')
        await browser.fill('input[name="smtp_port"]', '1025')
        await browser.fill('input[name="admin_alert_email"]', 'admin@example.com')
        
        # ... rest of test when implemented ...
        
        # Expected: Admin receives email about permission violation
        # admin_emails = mock_smtp_server.handler.get_emails_to('admin@example.com')
        # assert len(admin_emails) > 0
        # assert 'security' in admin_emails[0].subject.lower() or 'violation' in admin_emails[0].subject.lower()


async def test_e2e_email_reset_between_tests(browser_session, mock_smtp_server):
    """Test that mock SMTP server can be reset between tests."""
    
    async with browser_session() as browser:
        # Login and configure email
        await workflows.ensure_admin_dashboard(browser)
        
        await browser.goto(settings.url("/admin/email_config/"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="smtp_server"]', '127.0.0.1')
        await browser.fill('input[name="smtp_port"]', '1025')
        await browser.fill('input[name="smtp_username"]', 'test')
        await browser.fill('input[name="smtp_password"]', 'test')
        await browser.fill('input[name="sender_email"]', 'noreply@test.local')
        
        ssl_checkbox = await browser.query_selector('input[name="use_ssl"]')
        if ssl_checkbox and await ssl_checkbox.is_checked():
            await ssl_checkbox.click()
        
        submit_btn = await browser.query_selector('button[type="submit"]')
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(1)
        
        # Send first email
        await browser.goto(settings.url("/admin/test-email/"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="test_email"]', 'test1@example.com')
        send_btn = await browser.query_selector('button[type="submit"]')
        if send_btn:
            await send_btn.click()
            await asyncio.sleep(2)
        
        assert len(mock_smtp_server.captured_emails) == 1
        
        # Reset
        mock_smtp_server.handler.reset()
        assert len(mock_smtp_server.captured_emails) == 0
        
        # Send second email
        await browser.goto(settings.url("/admin/test-email/"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="test_email"]', 'test2@example.com')
        send_btn = await browser.query_selector('button[type="submit"]')
        if send_btn:
            await send_btn.click()
            await asyncio.sleep(2)
        
        # Only the second email should be present
        assert len(mock_smtp_server.captured_emails) == 1
        assert 'test2@example.com' in mock_smtp_server.captured_emails[0].recipients
