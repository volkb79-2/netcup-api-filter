# netcup-api-filter

A security proxy for the Netcup DNS API that provides granular access control.

## Problem

The Netcup API uses credentials (API key, password, customer ID) that provide full access to all DNS operations including:
- Viewing all domains and DNS records
- Modifying any DNS record
- Ordering new domains
- Other potentially dangerous operations

This poses a significant security risk when you need to grant limited access, such as:
- A host that should only update its own A record
- A monitoring system that should only read DNS records
- An automation script that should only manage specific subdomains

## Solution

This project implements a filtering proxy that sits between clients and the Netcup API, providing:
- **Token-based authentication**: Each client gets a unique token instead of full API credentials
- **Granular access control**: Define exactly what each token can access
- **Operation filtering**: Restrict tokens to specific operations (read, update, create, delete)
- **Domain and record filtering**: Limit access to specific domains and DNS record patterns
- **Record type filtering**: Allow access only to specific record types (A, AAAA, CNAME, etc.)

## Features

- ✅ **Token-based authentication** with bcrypt hashing
- ✅ **Granular access control** with realm-based domain matching
- ✅ **Admin web UI** for easy management (Flask-Admin)
- ✅ **Email notifications** for API access and security events
- ✅ **Comprehensive audit logging** to file and database
- ✅ **Database storage** (SQLite) for configuration and logs
- ✅ **YAML to database migration** tool
- ✅ **Phusion Passenger support** for webhosting deployment
- ✅ **Rate limiting** to prevent abuse
- ✅ **IP/network whitelisting** for origin restrictions

## Architecture

```
Client (with limited token)
    ↓
Netcup API Filter Proxy (validates permissions)
    ↓
Netcup API (full credentials stored securely)
```

## Admin Web UI

The filter includes a comprehensive admin web interface for managing clients, viewing logs, and configuring the system.

**Access:** Navigate to `/admin` after starting the application.

**Default credentials:** `admin` / `admin` (you will be forced to change this on first login)

### Admin UI Features:

1. **Dashboard** - Overview of clients, logs, and recent activity
2. **Client Management** - Create, edit, and manage API tokens with granular permissions
3. **Audit Logs** - View and search all API access attempts
4. **Netcup API Configuration** - Configure Netcup API credentials
5. **Email Settings** - Configure SMTP for notifications with test email functionality
6. **System Information** - View filesystem access, Python environment, and database location

### Managing Clients:

- Create new clients with auto-generated secure tokens
- Configure realm type (host = exact domain match, subdomain = *.subdomain pattern)
- Limit allowed DNS record types (A, AAAA, CNAME, NS only)
- Restrict operations (read, update, create, delete)
- Set IP/network access restrictions
- Enable email notifications per client
- Set token expiration dates
- Deactivate tokens without deleting them

### Email Notifications:

**Client notifications (per-client setting):**
- Sent on every API access when enabled
- Includes timestamp, operation, IP, result, and details

**Admin notifications (security events):**
- Authentication failures
- Permission denials
- Origin restriction violations
- Sent to configured admin email address

All emails are sent asynchronously with a 5-second delay to avoid blocking API responses.

### Audit Logging:

All API requests are logged to:
- **Database** - SQLite for easy querying through admin UI
- **File** - Text log with structured format (no automatic rotation)

Logs include:
- Timestamp
- Client ID
- IP address
- Operation performed
- Domain and DNS records
- Success/failure status
- Full request and response data (with sensitive data masked)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/volkb79-2/netcup-api-filter.git
cd netcup-api-filter
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Initialize the application:

**Option A: Using Admin UI (Recommended)**

Start the application with Passenger or standalone mode, then:
- Navigate to `/admin` and login with `admin`/`admin`
- Configure Netcup API credentials through the UI
- Create clients with tokens through the UI
- Configure email settings if desired

**Option B: Using YAML configuration (Legacy)**

```bash
cp config.example.yaml config.yaml
# Edit config.yaml with your settings
python migrate_yaml_to_db.py  # Migrate to database
```

4. Start the application:

**Standalone mode:**
```bash
python filter_proxy.py
```

**Webhosting (Passenger):**
See [WEBHOSTING_DEPLOYMENT.md](WEBHOSTING_DEPLOYMENT.md) for detailed instructions.

## Quick Start

1. Install dependencies: `pip install -r requirements.txt`
2. Start the application: `python passenger_wsgi.py` (or use Passenger)
3. Open browser to `http://localhost:5000/admin`
4. Login with `admin` / `admin` (change password when prompted)
5. Configure Netcup API credentials in "Netcup API" menu
6. Create a client in "Clients" menu
7. Copy the generated token (shown only once!)
8. Use the token to make API requests

## Configuration

### Admin UI Configuration (Recommended)

All configuration is now managed through the admin web UI at `/admin`:

- **Netcup API Config** - API credentials, endpoint URL, timeout
- **Email Settings** - SMTP configuration for notifications
- **Clients** - Token management with granular permissions

### YAML Configuration (Legacy)

The `config.yaml` file is now only used for initial bootstrap. Most settings should be configured via the admin UI.

For reference, the `config.yaml` file has three main sections:

### 1. Netcup API Credentials

Store your actual Netcup API credentials here (keep this file secure!):

```yaml
netcup:
  customer_id: "123456"
  api_key: "your-api-key"
  api_password: "your-api-password"
  api_url: "https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON"
```

### 2. Access Tokens

Define tokens with specific permissions:

```yaml
tokens:
  - token: "host1-update-token"
    description: "Allow host1 to update its A record"
    permissions:
      - domain: "example.com"
        record_name: "host1"
        record_types: ["A"]
        operations: ["read", "update"]
```

**Token fields:**
- `token`: The authentication token clients will use
- `description`: Human-readable description of the token's purpose
- `permissions`: List of permission rules

**Permission fields:**
- `domain`: Domain name (supports wildcards, e.g., `*.example.com`)
- `record_name`: DNS record hostname (supports wildcards, e.g., `web*`)
- `record_types`: Array of allowed record types (`["A", "AAAA"]` or `["*"]` for all)
- `operations`: Array of allowed operations:
  - `read`: View zone info and DNS records
  - `update`: Modify existing DNS records
  - `create`: Create new DNS records
  - `delete`: Delete DNS records
  - `*`: All operations

### 3. Server Configuration

```yaml
server:
  host: "0.0.0.0"
  port: 5000
  debug: false
```

## Usage

### Generating Tokens

The filter includes a token generation tool that creates cryptographically secure tokens:

```bash
# Generate a token for a host to update its A record
python generate_token.py \
  --description "Host1 Dynamic DNS" \
  --domain example.com \
  --record-name host1 \
  --record-types A \
  --operations read,update

# Generate a token with IP whitelist (recommended for security)
python generate_token.py \
  --description "Server1 Updates" \
  --domain example.com \
  --record-name server1 \
  --record-types A,AAAA \
  --operations read,update \
  --allowed-origins "192.168.1.100,10.0.0.0/24"

# Generate a read-only monitoring token
python generate_token.py \
  --description "DNS Monitoring" \
  --domain example.com \
  --record-name "*" \
  --record-types "*" \
  --operations read
```

The tool outputs YAML configuration that you can add directly to your `config.yaml` file.

**Manual token generation** (if you prefer):
```bash
# Generate a secure random token (64 hex characters)
openssl rand -hex 32
```

Then add it to your `config.yaml` with appropriate permissions.

### Starting the Server

**Standalone mode** (for development or VPS):
```bash
python filter_proxy.py
```

Or with a custom config file:
```bash
python filter_proxy.py /path/to/config.yaml
```

**Webhosting deployment** (WSGI/CGI):

See [WEBHOSTING_DEPLOYMENT.md](WEBHOSTING_DEPLOYMENT.md) for detailed instructions on deploying to shared hosting environments like Netcup Webhosting.

Quick start for WSGI:
```bash
# Use wsgi.py for Apache with mod_wsgi
# See WEBHOSTING_DEPLOYMENT.md for .htaccess configuration
```

**Docker deployment**:
```bash
docker-compose up -d
```

### API Endpoint

The proxy exposes a single endpoint that mimics the Netcup API:

**Endpoint**: `POST /api`

**Authentication**: Include token in one of these ways:
- Header: `Authorization: Bearer your-token-here`
- Header: `X-API-Token: your-token-here`
- Query parameter: `?token=your-token-here`

**Request format** (same as Netcup API):
```json
{
  "action": "infoDnsRecords",
  "param": {
    "domainname": "example.com"
  }
}
```

### Example: Update a DNS Record

```bash
curl -X POST http://localhost:5000/api \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer host1-update-token" \
  -d '{
    "action": "updateDnsRecords",
    "param": {
      "domainname": "example.com",
      "dnsrecordset": {
        "dnsrecords": [
          {
            "id": "123456",
            "hostname": "host1",
            "type": "A",
            "destination": "192.168.1.100",
            "priority": "0",
            "state": "yes",
            "deleterecord": false
          }
        ]
      }
    }
  }'
```

### Example: Read DNS Records

```bash
curl -X POST http://localhost:5000/api \
  -H "Content-Type: application/json" \
  -H "X-API-Token: readonly-token" \
  -d '{
    "action": "infoDnsRecords",
    "param": {
      "domainname": "example.com"
    }
  }'
```

## Supported Actions

The proxy currently supports these Netcup API actions:

- `infoDnsZone`: Get DNS zone information
- `infoDnsRecords`: List DNS records (filtered by permissions)
- `updateDnsRecords`: Update DNS records (validated against permissions)

## Use Cases

### 1. Dynamic DNS for a Single Host

A host needs to update only its own A record with its current IP:

```yaml
tokens:
  - token: "dynamic-dns-host1"
    description: "Host1 dynamic DNS updates"
    permissions:
      - domain: "example.com"
        record_name: "host1"
        record_types: ["A"]
        operations: ["read", "update"]
```

### 2. Read-Only Monitoring

A monitoring system needs to read all DNS records but cannot modify them:

```yaml
tokens:
  - token: "monitoring-readonly"
    description: "DNS monitoring access"
    permissions:
      - domain: "example.com"
        record_name: "*"
        record_types: ["*"]
        operations: ["read"]
```

### 3. Subdomain Management

An automation script manages all web server records:

```yaml
tokens:
  - token: "web-automation"
    description: "Manage web* subdomains"
    permissions:
      - domain: "example.com"
        record_name: "web*"
        record_types: ["A", "AAAA", "CNAME"]
        operations: ["read", "update", "create", "delete"]
```

## Security Best Practices

1. **Protect the config.yaml file**: Contains your actual Netcup credentials
   - Set file permissions: `chmod 600 config.yaml`
   - Never commit to version control
   - Use environment variables or secret management in production

2. **Generate strong tokens**: Use the included token generator
   ```bash
   python generate_token.py --description "..." --domain ... --record-name ... --record-types ... --operations ...
   ```
   Or manually with:
   ```bash
   openssl rand -hex 32
   ```

3. **Use IP/domain whitelisting**: Restrict token usage to specific origins
   ```yaml
   tokens:
     - token: "your-secure-token"
       allowed_origins:
         - "192.168.1.100"      # Single IP
         - "10.0.0.0/24"        # CIDR network
         - "server.example.com" # Domain name
         - "*.internal.net"     # Wildcard domain
   ```
   This prevents token abuse even if intercepted.

4. **Apply principle of least privilege**: Grant only the minimum permissions needed

5. **Use HTTPS in production**: Deploy behind a reverse proxy (nginx, Caddy) with TLS

6. **Monitor access logs**: Review the application logs for suspicious activity
   - Invalid token attempts
   - Origin restriction violations
   - Permission denied events

7. **Rotate tokens regularly**: Change tokens periodically, especially if compromised

## Logging

The proxy logs all access attempts and permission checks. Monitor these logs for:
- Invalid token attempts
- Permission denied events
- API errors

## Requirements

- Python 3.7+
- Dependencies listed in `requirements.txt`

## License

MIT License

## Contributing

Contributions welcome! Please open an issue or pull request.

## Support

For Netcup API documentation, see:
- https://helpcenter.netcup.com/en/wiki/domain/our-api
- https://ccp.netcup.net/run/webservice/servers/endpoint.php
