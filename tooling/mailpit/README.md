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

- **Web UI**: `$MAILPIT_URL/` (from `.env.services`; its path comes from `mailpit.web_root`)
- **SMTP**: `naf-<INSTANCE_ID>-mailpit:1025` from peers on the checkout network
- **API**: `$MAILPIT_API_URL` (from `.env.services`)

Source `.env.services` after the checkout's CIU environment is initialized; it resolves
these URLs from the container identity and the stack's configured webroot.

## Authentication

None. Mailpit is internal-only (no traefik labels, no host ports), so its UI/API
runs without auth and test processes need no credentials. Never publish it.

## Configuration

Stack-owned settings in `ciu.defaults.toml.j2`:

| Config key | Default | Description |
|------------|---------|-------------|
| `mailpit.web_port` | `8025` | Internal web UI/API port |
| `mailpit.smtp_port` | `1025` | Internal SMTP port |
| `mailpit.web_root` | Set in `ciu.defaults.toml.j2` | UI/API path prefix used by Compose, its healthcheck, and `.env.services` |
| `mailpit.max_message_size_mb` | `10` | Maximum message size in megabytes (Mailpit's unit; 0 = unlimited), rendered as `MP_MAX_MESSAGE_SIZE` |

The stack renders `mailpit.web_root` as `MP_WEBROOT`; neither the webroot nor the
message-size limit needs to be exported by the caller. `MAILPIT_VERBOSE` remains an
optional Compose environment override and defaults to `false`.

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
# List all messages
curl "$MAILPIT_API_URL/messages"

# Get specific message
curl "$MAILPIT_API_URL/message/{id}"

# Delete all messages
curl -X DELETE "$MAILPIT_API_URL/messages"
```

### Python Client

```python
from ui_tests.mailpit_client import MailpitClient

# Connect using the URL resolved by `.env.services`
mailpit = MailpitClient()

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

### Web UI returns 404

```bash
# Confirm the configured path is shared by Mailpit and its healthcheck.
rg -n 'web_root|MP_WEBROOT|healthcheck' tooling/mailpit/ciu.defaults.toml.j2 tooling/mailpit/ciu.compose.yml.j2
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
