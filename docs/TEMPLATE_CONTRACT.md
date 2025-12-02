# Template Variable Contract

This document defines the required variables for each template and the naming conventions used throughout the application.

## Naming Conventions

### Form Field IDs
- Use `snake_case` for all form field IDs and names
- Prefix with category when ambiguous: `smtp_host`, `smtp_port`, `from_email`
- Boolean fields: use descriptive names like `notify_new_account`

### Route Naming
- Blueprint prefix: `admin.`, `client.`, `api.`
- Action-based names: `admin.audit_logs`, `admin.account_detail`, `admin.config_email`
- RESTful patterns for API: GET/POST/PUT/DELETE on same route

### Template Variables
- Always pass explicit context - no relying on global state
- Use consistent names across similar pages:
  - `stats` - dictionary with page-specific statistics
  - `pagination` - pagination object for list pages
  - `form_data` - pre-filled form values for edit pages

---

## Admin Templates

### admin/base.html
Inherits: `base.html`
Required variables: None (uses session for auth)

### admin/dashboard.html
Inherits: `admin/base.html`
Required variables:
```python
{
    "stats": {
        "total_accounts": int,
        "pending_accounts": int,
        "active_tokens": int,
        "api_calls_today": int,
    },
    "recent_activity": List[ActivityLog],  # Last 10 logs
    "pending_realms": List[AccountRealm],  # Realms awaiting approval
}
```

### admin/accounts.html
Inherits: `admin/base.html`
Required variables:
```python
{
    "accounts": List[Account],
    "stats": {
        "total": int,
        "active": int,
        "pending": int,
    },
}
```

### admin/account_detail.html
Inherits: `admin/base.html`
Required variables:
```python
{
    "account": Account,
    "realms": List[AccountRealm],
    "tokens": List[APIToken],
    "activity": List[ActivityLog],
}
```

### admin/audit_logs.html
Inherits: `admin/base.html`
Required variables:
```python
{
    "logs": List[ActivityLog],
    "pagination": Pagination,  # Flask-SQLAlchemy pagination object
    "accounts": List[Account],  # For actor filter dropdown
    "stats": {
        "total_today": int,
        "logins_today": int,
        "failed_logins": int,
        "api_calls": int,
    },
    # Filter state (for form pre-population)
    "range": str,  # 'today', 'week', 'month', 'all'
    "action_filter": str,
    "actor_filter": str,
    "search": str,
}
```

### admin/config_email.html
Inherits: `admin/base.html`
Required variables:
```python
{
    "config": {
        "smtp_host": str,
        "smtp_port": int,
        "smtp_security": str,  # 'tls', 'ssl', 'none'
        "smtp_username": str,
        "smtp_password": str,  # Masked or empty
        "from_email": str,
        "from_name": str,
        "reply_to": str,
        "notify_new_account": bool,
        "notify_realm_request": bool,
        "notify_security": bool,
        "admin_email": str,
        "last_test_at": datetime | None,
        "last_test_success": bool,
        "last_test_error": str | None,
    },
    "stats": {
        "sent_today": int,
        "sent_week": int,
        "failed": int,
    },
}
```

Form field IDs (must match template):
- `#smtp_host` - SMTP server hostname
- `#smtp_port` - SMTP port number
- `#smtp_username` - SMTP auth username
- `#smtp_password` - SMTP auth password
- `#from_email` - Sender email address
- `#from_name` - Sender display name
- `#reply_to` - Reply-to address
- `#admin_email` - Admin notification address
- `#notify_new_account` - Checkbox
- `#notify_realm_request` - Checkbox
- `#notify_security` - Checkbox
- `input[name="smtp_security"]` - Radio buttons (sec_tls, sec_ssl, sec_none)

### admin/config_netcup.html
Inherits: `admin/base.html`
Required variables:
```python
{
    "config": {
        "customer_number": str,
        "api_key": str,  # Masked
        "api_password": str,  # Masked
        "api_endpoint": str,
        "timeout": int,
        "last_test_at": datetime | None,
        "last_test_success": bool,
        "last_test_error": str | None,
    },
    "stats": {
        "api_calls_today": int,
        "api_calls_week": int,
        "errors": int,
    },
}
```

Form field IDs:
- `#customer_number` - Netcup customer number
- `#api_key` - Netcup API key
- `#api_password` - Netcup API password
- `#api_endpoint` - API endpoint URL
- `#timeout` - Request timeout in seconds

### admin/system_info.html
Inherits: `admin/base.html`
Required variables:
```python
{
    "app": {
        "version": str,
        "environment": str,
        "debug": bool,
        "started_at": datetime,
    },
    "db": {
        "path": str,
        "size": str,
        "accounts": int,
        "realms": int,
        "tokens": int,
        "logs": int,
    },
    "server": {
        "hostname": str,
        "python_version": str,
        "flask_version": str,
        "platform": str,
    },
    "services": {
        "netcup_configured": bool,
        "email_configured": bool,
        "last_backup": datetime | None,
    },
}
```

---

## URL Routes

### Admin Blueprint (`/admin`)
| Route | Endpoint | Method | Purpose |
|-------|----------|--------|---------|
| `/` | `admin.dashboard` | GET | Dashboard |
| `/login` | `admin.login` | GET/POST | Login form |
| `/logout` | `admin.logout` | GET | Logout |
| `/accounts` | `admin.accounts` | GET | Account list |
| `/accounts/<id>` | `admin.account_detail` | GET | Account detail |
| `/pending` | `admin.pending` | GET | Pending approvals |
| `/audit` | `admin.audit_logs` | GET | Audit logs |
| `/config/netcup` | `admin.config_netcup` | GET/POST | Netcup config |
| `/config/email` | `admin.config_email` | GET/POST | Email config |
| `/system` | `admin.system_info` | GET | System info |

### API Blueprint (`/api`)
| Route | Method | Purpose |
|-------|--------|---------|
| `/dns/<domain>/records` | GET | List records |
| `/dns/<domain>/records` | POST | Create record |
| `/dns/<domain>/records/<id>` | PUT | Update record |
| `/dns/<domain>/records/<id>` | DELETE | Delete record |
| `/ddns/<domain>/<hostname>` | GET/POST | DDNS update |
| `/myip` | GET | Get caller IP |

---

## Test Workflow Contracts

Test workflows in `ui_tests/workflows.py` must use these exact selectors:

### Email Config Page
```python
# Form fields
"#smtp_host"      # SMTP server
"#smtp_port"      # Port number
"#from_email"     # Sender email
"#smtp_username"  # Auth username
"#smtp_password"  # Auth password

# Buttons
'button[type="submit"]'  # Save button
'button:has-text("Send Test Email")'  # Test button
```

### Netcup Config Page
```python
# Form fields
"#customer_number"  # Customer number
"#api_key"          # API key
"#api_password"     # API password
"#api_endpoint"     # Endpoint URL
"#timeout"          # Timeout seconds

# Buttons
'button[type="submit"]'  # Save button
```

---

## Validation

Templates should be validated against this contract:
1. All required variables are passed by view functions
2. Form field IDs match documented selectors
3. Routes use correct endpoint names
4. Test workflows use documented selectors
