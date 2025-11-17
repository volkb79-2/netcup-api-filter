"""
Ultra-minimal debug WSGI - guaranteed to work
"""
import sys
import os

# Setup paths
app_dir = os.path.dirname(__file__) or os.getcwd()
sys.path.insert(0, app_dir)
vendor_dir = os.path.join(app_dir, 'vendor')
if os.path.isdir(vendor_dir):
    sys.path.insert(0, vendor_dir)

# Define application FIRST (so it always exists)
def application(environ, start_response):
    status = '500 Internal Server Error'
    headers = [('Content-Type', 'text/html; charset=utf-8')]
    start_response(status, headers)
    return [b'<h1>Placeholder - will be replaced if imports work</h1>']

# Now try to import and replace application
try:
    from flask import Flask
    from filter_proxy import app as flask_app
    
    # Success! Replace the placeholder
    application = flask_app
    
except Exception as e:
    import traceback
    error_info = traceback.format_exc()
    
    # Save error to file
    try:
        error_file = os.path.join(app_dir, 'import_error.txt')
        with open(error_file, 'w') as f:
            f.write(error_info)
    except:
        pass
    
    # Create error display
    def application(environ, start_response):
        status = '500 Internal Server Error'  
        headers = [('Content-Type', 'text/html')]
        start_response(status, headers)
        
        html = f'''<!DOCTYPE html>
<html>
<head><title>Import Error</title></head>
<body style="font-family: monospace; background: #000; color: #0f0; padding: 20px;">
<h1>IMPORT ERROR</h1>
<pre>{error_info}</pre>
<p>Error also saved to: import_error.txt</p>
</body>
</html>'''
        
        return [html.encode('utf-8')]
