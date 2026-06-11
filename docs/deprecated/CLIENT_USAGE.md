# Client Usage Guide

> Stored in `/docs` with the rest of the living documentation. Pair this with `CONFIGURATION_GUIDE.md` and `OPERATIONS_GUIDE.md` when onboarding new token holders.

This guide explains how token holders can manage their permitted DNS records through the new client portal and with direct API calls. Every action described here respects the same access-control rules enforced by the Netcup API Filter.

## 1. Requirements

- A valid API token issued by the administrator (viewable only once when created).
- HTTPS access to your deployment (e.g., `https://hosting.example.com`).
- Optional: the domain(s) and record names covered by your token.

## 2. Client Portal Overview

- **URL:** `https://your-domain/client`
- **Authentication:** Paste your API token into the login form. Sessions inherit the server's secure cookie settings and expire after one hour of inactivity.
- **Scope:** The portal automatically limits all views and actions to the domains, record types, and operations allowed by your token. If your token is read-only, write operations are hidden.

### 2.1 Dashboard

After signing in you will see:
- **Operations card** – read/update/create/delete permissions granted to the token.
- **Record types card** – the DNS record types you can view or change.
- **Domains card** – each domain realm linked to this token. Every card shows zone TTL information, record counts, and a preview of the first five visible records.

### 2.2 Domain Management

Click *Open domain* to access the full record list for that domain:
- **Zone summary** – TTL, serial, refresh, retry, and expire values returned by `infoDnsZone`.
- **Permissions panel** – reminder of allowed operations and record types.
- **Records table** – only the DNS records that your token can read; each row offers *Edit* and *Delete* when the token allows those actions.
- **Create record** – available when the token has `create` permission. Supports hostname, type, destination, priority, TTL, and state fields.
- **Edit record** – pre-fills the current values so you can update destination/IP, TTL, etc.
- **Delete record** – sets the Netcup `deleterecord` flag through the API.

### 2.3 Activity Log

`/client/activity` shows up to the 25 most recent audit entries for your token (available when the deployment uses the database backend). You can quickly confirm whether updates succeeded, from which IP they originated, and what domains were touched.

## 3. API Equivalents

The portal is a convenience layer; every button ultimately calls `POST /api` on the same host. You can perform the same operations directly:

### 3.1 Read current DNS records

```bash
curl -X POST https://your-domain/api \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "action": "infoDnsRecords",
    "param": {"domainname": "example.com"}
  }'
```

### 3.2 Update an existing record

```bash
curl -X POST https://your-domain/api \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
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
            "destination": "203.0.113.42",
            "priority": "0",
            "ttl": "600",
            "state": "yes",
            "deleterecord": false
          }
        ]
      }
    }
  }'
```

### 3.3 Create a new record (when permitted)

```bash
curl -X POST https://your-domain/api \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "action": "updateDnsRecords",
    "param": {
      "domainname": "example.com",
      "dnsrecordset": {
        "dnsrecords": [
          {
            "hostname": "vpn",
            "type": "AAAA",
            "destination": "2001:db8::10",
            "priority": "0",
            "ttl": "3600",
            "state": "yes",
            "deleterecord": false
          }
        ]
      }
    }
  }'
```

### 3.4 Delete a record

```bash
curl -X POST https://your-domain/api \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "action": "updateDnsRecords",
    "param": {
      "domainname": "example.com",
      "dnsrecordset": {
        "dnsrecords": [
          {
            "id": "987654",
            "hostname": "oldhost",
            "type": "A",
            "destination": "198.51.100.44",
            "deleterecord": true
          }
        ]
      }
    }
  }'
```

## 4. Example Workflows

1. **Dynamic IPv4 update via portal**
   - Log in → Open domain → Click *Edit* on your `A` record → Enter the new public IP → Save. The audit log will show the change instantly.

2. **Dual-stack rollout via API**
   - Use the *Create record* UI (or the API example above) to add an `AAAA` record. Update the TTL to `300` while testing, then raise it later.

3. **Clean up obsolete hostnames**
   - From the domain table select *Delete*. The record disappears after Netcup confirms the update, and the audit log captures the removal.

4. **Read-only monitoring**
   - Tokens with only `read` permission can still view the dashboard, export current records (copy table or use `infoDnsRecords`), and review activity but will not see edit/delete buttons.

## 5. Troubleshooting

| Issue | Resolution |
| --- | --- |
| "Invalid token" on login | Confirm the token is active, not expired, and matches exactly (case-sensitive). |
| No domains listed | Token realm may not include any domains yet; contact the admin or verify assignments. |
| Update fails with "Permission denied" | The requested operation or record type exceeds the token's allowed operations/types. Check your assigned scope in the dashboard. |
| "Too many records" error | The API caps bulk updates at 100 records per request. Break large batches into multiple calls. |
| Rate limit exceeded | The `/api` endpoint allows 10 writes per minute per IP. Wait a minute or request a higher quota from the admin. |

## 6. Security Best Practices for Clients

- Keep tokens secret; treat them like passwords. Do not paste them into third-party tools.
- Enable IP restrictions on your token when possible (admins can configure this per client).
- Always access the portal over HTTPS and sign out from shared machines.
- Rotate tokens periodically or immediately after any suspected compromise.
- Leverage the activity log to monitor for unexpected operations.

For administrator-focused configuration details, continue following `README.md`. This document is dedicated to client-facing usage scenarios.
