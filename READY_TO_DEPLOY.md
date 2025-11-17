# READY TO DEPLOY - Instructions for Your Working Setup

## Status: ✅ Hello World is Working!

Your hello world test at https://hosting.vxxu.de/netcup-api-filter shows:
- ✅ Passenger is working
- ✅ Python 3.11.2 is running
- ✅ All files are uploaded correctly
- ✅ vendor/ and templates/ directories are present
- ✅ Database file exists

## What You Have Now

**Application Directory (from diagnostic page):**
```
/var/www/vhosts/hosting218629.ae98d.netcup.net/netcup-api-filter
```

**Control Panel Settings (should be):**
- App Root: `/netcup-api-filter` (relative path)
- Startup File: `passenger_wsgi_hello.py` (currently)
- Python Version: 3.11.2
- Modus: Entwicklung or Produktion

## Switch to Full Application - 2 Steps

### Step 1: Update .htaccess on Server

Via FTP or file manager, edit your `.htaccess` file on the server.

**Find this line:**
```apache
PassengerStartupFile passenger_wsgi_hello.py
```

**Change it to:**
```apache
PassengerStartupFile passenger_wsgi.py
```

**That's it!** All other settings stay the same:
```apache
PassengerEnabled on
PassengerAppRoot /netcup-api-filter
PassengerPython /usr/bin/python3
PassengerStartupFile passenger_wsgi.py  # ← Changed
PassengerAppType wsgi
```

### Step 2: Restart Application

**Option A - Via Control Panel:**
1. Go to Python settings
2. Click "Anwendung Neuladen"

**Option B - Via FTP/File Manager:**
1. Navigate to `/netcup-api-filter/tmp/`
2. Create or touch the file `restart.txt`
3. Wait 10 seconds

**Option C - Via SSH (if available):**
```bash
touch /var/www/vhosts/hosting218629.ae98d.netcup.net/netcup-api-filter/tmp/restart.txt
```

### Step 3: Test

Access: https://hosting.vxxu.de/netcup-api-filter/admin

**Expected Result:**
- You should see the admin login page
- Login with: `admin` / `admin`
- You'll be forced to change the password on first login

## Troubleshooting

### If you see 500 error after switching:

1. **Check error logs:**
   - Via Control Panel → Logs
   - Look for Python/Passenger errors
   - Should show specific error message

2. **Check application log:**
   - Via FTP: `/netcup-api-filter/netcup_filter.log`
   - Download and check for errors

3. **Common issues:**

   **"No module named 'flask'"**
   - Unlikely since vendor/ is confirmed present
   - But if it happens: Check that vendor/ was fully uploaded

   **"Database is locked" or permission errors**
   - Via FTP/file manager: Check netcup_filter.db permissions
   - Should be readable/writable by web server

   **"Template not found"**
   - Unlikely since templates/ is confirmed present
   - But verify templates/admin/ has all HTML files

### If it works immediately:

🎉 **Success!** You're done! 

Next steps:
1. Login to admin interface
2. Change admin password
3. Configure Netcup API credentials
4. Create API tokens for clients

## Understanding the Setup

### Why Relative Path Works

From netcup documentation:
> App Root ist relativ zum Webspace

Your setup:
- **Webspace root:** `/var/www/vhosts/hosting218629.ae98d.netcup.net/`
- **App Root (relative):** `/netcup-api-filter`
- **Full path:** `/var/www/vhosts/hosting218629.ae98d.netcup.net/netcup-api-filter`

The `.htaccess` in your app directory is correctly being read because:
1. Control panel Python settings point to this directory
2. Passenger knows to look there for configuration
3. The relative path `/netcup-api-filter` works with netcup's Passenger setup

### Why This is Better Than Document Root

Netcup recommends this for security:
- Your Python app files are **outside** the web-accessible document root
- Only the endpoints you configure are accessible via web
- Database and log files are protected from direct access

## For Future Reference

### Deployment Workflow

When you need to update the app:

1. Build new deployment: `./build_deployment.py`
2. Upload changed files via FTP
3. Restart: `touch tmp/restart.txt`

### Switching Between Hello World and Full App

Just change one line in `.htaccess`:
```apache
# For testing:
PassengerStartupFile passenger_wsgi_hello.py

# For production:
PassengerStartupFile passenger_wsgi.py
```

Then restart the app.

## Current Configuration Summary

**On Server (.htaccess in /netcup-api-filter/):**
```apache
PassengerEnabled on
PassengerAppRoot /netcup-api-filter
PassengerPython /usr/bin/python3
PassengerStartupFile passenger_wsgi_hello.py  # ← Change to passenger_wsgi.py
PassengerAppType wsgi
```

**In Control Panel:**
- App Root: `/netcup-api-filter`
- Startup File: Match what's in .htaccess
- Python Version: 3.11.2

**After your change:**
```apache
PassengerStartupFile passenger_wsgi.py  # ← Production
```

That's all you need to do! 🚀
