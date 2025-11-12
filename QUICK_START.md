# Quick Start Guide

This guide helps you get the Netcup API Filter Proxy up and running in minutes.

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

## Step 2: Configuration

```bash
# Copy the example configuration
cp config.example.yaml config.yaml

# Edit the configuration with your details
nano config.yaml  # or use your favorite editor
```

### Minimal Configuration

Edit `config.yaml` and fill in your Netcup credentials:

```yaml
netcup:
  customer_id: "YOUR_CUSTOMER_ID"
  api_key: "YOUR_API_KEY"
  api_password: "YOUR_API_PASSWORD"
  api_url: "https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON"

tokens:
  - token: "my-first-token-change-this"
    description: "Test token for host1"
    permissions:
      - domain: "yourdomain.com"
        record_name: "host1"
        record_types: ["A"]
        operations: ["read", "update"]

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

1. **Generate Strong Tokens**: Use `openssl rand -hex 32` to generate secure tokens
2. **Protect config.yaml**: Set permissions with `chmod 600 config.yaml`
3. **Use HTTPS in Production**: Deploy behind nginx/Caddy with TLS certificates
4. **Monitor Logs**: Review application logs regularly for suspicious activity
5. **Apply Least Privilege**: Grant only the minimum permissions needed

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
