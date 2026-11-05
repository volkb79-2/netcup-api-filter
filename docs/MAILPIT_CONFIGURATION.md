# Mailpit Configuration and Integration

## Overview

Mailpit is a modern SMTP testing server with a web UI for viewing captured emails during development and testing. This document covers its local configuration.

**Container Name**: `naf-mailpit` (as of 2024-12-08, prefixed for easy identification)

---

## Quick Start

### 1. Basic Usage (No Authentication)

```bash
# Start Mailpit with mock services
cd tooling/mock-services
docker compose up -d

# Access web UI
open http://localhost:8025

# SMTP endpoint (for Flask app)
# Host: naf-mailpit (or localhost from host)
# Port: 1025
```

---

## Access model

Mailpit is an internal test service. It has no public host-edge route or TLS material;
access its UI/API through its configured local port (normally `http://localhost:8025`) or
by container name (`http://naf-mailpit:8025`) from the project network. The ciu stack in
[`tooling/mailpit/`](../tooling/mailpit/) is the current operational reference.

---

## Mailpit Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `MP_UI_BIND_ADDR` | `0.0.0.0:8025` | Web UI listen address |
| `MP_SMTP_BIND_ADDR` | `0.0.0.0:1025` | SMTP listen address |
| `MP_SMTP_AUTH_ACCEPT_ANY` | `false` | Accept any SMTP auth credentials |
| `MP_SMTP_AUTH_ALLOW_INSECURE` | `false` | Allow SMTP auth without TLS |
| `MP_MAX_MESSAGE_SIZE` | `10485760` | Max email size (bytes, default 10MB) |
| `MP_VERBOSE` | `false` | Enable verbose logging |

See [Mailpit Runtime Options](https://mailpit.axllent.org/docs/configuration/runtime-options/) for complete list.

---

## Python API Client Integration

The project includes `MailpitClient` for programmatic email access:

```python
from ui_tests.mailpit_client import MailpitClient

# Connect (uses hostname 'naf-mailpit' or localhost)
mailpit = MailpitClient(base_url="http://naf-mailpit:8025")

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

**Symptoms**: `http://localhost:8025` times out or connection refused

**Solutions**:
1. Verify container is running:
   ```bash
   docker ps | grep naf-mailpit
   ```

2. Check port binding:
   ```bash
   docker port naf-mailpit
   # Should show: 8025/tcp -> 0.0.0.0:8025
   ```

3. Check logs:
   ```bash
   docker logs naf-mailpit
   ```

4. Test from inside devcontainer:
   ```bash
   curl http://naf-mailpit:8025/api/v1/info
   ```

### Issue: SMTP Connection Refused

**Symptoms**: Flask app logs `Connection refused` to SMTP server

**Solutions**:
1. Verify SMTP port:
   ```bash
   docker port naf-mailpit
   # Should show: 1025/tcp -> 0.0.0.0:1025
   ```

2. Test SMTP connection:
   ```bash
   telnet naf-mailpit 1025
   # Should connect and show Mailpit SMTP banner
   ```

3. Check Flask SMTP config matches container hostname:
   ```python
   SMTP_HOST = "naf-mailpit"  # Not "localhost" or "mailpit"
   SMTP_PORT = 1025
   ```

### Issue: WebSocket Connection Failed (Real-time Updates)

**Symptoms**: Web UI shows stale data, requires manual refresh

**Solutions**:
1. If behind nginx proxy, ensure WebSocket headers are set:
   ```nginx
   proxy_set_header Upgrade $http_upgrade;
   proxy_set_header Connection "upgrade";
   ```

2. Check browser console for WebSocket errors
3. Verify proxy is forwarding WebSocket traffic:
   ```bash
   docker logs netcup-api-filter-proxy | grep -i upgrade
   ```

---

## API Reference

### List Messages

```bash
# Get all messages
curl http://naf-mailpit:8025/api/v1/messages
```

### Get Message Content

```bash
# Get message by ID
curl http://naf-mailpit:8025/api/v1/message/{id}

# Get HTML part
curl http://naf-mailpit:8025/api/v1/message/{id}/html

# Get plain text part
curl http://naf-mailpit:8025/api/v1/message/{id}/text
```

### Delete Messages

```bash
# Delete single message
curl -X DELETE http://naf-mailpit:8025/api/v1/message/{id}

# Delete all messages
curl -X DELETE http://naf-mailpit:8025/api/v1/messages
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
- Web UI: `http://localhost:8025` (or `/mailpit/` via TLS proxy)
- SMTP: `naf-mailpit:1025`
- API: `http://naf-mailpit:8025/api/v1`
- Container: `naf-mailpit`
- Service name: `mailpit` (in `tooling/mock-services/docker-compose.yml`)
