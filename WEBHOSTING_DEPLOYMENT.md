# Webhosting Deployment Guide

This guide explains how to deploy the Netcup API Filter on shared webhosting environments (like Netcup Webhosting 4000).

## Prerequisites

- Shared hosting account with:
  - Python 3.7+ support
  - FTP/SFTP access (required for all methods)
  - SSH access (optional, only for Method 2)
  - Apache with Phusion Passenger support (standard on Netcup)
  - Access to configure .htaccess files

## Deployment Methods

### Method 1: Pre-Built Package (FTP-Only, No Command Line!) 🚀

**Perfect for users WITHOUT SSH access or command line experience!**

This method uses a pre-built deployment package with all dependencies bundled. You only need FTP/SFTP access.

#### Step 1: Build the Deployment Package

On your local machine (with Python installed):

```bash
# Clone or download the repository
git clone https://github.com/volkb79-2/netcup-api-filter.git
cd netcup-api-filter

# Build the deployment package
python build_deployment.py
```

This creates:
- `deploy.zip` - Ready-to-deploy package (includes all dependencies)
- `deploy.zip.sha256` - Hash for verification
- `deploy/` - Directory with all files (if you prefer to upload directly)

#### Step 2: Upload via FTP/SFTP

1. **Connect to your netcup webhosting via FTP/SFTP:**
   - Host: `ftp.yourdomain.com` or via SFTP: `ssh.webhosting-XXX.your-server.de`
   - Use your netcup webhosting credentials
   - Port 21 (FTP) or 22 (SFTP)

2. **Navigate to your domain directory:**
   - Example: `/www/htdocs/w0123456/yourdomain.com/`

3. **Create application directory:**
   - Create folder: `netcup-filter/`

4. **Upload files:**
   - Extract `deploy.zip` on your local computer
   - Upload ALL files and folders to `netcup-filter/` directory
   - Ensure you upload:
     - `vendor/` directory with ALL subdirectories (contains Python packages)
     - `templates/` directory with all HTML files
     - All `.py` files
     - `.htaccess` file
     - `netcup_filter.db` file
     - `DEPLOY_README.md` file

#### Step 3: Edit .htaccess

Open `.htaccess` in your FTP client's text editor (or download, edit locally, and re-upload):

**Find these lines:**
```apache
PassengerAppRoot /path/to/your/domain/netcup-filter
PassengerPython /path/to/your/domain/netcup-filter/venv/bin/python3
```

**Change to your actual paths:**
```apache
PassengerAppRoot /www/htdocs/w0123456/yourdomain.com/netcup-filter
PassengerPython /usr/bin/python3
```

**Important notes:**
- Replace `w0123456` with your actual webhosting ID
- Replace `yourdomain.com` with your actual domain
- Use system Python (`/usr/bin/python3`), NOT a venv path
- Save the file

#### Step 4: Test the Deployment

1. Open your browser to: `https://yourdomain.com/admin`
2. You should see the login page
3. Login with:
   - Username: `admin`
   - Password: `admin`
4. You'll be forced to change the password on first login

#### Step 5: Configure

1. **Change admin password** (required on first login)
2. **Configure Netcup API credentials:**
   - Go to "Configuration" → "Netcup API"
   - Enter your Netcup customer ID, API key, and API password
   - Click "Save"
3. **Create API tokens:**
   - Go to "Management" → "Clients"
   - Create clients with appropriate permissions

**Done!** Your Netcup API Filter is now running. See `DEPLOY_README.md` (included in the package) for troubleshooting and additional information.

---

### Method 2: Traditional Deployment (Requires SSH Access)

Netcup webhosting supports Phusion Passenger, which is the recommended deployment method for Python web applications.

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
git clone https://github.com/volkb79-2/netcup-api-filter.git .
```

#### Step 2: Install Dependencies

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

#### Step 3: Configure Database and Admin

The application now uses a database (SQLite) for configuration and stores most settings via the admin UI.

```bash
# Initialize database (will create default admin user)
python -c "from flask import Flask; from database import init_db; app = Flask(__name__); app.config['SECRET_KEY'] = 'temp'; init_db(app)"
```

**Default admin credentials:** `admin` / `admin` (you will be forced to change this on first login)

#### Step 4: Create .htaccess

Create a `.htaccess` file in the `netcup-filter` directory:

```apache
# .htaccess for Phusion Passenger deployment

# Enable Passenger
PassengerEnabled on
PassengerAppRoot /path/to/your/domain/netcup-filter

# Python configuration
PassengerPython /path/to/your/domain/netcup-filter/venv/bin/python3
PassengerStartupFile passenger_wsgi.py
PassengerAppType wsgi

# Optional: Set environment variables
SetEnv NETCUP_FILTER_DB_PATH /path/to/your/domain/netcup-filter/netcup_filter.db

# Protect sensitive files
<FilesMatch "^(config\.yaml|\.env|netcup_filter\.db|.*\.log)$">
    Require all denied
</FilesMatch>

# Allow admin UI access
<Location /admin>
    Require all granted
</Location>
```

**Important**: Replace `/path/to/your/domain/netcup-filter` with the actual path.

#### Step 5: Test the Deployment

```bash
# Test health endpoint
curl https://yourdomain.com/

# Access admin UI
# Navigate to: https://yourdomain.com/admin
# Login with: admin / admin (change password when prompted)
```

#### Step 6: Configure via Admin UI

1. Navigate to `https://yourdomain.com/admin`
2. Login with `admin` / `admin`
3. Change your password when prompted
4. Go to Configuration → Netcup API and enter your Netcup credentials
5. Go to Management → Clients to create API tokens
6. (Optional) Configure email settings in Configuration → Email Settings

#### Database Location

By default, the database is created in the current working directory. On shared hosting, you may want to specify a location:

```apache
# In .htaccess
SetEnv NETCUP_FILTER_DB_PATH /path/to/writable/directory/netcup_filter.db
```

Or check the System Info page in the admin UI to see where the database is located and verify filesystem access.

---

### Method 2: WSGI Deployment (Alternative)

If Passenger is not available, use standard WSGI deployment.

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

### Issue: Admin UI Not Accessible

**Solutions:**
1. Check that `.htaccess` allows access to `/admin` path
2. Verify `passenger_wsgi.py` is configured correctly
3. Ensure database is initialized and accessible
4. Check Apache error logs for specific errors
5. Try accessing root `/` first to ensure app is running

### Issue: Database Errors

**Solutions:**
1. Check database file permissions: `ls -la netcup_filter.db`
2. Verify directory is writable by web server user
3. Set `NETCUP_FILTER_DB_PATH` environment variable to a writable location
4. Check System Info page in admin UI for filesystem access tests
5. Ensure SQLite is installed: `python -c "import sqlite3; print(sqlite3.version)"`

### Issue: 500 Internal Server Error

**Solutions:**
1. Check Apache/Passenger error logs: `tail -f ~/logs/error.log` (path may vary)
2. Check application log: `tail -f netcup_filter.log`
3. Verify Python path in `.htaccess` matches your actual paths
4. Ensure all files have correct permissions
5. Check that virtual environment is activated and dependencies installed
6. Verify `passenger_wsgi.py` exists and is executable

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

# 5. Initialize database
python -c "from flask import Flask; from database import init_db; app = Flask(__name__); app.config['SECRET_KEY'] = 'temp'; init_db(app)"

# 6. (Optional) Migrate existing YAML config
# If you have an existing config.yaml:
cp config.example.yaml config.yaml
nano config.yaml  # Edit with your settings
python migrate_yaml_to_db.py

# 7. Create .htaccess (use Passenger example above)
nano .htaccess

# 8. Set permissions
chmod 755 .
chmod 644 *.py
chmod 600 config.yaml

# 9. Test
curl https://yourdomain.com/netcup-api-filter/
```

Your Netcup API Filter is now running on shared webhosting!
