"""Mock SMTP server for testing email functionality.

Uses aiosmtpd to provide a real SMTP server that captures emails
instead of sending them. Captured emails can be inspected in tests.

For a more feature-rich solution with web UI, consider:
- MailHog: https://github.com/mailhog/MailHog
- MailDev: https://github.com/maildev/maildev
- smtp4dev: https://github.com/rnwood/smtp4dev
"""
from __future__ import annotations

import asyncio
import email
from email.message import EmailMessage
from typing import List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CapturedEmail:
    """Represents a captured email message."""
    
    sender: str
    recipients: List[str]
    subject: str
    body_text: str
    body_html: str | None
    headers: Dict[str, str]
    raw_message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    @classmethod
    def from_message(cls, sender: str, recipients: List[str], message_data: bytes) -> 'CapturedEmail':
        """Parse email message data into CapturedEmail."""
        message_str = message_data.decode('utf-8', errors='replace')
        msg = email.message_from_string(message_str)
        
        # Extract text and HTML parts
        body_text = ""
        body_html = None
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == 'text/plain':
                    body_text = part.get_payload(decode=True).decode('utf-8', errors='replace')
                elif content_type == 'text/html':
                    body_html = part.get_payload(decode=True).decode('utf-8', errors='replace')
        else:
            content_type = msg.get_content_type()
            payload = msg.get_payload(decode=True)
            if payload:
                body_text = payload.decode('utf-8', errors='replace')
        
        return cls(
            sender=sender,
            recipients=recipients,
            subject=msg.get('Subject', ''),
            body_text=body_text,
            body_html=body_html,
            headers=dict(msg.items()),
            raw_message=message_str
        )
    
    def __repr__(self) -> str:
        return f"<Email from={self.sender} to={self.recipients} subject={self.subject!r}>"


class MockSMTPHandler:
    """SMTP handler that captures emails instead of sending them."""
    
    def __init__(self):
        self.captured_emails: List[CapturedEmail] = []
    
    async def handle_DATA(self, server, session, envelope):
        """Handle email data (called by aiosmtpd)."""
        print(f"[Mock SMTP] Received email from {envelope.mail_from} to {envelope.rcpt_tos}")
        
        try:
            captured = CapturedEmail.from_message(
                sender=envelope.mail_from,
                recipients=envelope.rcpt_tos,
                message_data=envelope.content
            )
            self.captured_emails.append(captured)
            print(f"[Mock SMTP] Captured: {captured.subject}")
            return '250 Message accepted for delivery'
        except Exception as e:
            print(f"[Mock SMTP] Error capturing email: {e}")
            return '500 Error capturing message'
    
    def reset(self):
        """Clear all captured emails."""
        self.captured_emails.clear()
    
    def get_emails_to(self, recipient: str) -> List[CapturedEmail]:
        """Get all emails sent to a specific recipient."""
        return [email for email in self.captured_emails if recipient in email.recipients]
    
    def get_emails_with_subject(self, subject_contains: str) -> List[CapturedEmail]:
        """Get all emails with subject containing the given string."""
        return [email for email in self.captured_emails 
                if subject_contains.lower() in email.subject.lower()]


class MockSMTPServer:
    """Async SMTP server for testing.
    
    Usage:
        server = MockSMTPServer(host='127.0.0.1', port=1025)
        await server.start()
        
        # ... run tests that send emails ...
        
        emails = server.handler.captured_emails
        assert len(emails) == 1
        assert emails[0].subject == "Test Subject"
        
        await server.stop()
    """
    
    def __init__(self, host: str = '127.0.0.1', port: int = 1025):
        self.host = host
        self.port = port
        self.handler = MockSMTPHandler()
        self.server = None
        self._server_task = None
    
    async def start(self):
        """Start the SMTP server."""
        try:
            from aiosmtpd.controller import Controller
            
            # Create controller with our handler
            self.controller = Controller(
                self.handler,
                hostname=self.host,
                port=self.port
            )
            
            # Start in a separate thread (aiosmtpd uses threading)
            self.controller.start()
            
            print(f"[Mock SMTP] Server started on {self.host}:{self.port}")
            
        except ImportError:
            print("[Mock SMTP] ERROR: aiosmtpd not installed")
            print("[Mock SMTP] Install with: pip install aiosmtpd")
            raise
    
    async def stop(self):
        """Stop the SMTP server."""
        if hasattr(self, 'controller') and self.controller:
            self.controller.stop()
            print(f"[Mock SMTP] Server stopped")
    
    def reset(self):
        """Clear captured emails."""
        self.handler.reset()
    
    @property
    def url(self) -> str:
        """Get SMTP connection string."""
        return f"{self.host}:{self.port}"
    
    @property
    def captured_emails(self) -> List[CapturedEmail]:
        """Get all captured emails."""
        return self.handler.captured_emails


# Alternative: Simple synchronous SMTP server using standard library
class SimpleMockSMTPServer:
    """Simple mock SMTP server using Python's smtpd module.
    
    This is a fallback option if aiosmtpd is not available.
    Note: smtpd module is deprecated in Python 3.12+.
    """
    
    def __init__(self, host: str = '127.0.0.1', port: int = 1025):
        self.host = host
        self.port = port
        self.captured_emails: List[CapturedEmail] = []
        self._server = None
        self._thread = None
    
    def start(self):
        """Start the SMTP server in a background thread."""
        import threading
        import smtpd
        import asyncore
        
        class CapturingSMTPServer(smtpd.SMTPServer):
            def __init__(self, localaddr, remoteaddr, capture_list):
                super().__init__(localaddr, remoteaddr)
                self.capture_list = capture_list
            
            def process_message(self, peer, mailfrom, rcpttos, data, **kwargs):
                captured = CapturedEmail.from_message(mailfrom, rcpttos, data)
                self.capture_list.append(captured)
                print(f"[Mock SMTP] Captured: {captured.subject}")
        
        self._server = CapturingSMTPServer(
            (self.host, self.port),
            None,
            self.captured_emails
        )
        
        def run_server():
            asyncore.loop()
        
        self._thread = threading.Thread(target=run_server, daemon=True)
        self._thread.start()
        
        print(f"[Mock SMTP] Simple server started on {self.host}:{self.port}")
    
    def stop(self):
        """Stop the SMTP server."""
        if self._server:
            self._server.close()
            print("[Mock SMTP] Simple server stopped")
    
    def reset(self):
        """Clear captured emails."""
        self.captured_emails.clear()


async def test_smtp_server():
    """Test the mock SMTP server directly."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    # Start mock server
    server = MockSMTPServer(host='127.0.0.1', port=1025)
    await server.start()
    
    try:
        # Give server time to start
        await asyncio.sleep(0.5)
        
        # Send test email
        msg = MIMEMultipart('alternative')
        msg['Subject'] = "Test Email from Mock SMTP"
        msg['From'] = "test@example.com"
        msg['To'] = "recipient@example.com"
        
        text = "This is the plain text version"
        html = "<html><body><p>This is the <b>HTML</b> version</p></body></html>"
        
        msg.attach(MIMEText(text, 'plain'))
        msg.attach(MIMEText(html, 'html'))
        
        # Connect and send
        smtp = smtplib.SMTP('127.0.0.1', 1025)
        smtp.send_message(msg)
        smtp.quit()
        
        print("[Test] Email sent successfully")
        
        # Check captured emails
        await asyncio.sleep(0.5)
        assert len(server.captured_emails) == 1
        
        email = server.captured_emails[0]
        assert email.sender == "test@example.com"
        assert "recipient@example.com" in email.recipients
        assert email.subject == "Test Email from Mock SMTP"
        assert "plain text version" in email.body_text
        assert email.body_html and "HTML" in email.body_html
        
        print("[Test] ✓ Email captured correctly")
        print(f"[Test]   Subject: {email.subject}")
        print(f"[Test]   From: {email.sender}")
        print(f"[Test]   To: {email.recipients}")
        print(f"[Test]   Body (text): {email.body_text[:50]}...")
        
    finally:
        await server.stop()


if __name__ == '__main__':
    asyncio.run(test_smtp_server())
