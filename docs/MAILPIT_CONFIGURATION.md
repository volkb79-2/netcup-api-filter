# Mailpit Configuration and Integration

## Overview

Mailpit is a modern SMTP testing server with a web UI for viewing captured emails during development and testing. This document covers its local configuration.

**Container name**: resolved per checkout as `naf-<INSTANCE_ID>-mailpit`.

---

## Quick Start

### 1. Basic Usage (No Authentication)

```bash
# Start the ciu-managed Mailpit stack
ciu up --dir tooling/mailpit

# Resolve its checkout-local URL
source .env.services
echo "$MAILPIT_URL"

# SMTP endpoint (for Flask app)
# Host: naf-<INSTANCE_ID>-mailpit on the checkout network
# Port: 1025
```

---

## Access model

Mailpit is an internal test service. It has no public host-edge route or TLS material;
access its UI/API through `MAILPIT_URL` and `MAILPIT_API_URL` from `.env.services`, or
from a peer using the resolved container identity. The ciu stack in
[`tooling/mailpit/`](../tooling/mailpit/) is the current operational reference.
Its URL path prefix is configured once as `mailpit.web_root`; `.env.services` derives
`MAILPIT_URL` and `MAILPIT_API_URL` from that setting and the resolved container identity.

---

## Mailpit Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `MP_UI_BIND_ADDR` | `0.0.0.0:8025` | Web UI listen address |
| `MP_SMTP_BIND_ADDR` | `0.0.0.0:1025` | SMTP listen address |
| `MP_SMTP_AUTH_ACCEPT_ANY` | `true` | Accept any SMTP auth credentials for this test service |
| `MP_SMTP_AUTH_ALLOW_INSECURE` | `true` | Allow SMTP auth without TLS on the internal test network |
| `MP_MAX_MESSAGE_SIZE` | `mailpit.max_message_size_mb` | Max message size in megabytes (0 = unlimited); configured in the stack defaults |
| `MP_WEBROOT` | `mailpit.web_root` | UI/API path prefix; configured in the stack defaults |
| `MP_VERBOSE` | `false` | Enable verbose logging |

See [Mailpit Runtime Options](https://mailpit.axllent.org/docs/configuration/runtime-options/) for complete list.

---

## Python API Client Integration

The project includes `MailpitClient` for programmatic email access:

```python
import os
from ui_tests.mailpit_client import MailpitClient

# Connect using the URL resolved by `.env.services`
mailpit = MailpitClient(base_url=os.environ["MAILPIT_URL"])

# Wait for specific email
msg = mailpit.wait_for_message(
    predicate=lambda m: "verification" in m.subject.lower(),
    timeout=10.0
)

# Extract 2FA code from email body
full_msg = mailpit.get_message(msg.id)
code_match = re.search(r'\b(\d{6})\b', full_msg.text)
code = code_match.group(1)

# Clean up
mailpit.delete_message(msg.id)
mailpit.close()
```

**Authentication**: none. Mailpit is internal-only (no traefik labels, no host ports),
so `MailpitClient` takes no credentials.

---

## Security Considerations

### Access control

Mailpit runs **without UI/API auth**. That is safe only because the stack is
internal-only: no traefik labels, no host ports, reachable solely by peers on the
project network. Never add a public ingress or host port for it; if that ever becomes
necessary, put auth back first (`MP_UI_AUTH_FILE`, not `MP_UI_AUTH`, to keep secrets out
of `docker inspect`).

---

## Testing Workflows

### Workflow 1: 2FA Email Verification

```python
# 1. Trigger 2FA login
await browser.goto(settings.url("/admin/login"))
await browser.fill("#username", "admin")
await browser.fill("#password", "password")
await browser.click("button[type='submit']")

# 2. Wait for 2FA email
mailpit = MailpitClient()
msg = mailpit.wait_for_message(
    predicate=lambda m: "verification" in m.subject.lower(),
    timeout=10.0
)

# 3. Extract code and complete login
full_msg = mailpit.get_message(msg.id)
code = re.search(r'\b(\d{6})\b', full_msg.text).group(1)

# 4. Submit code via JavaScript (avoid race with auto-submit)
await browser.evaluate(f"""
    document.getElementById('code').value = '{code}';
    document.getElementById('twoFaForm').submit();
""")

# 5. Clean up
mailpit.delete_message(msg.id)
```

### Workflow 2: Account Registration Email

```python
# 1. Submit registration form
await browser.goto(settings.url("/account/register"))
await browser.fill("#email", "newuser@example.test")
# ... fill other fields ...
await browser.click("button[type='submit']")

# 2. Verify email was sent
mailpit = MailpitClient()
msg = mailpit.wait_for_message(
    predicate=lambda m: "newuser@example.test" in m.to,
    timeout=5.0
)

assert msg is not None, "Registration email not sent"
assert "Welcome" in msg.subject

# 3. Extract verification link
full_msg = mailpit.get_message(msg.id)
link_match = re.search(r'https?://[^\s]+/verify/[^\s]+', full_msg.html)
verify_link = link_match.group(0)

# 4. Visit verification link
await browser.goto(verify_link)
```

---

## Troubleshooting

### Issue: Mailpit Web UI Not Accessible

**Symptoms**: the resolved `$MAILPIT_URL/` is unreachable or returns an error

**Solutions**:
1. Verify this checkout's container is running:
   ```bash
   docker ps --filter label=ciu.instance="$INSTANCE_ID"
   ```

2. Check the Mailpit logs:
   ```bash
   docker logs "$MAILPIT_HOST"
   ```

3. Confirm `MP_WEBROOT` and the healthcheck both use `mailpit.web_root` from
   `tooling/mailpit/ciu.defaults.toml.j2`.

4. Test from a peer on the checkout network:
   ```bash
   curl "$MAILPIT_API_URL/info"
   ```

### Issue: SMTP Connection Refused

**Symptoms**: Flask app logs `Connection refused` to SMTP server

**Solutions**:
1. Test SMTP connection from a peer on the checkout network:
   ```bash
   telnet "$MAILPIT_HOST" 1025
   # Should connect and show Mailpit SMTP banner
   ```

2. Check Flask SMTP config matches the resolved container hostname:
   ```python
   import os

   SMTP_HOST = os.environ["MAILPIT_HOST"]
   SMTP_PORT = 1025
   ```

### Issue: WebSocket Connection Failed (Real-time Updates)

**Symptoms**: Web UI shows stale data, requires manual refresh

**Solutions**:
1. Check browser console for WebSocket errors.
2. Confirm the UI is reached through the internal Mailpit service URL; this
   stack has no public proxy route or published host port.

---

## API Reference

### List Messages

```bash
# Get all messages
curl "$MAILPIT_API_URL/messages"
```

### Get Message Content

```bash
# Get message by ID
curl "$MAILPIT_API_URL/message/{id}"

# Get HTML part
curl "$MAILPIT_API_URL/message/{id}/html"

# Get plain text part
curl "$MAILPIT_API_URL/message/{id}/text"
```

### Delete Messages

```bash
# Delete single message
curl -X DELETE "$MAILPIT_API_URL/message/{id}"

# Delete all messages
curl -X DELETE "$MAILPIT_API_URL/messages"
```

---

## Related Documentation

- [Testing Lessons Learned](TESTING_LESSONS_LEARNED.md) - Browser automation patterns (2FA, email verification)
- [Testing Strategy](deprecated/TESTING_STRATEGY.md) - Overall testing architecture
- [UI Testing Guide](UI_TESTING_GUIDE.md) - Comprehensive UI testing approach
- [Mailpit Official Docs](https://mailpit.axllent.org/docs/) - Complete feature reference

---

## History

| Date | Change | Author |
|------|--------|--------|
| 2024-12-08 | Initial documentation | AI Agent |
| 2024-12-08 | Renamed container to `naf-mailpit` | AI Agent |
| 2026-11-05 | UI/API auth removed (internal-only stack); client takes no credentials | AI Agent |

---

**QUICK REFERENCE**:
- Web UI: `$MAILPIT_URL/` (internal-only; path comes from `mailpit.web_root`)
- SMTP: `$MAILPIT_HOST:1025`
- API: `$MAILPIT_API_URL`
- Container: `$MAILPIT_HOST`
- Service name: `mailpit` (in `tooling/mailpit/ciu.compose.yml.j2`)
