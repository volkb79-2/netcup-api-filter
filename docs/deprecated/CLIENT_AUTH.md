# Client Authentication Guide

> Part of the active documentation set in `/docs`. See `docs/README.md` for context.

## Authentication Format

The Netcup API Filter uses **two-factor client authentication**:

```
client_id:secret_key
```

### Example
```
myapp_prod:sK7mN2pQ9rT4vW1xZ5aB8cD3eF6gH0jK2lM4nP7
```

- **client_id**: Cleartext identifier (e.g., `myapp_prod`, `backup_server_01`)
- **secret_key**: Cryptographic secret (40 characters)
- **Separator**: Single colon (`:`)

## Using Your Token

### HTTP Header

```bash
Authorization: Bearer client_id:secret_key
```

### Example Requests

**Python (requests)**:
```python
import requests

CLIENT_ID = "myapp_prod"
SECRET_KEY = "sK7mN2pQ9rT4vW1xZ5aB8cD3eF6gH0jK2lM4nP7"
TOKEN = f"{CLIENT_ID}:{SECRET_KEY}"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

response = requests.post(
    "https://api.example.com/api",
    headers=headers,
    json={
        "action": "infoDnsRecords",
        "param": {"domainname": "example.com"}
    }
)
```

**Shell (curl)**:
```bash
CLIENT_ID="myapp_prod"
SECRET_KEY="sK7mN2pQ9rT4vW1xZ5aB8cD3eF6gH0jK2lM4nP7"
TOKEN="${CLIENT_ID}:${SECRET_KEY}"

curl -X POST https://api.example.com/api \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "infoDnsRecords",
    "param": {"domainname": "example.com"}
  }'
```

**JavaScript (fetch)**:
```javascript
const CLIENT_ID = 'myapp_prod';
const SECRET_KEY = 'sK7mN2pQ9rT4vW1xZ5aB8cD3eF6gH0jK2lM4nP7';
const TOKEN = `${CLIENT_ID}:${SECRET_KEY}`;

const response = await fetch('https://api.example.com/api', {
    method: 'POST',
    headers: {
        'Authorization': `Bearer ${TOKEN}`,
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({
        action: 'infoDnsRecords',
        param: { domainname: 'example.com' }
    })
});
```

## Getting Your Token

1. Admin creates your client via the Admin UI
2. Token is displayed **once** in this format: `client_id:secret_key`
3. **Save it immediately** - the secret key cannot be retrieved later
4. If lost, admin can regenerate the secret key (client_id stays the same)

## Security Best Practices

### ✅ DO:
- Store tokens in environment variables or secret managers
- Use HTTPS for all API requests
- Restrict IP ranges when possible
- Rotate credentials periodically

### ❌ DON'T:
- Hardcode tokens in source code
- Commit tokens to version control
- Share tokens between applications
- Send tokens in URL query parameters

## Example Client Script

See `example_client.py` for a complete working example:

```bash
# Test with preseeded client
python3 example_client.py \
  --url https://api.example.com \
  --token test_qweqweqwe_vi:qweqweqwe_vi_readonly_secret_key_12345 \
  --domain qweqweqwe.vi \
  --test records
```

## Troubleshooting

### "Invalid authentication token"

**Causes**:
- Wrong client_id or secret_key
- Missing colon separator
- Client is disabled
- Token has expired

**Solutions**:
- Verify token format: `client_id:secret_key`
- Check client status in admin UI
- Regenerate credentials if lost

### "Access denied"

**Causes**:
- Trying to access domain outside your realm
- Trying to modify record types you don't have permission for
- IP address not in allowed ranges

**Solutions**:
- Check your client permissions in admin UI
- Ensure your IP is whitelisted (if restrictions configured)
- Request admin to update your permissions

## API Actions

The filter proxy supports these Netcup API actions:

- `infoDnsZone` - Get DNS zone information (read-only)
- `infoDnsRecords` - List DNS records (read-only)
- `updateDnsRecords` - Modify DNS records (requires update permission)

Permissions are configured per-client by the administrator.

## See Also

- [Admin Guide](ADMIN_GUIDE.md) - For administrators managing clients
- [Client Usage](CLIENT_USAGE.md) - Detailed API documentation
- [Example Client](example_client.py) - Working Python example
