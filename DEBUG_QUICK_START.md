# Quick Debugging Steps

## You're seeing 404 or "Not Found" errors?

### Start with the Hello World test:

1. **Make sure `.htaccess` is in the RIGHT place:**
   - It MUST be in your domain's document root
   - On netcup: `/www/htdocs/w0123456/yourdomain.com/.htaccess`
   - NOT in a subdirectory!

2. **Use the test configuration:**
   ```bash
   # Via FTP or SSH, rename/copy:
   cp .htaccess.hello-world .htaccess
   ```

3. **Edit the test .htaccess:**
   - Change `PassengerAppRoot /netcup-api-filter` to your FULL path
   - Example: `PassengerAppRoot /www/htdocs/w0123456/yourdomain.com/netcup-api-filter`

4. **Restart the app:**
   - Via SSH: `mkdir -p tmp && touch tmp/restart.txt`
   - Via FTP: Create folder `tmp/`, upload empty file `restart.txt` into it
   - Via Control Panel: Click "Anwendung Neuladen"

5. **Access your domain:**
   - If you see diagnostic information → Passenger works! ✅
   - If still 404 → `.htaccess` is not being read, check location

### Next: Test the full application

1. **Switch .htaccess back to production:**
   - Edit `.htaccess` to use `PassengerStartupFile passenger_wsgi.py`
   - Or restore original .htaccess

2. **Restart again:**
   - `touch tmp/restart.txt`

3. **Check for errors:**
   - Look at error logs
   - See TROUBLESHOOTING.md for detailed steps

## Common Issues - Quick Fixes

### "No module named 'flask'" or similar import errors
**→ Upload the entire `vendor/` directory via FTP**

### "Database is locked" or "unable to open database"
**→ Check permissions: `chmod 644 netcup_filter.db`**

### "Template not found"
**→ Upload the entire `templates/` directory**

### Changes don't take effect
**→ Restart: `touch tmp/restart.txt` (wait 10 seconds)**

### Still not working?
**→ Read TROUBLESHOOTING.md for complete diagnostic procedure**

## Where are the logs?

Application logs (if app starts):
- `netcup_filter.log` (in app directory)
- `netcup_filter_audit.log` (in app directory)

Apache/Passenger logs:
- `~/logs/error.log` or `~/logs/error_log`
- Via hosting control panel → Logs section

## Need to verify Python is configured?

Via netcup control panel:
1. Go to "Python" settings (should say "Python für hosting.vxxu.de")
2. Check settings:
   - **App Root:** Should be `/netcup-api-filter` (or your directory name)
   - **Startup Datei:** Should be `passenger_wsgi.py`
   - **Python Version:** Should be 3.11.2 or higher
3. Click "Konfiguration neu schreiben" after changes
4. Click "Anwendung Neuladen" to restart

## Testing Workflow

```
1. Hello World Test
   ├─ Works? → Passenger is OK
   │  └─ Go to step 2
   └─ Fails? → Fix .htaccess location and PassengerAppRoot
      └─ Check TROUBLESHOOTING.md "Problem: 404 Error"

2. Full Application Test
   ├─ Works? → Success! 🎉
   │  └─ Access /admin and login
   └─ Fails with 500? → Check logs for specific error
      ├─ Import error? → Upload vendor/ directory
      ├─ Database error? → Check file permissions
      └─ Template error? → Upload templates/ directory
```

## Emergency Reset

If everything is broken:

1. Delete everything in the app directory
2. Re-extract deploy.zip locally
3. Upload ALL files via FTP (including vendor/ and templates/)
4. Edit .htaccess with correct paths
5. Restart: `touch tmp/restart.txt`

## Getting Help

When asking for help, provide:
1. Exact error message from browser
2. Last 20 lines from error log
3. Python version (from control panel or hello world test)
4. Full path where you uploaded files
5. Contents of your .htaccess (remove sensitive info)

See TROUBLESHOOTING.md for complete documentation.
