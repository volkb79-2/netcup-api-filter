# Client Configuration Templates

## Overview

The Netcup API Filter provides **6 pre-configured templates** for common DNS management scenarios. Templates automatically configure:
- Realm type (host vs subdomain)
- Allowed record types
- Allowed operations
- Recommended use cases

## Template Reference

### 1. 🏠 DDNS Single Host

**Use Case:** Dynamic DNS for a single hostname

**Configuration:**
- **Realm Type:** `host` (exact match)
- **Record Types:** A, AAAA
- **Operations:** read, update
- **Example:** `home.example.com`

**Recommended For:**
- Home network with dynamic IP
- VPN server with changing IP address
- Single server/device DDNS

**Security:** Minimal permissions - can only update IP addresses for the specified hostname.

---

### 2. 🌐 DDNS Subdomain Delegation

**Use Case:** Full control over subdomain zone for multiple dynamic hosts

**Configuration:**
- **Realm Type:** `subdomain` (wildcard match)
- **Record Types:** A, AAAA, CNAME
- **Operations:** read, update, create, delete
- **Example:** `dyn.example.com` (manages `*.dyn.example.com`)

**Recommended For:**
- Multiple dynamic hosts in subdomain
- IoT device fleet registration
- Kubernetes external-dns integration
- Docker Swarm service discovery

**Behavior:** Client can manage ANY hostname under `dyn.example.com`:
- `device1.dyn.example.com` → 192.168.1.100
- `device2.dyn.example.com` → 192.168.1.101
- `new-host.dyn.example.com` → can be created dynamically

---

### 3. 👁️ Read-Only Monitoring

**Use Case:** View DNS configuration without modification rights

**Configuration:**
- **Realm Type:** `host` (exact match)
- **Record Types:** A, AAAA, CNAME, NS, TXT, MX (all common types)
- **Operations:** read
- **Example:** `example.com`

**Recommended For:**
- Monitoring dashboards (Grafana, Prometheus exporters)
- Compliance auditing and reporting
- DNS health checks and validation
- Change tracking and alerting

**Security:** Read-only access - no modifications possible.

---

### 4. 🔒 LetsEncrypt DNS-01 Challenge

**Use Case:** Automated certificate issuance via ACME DNS-01 validation

**Configuration:**
- **Realm Type:** `subdomain` (wildcard match)
- **Record Types:** TXT
- **Operations:** read, create, delete
- **Example:** `_acme-challenge.example.com`

**Recommended For:**
- Certbot with DNS-01 plugin
- Traefik ACME DNS challenge
- Automated wildcard certificate issuance (`*.example.com`)
- Internal CA DNS validation

**Integration Examples:**
```bash
# Certbot
certbot certonly --dns-plugin --dns-credentials=/etc/letsencrypt/netcup.ini

# Traefik
certificatesResolvers.letsencrypt.acme.dnsChallenge.provider=netcup

# acme.sh
acme.sh --issue -d example.com -d *.example.com --dns dns_netcup
```

**Security:** Can only create/delete TXT records under `_acme-challenge.*` - no other record types or operations.

---

### 5. ⚙️ Full DNS Management

**Use Case:** Complete DNS control for automation and API integration

**Configuration:**
- **Realm Type:** `host` (exact match)
- **Record Types:** A, AAAA, CNAME, NS, TXT, MX, SRV (all types)
- **Operations:** read, update, create, delete (all operations)
- **Example:** `example.com`

**Recommended For:**
- CI/CD deployment automation
- Infrastructure as Code (Terraform, Pulumi, Ansible)
- Custom DNS management tools
- DNS provider API integration

**Security Warning:** Full permissions - use with caution. Consider narrower scopes for most use cases.

---

### 6. 🔗 CNAME Delegation

**Use Case:** Delegate CNAME record management for CDN/service provider

**Configuration:**
- **Realm Type:** `subdomain` (wildcard match)
- **Record Types:** CNAME
- **Operations:** read, update, create, delete
- **Example:** `cdn.example.com`

**Recommended For:**
- CDN provider integration (Cloudflare, Fastly, Akamai)
- SaaS service CNAME delegation
- Load balancer alias management (AWS ALB, GCP LB)
- Multi-CDN failover automation

**Use Case Example:**
```
cdn.example.com     → CNAME → cdn-provider.cloudflare.net
www.example.com     → CNAME → cdn.example.com
assets.example.com  → CNAME → cdn.example.com
```

Client can only manage CNAME records - cannot modify A/AAAA records or zone apex.

---

## Comparison Matrix

| Template | Realm Type | Write Access | Use Case | Security Level |
|----------|------------|--------------|----------|----------------|
| DDNS Single Host | host | Limited (update only) | Single dynamic IP | High |
| DDNS Subdomain | subdomain | Full (create/delete) | Multiple dynamic hosts | Medium |
| Read-Only Monitoring | host | None | Monitoring/auditing | Highest |
| LetsEncrypt DNS-01 | subdomain | Limited (TXT only) | Certificate automation | High |
| Full Management | host | Full (all types) | Automation/IaC | Low |
| CNAME Delegation | subdomain | Limited (CNAME only) | CDN integration | Medium |

## Realm Types Explained

### Host (Exact Match)

**Pattern:** `example.com`

**Matches:**
- ✅ `example.com` (exact match)
- ❌ `www.example.com` (subdomain)
- ❌ `api.example.com` (subdomain)

**Use When:** Client should only manage a specific hostname.

### Subdomain (Wildcard Match)

**Pattern:** `dyn.example.com`

**Matches:**
- ✅ `dyn.example.com` (the subdomain itself)
- ✅ `host1.dyn.example.com` (anything under subdomain)
- ✅ `device-99.dyn.example.com` (anything under subdomain)
- ❌ `example.com` (parent domain)
- ❌ `other.example.com` (sibling subdomain)

**Use When:** Client should manage all hosts under a subdomain (delegation).

## Customizing Templates

Templates are **starting points** - you can modify after applying:

1. **Select template** from dropdown
2. **Review pre-filled values**
3. **Customize** as needed:
   - Add/remove record types
   - Adjust operations
   - Change realm type if needed
4. **Provide required fields**:
   - Client ID (unique identifier)
   - Realm value (domain name)

## Security Best Practices

### Principle of Least Privilege

Always use the **most restrictive template** that meets your needs:

| Need | Template | Why |
|------|----------|-----|
| Update single IP | DDNS Single Host | Minimal write access |
| View configuration | Read-Only Monitoring | No write access |
| ACME certificates | LetsEncrypt DNS-01 | TXT records only |
| Multiple dynamic hosts | DDNS Subdomain | Scoped to subdomain |

### IP Whitelisting

Combine templates with IP restrictions:
- DDNS clients: Whitelist home/office network
- Monitoring: Whitelist monitoring servers
- CI/CD: Whitelist build agents

### Token Expiration

Set expiration dates for:
- Temporary integrations
- Testing/development tokens
- Short-term delegations

### Email Notifications

Enable email alerts for:
- Full Management template (high-privilege)
- Production automation tokens
- Subdomain delegation (wide scope)

## Integration Examples

### Terraform (Full Management)

```hcl
provider "netcup" {
  api_url    = "https://naf.example.com"
  client_id  = var.netcup_client_id
  secret_key = var.netcup_secret_key
}

resource "netcup_dns_record" "www" {
  zone     = "example.com"
  hostname = "www"
  type     = "A"
  destination = "192.0.2.1"
}
```

### Certbot (LetsEncrypt DNS-01)

```bash
certbot certonly \
  --manual \
  --preferred-challenges dns \
  --manual-auth-hook /usr/local/bin/netcup-dns-auth \
  -d *.example.com
```

### DDNS Update Script (DDNS Single Host)

```bash
#!/bin/bash
CURRENT_IP=$(curl -s https://api.ipify.org)
curl -X POST https://naf.example.com/api/updateDnsRecords \
  -H "Authorization: Bearer $TOKEN" \
  -d "{\"domainname\":\"example.com\",\"dnsrecordset\":{\"dnsrecords\":[{\"hostname\":\"home\",\"type\":\"A\",\"destination\":\"$CURRENT_IP\"}]}}"
```

### Kubernetes external-dns (DDNS Subdomain)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: external-dns
spec:
  template:
    spec:
      containers:
      - name: external-dns
        image: registry.k8s.io/external-dns/external-dns:v0.14.0
        args:
        - --source=service
        - --domain-filter=k8s.example.com
        - --provider=netcup
        - --netcup-api-url=https://naf.example.com
        env:
        - name: NETCUP_CLIENT_ID
          valueFrom:
            secretKeyRef:
              name: netcup-credentials
              key: client-id
        - name: NETCUP_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: netcup-credentials
              key: secret-key
```

## Template Selection Guide

**Start here:** Which statement best describes your need?

1. **"I need to update my home IP address"**
   → **DDNS Single Host** 🏠

2. **"I have multiple devices that need dynamic DNS"**
   → **DDNS Subdomain Delegation** 🌐

3. **"I just want to monitor DNS records"**
   → **Read-Only Monitoring** 👁️

4. **"I need wildcard SSL certificates"**
   → **LetsEncrypt DNS-01** 🔒

5. **"I'm integrating with Infrastructure as Code"**
   → **Full DNS Management** ⚙️

6. **"I'm setting up a CDN"**
   → **CNAME Delegation** 🔗

Still unsure? Start with **Read-Only Monitoring** and upgrade permissions as needed.
