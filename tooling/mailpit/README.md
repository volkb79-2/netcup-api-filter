# Mailpit - SMTP Testing Server

Modern SMTP testing server with web UI for email capture during development and testing.

## Quick Start

```bash
cd tooling/mailpit

# Start Mailpit
docker compose up -d

# View logs
docker compose logs -f

# Stop Mailpit
docker compose down
```

## Access

- **Web UI**: http://localhost:8025
- **SMTP**: naf-mailpit:1025 (from containers) or localhost:1025 (from host)
- **API**: http://naf-mailpit:8025/api/v1

## Authentication

Configured via `.env` file:
- Username: `admin` (default)
- Password: `MailpitDev123` (default)

Authentication is enabled by default (Mailpit runs with `MP_UI_AUTH`). Do not disable it unless you fully trust the network.

**Change credentials** by editing `.env`:
```bash
MAILPIT_USERNAME=myuser
MAILPIT_PASSWORD=MySecurePassword123!
```

Then restart:
```bash
docker compose down && docker compose up -d
```

## Configuration

All settings in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `MAILPIT_USERNAME` | `admin` | Web UI username |
| `MAILPIT_PASSWORD` | `MailpitDev123` | Web UI password |
| `MAILPIT_WEB_PORT` | `8025` | Web UI/API port |
| `MAILPIT_SMTP_PORT` | `1025` | SMTP port |
| `DOCKER_NETWORK_INTERNAL` | `naf-dev-network` | Docker network |
| `MAILPIT_MAX_MESSAGE_SIZE` | `10485760` | Max email size (10MB) |
| `MAILPIT_VERBOSE` | `false` | Enable verbose logging |

## Usage Examples

### Send Test Email

```bash
# Using Python
python3 -c "
import smtplib
from email.mime.text import MIMEText

msg = MIMEText('Test email body')
msg['Subject'] = 'Test Email'
msg['From'] = 'test@example.com'
msg['To'] = 'recipient@example.com'

with smtplib.SMTP('localhost', 1025) as smtp:
    smtp.send_message(msg)
"
```

### View via API

```bash
# List all messages (with auth)
curl -u admin:MailpitDev123 http://localhost:8025/api/v1/messages

# Get specific message
curl -u admin:MailpitDev123 http://localhost:8025/api/v1/message/{id}

# Delete all messages
curl -u admin:MailpitDev123 -X DELETE http://localhost:8025/api/v1/messages
```

### Python Client

```python
from ui_tests.mailpit_client import MailpitClient

# Connect with auth
mailpit = MailpitClient(
    base_url="http://localhost:8025",
    auth=("admin", "MailpitDev123")
)

# Wait for specific email
msg = mailpit.wait_for_message(
    predicate=lambda m: "verification" in m.subject.lower(),
    timeout=10.0
)

# Extract content
full_msg = mailpit.get_message(msg.id)
print(full_msg.text)

# Clean up
mailpit.delete_message(msg.id)
mailpit.close()
```

## Integration with Flask

Configure Flask to send emails to Mailpit:

```python
# In Flask app config
MAIL_SERVER = 'naf-mailpit'  # Container hostname
MAIL_PORT = 1025
MAIL_USE_TLS = False
MAIL_USE_SSL = False
MAIL_USERNAME = None  # SMTP auth not required for testing
MAIL_PASSWORD = None
```

## Troubleshooting

### Web UI not accessible

```bash
# Check if container is running
docker ps | grep naf-mailpit

# Check logs
docker compose logs

# Verify port binding
docker port naf-mailpit
# Should show: 8025/tcp -> 0.0.0.0:8025
```

### Authentication fails

```bash
# Verify credentials in .env
cat .env | grep MAILPIT

# Restart after changing credentials
docker compose restart
```

### SMTP connection refused

```bash
# Test SMTP connection
telnet localhost 1025
# Should show: 220 Mailpit ESMTP Service Ready

# From container
telnet naf-mailpit 1025
```

## Related Documentation

- [MAILPIT_CONFIGURATION.md](../../docs/MAILPIT_CONFIGURATION.md) - Complete configuration guide
- [TESTING_LESSONS_LEARNED.md](../../docs/TESTING_LESSONS_LEARNED.md) - Testing patterns
- [Mailpit Official Docs](https://mailpit.axllent.org/docs/)
