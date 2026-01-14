"""Tests for mock SMTP server functionality."""
import asyncio
import pytest
import smtplib
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


pytestmark = pytest.mark.asyncio


async def _wait_for_captured_emails(mock_smtp_server, expected_count: int, timeout_seconds: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while len(mock_smtp_server.captured_emails) < expected_count:
        if asyncio.get_running_loop().time() >= deadline:
            break
        await asyncio.sleep(0.01)

    assert len(mock_smtp_server.captured_emails) >= expected_count, (
        f"Expected at least {expected_count} captured email(s), got {len(mock_smtp_server.captured_emails)}"
    )


async def test_mock_smtp_captures_simple_email(mock_smtp_server):
    """Test that mock SMTP server captures a simple text email."""
    # Send a simple email
    msg = MIMEText("This is a test email body")
    msg['Subject'] = "Test Email Subject"
    msg['From'] = "sender@example.com"
    msg['To'] = "recipient@example.com"
    
    # Connect and send
    smtp = smtplib.SMTP('127.0.0.1', 1025)
    smtp.send_message(msg)
    smtp.quit()
    
    # Give server time to process
    await _wait_for_captured_emails(mock_smtp_server, expected_count=1)
    
    # Verify email was captured
    assert len(mock_smtp_server.captured_emails) == 1
    
    email = mock_smtp_server.captured_emails[0]
    assert email.sender == "sender@example.com"
    assert "recipient@example.com" in email.recipients
    assert email.subject == "Test Email Subject"
    assert "test email body" in email.body_text
    
    print(f"[Test] ✓ Simple email captured")
    print(f"[Test]   From: {email.sender}")
    print(f"[Test]   To: {email.recipients}")
    print(f"[Test]   Subject: {email.subject}")


async def test_mock_smtp_captures_html_email(mock_smtp_server):
    """Test that mock SMTP server captures HTML and text parts."""
    msg = MIMEMultipart('alternative')
    msg['Subject'] = "HTML Email Test"
    msg['From'] = "sender@example.com"
    msg['To'] = "recipient@example.com"
    
    text_part = "This is the plain text version"
    html_part = "<html><body><h1>HTML Version</h1><p>This is <b>bold</b></p></body></html>"
    
    msg.attach(MIMEText(text_part, 'plain'))
    msg.attach(MIMEText(html_part, 'html'))
    
    smtp = smtplib.SMTP('127.0.0.1', 1025)
    smtp.send_message(msg)
    smtp.quit()
    
    await _wait_for_captured_emails(mock_smtp_server, expected_count=1)
    
    assert len(mock_smtp_server.captured_emails) == 1
    
    email = mock_smtp_server.captured_emails[0]
    assert email.subject == "HTML Email Test"
    assert "plain text version" in email.body_text
    assert email.body_html is not None
    assert "<b>bold</b>" in email.body_html
    assert "HTML Version" in email.body_html
    
    print(f"[Test] ✓ HTML email captured")
    print(f"[Test]   Text part: {email.body_text[:50]}...")
    print(f"[Test]   HTML part: {email.body_html[:50]}...")


async def test_mock_smtp_multiple_recipients(mock_smtp_server):
    """Test email with multiple recipients."""
    msg = MIMEText("Email to multiple recipients")
    msg['Subject'] = "Multi-Recipient Test"
    msg['From'] = "sender@example.com"
    msg['To'] = "recipient1@example.com, recipient2@example.com"
    
    smtp = smtplib.SMTP('127.0.0.1', 1025)
    smtp.send_message(msg)
    smtp.quit()
    
    await _wait_for_captured_emails(mock_smtp_server, expected_count=1)
    
    assert len(mock_smtp_server.captured_emails) == 1
    
    email = mock_smtp_server.captured_emails[0]
    assert len(email.recipients) == 2
    assert "recipient1@example.com" in email.recipients
    assert "recipient2@example.com" in email.recipients
    
    print(f"[Test] ✓ Multiple recipients captured")
    print(f"[Test]   Recipients: {email.recipients}")


async def test_mock_smtp_multiple_emails(mock_smtp_server):
    """Test that server captures multiple emails."""
    smtp = smtplib.SMTP('127.0.0.1', 1025)
    
    for i in range(3):
        msg = MIMEText(f"Email body {i}")
        msg['Subject'] = f"Test Email {i}"
        msg['From'] = f"sender{i}@example.com"
        msg['To'] = "recipient@example.com"
        smtp.send_message(msg)
    
    smtp.quit()
    
    await _wait_for_captured_emails(mock_smtp_server, expected_count=3)
    
    assert len(mock_smtp_server.captured_emails) == 3
    
    for i, email in enumerate(mock_smtp_server.captured_emails):
        assert email.subject == f"Test Email {i}"
        assert email.sender == f"sender{i}@example.com"
    
    print(f"[Test] ✓ Multiple emails captured: {len(mock_smtp_server.captured_emails)}")


async def test_mock_smtp_filter_by_recipient(mock_smtp_server):
    """Test filtering emails by recipient."""
    smtp = smtplib.SMTP('127.0.0.1', 1025)
    
    # Send to different recipients
    for recipient in ["alice@example.com", "bob@example.com", "alice@example.com"]:
        msg = MIMEText(f"Email to {recipient}")
        msg['Subject'] = f"Email for {recipient}"
        msg['From'] = "sender@example.com"
        msg['To'] = recipient
        smtp.send_message(msg)
    
    smtp.quit()
    
    await _wait_for_captured_emails(mock_smtp_server, expected_count=3)
    
    # Filter by recipient
    alice_emails = mock_smtp_server.handler.get_emails_to("alice@example.com")
    bob_emails = mock_smtp_server.handler.get_emails_to("bob@example.com")
    
    assert len(alice_emails) == 2
    assert len(bob_emails) == 1
    
    print(f"[Test] ✓ Email filtering works")
    print(f"[Test]   Emails to alice: {len(alice_emails)}")
    print(f"[Test]   Emails to bob: {len(bob_emails)}")


async def test_mock_smtp_filter_by_subject(mock_smtp_server):
    """Test filtering emails by subject."""
    smtp = smtplib.SMTP('127.0.0.1', 1025)
    
    subjects = [
        "Password Reset Request",
        "Welcome to our service",
        "Password Changed Successfully"
    ]
    
    for subject in subjects:
        msg = MIMEText("Email body")
        msg['Subject'] = subject
        msg['From'] = "sender@example.com"
        msg['To'] = "recipient@example.com"
        smtp.send_message(msg)
    
    smtp.quit()
    
    await _wait_for_captured_emails(mock_smtp_server, expected_count=len(subjects))
    
    # Filter by subject keyword
    password_emails = mock_smtp_server.handler.get_emails_with_subject("password")
    welcome_emails = mock_smtp_server.handler.get_emails_with_subject("welcome")
    
    assert len(password_emails) == 2
    assert len(welcome_emails) == 1
    
    print(f"[Test] ✓ Subject filtering works")
    print(f"[Test]   Password emails: {len(password_emails)}")
    print(f"[Test]   Welcome emails: {len(welcome_emails)}")


async def test_mock_smtp_headers_captured(mock_smtp_server):
    """Test that email headers are captured."""
    msg = MIMEText("Test body")
    msg['Subject'] = "Header Test"
    msg['From'] = "sender@example.com"
    msg['To'] = "recipient@example.com"
    msg['X-Custom-Header'] = "CustomValue"
    msg['Reply-To'] = "noreply@example.com"
    
    smtp = smtplib.SMTP('127.0.0.1', 1025)
    smtp.send_message(msg)
    smtp.quit()
    
    await _wait_for_captured_emails(mock_smtp_server, expected_count=1)
    
    email = mock_smtp_server.captured_emails[0]
    
    assert 'Subject' in email.headers
    assert email.headers['Subject'] == "Header Test"
    assert 'X-Custom-Header' in email.headers
    assert email.headers['X-Custom-Header'] == "CustomValue"
    assert 'Reply-To' in email.headers
    
    print(f"[Test] ✓ Headers captured")
    print(f"[Test]   Custom header: {email.headers.get('X-Custom-Header')}")


async def test_mock_smtp_reset(mock_smtp_server):
    """Test that reset clears captured emails."""
    # Send first email
    msg = MIMEText("First email")
    msg['Subject'] = "Email 1"
    msg['From'] = "sender@example.com"
    msg['To'] = "recipient@example.com"
    
    smtp = smtplib.SMTP('127.0.0.1', 1025)
    smtp.send_message(msg)
    smtp.quit()
    
    await _wait_for_captured_emails(mock_smtp_server, expected_count=1)
    
    assert len(mock_smtp_server.captured_emails) == 1
    
    # Reset
    mock_smtp_server.reset()
    
    assert len(mock_smtp_server.captured_emails) == 0
    
    # Send second email
    msg2 = MIMEText("Second email")
    msg2['Subject'] = "Email 2"
    msg2['From'] = "sender@example.com"
    msg2['To'] = "recipient@example.com"
    
    smtp = smtplib.SMTP('127.0.0.1', 1025)
    smtp.send_message(msg2)
    smtp.quit()
    
    await _wait_for_captured_emails(mock_smtp_server, expected_count=1)
    
    assert len(mock_smtp_server.captured_emails) == 1
    assert mock_smtp_server.captured_emails[0].subject == "Email 2"
    
    print(f"[Test] ✓ Reset clears old emails")


async def test_mock_smtp_timestamp_recorded(mock_smtp_server):
    """Test that emails have timestamps."""
    from datetime import datetime, timedelta
    
    msg = MIMEText("Test with timestamp")
    msg['Subject'] = "Timestamp Test"
    msg['From'] = "sender@example.com"
    msg['To'] = "recipient@example.com"
    
    before = datetime.now(timezone.utc)
    
    smtp = smtplib.SMTP('127.0.0.1', 1025)
    smtp.send_message(msg)
    smtp.quit()
    
    await _wait_for_captured_emails(mock_smtp_server, expected_count=1)
    
    after = datetime.now(timezone.utc)
    
    email = mock_smtp_server.captured_emails[0]
    
    assert email.timestamp >= before
    assert email.timestamp <= after
    assert (after - email.timestamp).total_seconds() < 5
    
    print(f"[Test] ✓ Timestamp recorded: {email.timestamp}")


async def test_mock_smtp_raw_message_preserved(mock_smtp_server):
    """Test that raw message is preserved for advanced inspection."""
    msg = MIMEText("Original message text")
    msg['Subject'] = "Raw Message Test"
    msg['From'] = "sender@example.com"
    msg['To'] = "recipient@example.com"
    
    smtp = smtplib.SMTP('127.0.0.1', 1025)
    smtp.send_message(msg)
    smtp.quit()
    
    await _wait_for_captured_emails(mock_smtp_server, expected_count=1)
    
    email = mock_smtp_server.captured_emails[0]
    
    assert email.raw_message
    assert "Raw Message Test" in email.raw_message
    assert "Original message text" in email.raw_message
    assert "From: sender@example.com" in email.raw_message
    
    print(f"[Test] ✓ Raw message preserved")
    print(f"[Test]   Length: {len(email.raw_message)} bytes")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
