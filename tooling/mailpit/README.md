# Mailpit - SMTP Testing Server

Modern SMTP testing server with web UI for email capture during development and testing.

## Quick Start

Mailpit is a **ciu-managed** stack — there is no `docker-compose.yml` in this directory.
`ciu.compose.yml` is a RENDERED, gitignored artifact; edit `ciu.compose.yml.j2` (or the
name/image/port scalars in `ciu.defaults.toml.j2`), never the rendered output.
Load this checkout's generated environment before any ciu command.

```bash
eval "$(ciu env print)"

# Start Mailpit (also started by `run-gate local-build --with-mocks`)
ciu up --dir tooling/mailpit

# View logs
docker logs -f naf-<INSTANCE_ID>-mailpit

# Stop only this checkout's Mailpit stack
ciu down --dir tooling/mailpit
```

## Access

- **Web UI**: http://localhost:8025
- **SMTP**: `naf-<INSTANCE_ID>-mailpit:1025` from peers on the checkout network
- **API**: `http://naf-<INSTANCE_ID>-mailpit:8025/mailpit/api/v1`

## Authentication

None. Mailpit is internal-only (no traefik labels, no host ports), so its UI/API
runs without auth and test processes need no credentials. Never publish it.

## Configuration

Stack-local settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `MAILPIT_WEB_PORT` | `8025` | Web UI/API port |
| `MAILPIT_SMTP_PORT` | `1025` | SMTP port |
| `DOCKER_NETWORK_INTERNAL` | checkout network | Generated per-checkout ciu network identity |
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
MAIL_SERVER = 'naf-<INSTANCE_ID>-mailpit'  # resolved container hostname
MAIL_PORT = 1025
MAIL_USE_TLS = False
MAIL_USE_SSL = False
MAIL_USERNAME = None  # SMTP auth not required for testing
MAIL_PASSWORD = None
```

## Troubleshooting

### Web UI not accessible

```bash
# Check if this checkout's container is running
docker ps --filter label=ciu.instance="$INSTANCE_ID"

# Check logs
docker logs naf-<INSTANCE_ID>-mailpit

# Mailpit is internal-only: reach it on this checkout's Docker network; it has no
# published host port.
```

### Authentication fails

```bash
# Verify credentials in .env
cat .env | grep MAILPIT

# Restart after changing credentials
docker restart naf-<INSTANCE_ID>-mailpit
```

### SMTP connection refused

```bash
# From a peer container on this checkout's network
telnet naf-<INSTANCE_ID>-mailpit 1025
```

## Related Documentation

- [MAILPIT_CONFIGURATION.md](../../docs/MAILPIT_CONFIGURATION.md) - Complete configuration guide
- [TESTING_LESSONS_LEARNED.md](../../docs/TESTING_LESSONS_LEARNED.md) - Testing patterns
- [Mailpit Official Docs](https://mailpit.axllent.org/docs/)
