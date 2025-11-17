# Debugging the 404 Error - Action Plan

## Current Situation

✅ **Hello world works** - Passenger can run Python  
❌ **Full app shows 404** - The real app crashes silently  
📝 **Logs are empty (0 bytes)** - App crashes before logging starts

## Key Discovery

**The Control Panel UI "Startup Datei" setting OVERRIDES .htaccess!**

You saw hello world even though `.htaccess` said `passenger_wsgi.py` because the Control Panel was still set to `passenger_wsgi_hello.py`.

## Why the App is Failing

When `passenger_wsgi.py` crashes during startup (before it can initialize logging), Passenger returns a 404 error by default.

Most likely causes:
1. Import error - missing module from vendor/
2. Syntax error in one of the Python files
3. Database initialization problem
4. Permission issue

## Action Plan - Use Debug Version

I've created `passenger_wsgi_debug.py` which:
- Catches ALL startup errors
- Displays the full error message in the browser
- Logs errors to `netcup_filter_startup_error.log`
- Shows exactly which import fails

### Step 1: Switch to Debug Version

**Via Control Panel:**
1. Go to Python settings
2. Change "Startup Datei" to: `passenger_wsgi_debug.py`
3. Click "Konfiguration neu schreiben"
4. Click "Anwendung Neuladen"

### Step 2: Access Your Site

Visit: https://hosting.vxxu.de/netcup-api-filter

You should now see:
- **If it works:** The admin interface loads
- **If it fails:** A detailed error page showing:
  - The exact error message
  - Full Python traceback
  - Which import/line failed
  - Python path and directory info

### Step 3: Check the Error Log

Via SSH or FTP, check for:
```
/var/www/vhosts/hosting218629.ae98d.netcup.net/netcup-api-filter/netcup_filter_startup_error.log
```

This will have the complete error details even if the browser doesn't show them.

## Likely Issues and Solutions

### Issue 1: Missing vendor/ files

**Symptom:** `ImportError: No module named 'flask'` or similar

**Solution:**
1. Check that vendor/ was fully uploaded (should have ~38 subdirectories)
2. Re-upload vendor/ directory if needed
3. Use binary transfer mode in FTP

### Issue 2: Python version too old

**Symptom:** `SyntaxError` in the traceback

**Solution:**
- Needs Python 3.9+, you have 3.11.2, so this should be fine

### Issue 3: Database permissions

**Symptom:** `sqlite3.OperationalError: unable to open database file`

**Solution:**
```bash
chmod 644 netcup_filter.db
chmod 755 .  # Make sure directory is accessible
```

### Issue 4: Missing __pycache__ write permission

**Symptom:** `PermissionError` when trying to create .pyc files

**Solution:**
```bash
chmod 755 __pycache__
# Or just delete it:
rm -rf __pycache__
```

## What the Debug Version Does Differently

**Regular passenger_wsgi.py:**
- Crashes silently → Passenger shows 404
- Can't log errors because logging isn't set up yet

**Debug passenger_wsgi_debug.py:**
- Wraps EVERYTHING in try/except
- Shows errors in browser as HTML
- Logs to separate error file
- Continues to work as WSGI app even when crashed

## After You Find the Error

Once you see the actual error message:

1. **Fix the issue** (based on the error)
2. **Test again** with debug version
3. **When it works**, switch back to production:
   - Change "Startup Datei" to `passenger_wsgi.py`
   - Reload application

## Alternative: Check Passenger Logs

Passenger might have its own logs showing the crash:

**Locations to check:**
- `~/logs/error.log` or `~/logs/error_log`
- Application directory: look for `passenger.log`
- Control Panel → Logs section

Look for recent entries (23:20 or later) containing:
- Python errors
- passenger errors
- Your domain name

## Quick Test Commands

Via SSH:

```bash
cd /var/www/vhosts/hosting218629.ae98d.netcup.net/netcup-api-filter

# Check vendor directory
ls -la vendor/ | head -20

# Check file permissions
ls -la netcup_filter.db

# Try to import Flask manually
python3 -c "import sys; sys.path.insert(0, 'vendor'); import flask; print('Flask OK')"

# Try to import all our modules
python3 -c "import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'vendor'); import filter_proxy; print('filter_proxy OK')"
```

## Next Steps

1. **Upload `passenger_wsgi_debug.py`** (included in new deploy.zip, or upload manually)
2. **Change Control Panel setting** to use debug version
3. **Reload and visit site** - you'll see the actual error
4. **Report back** with the error message shown
5. **We'll fix** the specific issue
6. **Switch to production** version once working

The debug version will tell us exactly what's wrong! 🔍

## Incremental WSGI Test Files

Use the new entry-points to narrow down exactly where startup fails. Upload all of them once, then switch the "Startup Datei" field in the control panel step-by-step:

1. **`wsgi_step1_basic.py`** – static HTML page. Confirms Passenger + Python wiring only.
2. **`wsgi_step2_flask.py`** – imports Flask from `vendor/`. If this fails, the upload is incomplete.
3. **`wsgi_step3_filter_proxy.py`** – imports our `filter_proxy` module but does not run Flask.
4. **`wsgi_step4_app.py`** – binds to `filter_proxy.app` so we know the Flask app object loads.
5. **`wsgi_env_info.py`** – diagnostic page that lists environment variables, sys.path, and request info (handy when talking to hosting support).

### Testing Sequence

1. Set Startup Datei → `wsgi_step1_basic.py` and reload. If it fails, the issue is outside our code (permissions/App Root).
2. Move to each subsequent file. When one fails, keep it active and collect the error message (each file prints traceback info directly in the browser and/or writes a `.txt` log in the app directory).
3. Once `wsgi_step4_app.py` is green, switch to the full `passenger_wsgi.py` again and continue debugging there.

> Tip: Keep `wsgi_env_info.py` handy. When reporting problems to netcup support, include a screenshot of its output so they can see the exact interpreter and paths Passenger provides.
