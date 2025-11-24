# Quick Start Guide

This guide helps you get the Netcup API Filter Proxy up and running in minutes.

## 🎯 Configuration-Driven Architecture

All configuration comes from:
- **`.env.defaults`** - Version-controlled defaults (admin credentials, Flask settings)
- **Environment variables** - Override any default per environment
- **Admin UI** - Runtime configuration (Netcup API, clients, email settings)

No hardcoded values in code! See `CONFIG_DRIVEN_ARCHITECTURE.md` for complete details.

## Prerequisites

- Python 3.7 or higher
- Netcup API credentials (customer ID, API key, API password)
- A domain managed by Netcup

## Step 1: Installation

```bash
# Clone the repository
git clone https://github.com/volkb79-2/netcup-api-filter.git
cd netcup-api-filter

# Install dependencies
pip install -r requirements.txt
```

## Step 2: Start the Application

```bash
# Start in standalone mode
python passenger_wsgi.py
```

The application starts with default credentials from `.env.defaults`:
- Default admin username: `admin`
- Default admin password: `admin`
- You'll be forced to change the password on first login

## Step 3: Configure via Admin UI (Recommended)

1. **Open browser** to `http://localhost:5000/admin`
2. **Login** with credentials from `.env.defaults`
3. **Change password** when prompted
4. **Configure Netcup API:**
   - Go to "Configuration" → "Netcup API"
   - Enter your customer ID, API key, and API password
   - Click "Save"
5. **Create client tokens:**
   - Go to "Management" → "Clients"
   - Click "Create"
   - Set permissions (domain, operations, record types)
   - Copy the generated token (shown only once!)

**Done!** Your proxy is configured and ready to use.

## Alternative: YAML Configuration (Legacy)

You can also bootstrap from YAML if preferred:

```bash
# Copy the example configuration
cp config.example.yaml config.yaml

# Edit the configuration with your Netcup credentials
nano config.yaml  # or use your favorite editor
```

### Minimal YAML Configuration

Edit `config.yaml` and fill in your Netcup credentials:

```yaml
netcup:
  customer_id: "YOUR_CUSTOMER_ID"
  api_key: "YOUR_API_KEY"
  api_password: "YOUR_API_PASSWORD"
  api_url: "https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON"

tokens: []  # We'll generate tokens in the next step

server:
  host: "0.0.0.0"
  port: 5000
  debug: false
```

**Important**: Replace the placeholder values with your actual Netcup credentials.

### Generate Secure Tokens

Use the built-in token generator to create secure tokens:

```bash
# Generate a token for host1 to update its A record
python generate_token.py \
  --description "Host1 Dynamic DNS" \
  --domain yourdomain.com \
  --record-name host1 \
  --record-types A \
  --operations read,update

# Optional: Add IP whitelist for extra security
python generate_token.py \
  --description "Host1 Dynamic DNS" \
  --domain yourdomain.com \
  --record-name host1 \
  --record-types A \
  --operations read,update \
  --allowed-origins "192.168.1.100"
```

The tool will output YAML configuration. Copy the output and add it to your `config.yaml` under the `tokens:` section.

**Example output:**
```yaml
# Add this to your config.yaml file under 'tokens:'
  - description: Host1 Dynamic DNS
    permissions:
    - domain: yourdomain.com
      operations:
      - read
      - update
      record_name: host1
      record_types:
      - A
    token: f66ac29d22026b8ca0e59c9d4472e5f83782deb55b571b61f63c1bff50721fa7

# Token value (provide this to the client): f66ac29d22026b8ca0e59c9d4472e5f83782deb55b571b61f63c1bff50721fa7
```

Save the token value securely - you'll need to provide it to the client

server:
  host: "0.0.0.0"
  port: 5000
  debug: false
```

**Important**: 
- Replace `YOUR_CUSTOMER_ID`, `YOUR_API_KEY`, and `YOUR_API_PASSWORD` with your actual Netcup credentials
- Replace `yourdomain.com` with your actual domain
- Generate a strong random token (e.g., using `openssl rand -hex 32`)

## Step 3: Start the Server

```bash
python filter_proxy.py
```

You should see output like:
```
2025-11-12 03:55:02,534 - __main__ - INFO - Configuration loaded successfully. 1 tokens configured.
2025-11-12 03:55:02,534 - __main__ - INFO - Starting Netcup API Filter Proxy on 0.0.0.0:5000
 * Running on http://0.0.0.0:5000
```

## Step 4: Test the Server

### Health Check

```bash
curl http://localhost:5000/
```

Should return:
```json
{
  "service": "Netcup API Filter Proxy",
  "status": "running",
  "version": "1.0.0"
}
```

### Test DNS Query

```bash
curl -X POST http://localhost:5000/api \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer my-first-token-change-this" \
  -d '{
    "action": "infoDnsRecords",
    "param": {
      "domainname": "yourdomain.com"
    }
  }'
```

This will return DNS records that your token has permission to see.

## Step 5: Update a DNS Record

First, get the record ID from the previous query, then:

```bash
curl -X POST http://localhost:5000/api \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer my-first-token-change-this" \
  -d '{
    "action": "updateDnsRecords",
    "param": {
      "domainname": "yourdomain.com",
      "dnsrecordset": {
        "dnsrecords": [
          {
            "id": "RECORD_ID_HERE",
            "hostname": "host1",
            "type": "A",
            "destination": "YOUR_IP_ADDRESS",
            "priority": "0",
            "state": "yes",
            "deleterecord": false
          }
        ]
      }
    }
  }'
```

## Using Docker

```bash
# Build the image
docker build -t netcup-api-filter .

# Run with your config file
docker run -p 5000:5000 -v $(pwd)/config.yaml:/app/config.yaml:ro netcup-api-filter
```

Or use Docker Compose:

```bash
# Edit config.yaml first
docker-compose up -d
```

## Common Use Cases

### Dynamic DNS for a Host

Configure a token that allows a host to update only its own A record:

```yaml
tokens:
  - token: "host1-dyndns-token"
    description: "Dynamic DNS for host1"
    permissions:
      - domain: "example.com"
        record_name: "host1"
        record_types: ["A"]
        operations: ["read", "update"]
```

### Read-Only Monitoring

Create a token for monitoring systems that can only read records:

```yaml
tokens:
  - token: "monitoring-readonly"
    description: "Monitoring system readonly access"
    permissions:
      - domain: "example.com"
        record_name: "*"
        record_types: ["*"]
        operations: ["read"]
```

### Subdomain Management

Allow an automation script to manage specific subdomains:

```yaml
tokens:
  - token: "automation-web"
    description: "Manage web* subdomains"
    permissions:
      - domain: "example.com"
        record_name: "web*"
        record_types: ["A", "AAAA", "CNAME"]
        operations: ["read", "update", "create", "delete"]
```

## Security Tips

1. **Generate Strong Tokens**: Use the built-in token generator
   ```bash
   python generate_token.py --description "..." --domain ... --record-name ... --record-types ... --operations ...
   ```
   Or manually: `openssl rand -hex 32`

2. **Use IP Whitelisting**: Restrict tokens to specific IPs or domains
   ```bash
   python generate_token.py ... --allowed-origins "192.168.1.100,10.0.0.0/24"
   ```
   This prevents token abuse even if intercepted.

3. **Protect config.yaml**: Set permissions with `chmod 600 config.yaml`

4. **Use HTTPS in Production**: Deploy behind nginx/Caddy with TLS certificates

5. **Monitor Logs**: Review application logs regularly for suspicious activity

6. **Apply Least Privilege**: Grant only the minimum permissions needed

## Troubleshooting

### Server won't start

- Check if port 5000 is already in use: `lsof -i :5000`
- Verify config.yaml syntax with a YAML validator
- Check Python version: `python --version` (needs 3.7+)

### Authentication errors

- Verify your Netcup credentials in config.yaml
- Check if your token matches exactly (case-sensitive)
- Review server logs for detailed error messages

### Permission denied errors

- Review the permission rules in config.yaml
- Check if domain/hostname/record type matches the pattern
- Verify the operation (read/update/create/delete) is allowed

## Next Steps

- Read the full [README.md](README.md) for detailed documentation
- Customize token permissions for your use case
- Set up proper logging and monitoring
- Deploy to production with TLS/HTTPS

## Support

For issues or questions:
- Check the [README.md](README.md) documentation
- Review the Netcup API docs: https://helpcenter.netcup.com/en/wiki/domain/our-api
- Open an issue on GitHub
