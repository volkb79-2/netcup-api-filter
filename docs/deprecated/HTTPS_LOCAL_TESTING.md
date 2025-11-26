# HTTPS Local Testing with Let's Encrypt Certificates

> **Status:** Archived. Follow the TLS workflow documented in `OPERATIONS_GUIDE.md` for current instructions.

## Quick Start

```bash
cd /workspaces/netcup-api-filter/tooling/local_proxy

# 1. Auto-detect FQDN and generate proxy.env
./auto-detect-fqdn.sh

# 2. Render nginx configuration
./render-nginx-conf.sh

# 3. Stage configuration for Docker (required in devcontainer)
./stage-proxy-inputs.sh

# 4. Create/join Docker network
docker network create naf-local 2>/dev/null || true
docker network connect naf-local "$(hostname)" 2>/dev/null || echo "Already connected"

# 5. Start Flask backend
cd /workspaces/netcup-api-filter
export FLASK_ENV="local_test"
export NETCUP_FILTER_DB_PATH="/workspaces/netcup-api-filter/tmp/local-https-test.db"
gunicorn passenger_wsgi:application -b 0.0.0.0:5100 --daemon \
  --access-logfile /workspaces/netcup-api-filter/tmp/https-gunicorn-access.log \
  --error-logfile /workspaces/netcup-api-filter/tmp/https-gunicorn-error.log

# 6. Start HTTPS proxy
cd /workspaces/netcup-api-filter/tooling/local_proxy
docker compose --env-file proxy.env up -d

# 7. Verify it's working
# Get detected FQDN
FQDN=$(grep LOCAL_TLS_DOMAIN proxy.env | cut -d= -f2)
curl -v --resolve "$FQDN:443:127.0.0.1" "https://$FQDN/" 2>&1 | grep "subject:"

# 8. Run tests (optional)
cd /workspaces/netcup-api-filter
UI_BASE_URL="https://$FQDN" pytest ui_tests/tests/test_admin_ui.py -v

# 9. Cleanup
docker compose --env-file proxy.env down
pkill -f "gunicorn.*passenger_wsgi"
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ Client (Browser/Playwright/curl)                                │
│   ↓                                                              │
│   curl --resolve "gstammtisch.dchive.de:443:127.0.0.1"          │
│        https://gstammtisch.dchive.de/                            │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Docker Host: 0.0.0.0:443 → local-proxy container                │
│                                                                  │
│   nginx (TLS termination)                                       │
│   - Cert: /etc/letsencrypt/live/gstammtisch.dchive.de/         │
│   - Real Let's Encrypt certificate                              │
│   - disable_symlinks off (follows archive/ symlinks)            │
│                                                                  │
│   ↓ proxy_pass http://netcup-api-filter-devcontainer:5100      │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Docker Network: naf-local (172.27.0.x)                          │
│                                                                  │
│   netcup-api-filter-devcontainer:5100                           │
│   - Gunicorn running passenger_wsgi:application                 │
│   - FLASK_ENV=local_test (disables Secure cookie flag)          │
│   - Same code as production deployment                          │
│   - Receives X-Forwarded-Proto: https from nginx                │
└─────────────────────────────────────────────────────────────────┘
```

## Why This Approach?

### Problem: Session Cookies Require Matching Protocol

From RFC 6265 (HTTP State Management Mechanism):
> If the Secure attribute is present, the user agent will only send the cookie over HTTPS connections.

**Production** (`https://naf.vxxu.de`):
- Flask config: `SESSION_COOKIE_SECURE = True`
- Protocol: HTTPS ✅
- Result: Browser sends cookies ✅

**Local HTTP** (`http://127.0.0.1:5100`):
- Flask config: `SESSION_COOKIE_SECURE = False` (via `FLASK_ENV=local_test`)
- Protocol: HTTP ✅
- Result: Browser sends cookies ✅

**Local HTTPS with Public FQDN** (`https://gstammtisch.dchive.de:443`):
- Flask config: `SESSION_COOKIE_SECURE = True` (no override)
- Protocol: HTTPS ✅
- Certificate: Real Let's Encrypt ✅
- Result: **100% production parity** ✅✅✅

### Benefits

1. **True Production Parity**: Same HTTPS, same certificates, same secure cookies
2. **No Browser Security Bypass**: Uses real certificates, not self-signed
3. **Observable**: Full access to Flask logs, database, and internal state
4. **Playwright Compatible**: MCP server can connect via real public FQDN
5. **CI-Ready**: Works in GitHub Actions with public runners (use `--resolve` flag)

## Configuration

### Auto-Detection Script

`./auto-detect-fqdn.sh` performs:

1. **External IP Detection**: Queries ipify.org, icanhazip.com, ifconfig.me, checkip.amazonaws.com
2. **Reverse DNS Lookup**: Uses `dig -x`, `host`, or `nslookup` on detected IP
3. **Certificate Path Computation**: `$LE_CERT_BASE/live/$DETECTED_FQDN/`
4. **proxy.env Generation**: Writes `LOCAL_TLS_DOMAIN`, `LE_CERT_BASE`, paths

**Options**:
- `--dry-run`: Print detected values without writing files
- `--verify-certs`: Check if Let's Encrypt certificates exist
- `--output FILE`: Write to custom file (default: `proxy.env`)

**Environment Overrides**:
- `FORCE_PUBLIC_IP`: Skip IP detection, use this IP
- `FORCE_FQDN`: Skip reverse DNS, use this FQDN
- `LE_CERT_BASE`: Base directory for Let's Encrypt (default: `/etc/letsencrypt`)

Example with override:
```bash
FORCE_FQDN=gstammtisch.dchive.de ./auto-detect-fqdn.sh --verify-certs
```

### Generated proxy.env

```bash
# Auto-generated by auto-detect-fqdn.sh
LOCAL_TLS_DOMAIN=gstammtisch.dchive.de
LOCAL_APP_HOST=__auto__  # Injected by run-ui-validation.sh
LOCAL_APP_PORT=5100
LOCAL_TLS_BIND_HTTPS=443
LOCAL_TLS_BIND_HTTP=80
LE_CERT_BASE=/etc/letsencrypt
LOCAL_PROXY_NETWORK=naf-local
LOCAL_PROXY_CONFIG_PATH=/tmp/netcup-local-proxy/conf.d
```

### Docker Compose Configuration

Key settings in `docker-compose.yml`:

```yaml
volumes:
  # ✅ CORRECT: Mount entire /etc/letsencrypt directory (preserves symlinks)
  - "${LE_CERT_BASE}:/etc/letsencrypt:ro"
  
  # ❌ WRONG: Mounting individual files breaks symlinks
  # - "/etc/letsencrypt/live/domain/privkey.pem:/certs/key.pem:ro"
```

### nginx Configuration

Key settings in `nginx.conf.template`:

```nginx
ssl_certificate     /etc/letsencrypt/live/${LOCAL_TLS_DOMAIN}/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/${LOCAL_TLS_DOMAIN}/privkey.pem;
ssl_protocols       TLSv1.2 TLSv1.3;
disable_symlinks    off;  # Required to follow archive/ symlinks
```

## Debugging

### 1. Verify Public IP and FQDN Detection

```bash
cd /workspaces/netcup-api-filter/tooling/local_proxy
./auto-detect-fqdn.sh --dry-run --verify-certs
```

Expected output:
```
[SUCCESS] Detected public IP: 152.53.179.117
[SUCCESS] Detected public FQDN: gstammtisch.dchive.de
[SUCCESS] Certificates verified:
  Fullchain: /etc/letsencrypt/live/gstammtisch.dchive.de/fullchain.pem -> ...
  Private Key: /etc/letsencrypt/live/gstammtisch.dchive.de/privkey.pem -> ...
```

### 2. Verify Certificates on Host

```bash
# Check certificate directory exists
docker run --rm -v /etc/letsencrypt:/certs:ro alpine:latest \
  ls -la /certs/live/

# Verify symlinks for your domain
docker run --rm -v /etc/letsencrypt:/certs:ro alpine:latest \
  ls -la /certs/live/gstammtisch.dchive.de/

# Test certificate content
docker run --rm -v /etc/letsencrypt:/certs:ro alpine:latest \
  cat /certs/live/gstammtisch.dchive.de/fullchain.pem | head -5
```

Expected:
```
lrwxrwxrwx ... fullchain.pem -> ../../archive/gstammtisch.dchive.de/fullchain2.pem
lrwxrwxrwx ... privkey.pem -> ../../archive/gstammtisch.dchive.de/privkey2.pem

-----BEGIN CERTIFICATE-----
MIIDmDCCAx6gAwIBAgISBaKw+01EhxnolrCfdQSv3VyNMAoGCCqGSM49BAMDMDIx
...
```

### 3. Verify Docker Network

```bash
# Create network if not exists
docker network create naf-local 2>/dev/null || true

# Connect devcontainer to network
DEVCONTAINER_NAME=$(hostname)
docker network connect naf-local "$DEVCONTAINER_NAME" 2>/dev/null || echo "Already connected"

# Verify connectivity
docker network inspect naf-local | grep -A 5 "Containers"
```

### 4. Verify Flask Backend

```bash
# Check if gunicorn is running
ps aux | grep "gunicorn.*passenger_wsgi"

# Check Flask logs
tail -f /workspaces/netcup-api-filter/tmp/https-gunicorn-error.log

# Test internal HTTP endpoint
curl http://$(hostname):5100/
```

### 5. Verify Nginx Proxy

```bash
# Check container status
docker ps | grep local-proxy

# Check nginx config
docker exec local-proxy cat /etc/nginx/conf.d/default.conf

# Check nginx logs
docker logs local-proxy

# Verify certificate paths in container
docker exec local-proxy ls -la /etc/letsencrypt/live/
```

### 6. Test HTTPS Connection

```bash
# Get FQDN from config
FQDN=$(grep LOCAL_TLS_DOMAIN proxy.env | cut -d= -f2)

# Test with curl (resolve to localhost)
curl -v --resolve "$FQDN:443:127.0.0.1" "https://$FQDN/" 2>&1 | grep -E "(subject:|issuer:)"

# Expected output:
# subject: CN=gstammtisch.dchive.de
# issuer: C=US; O=Let's Encrypt; CN=E5
```

### 7. Test from Playwright

```bash
cd /workspaces/netcup-api-filter

# Set base URL to HTTPS endpoint
export UI_BASE_URL="https://gstammtisch.dchive.de"
export UI_ADMIN_USERNAME="admin"
export UI_ADMIN_PASSWORD="admin"

# Run a single test
pytest ui_tests/tests/test_admin_ui.py::test_admin_authentication_flow -v
```

## Common Issues

### Issue: Certificate directory not found

**Symptom**:
```
[ERROR] Certificate directory does not exist: /etc/letsencrypt/live/gstammtisch.dchive.de
```

**Solution**:
1. Verify certificates exist on **host** (not devcontainer):
   ```bash
   docker run --rm -v /etc/letsencrypt:/certs:ro alpine:latest ls /certs/live/
   ```
2. If no certificates found, install certbot on host and obtain certificates:
   ```bash
   # On host machine (outside devcontainer)
   sudo apt-get install certbot
   sudo certbot certonly --standalone -d gstammtisch.dchive.de
   ```

### Issue: Reverse DNS returns wrong domain

**Symptom**:
```
[SUCCESS] Detected public FQDN: wrong-domain.example.com
```

**Solution**:
Force the correct FQDN:
```bash
FORCE_FQDN=gstammtisch.dchive.de ./auto-detect-fqdn.sh
```

### Issue: nginx fails to start with symlink errors

**Symptom**:
```
nginx: [emerg] cannot load certificate "/etc/letsencrypt/live/.../fullchain.pem"
```

**Solution**:
Verify `disable_symlinks off;` is in nginx config:
```bash
grep disable_symlinks /workspaces/netcup-api-filter/tooling/local_proxy/nginx.conf
```

If missing, re-render:
```bash
./render-nginx-conf.sh
./stage-proxy-inputs.sh
docker compose --env-file proxy.env restart
```

### Issue: Connection refused when accessing HTTPS

**Symptom**:
```
curl: (7) Failed to connect to gstammtisch.dchive.de port 443: Connection refused
```

**Solution**:
1. Check proxy container is running:
   ```bash
   docker ps | grep local-proxy
   ```
2. Check port binding:
   ```bash
   docker port local-proxy
   ```
3. Verify you're resolving to localhost:
   ```bash
   # Either use --resolve flag:
   curl --resolve "gstammtisch.dchive.de:443:127.0.0.1" https://gstammtisch.dchive.de/
   
   # Or update /etc/hosts (in container):
   echo "127.0.0.1 gstammtisch.dchive.de" | sudo tee -a /etc/hosts
   ```

### Issue: Flask receives HTTP instead of HTTPS

**Symptom**:
Secure cookies not working even with nginx proxy.

**Solution**:
Verify nginx sends `X-Forwarded-Proto: https`:
```bash
docker exec local-proxy cat /etc/nginx/conf.d/default.conf | grep X-Forwarded-Proto
```

Should show:
```
proxy_set_header X-Forwarded-Proto https;
```

## Integration with Existing Workflows

### With run-ui-validation.sh

The existing `tooling/run-ui-validation.sh` can be enhanced to use HTTPS:

```bash
# Before running tests, auto-detect FQDN and start HTTPS proxy
cd /workspaces/netcup-api-filter/tooling/local_proxy
./auto-detect-fqdn.sh
FQDN=$(grep LOCAL_TLS_DOMAIN proxy.env | cut -d= -f2)

# Export for run-ui-validation.sh
export UI_BASE_URL="https://$FQDN"
export LOCAL_TLS_DOMAIN="$FQDN"

cd /workspaces/netcup-api-filter
./tooling/run-ui-validation.sh
```

### With Playwright MCP Server

```bash
# Start HTTPS proxy first
cd /workspaces/netcup-api-filter/tooling/local_proxy
./auto-detect-fqdn.sh && ./render-nginx-conf.sh && ./stage-proxy-inputs.sh
docker compose --env-file proxy.env up -d

# Get FQDN
FQDN=$(grep LOCAL_TLS_DOMAIN proxy.env | cut -d= -f2)

# Start Playwright MCP with HTTPS URL
cd /workspaces/netcup-api-filter/tooling/playwright
export PLAYWRIGHT_START_URL="https://$FQDN"
docker compose up -d
```

### With CI/CD

GitHub Actions example:

```yaml
- name: Setup HTTPS testing
  run: |
    cd tooling/local_proxy
    FORCE_FQDN=gstammtisch.dchive.de ./auto-detect-fqdn.sh
    ./render-nginx-conf.sh
    docker network create naf-local
    docker compose --env-file proxy.env up -d
    
- name: Run HTTPS tests
  run: |
    FQDN=$(grep LOCAL_TLS_DOMAIN tooling/local_proxy/proxy.env | cut -d= -f2)
    pytest ui_tests/tests \
      --base-url="https://$FQDN" \
      --resolve="$FQDN:443:127.0.0.1"
```

## Production vs Local HTTPS Comparison

| Aspect | Production (Webhosting) | Local HTTPS (This Setup) |
|--------|------------------------|--------------------------|
| **URL** | https://naf.vxxu.de | https://gstammtisch.dchive.de |
| **Certificate** | Let's Encrypt (auto-renewed) | Let's Encrypt (same CA) |
| **TLS Termination** | Hoster's nginx/apache | Our nginx container |
| **Backend** | Phusion Passenger (passenger_wsgi) | Gunicorn (passenger_wsgi) |
| **Session Cookies** | Secure=True (HTTPS) | Secure=True (HTTPS) |
| **Observability** | Limited (FTP logs only) | **Full** (all logs accessible) |
| **Database** | SQLite (read-only via FTP) | SQLite (read-write) |
| **Code Updates** | FTP deploy (./build-and-deploy.sh) | Live editing in devcontainer |
| **Cost** | Webhosting subscription | Free (uses existing infrastructure) |

**Key Insight**: Local HTTPS setup provides 100% production parity for session cookies, TLS behavior, and browser security policies, while maintaining full debugging capabilities that production webhosting lacks.

## Performance Notes

- **Cold start**: ~5 seconds (nginx container + gunicorn boot)
- **Request latency**: +2-5ms vs direct HTTP (TLS handshake + nginx proxy overhead)
- **Certificate validation**: Cached by nginx after first request
- **Memory overhead**: ~10MB (nginx container) + gunicorn (same as HTTP testing)

## Security Considerations

1. **Read-Only Certificate Mount**: `LE_CERT_BASE` mounted `:ro` prevents accidental modification
2. **No Port Conflicts**: Uses standard 443/80 ports (requires root or port forwarding)
3. **Network Isolation**: Uses dedicated `naf-local` Docker network
4. **Secret Handling**: Private keys never leave host filesystem
5. **Container User**: nginx runs as `nginx:nginx` (not root) inside container

## Future Enhancements

1. **Automatic /etc/hosts Updates**: Script to inject FQDN → 127.0.0.1 mapping
2. **Certificate Renewal Testing**: Simulate certbot renewal workflow
3. **Multi-Domain Support**: Test with SAN certificates covering multiple FQDNs
4. **HTTP/2 Testing**: Verify modern protocol support
5. **WebSocket over HTTPS**: Test realtime features with TLS
