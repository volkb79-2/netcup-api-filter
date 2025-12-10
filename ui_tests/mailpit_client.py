"""Mailpit client for testing email functionality.

Provides a synchronous client to interact with Mailpit's REST API.
Mailpit is a modern replacement for MailHog that provides SMTP testing
with a web UI and comprehensive REST API.

Configuration:
    Start Mailpit via Docker:
        cd tooling/mailpit && docker compose up -d
    
    Access via container hostname on shared network:
        - Service name: naf-dev-mailpit (Docker Compose auto-generates container name)
        - Hostname: naf-dev-mailpit (DNS resolution within Docker network)
        - API: http://naf-dev-mailpit:8025/mailpit/api/v1
        - SMTP: mailpit:1025
    
    Authentication:
        Mailpit requires basic auth for API access. Credentials are read from:
        1. Constructor arguments: MailpitClient(username="...", password="...")
        2. Environment variables: MAILPIT_USERNAME, MAILPIT_PASSWORD
        3. Defaults: admin / MailpitDev123! (from tooling/mailpit/.env)

Usage:
    # Uses environment variables or defaults
    client = MailpitClient()
    client.clear()
    
    # Or pass credentials explicitly
    client = MailpitClient(username="admin", password="secret")
    client.clear()
    
    # ... trigger email sending to mailpit:1025 ...
    
    messages = client.list_messages()
    assert messages.count == 1
    
    msg = client.get_message(messages.messages[0].id)
    assert "verification" in msg.subject.lower()
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx


@dataclass
class MailpitAddress:
    """Email address with optional name."""
    
    address: str
    name: str = ""
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MailpitAddress:
        return cls(
            address=data.get("Address", ""),
            name=data.get("Name", ""),
        )


@dataclass
class MailpitMessageSummary:
    """Summary of a message as returned by list endpoint."""
    
    id: str
    message_id: str
    from_address: MailpitAddress
    to: list[MailpitAddress]
    cc: list[MailpitAddress]
    bcc: list[MailpitAddress]
    subject: str
    snippet: str
    created: datetime
    read: bool
    attachments: int
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MailpitMessageSummary:
        return cls(
            id=data.get("ID", ""),
            message_id=data.get("MessageID", ""),
            from_address=MailpitAddress.from_dict(data.get("From", {})),
            to=[MailpitAddress.from_dict(a) for a in (data.get("To") or [])],
            cc=[MailpitAddress.from_dict(a) for a in (data.get("Cc") or [])],
            bcc=[MailpitAddress.from_dict(a) for a in (data.get("Bcc") or [])],
            subject=data.get("Subject", ""),
            snippet=data.get("Snippet", ""),
            created=datetime.fromisoformat(data.get("Created", "").replace("Z", "+00:00"))
            if data.get("Created")
            else datetime.now(),
            read=data.get("Read", False),
            attachments=data.get("Attachments", 0),
        )


@dataclass
class MailpitMessageList:
    """List of messages with pagination info."""
    
    total: int
    count: int
    unread: int
    messages: list[MailpitMessageSummary]
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MailpitMessageList:
        return cls(
            total=data.get("total", 0),
            count=data.get("count", 0),
            unread=data.get("unread", 0),
            messages=[
                MailpitMessageSummary.from_dict(m) for m in data.get("messages", [])
            ],
        )


@dataclass
class MailpitMessage:
    """Full message with body content."""
    
    id: str
    message_id: str
    from_address: MailpitAddress
    to: list[MailpitAddress]
    cc: list[MailpitAddress]
    bcc: list[MailpitAddress]
    reply_to: list[MailpitAddress]
    subject: str
    created: datetime
    text: str
    html: str
    size: int
    attachments: list[dict[str, Any]]
    headers: dict[str, list[str]]
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MailpitMessage:
        return cls(
            id=data.get("ID", ""),
            message_id=data.get("MessageID", ""),
            from_address=MailpitAddress.from_dict(data.get("From", {})),
            to=[MailpitAddress.from_dict(a) for a in (data.get("To") or [])],
            cc=[MailpitAddress.from_dict(a) for a in (data.get("Cc") or [])],
            bcc=[MailpitAddress.from_dict(a) for a in (data.get("Bcc") or [])],
            reply_to=[MailpitAddress.from_dict(a) for a in (data.get("ReplyTo") or [])],
            subject=data.get("Subject", ""),
            created=datetime.fromisoformat(data.get("Created", "").replace("Z", "+00:00"))
            if data.get("Created")
            else datetime.now(),
            text=data.get("Text", ""),
            html=data.get("HTML", ""),
            size=data.get("Size", 0),
            attachments=data.get("Attachments") or [],
            headers=data.get("Headers") or {},
        )
    
    def __repr__(self) -> str:
        return f"<MailpitMessage id={self.id!r} subject={self.subject!r}>"


class MailpitClient:
    """Synchronous client for Mailpit REST API.
    
    Args:
        base_url: Mailpit API base URL (default: from env or http://naf-dev-mailpit:8025/mailpit)
        timeout: Request timeout in seconds
    
    Usage:
        client = MailpitClient()
        
        # Clear mailbox
        client.clear()
        
        # List all messages
        messages = client.list_messages()
        print(f"Total: {messages.total}")
        
        # Get full message
        if messages.messages:
            msg = client.get_message(messages.messages[0].id)
            print(f"Subject: {msg.subject}")
            print(f"Body: {msg.text}")
        
        # Search messages
        results = client.search("subject:verification")
        
        # Wait for message (with polling)
        msg = client.wait_for_message(
            predicate=lambda m: "token" in m.subject.lower(),
            timeout=10.0
        )
    """
    
    # Default base URL (fallback if environment not set)
    _DEFAULT_BASE_URL_FALLBACK = "http://naf-dev-mailpit:8025/mailpit"
    
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 10.0,
        username: str | None = None,
        password: str | None = None,
    ):
        # Read from environment (.env.services) or fall back to static value
        default_url = os.environ.get("MAILPIT_URL", self._DEFAULT_BASE_URL_FALLBACK)
        self.base_url = (
            base_url
            or default_url
        ).rstrip("/")
        self.api_url = f"{self.base_url}/api/v1"
        self.timeout = timeout
        
        # Authentication credentials (from args or environment ONLY)
        # NO DEFAULTS - must be set in environment from tooling/mailpit/.env
        username = username or os.environ.get("MAILPIT_USERNAME")
        password = password or os.environ.get("MAILPIT_PASSWORD")
        
        if not username or not password:
            raise ValueError(
                "Mailpit authentication required: set MAILPIT_USERNAME and MAILPIT_PASSWORD "
                "environment variables (source tooling/mailpit/.env)"
            )
        
        # Create httpx client with basic auth
        self._client = httpx.Client(
            timeout=timeout,
            auth=(username, password),
        )
    
    def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make HTTP request to Mailpit API."""
        url = f"{self.api_url}{endpoint}"
        response = self._client.request(method, url, **kwargs)
        response.raise_for_status()
        return response
    
    def info(self) -> dict[str, Any]:
        """Get Mailpit server info."""
        return self._request("GET", "/info").json()
    
    def list_messages(self, limit: int = 50, start: int = 0) -> MailpitMessageList:
        """List messages in the mailbox.
        
        Args:
            limit: Maximum number of messages to return
            start: Offset for pagination
        
        Returns:
            MailpitMessageList with message summaries
        """
        response = self._request(
            "GET",
            "/messages",
            params={"limit": limit, "start": start},
        )
        return MailpitMessageList.from_dict(response.json())
    
    def get_message(self, message_id: str) -> MailpitMessage:
        """Get full message by ID.
        
        Args:
            message_id: Message ID (from MessageSummary.id)
        
        Returns:
            Full MailpitMessage with body content
        """
        response = self._request("GET", f"/message/{message_id}")
        return MailpitMessage.from_dict(response.json())
    
    def search(
        self,
        query: str,
        limit: int = 50,
        start: int = 0,
    ) -> MailpitMessageList:
        """Search messages.
        
        Query syntax:
            - subject:word - Match subject containing word
            - from:email@example.com - Match sender
            - to:email@example.com - Match recipient
            - is:read / is:unread - Filter by read status
            - has:attachment - Has attachments
            - before:YYYY-MM-DD / after:YYYY-MM-DD - Date filters
        
        Args:
            query: Search query string
            limit: Maximum results
            start: Offset for pagination
        
        Returns:
            MailpitMessageList with matching messages
        """
        response = self._request(
            "GET",
            "/search",
            params={"query": query, "limit": limit, "start": start},
        )
        return MailpitMessageList.from_dict(response.json())
    
    def delete_message(self, message_id: str) -> None:
        """Delete a specific message.
        
        Args:
            message_id: Message ID to delete
        """
        self._request("DELETE", f"/messages", json={"IDs": [message_id]})
    
    def clear(self) -> None:
        """Delete all messages in the mailbox."""
        self._request("DELETE", "/messages")
    
    def mark_read(self, message_id: str) -> None:
        """Mark a message as read.
        
        Args:
            message_id: Message ID to mark
        """
        self._request("PUT", f"/messages", json={"IDs": [message_id], "Read": True})
    
    def mark_unread(self, message_id: str) -> None:
        """Mark a message as unread.
        
        Args:
            message_id: Message ID to mark
        """
        self._request("PUT", f"/messages", json={"IDs": [message_id], "Read": False})
    
    def wait_for_message(
        self,
        predicate: callable = None,
        timeout: float = 10.0,
        poll_interval: float = 0.5,
    ) -> MailpitMessage | None:
        """Wait for a message matching the predicate.
        
        Args:
            predicate: Function that takes MailpitMessageSummary and returns bool.
                       If None, waits for any message.
            timeout: Maximum time to wait in seconds
            poll_interval: Time between polls in seconds
        
        Returns:
            Full MailpitMessage if found, None if timeout
        
        Example:
            # Wait for verification email
            msg = client.wait_for_message(
                predicate=lambda m: "verification" in m.subject.lower()
            )
        """
        import time
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            messages = self.list_messages()
            for summary in messages.messages:
                if predicate is None or predicate(summary):
                    return self.get_message(summary.id)
            time.sleep(poll_interval)
        
        return None
    
    def wait_for_count(
        self,
        count: int,
        timeout: float = 10.0,
        poll_interval: float = 0.5,
    ) -> bool:
        """Wait until mailbox has at least N messages.
        
        Args:
            count: Minimum message count to wait for
            timeout: Maximum time to wait
            poll_interval: Time between polls
        
        Returns:
            True if count reached, False if timeout
        """
        import time
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            messages = self.list_messages()
            if messages.total >= count:
                return True
            time.sleep(poll_interval)
        
        return False
    
    def get_latest(self) -> MailpitMessage | None:
        """Get the most recent message.
        
        Returns:
            Most recent MailpitMessage, or None if mailbox is empty
        """
        messages = self.list_messages(limit=1)
        if messages.messages:
            return self.get_message(messages.messages[0].id)
        return None
    
    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()
    
    def __enter__(self) -> MailpitClient:
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


# For backwards compatibility with aiosmtpd-based tests,
# provide a CapturedEmail-like interface
@dataclass
class CapturedEmail:
    """Adapter class for compatibility with aiosmtpd-based tests.
    
    Wraps MailpitMessage to provide same interface as the old
    mock_smtp_server.CapturedEmail class.
    """
    
    sender: str
    recipients: list[str]
    subject: str
    body_text: str
    body_html: str | None
    headers: dict[str, str]
    raw_message: str
    timestamp: datetime
    
    @classmethod
    def from_mailpit_message(cls, msg: MailpitMessage) -> CapturedEmail:
        """Convert MailpitMessage to CapturedEmail format."""
        return cls(
            sender=msg.from_address.address,
            recipients=[a.address for a in msg.to],
            subject=msg.subject,
            body_text=msg.text,
            body_html=msg.html if msg.html else None,
            headers={k: v[0] if v else "" for k, v in msg.headers.items()},
            raw_message="",  # Not available via Mailpit API
            timestamp=msg.created,
        )


def test_mailpit_client() -> None:
    """Test the Mailpit client.
    
    Requires Mailpit to be running:
        cd tooling/mailpit && docker compose up -d
    """
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    
    # Use SMTP endpoint from environment or default
    smtp_host = os.environ.get("MAILPIT_SMTP_HOST", "mailpit")
    smtp_port = int(os.environ.get("MAILPIT_SMTP_PORT", "1025"))
    
    client = MailpitClient()
    
    print(f"[Test] Mailpit info: {client.info()}")
    
    # Clear mailbox
    client.clear()
    
    # Send test email
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Test Email via Mailpit"
    msg["From"] = "test@example.com"
    msg["To"] = "recipient@example.com"
    
    text = "This is the plain text version"
    html = "<html><body><p>This is the <b>HTML</b> version</p></body></html>"
    
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))
    
    smtp = smtplib.SMTP(smtp_host, smtp_port)
    smtp.send_message(msg)
    smtp.quit()
    
    print("[Test] Email sent successfully")
    
    # Wait for message
    received = client.wait_for_message(timeout=5.0)
    assert received is not None, "No message received"
    
    assert received.from_address.address == "test@example.com"
    assert received.to[0].address == "recipient@example.com"
    assert received.subject == "Test Email via Mailpit"
    assert "plain text version" in received.text
    assert "HTML" in received.html
    
    print("[Test] ✓ Email captured correctly via Mailpit")
    print(f"[Test]   Subject: {received.subject}")
    print(f"[Test]   From: {received.from_address.address}")
    print(f"[Test]   To: {[a.address for a in received.to]}")
    print(f"[Test]   Body (text): {received.text[:50]}...")
    
    # Test search
    results = client.search("subject:Test")
    assert results.total >= 1
    print(f"[Test] ✓ Search found {results.total} messages")
    
    # Test compatibility layer
    captured = CapturedEmail.from_mailpit_message(received)
    assert captured.sender == "test@example.com"
    assert captured.subject == "Test Email via Mailpit"
    print("[Test] ✓ Compatibility layer works")
    
    # Cleanup
    client.clear()
    client.close()
    
    print("[Test] All tests passed!")


if __name__ == "__main__":
    test_mailpit_client()
