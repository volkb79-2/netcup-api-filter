# Netcup API Filter - Admin Guide

> Lives in `/docs` as part of the core documentation set (`CONFIGURATION_GUIDE.md`, `OPERATIONS_GUIDE.md`, `CLIENT_USAGE.md`). Keep this guide current with any admin UI changes.

Complete guide for administrators managing the Netcup API Filter system through the web UI.

## Table of Contents

1. [Initial Setup](#initial-setup)
2. [Dashboard Overview](#dashboard-overview)
3. [Managing Clients](#managing-clients)
4. [Viewing Audit Logs](#viewing-audit-logs)
5. [Configuring Email Notifications](#configuring-email-notifications)
6. [Netcup API Configuration](#netcup-api-configuration)
7. [System Information](#system-information)
8. [Security Best Practices](#security-best-practices)
9. [Troubleshooting](#troubleshooting)

## Initial Setup

### First Login

1. Navigate to your application URL followed by `/admin` (e.g., `https://yourdomain.com/admin`)
2. Login with the default credentials:
   - Username: `admin`
   - Password: `admin`
3. You will be immediately prompted to change your password
4. Choose a strong password (minimum 8 characters)

### Initial Configuration

After changing your password, configure the system:

1. **Configure Netcup API** (Required)
   - Go to: Configuration → Netcup API
   - Enter your Netcup customer ID, API key, and API password
   - These credentials are stored securely in the database
   - Click "Save Configuration"

2. **Configure Email Settings** (Optional but recommended)
   - Go to: Configuration → Email Settings
   - Enter your SMTP server details
   - Set sender and admin email addresses
   - Use "Send Test Email" to verify configuration

3. **Create Your First Client**
   - Go to: Management → Clients → Create
   - Fill in the required fields
   - Save and copy the generated token (shown only once!)

## Dashboard Overview

The dashboard provides at-a-glance statistics:

- **Total Clients** - All registered clients
- **Active Clients** - Currently active clients
- **Total Logs** - Number of audit log entries
- **Recent Activity** - Last 10 API access attempts

### Quick Actions

- **Add Client** - Create a new client token
- **View Logs** - Jump to audit log viewer

## Managing Clients

### Creating a New Client

1. Navigate to: Management → Clients → Create
2. Fill in the required fields:

**Basic Information:**
- **Client ID**: Unique identifier (e.g., `web-server-1`, `ddns-host`)
- **Description**: Human-readable description of the client's purpose

**Realm Configuration:**
- **Realm Type**: Choose domain matching mode
  - `host`: Exact domain match (e.g., `example.com`)
  - `subdomain`: Subdomain pattern match (e.g., `*.example.com` including the domain itself)
- **Realm Value**: Domain name (e.g., `example.com`)

**Permissions:**
- **Allowed Record Types**: Select DNS record types (A, AAAA, CNAME, NS)
  - Hold Ctrl/Cmd to select multiple
  - Client can ONLY modify these record types
- **Allowed Operations**: Select operations (read, update, create, delete)
  - `read`: View DNS records
  - `update`: Modify existing DNS records
  - `create`: Add new DNS records
  - `delete`: Remove DNS records

**IP Access Control (Optional):**
- **Allowed IP Ranges**: Enter one IP/range per line
  - Single IP: `192.168.1.100`
  - CIDR notation: `192.168.1.0/24`
  - IP range: `192.168.1.1-192.168.1.254`
  - Wildcard: `192.168.1.*`
  - Leave empty to allow all IPs

**Email Notifications (Optional):**
- **Email Address**: Client's email for notifications
- **Email Notifications Enabled**: Toggle to send notifications on every API access

**Expiration (Optional):**
- **Token Expires At**: Set expiration date/time for automatic token deactivation

3. Click "Save"
4. **Important**: Copy the generated token immediately - it cannot be retrieved later!

### Editing a Client

1. Navigate to: Management → Clients
2. Click the edit icon next to the client
3. Modify any settings except the secret token
4. Click "Save"

**Note**: You cannot view or regenerate the secret token after creation. To change a token, you must create a new client.

### Deactivating a Client

To temporarily disable a client without deleting it:

1. Edit the client
2. Uncheck "Active"
3. Save

The client's token will no longer work until you reactivate it.

### Deleting a Client

To permanently remove a client:

1. Navigate to: Management → Clients
2. Click the delete icon next to the client
3. Confirm deletion

**Warning**: This action cannot be undone. Consider deactivating instead of deleting.

## Viewing Audit Logs

Access detailed logs of all API activity:

1. Navigate to: Logs → Audit Logs

### Log Information

Each log entry shows:
- **Timestamp**: When the request occurred
- **Client ID**: Which client made the request
- **IP Address**: Source IP address
- **Operation**: Action performed (infoDnsZone, infoDnsRecords, updateDnsRecords)
- **Domain**: Target domain
- **Success**: ✓ (success) or ✗ (failure)

### Filtering Logs

Use the built-in filters to narrow down logs:
- **Client ID**: Show only logs from a specific client
- **Operation**: Filter by operation type
- **Success**: Show only successful or failed requests
- **Timestamp**: Date range filtering

### Searching Logs

Use the search box to find specific:
- Client IDs
- IP addresses
- Domains
- Operations

### Pagination

- Default: 50 entries per page
- Use pagination controls at the bottom to navigate

## Configuring Email Notifications

Email notifications alert you and your clients about API activity and security events.

### SMTP Configuration

1. Navigate to: Configuration → Email Settings

2. Fill in SMTP details:
   - **SMTP Server**: Hostname (e.g., `smtp.gmail.com`)
   - **SMTP Port**: Port number (465 for SSL, 587 for TLS)
   - **SMTP Username**: Authentication username
   - **SMTP Password**: Authentication password
   - **Sender Email**: Email address to send from
   - **Use SSL**: Check for SSL/TLS encryption (recommended)

3. **Admin Email**: Enter admin email for security alerts

4. Click "Save Configuration"

### Testing Email

After configuring:
1. Enter a test email address
2. Click "Send Test Email"
3. Check the inbox for the test message
4. If it fails, check logs for error details

### Common SMTP Settings

**Gmail:**
- Server: `smtp.gmail.com`
- Port: 587
- Use TLS
- Note: May require app-specific password

**Outlook/Office365:**
- Server: `smtp-mail.outlook.com`
- Port: 587
- Use TLS

**Yahoo:**
- Server: `smtp.mail.yahoo.com`
- Port: 465
- Use SSL

### Types of Notifications

**Client Notifications (per-client):**
- Sent when "Email Notifications Enabled" is checked for a client
- Includes: timestamp, operation, IP, result, DNS record details
- Sent with 5-second delay (async, doesn't block API)

**Admin Notifications (security):**
- Authentication failures (invalid tokens)
- Permission denials
- Origin restriction violations
- Sent immediately to admin email

## Netcup API Configuration

Configure your Netcup API credentials:

1. Navigate to: Configuration → Netcup API

2. Enter your credentials:
   - **Customer ID**: Your Netcup customer number
   - **API Key**: Your Netcup API key
   - **API Password**: Your Netcup API password
   - **API URL**: Endpoint URL (default is usually correct)
   - **Timeout**: Request timeout in seconds (default: 30)

3. Click "Save Configuration"

### Finding Your Netcup Credentials

1. Log in to Netcup Customer Control Panel (CCP)
2. Navigate to Master Data → API
3. Generate or retrieve your API credentials

### Security Note

These credentials provide FULL access to your Netcup account. The filter proxy uses them to perform DNS operations on behalf of limited-access clients. Keep them secure and never share them.

## System Information

View technical details about your deployment:

Navigate to: System → System Info

### Information Displayed

**Python Environment:**
- Python version and implementation
- Platform and architecture
- Executable path
- Installation prefix

**Directory Information:**
- Current working directory
- Script directory
- Home directory
- Database file location

**Filesystem Access Tests:**
- Shows which directories are writable
- Important for database and log files
- Red flags indicate permission issues

### Troubleshooting Filesystem Issues

If database or logs aren't working:
1. Check System Info for write access tests
2. Ensure the application has write permissions
3. Consider setting `NETCUP_FILTER_DB_PATH` environment variable
4. Check webhosting provider's documentation for file permissions

## Security Best Practices

### Password Security

✅ **DO:**
- Change the default admin password immediately
- Use a strong, unique password (12+ characters)
- Use a password manager
- Change password periodically

❌ **DON'T:**
- Use the default `admin`/`admin` credentials
- Share the admin password
- Use simple or common passwords
- Reuse passwords from other services

### Token Management

✅ **DO:**
- Generate tokens through the admin UI (cryptographically secure)
- Copy and store tokens securely immediately after creation
- Use descriptive client IDs and descriptions
- Set token expiration dates when appropriate
- Use IP restrictions whenever possible
- Apply principle of least privilege (minimum necessary permissions)
- Deactivate unused tokens promptly

❌ **DON'T:**
- Manually create tokens (use the admin UI)
- Share tokens between multiple clients
- Grant unnecessary permissions
- Store tokens in version control or logs
- Transmit tokens over insecure channels

### Email Configuration

✅ **DO:**
- Use SSL/TLS for SMTP connections
- Use app-specific passwords when available
- Test email configuration after setup
- Monitor admin email for security alerts

❌ **DON'T:**
- Use unencrypted SMTP connections
- Ignore security alert emails
- Use weak email passwords

### Access Control

✅ **DO:**
- Use realm type appropriately:
  - `host` for specific domain access
  - `subdomain` for wildcard subdomain access
- Limit allowed record types to only what's needed
- Restrict operations to minimum required
- Set IP access restrictions when clients have static IPs
- Review and audit client permissions regularly

❌ **DON'T:**
- Grant wildcard permissions unless absolutely necessary
- Allow all operations when only `read` is needed
- Skip IP restrictions for sensitive clients

### Monitoring

✅ **DO:**
- Review audit logs regularly
- Monitor failed authentication attempts
- Watch for unusual access patterns
- Act on security alert emails promptly
- Keep track of active vs. inactive clients

❌ **DON'T:**
- Ignore repeated failed access attempts
- Let audit logs grow indefinitely without review
- Disable email notifications completely

## Troubleshooting

### Can't Login to Admin UI

**Problem**: Login fails with correct credentials

**Solutions**:
1. Check if password was changed from default
2. Verify database file is accessible and writable
3. Check application logs for errors
4. Try resetting database (if acceptable to lose data)

### Client Token Not Working

**Problem**: API requests fail with "Invalid authentication token"

**Solutions**:
1. Verify token is correct (no extra spaces, complete)
2. Check if client is active (edit client, verify "Active" is checked)
3. Check if token is expired (Token Expires At field)
4. Verify token format is hex (32-128 characters)
5. Check audit logs for error details

### Permission Denied Errors

**Problem**: API requests fail with "Permission denied"

**Solutions**:
1. Verify realm type and value match the domain
   - `host`: domain must exactly match realm_value
   - `subdomain`: domain must be realm_value or *.realm_value
2. Check allowed record types include the record being accessed
3. Verify allowed operations include the operation being performed
4. Check IP access restrictions if configured
5. Review audit logs for specific error messages

### Email Notifications Not Sending

**Problem**: Emails not being received

**Solutions**:
1. Verify SMTP configuration is correct
2. Use "Send Test Email" feature
3. Check application logs for email errors
4. Verify "Email Notifications Enabled" is checked for client
5. Check client has valid email address
6. Verify SMTP credentials and permissions
7. Check spam/junk folders

### Database Errors

**Problem**: "Database locked" or "Unable to open database"

**Solutions**:
1. Check filesystem permissions (System Info page)
2. Verify database file location is writable
3. Set `NETCUP_FILTER_DB_PATH` environment variable
4. Restart the application
5. Check for concurrent access issues

### Slow Performance

**Problem**: Admin UI or API responses are slow

**Solutions**:
1. Check audit log size (too many entries)
2. Consider archiving old logs
3. Verify database is on fast storage
4. Check server resources (CPU, memory)
5. Review rate limiting settings

### Migration Issues

**Problem**: `migrate_yaml_to_db.py` fails

**Solutions**:
1. Verify `config.yaml` exists and is valid YAML
2. Check database is accessible and writable
3. Review migration script output for specific errors
4. Ensure all required fields in YAML are present
5. Run with: `python migrate_yaml_to_db.py config.yaml`

## Getting Help

If you encounter issues not covered in this guide:

1. Check application logs for detailed error messages
2. Review the [README.md](README.md) for general information
3. Check [WEBHOSTING_DEPLOYMENT.md](WEBHOSTING_DEPLOYMENT.md) for deployment-specific issues
4. Open an issue on GitHub with:
   - Detailed description of the problem
   - Steps to reproduce
   - Relevant log entries (with sensitive data removed)
   - System information from System Info page
