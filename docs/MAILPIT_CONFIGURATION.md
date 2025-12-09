# Mailpit Configuration and Integration

## Overview

Mailpit is a modern SMTP testing server with a web UI for viewing captured emails during development and testing. This document covers configuration, authentication, and integration with the local TLS proxy.

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

### 2. With Basic Authentication

Update [`tooling/mock-services/docker-compose.yml`](../tooling/mock-services/docker-compose.yml):

```yaml
services:
  mailpit:
    image: axllent/mailpit:latest
    container_name: naf-mailpit
    hostname: naf-mailpit
    environment:
      # ... existing settings ...
      
      # Basic auth for web UI and API
      MP_UI_AUTH: "admin:SecurePassword123"
      
      # Or use password file (more secure)
      # MP_UI_AUTH_FILE: /config/passwords.txt
    # volumes:
    #   - ./mailpit-config/passwords.txt:/config/passwords.txt:ro
```

**Password File Format** (`passwords.txt`):
```
admin:$apr1$abc123def$HashedPasswordHere
user:$apr1$xyz789abc$AnotherHashedPassword
```

Generate passwords with Apache `htpasswd`:
```bash
htpasswd -n admin
# Enter password when prompted
# Output: admin:$apr1$...
```

### 3. Access with Authentication

```bash
# Browser (prompts for credentials)
open http://localhost:8025

# API with credentials
curl -u admin:SecurePassword123 http://localhost:8025/api/v1/messages
```

---

## Integration with Local TLS Proxy

To access Mailpit through the main application URL (e.g., `https://naf.example.com/mailpit`), configure nginx reverse proxy.

### Step 1: Update nginx Configuration Template

Edit [`tooling/reverse-proxy/nginx.conf.template`](../tooling/reverse-proxy/nginx.conf.template):

```nginx
server {
    listen 443 ssl http2;
    server_name ${LOCAL_TLS_DOMAIN};

    # ... existing SSL config ...

    # Main application (Flask backend)
    location / {
        proxy_pass http://${BACKEND_HOST}:${BACKEND_PORT};
        # ... existing proxy settings ...
    }

    # Mailpit web UI
    location /mailpit/ {
        # Remove /mailpit prefix before proxying
        rewrite ^/mailpit/(.*) /$1 break;
        
        proxy_pass http://naf-mailpit:8025;
        proxy_http_version 1.1;
        
        # WebSocket support (for real-time UI updates)
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Standard proxy headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Optional: Pass through basic auth credentials
        proxy_set_header Authorization $http_authorization;
        proxy_pass_header Authorization;
    }
}
```

### Step 2: Rebuild and Restart Proxy

```bash
cd tooling/reverse-proxy

# Regenerate nginx config from template
./render-nginx-conf.sh

# Stage inputs (copy config and certs)
./stage-proxy-inputs.sh

# Restart proxy
docker compose down
docker compose up -d
```

### Step 3: Access via HTTPS

```bash
# Example URL
open https://naf.example.com/mailpit/

# Or with authentication
curl -u admin:SecurePassword123 https://naf.example.com/mailpit/api/v1/messages
```

---

## Mailpit Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `MP_UI_BIND_ADDR` | `0.0.0.0:8025` | Web UI listen address |
| `MP_SMTP_BIND_ADDR` | `0.0.0.0:1025` | SMTP listen address |
| `MP_UI_AUTH` | - | Space-separated `user:pass` pairs (ENV only, not CLI) |
| `MP_UI_AUTH_FILE` | - | Path to htpasswd-style password file |
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

# With authentication
mailpit = MailpitClient(
    base_url="http://naf-mailpit:8025",
    auth=("admin", "SecurePassword123")
)

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

**Authentication in Tests**:
```python
# Read credentials from environment or .env file
MAILPIT_USER = os.environ.get("MAILPIT_USER", "admin")
MAILPIT_PASS = os.environ.get("MAILPIT_PASSWORD", "")

if MAILPIT_PASS:
    mailpit = MailpitClient(auth=(MAILPIT_USER, MAILPIT_PASS))
else:
    mailpit = MailpitClient()  # No auth
```

---

## Security Considerations

### Development vs Production

| Environment | Authentication | Access |
|-------------|----------------|--------|
| **Local Development** | Optional | Localhost only |
| **CI/CD** | Optional | Isolated network |
| **Staging/Production** | **Required** | Behind TLS proxy with auth |

### Best Practices

1. **Enable authentication** when exposing Mailpit outside localhost
2. **Use password file** instead of `MP_UI_AUTH` (ENV vars visible in `docker inspect`)
3. **Restrict network access** - Mailpit should not be internet-facing
4. **Use TLS proxy** - Always access via HTTPS in staging/production
5. **Rotate passwords** - Change default credentials immediately

### Password File Security

```bash
# Generate secure password file
htpasswd -c mailpit-passwords.txt admin
# Enter password (min 12 chars, mixed case + numbers + symbols)

# Set restrictive permissions
chmod 600 mailpit-passwords.txt

# Mount read-only in container
# docker-compose.yml:
#   volumes:
#     - ./mailpit-passwords.txt:/config/passwords.txt:ro
```

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

### Issue: Authentication Always Fails

**Symptoms**: Web UI shows 401 Unauthorized despite correct credentials

**Solutions**:
1. Verify credentials format in `MP_UI_AUTH`:
   ```yaml
   # ✅ Correct
   MP_UI_AUTH: "admin:password"
   
   # ❌ Wrong
   MP_UI_AUTH: "admin password"  # Missing colon
   MP_UI_AUTH: "admin:password user:pass"  # Multiple users need space
   ```

2. Check password file format:
   ```bash
   cat mailpit-passwords.txt
   # Should be: username:$apr1$salt$hash
   ```

3. Restart container after config change:
   ```bash
   docker restart naf-mailpit
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

# With auth
curl -u admin:password http://naf-mailpit:8025/api/v1/messages
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
- [Testing Strategy](TESTING_STRATEGY.md) - Overall testing architecture
- [UI Testing Guide](UI_TESTING_GUIDE.md) - Comprehensive UI testing approach
- [Mailpit Official Docs](https://mailpit.axllent.org/docs/) - Complete feature reference

---

## History

| Date | Change | Author |
|------|--------|--------|
| 2024-12-08 | Initial documentation | AI Agent |
| 2024-12-08 | Renamed container to `naf-mailpit` | AI Agent |

---

**QUICK REFERENCE**:
- Web UI: `http://localhost:8025` (or `/mailpit/` via TLS proxy)
- SMTP: `naf-mailpit:1025`
- API: `http://naf-mailpit:8025/api/v1`
- Container: `naf-mailpit`
- Service name: `mailpit` (in `tooling/mock-services/docker-compose.yml`)
