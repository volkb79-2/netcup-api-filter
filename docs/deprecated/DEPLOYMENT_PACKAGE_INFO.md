# Deployment Package - What's New

## Summary

Your new deployment package (`deploy.zip`) now includes comprehensive debugging and troubleshooting tools to help identify and resolve deployment issues on netcup webhosting.

**Package built:** November 16, 2025 at 23:03  
**SHA256:** `49ab065240e013e31e306817c8c01dd95fc7f99f7ce69aeac1d208eae4f96433`

## What's Included

### New Diagnostic Files

1. **`passenger_wsgi_hello.py`** - Hello World WSGI Application
   - Minimal test application with no dependencies
   - Shows environment diagnostics
   - Verifies Passenger is working before trying the full app
   - Use this FIRST to test basic setup

2. **`.htaccess.hello-world`** - Test Configuration
   - Minimal .htaccess for testing hello world
   - No PassengerPython needed
   - Use this to verify Passenger basics work

3. **`TROUBLESHOOTING.md`** - Complete Troubleshooting Guide
   - Detailed solutions for all common problems
   - Step-by-step diagnostic procedures
   - Configuration checklists
   - Log file locations
   - Testing methodology

4. **`DEBUG_QUICK_START.md`** - Quick Reference
   - Fast lookup for common issues
   - Emergency procedures
   - Testing workflow diagram
   - Where to find logs

### Existing Files (Still Included)

- All application Python files
- Complete `vendor/` directory with all dependencies
- `templates/` directory with admin UI
- Pre-initialized `netcup_filter.db` database
- Production `.htaccess` configuration
- `DEPLOY_README.md` deployment guide
- Example configuration files

## Recommended Testing Workflow

### Phase 1: Hello World Test (Start Here!)

This verifies that Passenger can run Python code at all.

1. **Extract deploy.zip and upload to webspace**
   - Upload ALL files including `passenger_wsgi_hello.py`
   - Upload `vendor/` and `templates/` directories

2. **Copy test configuration:**
   ```bash
   cp .htaccess.hello-world .htaccess
   ```
   Or via FTP: Rename `.htaccess.hello-world` to `.htaccess`

3. **Edit .htaccess:**
   - Change `PassengerAppRoot /netcup-api-filter` to your actual full path
   - Example: `PassengerAppRoot /www/htdocs/w0123456/hosting.vxxu.de/netcup-api-filter`

4. **Restart the application:**
   - Via SSH: `mkdir -p tmp && touch tmp/restart.txt`
   - Via FTP: Create folder `tmp/`, upload empty file `restart.txt`
   - Via Control Panel: Click "Anwendung Neuladen"

5. **Access your domain in browser:**
   - **Success:** You see a page titled "Success! Passenger WSGI is Working!"
     - Review the diagnostic information shown
     - Note the Python version
     - Verify files are listed correctly
     - → Proceed to Phase 2
   
   - **Failure:** Still see 404 or error
     - → Read TROUBLESHOOTING.md section "Problem: 404 Error"
     - Most likely: .htaccess is not in document root, or PassengerAppRoot is wrong

### Phase 2: Full Application Test

Once hello world works, test the full application.

1. **Switch to production configuration:**
   - Edit `.htaccess` to change:
     - `PassengerStartupFile passenger_wsgi_hello.py` 
     - to `PassengerStartupFile passenger_wsgi.py`

2. **Restart again:**
   - `touch tmp/restart.txt` or via control panel

3. **Access /admin:**
   - **Success:** Login page appears → You're done! 🎉
   - **Failure:** 500 error → Check error logs for specific issue

4. **Common Phase 2 Issues:**
   - "No module named 'flask'" → Verify vendor/ directory uploaded completely
   - "Database is locked" → Check file permissions on netcup_filter.db
   - "Template not found" → Verify templates/ directory uploaded

## Troubleshooting Your Current Issue

Based on your description, you're seeing 404 errors. This means Passenger isn't even trying to run your Python code. The issue is configuration, not the application itself.

### Most Likely Problem: .htaccess Location

**The Issue:**
- You mentioned `.htaccess` might not have effect because `/netcup-api-filter` is not part of the document root
- This is exactly the problem!

**The Solution:**
- `.htaccess` MUST be in the domain's document root that Apache serves
- On netcup, this is typically something like:
  - `/www/htdocs/w0123456/hosting.vxxu.de/.htaccess`

**Two Deployment Options:**

#### Option A: Files in Document Root
```
/www/htdocs/w0123456/hosting.vxxu.de/
├── .htaccess               ← Here!
├── passenger_wsgi.py
├── vendor/
├── templates/
└── ... (all other files)
```

In this case, `.htaccess` should have:
```apache
PassengerAppRoot /www/htdocs/w0123456/hosting.vxxu.de
```

#### Option B: Files in Subdirectory (Recommended)
```
/www/htdocs/w0123456/hosting.vxxu.de/
├── .htaccess               ← Still in document root!
└── netcup-api-filter/
    ├── passenger_wsgi.py
    ├── vendor/
    ├── templates/
    └── ... (all other files)
```

In this case, `.htaccess` should have:
```apache
PassengerAppRoot /www/htdocs/w0123456/hosting.vxxu.de/netcup-api-filter
```

### Missing Python Binary Issue

You mentioned there's no `/usr/bin/python3`. This is actually OK because:

1. **For hello world test:** No Python path needed at all (no dependencies)
2. **For full app:** Python is configured via control panel, not via PassengerPython
3. **All dependencies are vendored:** The `vendor/` directory has everything

**Action:** You can remove or comment out the `PassengerPython` line from `.htaccess`.

## Quick Start for Your Situation

Given what you've described, here's what to do:

### Step 1: Test with Hello World

1. Find your domain's actual document root (check FTP client or control panel)

2. Place `.htaccess` there with this content:
   ```apache
   PassengerEnabled on
   PassengerAppRoot /netcup-api-filter
   PassengerStartupFile passenger_wsgi_hello.py
   PassengerAppType wsgi
   ```

3. Edit `PassengerAppRoot` to be the full absolute path to where you uploaded files

4. Restart: Create/touch `tmp/restart.txt` in the netcup-api-filter directory

5. Access your domain - you should see diagnostics

### Step 2: Review Diagnostics

The hello world page will show you:
- Python version available
- Application directory (verify this matches PassengerAppRoot)
- Whether files are present
- Python path

### Step 3: Fix Any Issues

Based on diagnostics:
- If "Application Directory" is wrong → Fix PassengerAppRoot
- If files aren't listed → Upload files to correct location
- If vendor/ or templates/ missing → Upload those directories

### Step 4: Switch to Full App

Once hello world works, just change one line in `.htaccess`:
```apache
PassengerStartupFile passenger_wsgi.py
```

Then restart and test.

## Where to Find Help

1. **`DEBUG_QUICK_START.md`** - Quick lookup of common issues
2. **`TROUBLESHOOTING.md`** - Complete diagnostic procedures
3. **`DEPLOY_README.md`** - Full deployment instructions

## Need Logs?

### Application Logs
If the app starts at all, it creates:
- `netcup_filter.log` - in the application directory
- `netcup_filter_audit.log` - in the application directory

### Apache/Passenger Logs
Via hosting control panel or FTP:
- `~/logs/error.log` or `~/logs/error_log`

### Passenger-Specific Logs
May be in:
- Application directory: look for `passenger.log`
- Home directory: `~/logs/passenger.log`

## Summary of Key Points

1. ✅ **Start with hello world** - It has zero dependencies and verifies basic setup
2. ✅ **`.htaccess` location is critical** - Must be in document root
3. ✅ **PassengerAppRoot must be absolute path** - Full path from root of filesystem
4. ✅ **No PassengerPython needed** - Control panel Python config + vendored deps = sufficient
5. ✅ **Always restart after changes** - `touch tmp/restart.txt`

## Files to Review

Read these in order:

1. **DEBUG_QUICK_START.md** (5 min read) - Start here for quick fixes
2. **TROUBLESHOOTING.md** (15 min read) - Complete diagnostic procedures
3. **DEPLOY_README.md** (10 min read) - Full deployment guide

## Next Actions

1. Extract the new `deploy.zip`
2. Follow "Phase 1: Hello World Test" above
3. Once hello world works, switch to full app
4. If stuck at any point, consult TROUBLESHOOTING.md
5. Collect diagnostics from hello world page before asking for help

Good luck! The hello world test should quickly show you exactly what's wrong. 🚀
