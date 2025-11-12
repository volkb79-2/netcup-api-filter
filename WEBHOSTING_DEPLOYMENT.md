# Webhosting Deployment Guide

This guide explains how to deploy the Netcup API Filter on shared webhosting environments (like Netcup Webhosting 4000) where you have SSH access but cannot run Docker containers.

## Prerequisites

- Shared hosting account with:
  - Python 3.7+ support
  - SSH access
  - Apache with mod_wsgi or CGI support
  - Access to configure .htaccess files

## Deployment Methods

### Method 1: WSGI Deployment (Recommended)

WSGI (Web Server Gateway Interface) is the recommended method for Python web applications on shared hosting.

#### Step 1: Upload Files

Upload all files via SSH/SFTP to your webhosting account:

```bash
# Connect via SSH
ssh username@ssh.webhosting-123.your-server.de

# Navigate to your web directory
cd /path/to/your/domain/

# Create application directory
mkdir netcup-filter
cd netcup-filter

# Upload files (or use git clone)
# You can use scp, sftp, or git to get files here
```

Upload these files:
- `filter_proxy.py`
- `netcup_client.py`
- `access_control.py`
- `wsgi.py`
- `requirements.txt`
- `config.yaml` (created from config.example.yaml)

#### Step 2: Install Dependencies

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

#### Step 3: Configure Application

```bash
# Copy example config
cp config.example.yaml config.yaml

# Edit configuration with your credentials
nano config.yaml
```

Fill in your Netcup API credentials and configure tokens.

#### Step 4: Create .htaccess

Create a `.htaccess` file in the `netcup-filter` directory:

```apache
# .htaccess for WSGI deployment

# Use WSGI if available
<IfModule mod_wsgi.c>
    WSGIScriptAlias / /path/to/your/domain/netcup-filter/wsgi.py
    WSGIPythonPath /path/to/your/domain/netcup-filter:/path/to/your/domain/netcup-filter/venv/lib/python3.9/site-packages
    
    <Directory /path/to/your/domain/netcup-filter>
        <Files wsgi.py>
            Require all granted
        </Files>
    </Directory>
</IfModule>

# Protect sensitive files
<FilesMatch "^(config\.yaml|\.env)$">
    Require all denied
</FilesMatch>
```

**Important**: Replace `/path/to/your/domain/netcup-filter` with the actual path.

#### Step 5: Set Environment Variable (Optional)

If your config file is in a different location:

```bash
export NETCUP_FILTER_CONFIG=/path/to/config.yaml
```

Add this to your `.bashrc` or `.profile` to make it persistent.

#### Step 6: Test the Deployment

```bash
# Test health endpoint
curl https://yourdomain.com/netcup-filter/

# Test API endpoint (with a valid token)
curl -X POST https://yourdomain.com/netcup-filter/api \
  -H "Content-Type: application/json" \
  -H "Authorization: ******" \
  -d '{"action":"infoDnsZone","param":{"domainname":"yourdomain.com"}}'
```

---

### Method 2: CGI Deployment (Fallback)

If WSGI is not available, use CGI deployment.

#### Step 1-3: Same as WSGI

Follow steps 1-3 from the WSGI deployment method above.

#### Step 4: Create .htaccess for CGI

Create a `.htaccess` file:

```apache
# .htaccess for CGI deployment

Options +ExecCGI
AddHandler cgi-script .py

# Rewrite rules to route all requests to CGI handler
RewriteEngine On
RewriteCond %{REQUEST_FILENAME} !-f
RewriteCond %{REQUEST_FILENAME} !-d
RewriteRule ^(.*)$ cgi_handler.py [L]

# Protect sensitive files
<FilesMatch "^(config\.yaml|\.env)$">
    Require all denied
</FilesMatch>
```

#### Step 5: Make CGI Handler Executable

```bash
chmod +x cgi_handler.py
```

#### Step 6: Test the Deployment

Same as WSGI method step 6.

---

## Netcup Webhosting 4000 Specific Instructions

For Netcup Webhosting 4000 (https://www.netcup.com/de/hosting/webhosting/webhosting-4000-nue):

### Available Python Versions

Netcup webhosting typically supports Python 3.9+. Check with:

```bash
python3 --version
```

### Directory Structure

```
/www/htdocs/w0123456/
├── yourdomain.com/
│   └── netcup-filter/
│       ├── venv/
│       ├── filter_proxy.py
│       ├── netcup_client.py
│       ├── access_control.py
│       ├── wsgi.py
│       ├── cgi_handler.py
│       ├── config.yaml
│       ├── requirements.txt
│       └── .htaccess
```

### File Permissions

```bash
# Set correct permissions
chmod 755 netcup-filter/
chmod 644 *.py
chmod 755 cgi_handler.py  # Only if using CGI
chmod 600 config.yaml
```

### Python Path Configuration

If you encounter import errors, you may need to adjust the Python path in `wsgi.py` or `cgi_handler.py`:

```python
import sys
sys.path.insert(0, '/www/htdocs/w0123456/yourdomain.com/netcup-filter')
sys.path.insert(0, '/www/htdocs/w0123456/yourdomain.com/netcup-filter/venv/lib/python3.9/site-packages')
```

---

## Alternative: Running as Background Service

If your hosting provider allows persistent processes (check with support):

```bash
# Using screen or tmux
screen -S netcup-filter
cd /path/to/netcup-filter
source venv/bin/activate
python filter_proxy.py config.yaml

# Detach with Ctrl+A, D
```

Or use a process manager like `supervisor` if available.

---

## Troubleshooting

### Issue: 500 Internal Server Error

**Solutions:**
1. Check Apache error logs: `tail -f /var/log/apache2/error.log`
2. Verify Python path in `.htaccess` matches your actual paths
3. Ensure all files have correct permissions
4. Check that virtual environment is activated and dependencies installed

### Issue: Module Import Errors

**Solutions:**
1. Verify `sys.path` includes your application directory
2. Check virtual environment Python version matches hosting Python version
3. Reinstall dependencies: `pip install --force-reinstall -r requirements.txt`

### Issue: Configuration Not Found

**Solutions:**
1. Check `NETCUP_FILTER_CONFIG` environment variable
2. Verify `config.yaml` is in the same directory as `wsgi.py`
3. Use absolute path in environment variable

### Issue: Permission Denied for config.yaml

**Solutions:**
1. Ensure web server user can read config.yaml
2. Set permissions: `chmod 640 config.yaml`
3. Check directory permissions: `chmod 755 netcup-filter/`

---

## Security Considerations for Shared Hosting

1. **Protect config.yaml**: Ensure it's not accessible via web
   ```apache
   <FilesMatch "^config\.yaml$">
       Require all denied
   </FilesMatch>
   ```

2. **Use HTTPS**: Always deploy behind HTTPS (most providers offer Let's Encrypt)

3. **Restrict access by IP**: Add to .htaccess if you want to limit access:
   ```apache
   <RequireAll>
       Require ip 192.168.1.0/24
       Require ip 10.0.0.0/8
   </RequireAll>
   ```

4. **Monitor logs**: Regularly check access logs for suspicious activity

5. **Keep dependencies updated**: 
   ```bash
   pip list --outdated
   pip install --upgrade -r requirements.txt
   ```

---

## Performance Tips

1. **Use WSGI over CGI**: WSGI is significantly faster
2. **Enable caching**: Configure Apache's mod_cache if available
3. **Limit token count**: Each request validates against all tokens
4. **Use specific IP whitelists**: Reduces validation overhead

---

## Getting Help

- Check your hosting provider's Python documentation
- Review Apache error logs
- Test locally first: `python filter_proxy.py`
- Contact hosting support for WSGI/CGI configuration help

---

## Example: Complete Setup on Netcup Webhosting

```bash
# 1. Connect via SSH
ssh w0123456@ssh.webhosting-123.your-server.de

# 2. Navigate to web directory
cd /www/htdocs/w0123456/yourdomain.com/

# 3. Clone or upload files
git clone https://github.com/volkb79-2/netcup-api-filter.git
cd netcup-api-filter

# 4. Setup virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 5. Configure
cp config.example.yaml config.yaml
nano config.yaml  # Edit with your settings

# 6. Generate token
python generate_token.py \
  --description "My Host DynDNS" \
  --domain yourdomain.com \
  --record-name myhost \
  --record-types A \
  --operations read,update

# 7. Create .htaccess (use WSGI example above)
nano .htaccess

# 8. Set permissions
chmod 755 .
chmod 644 *.py
chmod 600 config.yaml

# 9. Test
curl https://yourdomain.com/netcup-api-filter/
```

Your Netcup API Filter is now running on shared webhosting!
