# Mock SMTP Server for Email Testing

Mock SMTP server implementation for testing email functionality without sending real emails. Uses **aiosmtpd** to provide a real SMTP server that captures emails for inspection.

## Features

✅ **Real SMTP Protocol** - Works with any SMTP client (smtplib, etc.)  
✅ **Email Capture** - All emails stored in memory for inspection  
✅ **Full Content** - Captures headers, text, HTML, and raw message  
✅ **Multiple Recipients** - Handles CC, BCC, multiple To addresses  
✅ **Filtering** - Filter by recipient, subject, timestamp  
✅ **Reset** - Clear captured emails between tests  
✅ **Timestamps** - Track when each email was received  

## Quick Start

### In Tests (Recommended)

```python
async def test_email_sending(mock_smtp_server):
    """Test that application sends correct emails."""
    
    # Configure application to use mock SMTP
    # Host: 127.0.0.1, Port: 1025
    
    # ... trigger email sending in your application ...
    
    # Inspect captured emails
    assert len(mock_smtp_server.captured_emails) == 1
    
    email = mock_smtp_server.captured_emails[0]
    assert email.sender == "noreply@example.com"
    assert "user@example.com" in email.recipients
    assert email.subject == "Welcome to our service"
    assert "Thank you for signing up" in email.body_text
    
    # Check HTML version (if multipart)
    if email.body_html:
        assert "<h1>Welcome</h1>" in email.body_html
```

### Standalone Testing

Test the mock SMTP server directly:

```bash
cd /workspaces/netcup-api-filter
python -m ui_tests.mock_smtp_server
```

Or use it programmatically:

```python
import asyncio
from ui_tests.mock_smtp_server import MockSMTPServer

async def test():
    server = MockSMTPServer(host='127.0.0.1', port=1025)
    await server.start()
    
    # ... send emails via SMTP to 127.0.0.1:1025 ...
    
    print(f"Captured {len(server.captured_emails)} emails")
    for email in server.captured_emails:
        print(f"  - {email.subject} from {email.sender}")
    
    await server.stop()

asyncio.run(test())
```

## Configuration

**Default Settings:**
- Host: `127.0.0.1`
- Port: `1025`
- Protocol: SMTP (no authentication, no TLS)

**Why these defaults?**
- Port 1025: Non-privileged port (doesn't require root)
- Localhost only: Prevents external connections
- No auth: Simplifies testing (authentication can be tested separately)

## CapturedEmail Object

Each captured email has:

```python
@dataclass
class CapturedEmail:
    sender: str              # Envelope FROM address
    recipients: List[str]    # Envelope TO addresses
    subject: str             # Email subject
    body_text: str           # Plain text part
    body_html: str | None    # HTML part (if present)
    headers: Dict[str, str]  # All email headers
    raw_message: str         # Complete raw email
    timestamp: datetime      # When email was received
```

## Filtering Emails

### By Recipient

```python
# Get all emails sent to specific recipient
alice_emails = mock_smtp_server.handler.get_emails_to("alice@example.com")

for email in alice_emails:
    print(f"To Alice: {email.subject}")
```

### By Subject

```python
# Get all password reset emails
reset_emails = mock_smtp_server.handler.get_emails_with_subject("password reset")

assert len(reset_emails) == 1
assert "click the link" in reset_emails[0].body_text
```

### Custom Filtering

```python
# Get all emails from last hour
from datetime import datetime, timedelta

recent = [
    email for email in mock_smtp_server.captured_emails
    if (datetime.utcnow() - email.timestamp) < timedelta(hours=1)
]
```

## Common Test Patterns

### Test Welcome Email

```python
async def test_welcome_email_sent(mock_smtp_server):
    # Trigger user registration
    response = await client.post("/register", json={
        "email": "newuser@example.com",
        "password": "Password123!"
    })
    
    assert response.status_code == 201
    
    # Check welcome email was sent
    await asyncio.sleep(0.5)  # Give email time to send
    
    assert len(mock_smtp_server.captured_emails) == 1
    email = mock_smtp_server.captured_emails[0]
    
    assert email.subject == "Welcome to Netcup API Filter"
    assert "newuser@example.com" in email.recipients
    assert "getting started" in email.body_text.lower()
```

### Test Password Reset Email

```python
async def test_password_reset_email(mock_smtp_server):
    # Request password reset
    response = await client.post("/password-reset", json={
        "email": "user@example.com"
    })
    
    assert response.status_code == 200
    
    # Check reset email
    await asyncio.sleep(0.5)
    
    emails = mock_smtp_server.handler.get_emails_with_subject("password reset")
    assert len(emails) == 1
    
    email = emails[0]
    assert "user@example.com" in email.recipients
    
    # Extract reset link from email
    import re
    link_match = re.search(r'https?://[^\s]+/reset/[^\s]+', email.body_text)
    assert link_match, "Reset link should be in email"
    reset_link = link_match.group(0)
    
    # Use reset link to change password
    # ...
```

### Test Email Contains Correct Data

```python
async def test_notification_email_content(mock_smtp_server):
    # Trigger notification
    await trigger_dns_change_notification(domain="example.com", record_type="A")
    
    await asyncio.sleep(0.5)
    
    email = mock_smtp_server.captured_emails[0]
    
    # Check subject
    assert "DNS Change" in email.subject
    assert "example.com" in email.subject
    
    # Check content
    assert "example.com" in email.body_text
    assert "A record" in email.body_text or "A-record" in email.body_text
    
    # Check headers
    assert email.headers.get('X-Priority') == '1'  # High priority
    assert 'Date' in email.headers
```

### Test Multiple Recipients

```python
async def test_notification_to_multiple_admins(mock_smtp_server):
    admins = ["admin1@example.com", "admin2@example.com"]
    
    # Trigger admin notification
    await send_admin_alert("System maintenance required")
    
    await asyncio.sleep(0.5)
    
    # Check one email was sent to both admins
    assert len(mock_smtp_server.captured_emails) == 1
    email = mock_smtp_server.captured_emails[0]
    
    for admin in admins:
        assert admin in email.recipients
```

### Test HTML and Text Versions

```python
async def test_email_has_both_versions(mock_smtp_server):
    await send_marketing_email("user@example.com")
    
    await asyncio.sleep(0.5)
    
    email = mock_smtp_server.captured_emails[0]
    
    # Check text version
    assert email.body_text
    assert "special offer" in email.body_text.lower()
    
    # Check HTML version
    assert email.body_html
    assert "<h1>" in email.body_html
    assert "<a href=" in email.body_html
    
    # HTML should be richer than text
    assert len(email.body_html) > len(email.body_text)
```

## Integration with Application Tests

### Configure Email in E2E Tests

```python
async def test_e2e_with_email(mock_smtp_server, browser_session, mock_netcup_api_server):
    """Complete E2E test including email verification."""
    
    async with browser_session() as browser:
        # Configure email settings in admin UI
        await browser.goto(settings.url("/admin/email_config/"))
        await browser.fill("#smtp_server", "127.0.0.1")
        await browser.fill("#smtp_port", "1025")
        await browser.fill("#sender_email", "noreply@example.com")
        await browser.submit("form")
        
        # Trigger action that sends email
        await browser.goto(settings.url("/admin/client/new/"))
        await browser.fill("#email_address", "client@example.com")
        # ... create client ...
        
        # Verify email was sent
        await asyncio.sleep(0.5)
        
        assert len(mock_smtp_server.captured_emails) == 1
        email = mock_smtp_server.captured_emails[0]
        
        assert "client@example.com" in email.recipients
        assert "API Client Created" in email.subject
```

## Alternatives

If you need more features, consider these alternatives:

### MailHog
- Web UI for viewing emails: http://localhost:8025
- SMTP server on port 1025
- Docker: `docker run -p 1025:1025 -p 8025:8025 mailhog/mailhog`
- Great for manual testing and debugging

### MailDev
- Similar to MailHog with web UI
- Node.js based
- Install: `npm install -g maildev`
- Run: `maildev`

### smtp4dev
- .NET based SMTP server with web UI
- Windows, Linux, macOS
- Docker: `docker run -p 3000:80 -p 2525:25 rnwood/smtp4dev`

**Why use our mock instead?**
- ✅ No external dependencies (just aiosmtpd)
- ✅ Programmatic access to emails (no parsing HTML UI)
- ✅ Async/await integration with tests
- ✅ Fast startup (no Docker overhead)
- ✅ Easy filtering and assertions

## Troubleshooting

**Port already in use:**
```bash
lsof -ti:1025 | xargs kill -9
```

**aiosmtpd not installed:**
```bash
pip install aiosmtpd
```

**Emails not captured:**
- Check that application is configured to use 127.0.0.1:1025
- Add `await asyncio.sleep(0.5)` after triggering email
- Check for exceptions in application logs
- Verify firewall isn't blocking port 1025

**Deprecation warnings:**
- `datetime.utcnow()` warnings are harmless
- Can be fixed by using `datetime.now(datetime.UTC)` instead

## Test Results

All mock SMTP tests passing ✅:

```
test_mock_smtp_captures_simple_email ........ PASSED
test_mock_smtp_captures_html_email .......... PASSED
test_mock_smtp_multiple_recipients ........... PASSED
test_mock_smtp_multiple_emails ............... PASSED
test_mock_smtp_filter_by_recipient ........... PASSED
test_mock_smtp_filter_by_subject ............. PASSED
test_mock_smtp_headers_captured .............. PASSED
test_mock_smtp_reset .........................  PASSED
test_mock_smtp_timestamp_recorded ............ PASSED
test_mock_smtp_raw_message_preserved ......... PASSED
```

10 tests validate:
- ✅ Simple text emails
- ✅ HTML + text multipart emails
- ✅ Multiple recipients
- ✅ Multiple emails in sequence
- ✅ Filtering by recipient
- ✅ Filtering by subject
- ✅ Header capture
- ✅ Reset functionality
- ✅ Timestamp tracking
- ✅ Raw message preservation
