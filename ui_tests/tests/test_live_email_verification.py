"""
Live Email Verification Tests

These tests verify that emails sent by the application are actually
delivered and can be read via IMAP. This provides end-to-end verification
that the email infrastructure is working correctly.

Prerequisites:
- IMAP credentials configured in .env (IMAP_HOST, IMAP_USER, IMAP_PASSWORD, etc.)
- SMTP configured in the application (via admin UI or config)
- A test email account that can receive emails

Usage:
    pytest ui_tests/tests/test_live_email_verification.py -v --mode live

Note: These tests only run in live mode (--mode live) as they require
real email infrastructure.
"""
import imaplib
import email
import os
import time
import logging
import re
from datetime import datetime, timedelta
from email.header import decode_header
from typing import Optional, Tuple, List

import pytest

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

def get_imap_config() -> dict:
    """Get IMAP configuration from environment variables."""
    return {
        'host': os.environ.get('IMAP_HOST', ''),
        'port': int(os.environ.get('IMAP_PORT', '993')),
        'user': os.environ.get('IMAP_USER', ''),
        'password': os.environ.get('IMAP_PASSWORD', ''),
        'use_tls': os.environ.get('IMAP_USE_TLS', 'true').lower() == 'true',
        'mailbox': os.environ.get('IMAP_MAILBOX', 'INBOX'),
        'timeout': int(os.environ.get('IMAP_TIMEOUT', '30')),
    }


def is_imap_configured() -> bool:
    """Check if IMAP is properly configured."""
    config = get_imap_config()
    return bool(config['host'] and config['user'] and config['password'])


# =============================================================================
# IMAP Client Helpers
# =============================================================================

class IMAPClient:
    """
    IMAP client for reading emails during tests.
    
    Usage:
        with IMAPClient() as client:
            emails = client.search_emails(subject='Verification Code')
            code = client.extract_code(emails[0])
    """
    
    def __init__(self):
        self.config = get_imap_config()
        self.connection: Optional[imaplib.IMAP4_SSL] = None
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
    
    def connect(self):
        """Connect to IMAP server."""
        if self.config['use_tls']:
            self.connection = imaplib.IMAP4_SSL(
                self.config['host'],
                self.config['port']
            )
        else:
            self.connection = imaplib.IMAP4(
                self.config['host'],
                self.config['port']
            )
        
        self.connection.login(self.config['user'], self.config['password'])
        self.connection.select(self.config['mailbox'])
        logger.info(f"Connected to IMAP: {self.config['host']}")
    
    def disconnect(self):
        """Disconnect from IMAP server."""
        if self.connection:
            try:
                self.connection.logout()
            except Exception:
                pass
            self.connection = None
    
    def search_emails(
        self,
        subject: Optional[str] = None,
        sender: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 10,
    ) -> List[dict]:
        """
        Search for emails matching criteria.
        
        Args:
            subject: Subject contains this string
            sender: From address contains this string
            since: Emails received after this time
            limit: Maximum number of emails to return
            
        Returns:
            List of email dictionaries with 'subject', 'from', 'date', 'body', 'uid'
        """
        if not self.connection:
            raise RuntimeError("Not connected to IMAP server")
        
        # Build search criteria
        criteria = ['ALL']
        if since:
            date_str = since.strftime('%d-%b-%Y')
            criteria = [f'SINCE {date_str}']
        
        # Search for emails
        status, data = self.connection.search(None, *criteria)
        if status != 'OK':
            return []
        
        email_ids = data[0].split()
        if not email_ids:
            return []
        
        # Get most recent emails first
        email_ids = email_ids[-limit:][::-1]
        
        emails = []
        for email_id in email_ids:
            status, data = self.connection.fetch(email_id, '(RFC822)')
            if status != 'OK':
                continue
            
            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            # Decode subject
            subject_header = msg.get('Subject', '')
            decoded_subject = self._decode_header(subject_header)
            
            # Decode from
            from_header = msg.get('From', '')
            decoded_from = self._decode_header(from_header)
            
            # Get body
            body = self._get_email_body(msg)
            
            email_dict = {
                'uid': email_id.decode() if isinstance(email_id, bytes) else email_id,
                'subject': decoded_subject,
                'from': decoded_from,
                'date': msg.get('Date', ''),
                'body': body,
                'html': self._get_email_html(msg),
            }
            
            # Filter by subject
            if subject and subject.lower() not in decoded_subject.lower():
                continue
            
            # Filter by sender
            if sender and sender.lower() not in decoded_from.lower():
                continue
            
            emails.append(email_dict)
        
        return emails
    
    def wait_for_email(
        self,
        subject: Optional[str] = None,
        sender: Optional[str] = None,
        timeout: int = 60,
        poll_interval: int = 5,
    ) -> Optional[dict]:
        """
        Wait for an email matching criteria to arrive.
        
        Args:
            subject: Subject contains this string
            sender: From address contains this string
            timeout: Maximum time to wait (seconds)
            poll_interval: Time between checks (seconds)
            
        Returns:
            Email dictionary if found, None if timeout
        """
        start_time = time.time()
        since = datetime.now() - timedelta(minutes=5)  # Look at recent emails
        
        while time.time() - start_time < timeout:
            emails = self.search_emails(
                subject=subject,
                sender=sender,
                since=since,
                limit=5,
            )
            
            if emails:
                logger.info(f"Found email: {emails[0]['subject']}")
                return emails[0]
            
            logger.debug(f"No email found yet, waiting {poll_interval}s...")
            time.sleep(poll_interval)
        
        logger.warning(f"Timeout waiting for email (subject={subject}, sender={sender})")
        return None
    
    def _decode_header(self, header_value: str) -> str:
        """Decode email header value."""
        decoded_parts = decode_header(header_value)
        decoded = []
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(charset or 'utf-8', errors='replace'))
            else:
                decoded.append(part)
        return ''.join(decoded)
    
    def _get_email_body(self, msg: email.message.Message) -> str:
        """Extract plain text body from email."""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == 'text/plain':
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or 'utf-8'
                        return payload.decode(charset, errors='replace')
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or 'utf-8'
                return payload.decode(charset, errors='replace')
        return ''
    
    def _get_email_html(self, msg: email.message.Message) -> str:
        """Extract HTML body from email."""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == 'text/html':
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or 'utf-8'
                        return payload.decode(charset, errors='replace')
        return ''


def extract_verification_code(text: str) -> Optional[str]:
    """
    Extract a 6-digit verification code from email body.
    
    Looks for patterns like:
    - "Your verification code is: 123456"
    - "Code: 123456"
    - Standalone 6-digit number with spacing
    """
    # Try various patterns
    patterns = [
        r'(?:code|verification|reset)[:\s]+(\d{6})',  # "Code: 123456"
        r'(\d{6})',  # Any 6-digit sequence
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def imap_client():
    """Provide IMAP client for tests."""
    if not is_imap_configured():
        pytest.skip("IMAP not configured (set IMAP_HOST, IMAP_USER, IMAP_PASSWORD)")
    
    with IMAPClient() as client:
        yield client


@pytest.fixture
def skip_unless_live():
    """Skip test if not in live mode."""
    mode = os.environ.get('DEPLOYMENT_MODE', 'mock')
    if mode != 'live':
        pytest.skip("Test requires live mode (--mode live)")


# =============================================================================
# Tests
# =============================================================================

@pytest.mark.live
class TestIMAPConnection:
    """Test IMAP connectivity."""
    
    def test_imap_connection(self, imap_client, skip_unless_live):
        """Verify IMAP connection works."""
        # Just being able to create the client means connection worked
        assert imap_client.connection is not None
    
    def test_imap_search(self, imap_client, skip_unless_live):
        """Test searching for emails."""
        emails = imap_client.search_emails(limit=5)
        # We don't assert content, just that search works
        assert isinstance(emails, list)


@pytest.mark.live
class TestEmailVerification:
    """Test email delivery verification."""
    
    def test_verification_email_received(self, imap_client, page, skip_unless_live):
        """
        Test that verification email is received during registration.
        
        1. Start registration flow
        2. Wait for verification email
        3. Extract code from email
        4. Complete registration with code
        """
        # This is a skeleton - implement with actual registration flow
        pytest.skip("Skeleton test - implement registration flow")
        
        # Example implementation:
        # page.goto(f"{UI_BASE_URL}/account/register")
        # page.fill("#username", "testuser_live")
        # page.fill("#email", IMAP_USER)  # Send to our monitored mailbox
        # page.fill("#password", "SecurePass123!")
        # page.click("button[type=submit]")
        
        # Wait for verification email
        # email = imap_client.wait_for_email(
        #     subject="Verify Your Email",
        #     timeout=60,
        # )
        # assert email is not None
        
        # Extract code
        # code = extract_verification_code(email['body'])
        # assert code is not None
        # assert len(code) == 6
    
    def test_2fa_email_received(self, imap_client, page, skip_unless_live):
        """
        Test that 2FA email is received during login.
        
        1. Login with valid credentials (2FA enabled)
        2. Wait for 2FA email
        3. Extract code from email
        4. Complete 2FA with code
        """
        pytest.skip("Skeleton test - implement 2FA flow")
    
    def test_password_reset_email_received(self, imap_client, page, skip_unless_live):
        """
        Test that password reset email is received.
        
        1. Request password reset
        2. Wait for reset email
        3. Extract code from email
        4. Complete password reset with code
        """
        pytest.skip("Skeleton test - implement password reset flow")
    
    def test_admin_notification_email(self, imap_client, skip_unless_live):
        """
        Test that admin receives notification for pending accounts.
        
        Requires:
        - Admin email configured to monitored mailbox
        - New account registration
        """
        pytest.skip("Skeleton test - implement admin notification test")


@pytest.mark.live
class TestEmailContent:
    """Test email content and formatting."""
    
    def test_verification_email_content(self, imap_client, skip_unless_live):
        """Verify email contains expected content."""
        pytest.skip("Skeleton test - search for recent verification email")
    
    def test_email_html_rendering(self, imap_client, skip_unless_live):
        """Verify HTML email renders correctly."""
        pytest.skip("Skeleton test - check HTML content")


# =============================================================================
# Utility for Manual Testing
# =============================================================================

if __name__ == '__main__':
    """Run manual IMAP test."""
    import sys
    
    if not is_imap_configured():
        print("IMAP not configured!")
        print("Set: IMAP_HOST, IMAP_USER, IMAP_PASSWORD")
        sys.exit(1)
    
    print("Connecting to IMAP...")
    with IMAPClient() as client:
        print(f"Connected to {get_imap_config()['host']}")
        
        print("\nSearching for recent emails...")
        emails = client.search_emails(limit=5)
        
        print(f"\nFound {len(emails)} emails:")
        for e in emails:
            print(f"  - {e['subject'][:60]}...")
            print(f"    From: {e['from']}")
            print(f"    Date: {e['date']}")
            
            code = extract_verification_code(e['body'])
            if code:
                print(f"    Found code: {code}")
            print()
