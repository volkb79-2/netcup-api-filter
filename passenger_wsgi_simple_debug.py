"""
Simple Debug WSGI - Shows exactly what error occurs during import
"""
import sys
import os

app_dir = os.path.dirname(__file__) or os.getcwd()
sys.path.insert(0, app_dir)
vendor_dir = os.path.join(app_dir, 'vendor')
if os.path.isdir(vendor_dir):
    sys.path.insert(0, vendor_dir)

error_message = None

try:
    # Try step by step
    import logging
    logging.basicConfig(level=logging.INFO, filename='startup_debug.log')
    log = logging.getLogger(__name__)
    
    log.info("=== STARTUP DEBUG ===")
    log.info(f"App dir: {app_dir}")
    log.info(f"Vendor dir exists: {os.path.isdir(vendor_dir)}")
    log.info(f"Python version: {sys.version}")
    
    log.info("Importing Flask...")
    from flask import Flask
    log.info("Flask OK")
    
    log.info("Importing database...")
    from database import init_db
    log.info("database OK")
    
    log.info("Importing admin_ui...")
    from admin_ui import setup_admin_ui
    log.info("admin_ui OK")
    
    log.info("Importing filter_proxy...")
    from filter_proxy import app, limiter
    log.info("filter_proxy OK")
    
    log.info("All imports successful!")
    
    # If we got here, use the real app
    application = app
    
except Exception as e:
    import traceback
    error_details = traceback.format_exc()
    error_message = str(e)
    
    # Write to file
    try:
        with open(os.path.join(app_dir, 'startup_error.txt'), 'w') as f:
            f.write("STARTUP ERROR\n")
            f.write("=" * 60 + "\n")
            f.write(error_details)
    except:
        pass
    
    # Create error display app
    def application(environ, start_response):
        status = '500 Internal Server Error'
        headers = [('Content-Type', 'text/html; charset=utf-8')]
        start_response(status, headers)
        
        html = """<!DOCTYPE html>
<html>
<head><title>Startup Error</title>
<style>
body { font-family: monospace; background: #1e1e1e; color: #fff; padding: 20px; }
.error { background: #5a1d1d; padding: 20px; border: 2px solid #f44336; }
pre { background: #2d2d2d; padding: 15px; overflow-x: auto; }
</style>
</head>
<body>
<h1>Application Startup Failed</h1>
<div class="error">
<h2>Error:</h2>
<pre>%s</pre>
</div>
<p>Check startup_error.txt in app directory for full details</p>
</body>
</html>
""" % error_details.replace('<', '&lt;').replace('>', '&gt;')
        
        return [html.encode('utf-8')]
