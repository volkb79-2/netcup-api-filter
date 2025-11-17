# Troubleshooting Guide - Netcup API Filter Deployment

This guide addresses common deployment issues for netcup webhosting and similar Phusion Passenger environments.

## Problem: 404 Error or "Not Found" Message

### Symptoms
- Browser shows 404 error
- Plain text message: "Not Found - The requested URL was not found on the server"

### Root Causes & Solutions

#### 1. .htaccess is not being read

**Cause:** The `.htaccess` file is not in the document root that Apache is serving.

**Solution:**
- On netcup webhosting, `.htaccess` must be in your domain's document root
- Example: If your domain is `hosting.vxxu.de`, the `.htaccess` should be at:
  - `/www/htdocs/w0123456/hosting.vxxu.de/.htaccess`
- Do NOT place it in a subdirectory like `/netcup-api-filter/.htaccess` unless that's the actual document root

**Action Steps:**
1. Find your domain's document root via hosting control panel
2. Move `.htaccess` to that location
3. Edit `PassengerAppRoot` to point to where your Python files are
4. Restart the application (create/touch `tmp/restart.txt`)

#### 2. PassengerAppRoot points to wrong location

**Cause:** The `PassengerAppRoot` directive doesn't match where you uploaded files.

**Solution:**
Edit `.htaccess` and verify the path:

```apache
# If files are in document root:
PassengerAppRoot /www/htdocs/w0123456/hosting.vxxu.de

# If files are in a subdirectory:
PassengerAppRoot /www/htdocs/w0123456/hosting.vxxu.de/netcup-api-filter
```

**How to find the correct path:**
1. SSH into your hosting (if available): `pwd` will show current directory
2. Or via FTP client: check the full path shown in the client
3. Or hosting control panel: Python settings usually show the paths

#### 3. Passenger is not enabled for your account

**Cause:** Phusion Passenger may not be available or enabled.

**Solution:**
- Check netcup hosting control panel → "Python" section
- Verify Passenger support is listed
- Contact netcup support if Passenger is not available

#### 4. Python version is not configured

**Cause:** No Python environment is set up in the hosting control panel.

**Solution:**
1. Go to netcup control panel → "Python" settings
2. Set:
   - **App Root:** `/netcup-api-filter` (or your actual path)
   - **Startup File:** `passenger_wsgi.py`
   - **Python Version:** 3.11.2 (or whatever is available)
   - **Modus:** `Entwicklung` or `Produktion`
3. Click "Konfiguration neu schreiben" to apply changes
4. Click "Anwendung Neuladen" to restart

## Problem: 500 Internal Server Error

### Symptoms
- HTTP 500 error in browser
- Application crashes during startup

### Root Causes & Solutions

#### 1. Missing or incomplete vendor/ directory

**Cause:** Dependencies were not uploaded or are incomplete.

**Solution:**
1. Re-extract `deploy.zip` locally
2. Verify `vendor/` directory contains subdirectories like:
   - `flask/`
   - `sqlalchemy/`
   - `requests/`
   - `yaml/`
   - etc. (should be ~34 packages)
3. Upload entire `vendor/` directory via FTP (this may take 10-15 minutes)
4. Ensure FTP transfer mode is BINARY (not ASCII)

#### 2. Python version mismatch

**Cause:** Hosting Python version is too old.

**Solution:**
- Minimum required: Python 3.9
- Recommended: Python 3.11+
- Check hosting control panel → Python settings
- Select newest available version

#### 3. Import errors or missing modules

**Cause:** Vendor directory is not being found.

**Solution:**
Check that `passenger_wsgi.py` has this code near the top:

```python
vendor_dir = os.path.join(app_dir, 'vendor')
if os.path.isdir(vendor_dir):
    sys.path.insert(0, vendor_dir)
```

#### 4. Database initialization failed

**Cause:** Database file is missing or not writable.

**Solution:**
1. Verify `netcup_filter.db` was uploaded
2. Check permissions: File should be readable/writable by web server
3. Via SSH (if available):
   ```bash
   chmod 644 netcup_filter.db
   ```
4. Ensure parent directory is writable (SQLite needs to create journal files)

#### 5. Check error logs

**Location of error logs:**
- Via hosting control panel: Usually under "Logs" or "Statistics"
- Via SSH: `~/logs/error.log` or `~/logs/error_log`
- Via FTP: Look for `logs/` directory in your home folder

**Look for messages like:**
- `ImportError: No module named 'flask'` → vendor/ directory issue
- `sqlite3.OperationalError: unable to open database` → database permissions
- `SyntaxError` → Python version too old

## Step-by-Step Diagnostic Procedure

### Phase 1: Test Basic WSGI

**Goal:** Verify Passenger can run Python code at all.

1. **Upload the hello world test:**
   - Use `passenger_wsgi_hello.py` (included in this repository)
   - Upload via FTP to your app directory

2. **Create test .htaccess:**
   ```apache
   PassengerEnabled on
   PassengerAppRoot /your/actual/path
   PassengerStartupFile passenger_wsgi_hello.py
   PassengerAppType wsgi
   ```

3. **Access your domain:**
   - If you see "Success! Passenger WSGI is Working!" → Passenger is OK, proceed to Phase 2
   - If you still get 404/500 → Fix basic configuration first

4. **Check the diagnostic information:**
   - Note the Python version shown
   - Verify "Application Directory" matches your upload location
   - Check that files are listed correctly

### Phase 2: Test Full Application

1. **Switch back to main application:**
   - Rename or modify `.htaccess` to use `passenger_wsgi.py`
   - Restart application: `touch tmp/restart.txt` (create `tmp/` directory if needed)

2. **Watch for errors:**
   - Check error logs immediately
   - Look for specific error messages

3. **Common error patterns:**

   **"No module named 'flask'"**
   - Upload vendor/ directory completely
   - Verify PassengerAppRoot is correct
   
   **"Database is locked"**
   - Check file permissions on .db file
   - Ensure no other process is using it
   
   **"Template not found"**
   - Upload templates/ directory
   - Verify directory structure is intact

## Configuration Checklist

Use this checklist to verify your setup:

### Files Uploaded ✓
- [ ] `passenger_wsgi.py` (or `passenger_wsgi_hello.py` for testing)
- [ ] `filter_proxy.py`
- [ ] `admin_ui.py`
- [ ] `database.py`
- [ ] `access_control.py`
- [ ] `netcup_client.py`
- [ ] All other `.py` files
- [ ] `netcup_filter.db`
- [ ] `.htaccess` (in document root!)
- [ ] `vendor/` directory with all subdirectories
- [ ] `templates/` directory with all HTML files
- [ ] `requirements.txt`

### .htaccess Configuration ✓
- [ ] `PassengerEnabled on`
- [ ] `PassengerAppRoot` points to correct absolute path
- [ ] `PassengerStartupFile passenger_wsgi.py`
- [ ] `PassengerAppType wsgi`
- [ ] File is in the domain's document root

### Hosting Control Panel ✓
- [ ] Python app configured
- [ ] App Root path matches PassengerAppRoot
- [ ] Startup file is `passenger_wsgi.py`
- [ ] Python version is 3.9 or higher
- [ ] Configuration saved and applied

### File Permissions ✓
- [ ] `netcup_filter.db` is readable/writable (644 or 666)
- [ ] Application directory is readable/executable (755)
- [ ] All .py files are readable (644)

## Getting Logs

### Method 1: Check Application Logs

The application creates its own log files:

1. Via FTP, look for:
   - `netcup_filter.log` (application log)
   - `netcup_filter_audit.log` (audit log)

2. Download and check for error messages

### Method 2: Check Passenger Logs

Passenger may create logs in:
- `~/logs/passenger.log`
- Application directory might have `passenger.log`

### Method 3: Check Apache Error Logs

Via hosting control panel or FTP:
- `~/logs/error.log`
- `~/logs/error_log`

Look for lines containing:
- Your domain name
- Python
- passenger
- netcup-filter

## Testing Checklist

Work through these tests in order:

### Test 1: Can Apache serve files?
- Upload a simple `test.html` file
- Access it via browser
- **Pass:** HTML shows → Apache works
- **Fail:** 404 error → Check document root

### Test 2: Is Passenger enabled?
- Use `.htaccess.hello-world` configuration
- Use `passenger_wsgi_hello.py`
- Access domain in browser
- **Pass:** See diagnostics page → Passenger works
- **Fail:** 404/500 error → Check Passenger configuration

### Test 3: Are dependencies available?
- Check diagnostics page shows vendor/ directory exists
- Check Python path includes vendor/
- **Pass:** vendor/ is present → Dependencies OK
- **Fail:** vendor/ missing → Upload vendor/ directory

### Test 4: Does full app start?
- Switch to `passenger_wsgi.py`
- Access domain in browser
- **Pass:** See login page or admin interface → Success!
- **Fail:** Error → Check logs for specific error

## Common Netcup-Specific Issues

### Issue: PassengerPython path doesn't work

**Problem:** You don't know the Python binary path.

**Solution:** Don't set PassengerPython at all!
- Remove or comment out the `PassengerPython` line from `.htaccess`
- Use the Python version configured in the control panel
- The vendor/ directory has all dependencies anyway

### Issue: tmp/restart.txt doesn't restart app

**Solution:**
1. Make sure `tmp/` directory exists in your PassengerAppRoot
2. Create it if needed: `mkdir tmp`
3. Use: `touch tmp/restart.txt` or just create the file via FTP
4. Wait 5-10 seconds for Passenger to detect the change

### Issue: Changes to .htaccess don't take effect

**Solution:**
1. Save the .htaccess file
2. Trigger a restart: Create/touch `tmp/restart.txt`
3. Clear browser cache
4. Wait a minute and try again

## Still Not Working?

### Gather Information

Before seeking help, collect:

1. **Exact error message** from browser
2. **Error log contents** (last 20-30 lines)
3. **Python version** from hosting panel
4. **Full path** where files are uploaded
5. **Contents of .htaccess** (sanitize passwords if any)
6. **Output from hello world test** (if that works)

### Get Help

- Create GitHub issue with information above
- Contact netcup support for Passenger-specific questions
- Check netcup documentation for Python hosting

## Quick Reference: Restart Application

After making changes, restart the app:

**Method 1: Via Control Panel**
- Click "Anwendung Neuladen" or "Restart Application"

**Method 2: Via SSH**
```bash
cd /path/to/app
mkdir -p tmp
touch tmp/restart.txt
```

**Method 3: Via FTP**
- Navigate to application directory
- Create folder `tmp` if it doesn't exist
- Upload an empty file named `restart.txt` to `tmp/`

The application will restart within a few seconds.

---

## Success Indicators

You'll know it's working when:

1. ✅ Browser shows admin login page at `/admin`
2. ✅ Can login with admin/admin
3. ✅ Admin interface loads without errors
4. ✅ No error messages in browser console
5. ✅ Log files show successful startup messages

Good luck! 🚀
