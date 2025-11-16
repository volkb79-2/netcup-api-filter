# Security Hardening Guide

This document describes the security measures implemented in the Netcup API Filter and provides recommendations for secure deployment.

## Implemented Security Measures

### 1. Input Validation

#### Domain Name Validation
- **Protection**: Validates domain names against RFC 1035 specification
- **Implementation**: `validate_domain_name()` in `filter_proxy.py`
- **Prevents**: Domain injection attacks, DNS rebinding

#### Hostname Validation
- **Protection**: Validates DNS hostnames with support for wildcards
- **Implementation**: `validate_hostname()` in `filter_proxy.py`
- **Prevents**: Invalid hostname injection

#### Token Format Validation
- **Protection**: Tokens must be 32-128 character hex strings
- **Implementation**: Regex validation in `api_proxy()`
- **Prevents**: Token format attacks, invalid token injection

#### Pattern Validation (ReDoS Protection)
- **Protection**: Limits pattern length and character set in fnmatch patterns
- **Implementation**: `SAFE_PATTERN_REGEX` in `access_control.py`
- **Prevents**: Regular Expression Denial of Service (ReDoS) attacks
- **Max pattern length**: 100 characters
- **Allowed characters**: `a-zA-Z0-9\-\.\*_/`

### 2. Request Size Limits

#### Maximum Content Length
- **Protection**: Limits request body size to 10MB
- **Implementation**: `app.config['MAX_CONTENT_LENGTH']`
- **Prevents**: Memory exhaustion, DoS attacks

#### Maximum Records Per Request
- **Protection**: Limits DNS record updates to 100 records per request
- **Implementation**: Check in `handle_update_dns_records()`
- **Prevents**: Resource exhaustion

#### Configuration File Size Limit
- **Protection**: Limits config.yaml to 1MB
- **Implementation**: Size check in `load_config()`
- **Prevents**: YAML bomb attacks

### 3. Rate Limiting

#### Global Rate Limits
- **Default**: 200 requests per hour, 50 per minute
- **Implementation**: Flask-Limiter with in-memory storage
- **Scope**: Per IP address

#### API Endpoint Rate Limits
- **Limit**: 10 requests per minute per IP
- **Implementation**: `@limiter.limit("10 per minute")` decorator
- **Prevents**: Brute force attacks, API abuse, DoS

#### Health Check Exemption
- **Path**: `/` (health check endpoint)
- **Implementation**: `@limiter.exempt` decorator
- **Reason**: Allow monitoring without rate limiting

### 4. Authentication & Authorization

#### Token Storage
- **Method**: Tokens stored in configuration with SHA-256 hashing recommended
- **Location**: `config.yaml` (file permissions: 600)
- **Never logged**: Tokens are never logged in application logs

#### Multi-Layer Authorization
1. **Token validation**: Check if token exists
2. **Origin validation**: Check IP/domain whitelist
3. **Permission validation**: Check domain/record permissions
4. **Operation validation**: Check allowed operations

#### IP/Domain Whitelisting
- **Support**: Single IPs, CIDR networks, domains, wildcards
- **Implementation**: `check_origin()` in `access_control.py`
- **Benefits**: Prevents token replay from unauthorized locations

### 5. Security Headers

All responses include security headers:

```
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
Content-Security-Policy: default-src 'none'
Referrer-Policy: no-referrer
```

- **Prevents**: Clickjacking, MIME sniffing, XSS, information leakage

### 6. Content-Type Validation

- **Required**: `Content-Type: application/json`
- **Implementation**: Check in `api_proxy()`
- **Prevents**: Content confusion attacks

### 7. Error Handling

#### No Stack Trace Exposure
- **Implementation**: Generic error messages in production
- **Logged**: Detailed errors logged server-side only
- **Prevents**: Information disclosure

#### Structured Error Messages
```json
{
  "status": "error",
  "message": "Generic error message"
}
```

### 8. Logging Security

#### What is Logged
- Authentication failures (without token values)
- Authorization failures
- Invalid requests
- IP addresses of failed attempts

#### What is NOT Logged
- Valid tokens
- API credentials
- Full request/response bodies containing sensitive data

### 9. Token in Query Parameters (Deprecated)

⚠️ **Security Warning**: Token in query parameters is supported for backward compatibility but **not recommended**.

**Issues:**
- Tokens may appear in access logs
- Tokens may be stored in browser history
- Tokens may be sent in Referer header

**Recommendation**: Always use `Authorization` header:
```
Authorization: ******
```

### 10. YAML Deserialization Protection

- **Method**: Using `yaml.safe_load()` instead of `yaml.load()`
- **File size limit**: 1MB
- **Prevents**: Remote code execution, YAML bombs

---

## Deployment Security Recommendations

### 1. HTTPS/TLS Enforcement

**Critical**: Always deploy behind HTTPS in production.

#### Using Nginx as Reverse Proxy

```nginx
server {
    listen 443 ssl http2;
    server_name api.example.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name api.example.com;
    return 301 https://$server_name$request_uri;
}
```

#### Using Caddy

```caddyfile
api.example.com {
    reverse_proxy localhost:5000
}
```

### 2. Configuration File Security

```bash
# Set restrictive permissions
chmod 600 config.yaml
chown www-data:www-data config.yaml  # Adjust user as needed

# Verify
ls -l config.yaml
# Should show: -rw------- 1 www-data www-data
```

### 3. Token Generation

Always use cryptographically secure random tokens:

```bash
# Generate secure token (recommended)
python generate_token.py --description "..." --domain ... --record-name ... --record-types ... --operations ...

# Or manually
openssl rand -hex 32
```

**Never use**:
- Predictable patterns
- Sequential numbers
- Dictionary words
- Short tokens (< 32 characters)

### 4. IP Whitelisting (Recommended)

Always restrict tokens to specific IP addresses when possible:

```yaml
tokens:
  - token: "..."
    allowed_origins:
      - "203.0.113.50"      # Production server
      - "198.51.100.0/24"   # Office network
```

### 5. Principle of Least Privilege

Grant minimum required permissions:

```yaml
# ✅ GOOD: Specific permissions
permissions:
  - domain: "example.com"
    record_name: "host1"
    record_types: ["A"]
    operations: ["read", "update"]

# ❌ BAD: Overly broad permissions
permissions:
  - domain: "*"
    record_name: "*"
    record_types: ["*"]
    operations: ["*"]
```

### 6. Monitor Access Logs

Regularly review logs for:
- Repeated authentication failures
- Access from unexpected IPs
- Unusual request patterns
- Rate limit violations

```bash
# Example: Check for authentication failures
grep "Invalid token" /var/log/netcup-filter/app.log | tail -20

# Example: Check for rate limit violations
grep "Rate limit exceeded" /var/log/netcup-filter/app.log
```

### 7. Firewall Rules

Restrict access at network level:

```bash
# Example: UFW firewall
sudo ufw allow from 203.0.113.0/24 to any port 5000
sudo ufw deny 5000
```

### 8. Keep Dependencies Updated

```bash
# Check for updates
pip list --outdated

# Update packages
pip install --upgrade -r requirements.txt

# Security audit
pip-audit  # Install with: pip install pip-audit
```

### 9. Disable Debug Mode in Production

Ensure in `config.yaml`:
```yaml
server:
  debug: false  # NEVER true in production
```

### 10. Environment Isolation

Run the application with limited privileges:

```bash
# Create dedicated user
sudo useradd -r -s /bin/false netcup-filter

# Run as unprivileged user
sudo -u netcup-filter python filter_proxy.py
```

---

## Security Checklist for Production Deployment

- [ ] HTTPS/TLS enabled and enforced
- [ ] Debug mode disabled (`debug: false`)
- [ ] Config file permissions set to 600
- [ ] Strong, random tokens generated
- [ ] IP whitelisting configured where applicable
- [ ] Principle of least privilege applied to all tokens
- [ ] Rate limiting enabled (default)
- [ ] Security headers enabled (automatic)
- [ ] Firewall rules configured
- [ ] Application running as unprivileged user
- [ ] Logs monitored regularly
- [ ] Dependencies up to date
- [ ] Backup of configuration file
- [ ] Token rotation schedule established

---

## Known Limitations & Mitigations

### Rate Limiting Storage

**Current**: In-memory storage (resets on restart)
**Limitation**: Distributed deployments need shared storage
**Mitigation**: For production, use Redis:

```python
# In filter_proxy.py
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    storage_uri="redis://localhost:6379",
)
```

### Session Management

**Current**: Simple session handling in NetcupClient
**Limitation**: Sessions may expire during long operations
**Mitigation**: Automatic retry with re-login implemented

---

## Incident Response

### If a Token is Compromised

1. **Immediately**:
   - Remove token from `config.yaml`
   - Restart application
   - Check logs for unauthorized access

2. **Investigate**:
   - Review access logs for the compromised token
   - Identify potentially affected DNS records
   - Verify current DNS configuration

3. **Remediate**:
   - Generate new token
   - Update client configuration
   - Consider additional IP restrictions

4. **Prevent**:
   - Review token distribution process
   - Implement stricter IP whitelisting
   - Consider shorter token rotation schedule

### Suspected Attack

1. Check rate limit logs
2. Review authentication failure patterns
3. Check for unusual request patterns
4. Temporarily increase rate limits if false positive
5. Block attacking IPs at firewall level if confirmed

---

## Security Reporting

If you discover a security vulnerability:

1. **Do NOT** open a public issue
2. Contact the maintainer privately
3. Provide detailed reproduction steps
4. Allow time for fix before disclosure

---

## Compliance & Best Practices

This implementation follows:
- OWASP Top 10 mitigation strategies
- CIS Benchmarks for web application security
- NIST guidelines for access control
- RFC standards for DNS operations

---

## Additional Resources

- [OWASP Web Application Security](https://owasp.org/)
- [CIS Benchmarks](https://www.cisecurity.org/cis-benchmarks)
- [Flask Security Best Practices](https://flask.palletsprojects.com/en/latest/security/)
- [Netcup API Documentation](https://helpcenter.netcup.com/en/wiki/domain/our-api)

## Admin UI Security (New in v2.0)

### Authentication & Session Management

#### Secure Cookie Configuration
- **SESSION_COOKIE_SECURE=True**: Cookies only sent over HTTPS
- **SESSION_COOKIE_HTTPONLY=True**: Prevents JavaScript access to cookies
- **SESSION_COOKIE_SAMESITE=Lax**: CSRF protection
- **PERMANENT_SESSION_LIFETIME=3600**: 1-hour session timeout

#### Persistent Secret Key
- Stored in `.secret_key` file with 600 permissions
- Falls back to `SECRET_KEY` environment variable
- Prevents session invalidation on restart

#### Account Lockout Protection
- **5 failed login attempts** = 15-minute lockout per IP
- Automatic lockout expiration
- Failed attempt counter stored in database

### CSRF Protection

- **Flask-Admin SecureForm** with CSRF tokens on all forms
- **SameSite cookie attribute** for additional protection
- **CSRF validation** on all state-changing operations

### Content Security Policy

#### Admin UI (`/admin/*`):
```
default-src 'self';
script-src 'self' 'unsafe-inline' [CDN allowlist];
style-src 'self' 'unsafe-inline' [CDN allowlist];
img-src 'self' data:;
font-src 'self' [CDN allowlist];
connect-src 'self'
```

#### API endpoints:
```
default-src 'none'; frame-ancestors 'none'
```

### Additional HTTP Security Headers

- **X-Frame-Options: SAMEORIGIN** - Prevents clickjacking
- **Strict-Transport-Security** - Forces HTTPS (when available)
- **Referrer-Policy: strict-origin-when-cross-origin** - Limits referrer leakage

### Admin UI Security Checklist

Before exposing admin UI to the internet:

- [ ] Changed default admin password (`admin`/`admin`)
- [ ] Set strong `SECRET_KEY` environment variable
- [ ] Configured HTTPS with valid SSL certificate
- [ ] Verified secure cookie settings are applied
- [ ] Tested account lockout mechanism (5 failed attempts)
- [ ] Configured admin email for security alerts
- [ ] Restricted admin UI access by IP (if possible)
- [ ] Enabled HSTS header
- [ ] Verified CSRF tokens on all forms
- [ ] Tested session timeout (1 hour)
- [ ] Backed up `.secret_key` file securely
- [ ] Set database file permissions to 600

### Admin UI Attack Surface

**Exposed endpoints:**
- `/admin/login` - Login page (rate limited via lockout)
- `/admin/*` - All admin views (requires authentication)

**Mitigations:**
1. Account lockout after 5 failed attempts
2. CSRF protection on all forms
3. Secure session cookies
4. XSS protection via CSP headers
5. Forced password change from default
6. Bcrypt password hashing (cost factor 12)

### Recommended Network-Level Protection

For maximum security, restrict admin UI access:

**Apache .htaccess:**
```apache
<Location /admin>
    # Allow only specific IPs
    Require ip 192.168.1.0/24
    Require ip 10.0.0.1
</Location>
```

**Firewall rules:**
```bash
# Allow admin UI only from specific IPs
iptables -A INPUT -p tcp --dport 443 -s 192.168.1.0/24 -j ACCEPT
iptables -A INPUT -p tcp --dport 443 -j DROP
```

### Security Monitoring

**Monitor these events:**
1. Failed login attempts (audit logs)
2. Account lockouts (system logs)
3. Password changes (audit logs)
4. Client token creations (audit logs)
5. Configuration changes (audit logs)

**Alert on:**
- 3+ failed logins from same IP in 1 minute
- 10+ failed logins from different IPs in 5 minutes
- Password change for admin user
- Database file permission changes

