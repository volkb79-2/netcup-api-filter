# Usage Examples

> Part of the active documentation set in `/docs`. See `docs/README.md` for context.

This document provides practical examples of using the Netcup API Filter in various scenarios.

## Table of Contents

1. [Token Generation Examples](#token-generation-examples)
2. [Common Use Cases](#common-use-cases)
3. [API Usage Examples](#api-usage-examples)
4. [Security Configurations](#security-configurations)

---

## Token Generation Examples

### Basic Dynamic DNS Token

Generate a token for a host to update its own A record:

```bash
python generate_token.py \
  --description "Home Server Dynamic DNS" \
  --domain example.com \
  --record-name home \
  --record-types A \
  --operations read,update
```

**Output:**
```yaml
  - description: Home Server Dynamic DNS
    permissions:
    - domain: example.com
      operations:
      - read
      - update
      record_name: home
      record_types:
      - A
    token: a7f3e2b8c9d1f0e5a4b3c2d1e0f9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1
```

Copy the token value and provide it to your client application.

### Token with IP Whitelist

Generate a token restricted to specific IP addresses:

```bash
python generate_token.py \
  --description "Office Server Updates" \
  --domain example.com \
  --record-name office \
  --record-types A,AAAA \
  --operations read,update \
  --allowed-origins "203.0.113.10,198.51.100.0/24"
```

This token can only be used from:
- IP address 203.0.113.10
- Any IP in the 198.51.100.0/24 network

### Token with Domain Whitelist

Generate a token restricted to specific domains:

```bash
python generate_token.py \
  --description "API Client" \
  --domain example.com \
  --record-name api \
  --record-types A \
  --operations read,update \
  --allowed-origins "api.example.com,*.internal.example.com"
```

This token can only be used from:
- api.example.com
- Any subdomain of internal.example.com

### Read-Only Monitoring Token

Generate a token for DNS monitoring (no modifications allowed):

```bash
python generate_token.py \
  --description "DNS Monitoring System" \
  --domain example.com \
  --record-name "*" \
  --record-types "*" \
  --operations read
```

### Wildcard Subdomain Management

Generate a token to manage all web servers:

```bash
python generate_token.py \
  --description "Web Server Management" \
  --domain example.com \
  --record-name "web*" \
  --record-types A,AAAA \
  --operations read,update,create,delete
```

This allows managing: web1, web2, webserver, web-prod, etc.

### Multiple Domains

Generate a token for multiple domains:

```bash
# First, generate base token for domain1
python generate_token.py \
  --description "Multi-Domain Management" \
  --domain "*.example.com" \
  --record-name "server1" \
  --record-types A \
  --operations read,update
```

Then manually edit config.yaml to add more domains to the permissions array.

---

## Common Use Cases

### Use Case 1: Home Dynamic DNS

**Scenario**: You have a home server with a dynamic IP that needs to update its DNS record.

**Setup:**

1. Generate token:
```bash
python generate_token.py \
  --description "Home Server DynDNS" \
  --domain myhome.com \
  --record-name server \
  --record-types A \
  --operations read,update
```

2. Configure on home server (using curl):
```bash
#!/bin/bash
TOKEN="your-token-here"
DOMAIN="myhome.com"
HOSTNAME="server"
PROXY="https://dns-filter.example.com"

# Get current public IP
CURRENT_IP=$(curl -s https://api.ipify.org)

# Get current DNS record
RESPONSE=$(curl -s -X POST "$PROXY/api" \
  -H "Authorization: ******" \
  -H "Content-Type: application/json" \
  -d "{\"action\":\"infoDnsRecords\",\"param\":{\"domainname\":\"$DOMAIN\"}}")

# Parse record ID and current IP from DNS
RECORD_ID=$(echo "$RESPONSE" | jq -r ".responsedata.dnsrecords[] | select(.hostname==\"$HOSTNAME\") | .id")
DNS_IP=$(echo "$RESPONSE" | jq -r ".responsedata.dnsrecords[] | select(.hostname==\"$HOSTNAME\") | .destination")

# Update if different
if [ "$CURRENT_IP" != "$DNS_IP" ]; then
  curl -X POST "$PROXY/api" \
    -H "Authorization: ******" \
    -H "Content-Type: application/json" \
    -d "{\"action\":\"updateDnsRecords\",\"param\":{\"domainname\":\"$DOMAIN\",\"dnsrecordset\":{\"dnsrecords\":[{\"id\":\"$RECORD_ID\",\"hostname\":\"$HOSTNAME\",\"type\":\"A\",\"destination\":\"$CURRENT_IP\",\"priority\":\"0\",\"state\":\"yes\",\"deleterecord\":false}]}}}"
  echo "DNS updated to $CURRENT_IP"
else
  echo "DNS already up to date"
fi
```

3. Add to crontab to run every 5 minutes:
```bash
*/5 * * * * /home/user/update-dns.sh
```

### Use Case 2: Automated Load Balancer Updates

**Scenario**: Auto-scaling web servers need to register themselves in DNS.

**Setup:**

1. Generate token with IP whitelist:
```bash
python generate_token.py \
  --description "Web Server Auto-Registration" \
  --domain example.com \
  --record-name "web*" \
  --record-types A \
  --operations read,create,delete \
  --allowed-origins "10.0.0.0/8"
```

2. Cloud-init script for new servers:
```bash
#!/bin/bash
TOKEN="your-token-here"
DOMAIN="example.com"
HOSTNAME="web-$(hostname -s)"
PROXY="https://dns-filter.example.com"
IP=$(hostname -I | awk '{print $1}')

# Register server in DNS
curl -X POST "$PROXY/api" \
  -H "Authorization: ******" \
  -H "Content-Type: application/json" \
  -d "{\"action\":\"updateDnsRecords\",\"param\":{\"domainname\":\"$DOMAIN\",\"dnsrecordset\":{\"dnsrecords\":[{\"hostname\":\"$HOSTNAME\",\"type\":\"A\",\"destination\":\"$IP\",\"priority\":\"0\",\"state\":\"yes\",\"deleterecord\":false}]}}}"
```

### Use Case 3: Multi-Tenant SaaS Platform

**Scenario**: Each customer gets a subdomain, managed via API.

**Setup:**

1. Generate token for each customer with their subdomain:
```bash
python generate_token.py \
  --description "Customer ABC123" \
  --domain example.com \
  --record-name "abc123" \
  --record-types A,AAAA,CNAME \
  --operations read,update
```

2. Application integrates with proxy to update customer DNS.

### Use Case 4: CI/CD Pipeline Integration

**Scenario**: Deployment pipeline updates DNS records after deployment.

**Setup:**

1. Generate token for CI/CD system:
```bash
python generate_token.py \
  --description "CI/CD Pipeline" \
  --domain example.com \
  --record-name "staging-*,prod-*" \
  --record-types A,CNAME \
  --operations read,update \
  --allowed-origins "ci-server.internal.example.com"
```

2. GitLab CI example:
```yaml
deploy:
  script:
    - deploy_application.sh
    - |
      curl -X POST "$DNS_PROXY/api" \
        -H "Authorization: ******" \
        -H "Content-Type: application/json" \
        -d "{\"action\":\"updateDnsRecords\",\"param\":{\"domainname\":\"example.com\",\"dnsrecordset\":{\"dnsrecords\":[{\"id\":\"$RECORD_ID\",\"hostname\":\"staging-api\",\"type\":\"A\",\"destination\":\"$NEW_SERVER_IP\",\"priority\":\"0\",\"state\":\"yes\",\"deleterecord\":false}]}}}"
```

---

## API Usage Examples

### Check DNS Zone Information

```bash
curl -X POST https://dns-filter.example.com/api \
  -H "Content-Type: application/json" \
  -H "Authorization: ******" \
  -d '{
    "action": "infoDnsZone",
    "param": {
      "domainname": "example.com"
    }
  }'
```

**Response:**
```json
{
  "status": "success",
  "responsedata": {
    "name": "example.com",
    "ttl": "86400",
    "serial": "2023110801",
    "refresh": "28800",
    "retry": "7200",
    "expire": "604800",
    "dnssecstatus": false
  }
}
```

### List DNS Records

```bash
curl -X POST https://dns-filter.example.com/api \
  -H "Content-Type: application/json" \
  -H "Authorization: ******" \
  -d '{
    "action": "infoDnsRecords",
    "param": {
      "domainname": "example.com"
    }
  }'
```

**Response (filtered by token permissions):**
```json
{
  "status": "success",
  "responsedata": {
    "dnsrecords": [
      {
        "id": "123456",
        "hostname": "host1",
        "type": "A",
        "priority": "0",
        "destination": "192.0.2.1",
        "deleterecord": false,
        "state": "yes"
      }
    ]
  }
}
```

### Update A Record

```bash
curl -X POST https://dns-filter.example.com/api \
  -H "Content-Type: application/json" \
  -H "Authorization: ******" \
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
            "destination": "192.0.2.100",
            "priority": "0",
            "state": "yes",
            "deleterecord": false
          }
        ]
      }
    }
  }'
```

### Create New Record

```bash
curl -X POST https://dns-filter.example.com/api \
  -H "Content-Type: application/json" \
  -H "Authorization: ******" \
  -d '{
    "action": "updateDnsRecords",
    "param": {
      "domainname": "example.com",
      "dnsrecordset": {
        "dnsrecords": [
          {
            "hostname": "newhost",
            "type": "A",
            "destination": "192.0.2.200",
            "priority": "0",
            "state": "yes",
            "deleterecord": false
          }
        ]
      }
    }
  }'
```

### Delete Record

```bash
curl -X POST https://dns-filter.example.com/api \
  -H "Content-Type: application/json" \
  -H "Authorization: ******" \
  -d '{
    "action": "updateDnsRecords",
    "param": {
      "domainname": "example.com",
      "dnsrecordset": {
        "dnsrecords": [
          {
            "id": "123456",
            "hostname": "oldhost",
            "type": "A",
            "destination": "192.0.2.1",
            "priority": "0",
            "state": "yes",
            "deleterecord": true
          }
        ]
      }
    }
  }'
```

---

## Security Configurations

### High Security: IP Whitelist + Specific Records

```yaml
tokens:
  - token: "highly-restricted-token"
    description: "Production server - IP restricted"
    permissions:
      - domain: "example.com"
        record_name: "prod-app"
        record_types: ["A"]
        operations: ["read", "update"]
    allowed_origins:
      - "203.0.113.50"  # Production server IP only
```

### Medium Security: Network Whitelist + Wildcard Records

```yaml
tokens:
  - token: "office-network-token"
    description: "Office network - development servers"
    permissions:
      - domain: "example.com"
        record_name: "dev-*"
        record_types: ["A", "AAAA"]
        operations: ["read", "update", "create", "delete"]
    allowed_origins:
      - "10.0.0.0/8"       # Office network
      - "172.16.0.0/12"    # VPN network
```

### Read-Only: No IP Restrictions

```yaml
tokens:
  - token: "monitoring-token"
    description: "Monitoring system - read only"
    permissions:
      - domain: "example.com"
        record_name: "*"
        record_types: ["*"]
        operations: ["read"]
    # No allowed_origins = accessible from anywhere (still requires token)
```

### Multi-Environment Setup

```yaml
tokens:
  # Development environment
  - token: "dev-token"
    description: "Development environment"
    permissions:
      - domain: "example.com"
        record_name: "dev-*"
        record_types: ["A", "AAAA", "CNAME"]
        operations: ["read", "update", "create", "delete"]
    allowed_origins:
      - "*.dev.internal.example.com"
  
  # Staging environment
  - token: "staging-token"
    description: "Staging environment"
    permissions:
      - domain: "example.com"
        record_name: "staging-*"
        record_types: ["A", "AAAA", "CNAME"]
        operations: ["read", "update"]
    allowed_origins:
      - "*.staging.internal.example.com"
  
  # Production environment
  - token: "prod-token"
    description: "Production environment"
    permissions:
      - domain: "example.com"
        record_name: "prod-*"
        record_types: ["A", "AAAA"]
        operations: ["read", "update"]
    allowed_origins:
      - "203.0.113.0/24"  # Production network only
```

---

## Python Client Example

```python
#!/usr/bin/env python3
"""
Simple Python client for Netcup API Filter
"""
import requests
import json

class NetcupFilterClient:
    def __init__(self, base_url, token):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
    
    def _request(self, action, param):
        """Make API request"""
        url = f"{self.base_url}/api"
        payload = {
            "action": action,
            "param": param
        }
        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()
    
    def get_records(self, domain):
        """Get DNS records for domain"""
        return self._request("infoDnsRecords", {"domainname": domain})
    
    def update_a_record(self, domain, hostname, ip, record_id):
        """Update an A record"""
        return self._request("updateDnsRecords", {
            "domainname": domain,
            "dnsrecordset": {
                "dnsrecords": [{
                    "id": record_id,
                    "hostname": hostname,
                    "type": "A",
                    "destination": ip,
                    "priority": "0",
                    "state": "yes",
                    "deleterecord": False
                }]
            }
        })

# Usage
if __name__ == "__main__":
    client = NetcupFilterClient(
        base_url="https://dns-filter.example.com",
        token="your-token-here"
    )
    
    # Get records
    records = client.get_records("example.com")
    print(json.dumps(records, indent=2))
    
    # Update record
    result = client.update_a_record(
        domain="example.com",
        hostname="host1",
        ip="192.0.2.100",
        record_id="123456"
    )
    print(json.dumps(result, indent=2))
```

---

## Error Handling

### Invalid Token

**Request:**
```bash
curl -X POST https://dns-filter.example.com/api \
  -H "Authorization: ******" \
  -d '{"action":"infoDnsRecords","param":{"domainname":"example.com"}}'
```

**Response:**
```json
{
  "status": "error",
  "message": "Invalid authentication token"
}
```

### Origin Not Allowed

**Request from unauthorized IP:**
```json
{
  "status": "error",
  "message": "Access denied: origin not allowed"
}
```

### Permission Denied

**Request to modify unauthorized record:**
```json
{
  "status": "error",
  "message": "No permission to update record host2 (A)"
}
```

---

## Best Practices

1. **Always use IP whitelisting** for production tokens
2. **Use specific record patterns** instead of wildcards when possible
3. **Create separate tokens** for different environments
4. **Monitor logs regularly** for unauthorized access attempts
5. **Rotate tokens** if they may have been compromised
6. **Test with curl** before integrating into applications
7. **Store tokens securely** (environment variables, secret managers)
8. **Document token purposes** in the description field

---

For more information, see:
- [README.md](README.md) - Full documentation
- [QUICK_START.md](QUICK_START.md) - Quick start guide
- [WEBHOSTING_DEPLOYMENT.md](WEBHOSTING_DEPLOYMENT.md) - Deployment instructions
