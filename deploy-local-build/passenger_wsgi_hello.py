"""
Minimal Hello World WSGI Application for Testing Phusion Passenger
Use this to verify that Passenger is working before trying the full application
"""
import sys
import os

def application(environ, start_response):
    """Simple WSGI application that returns diagnostics"""
    
    status = '200 OK'
    response_headers = [('Content-Type', 'text/html; charset=utf-8')]
    start_response(status, response_headers)
    
    # Gather diagnostic information
    app_dir = os.path.dirname(__file__) or os.getcwd()
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Netcup API Filter - Hello World Test</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
        .container {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); max-width: 800px; margin: 0 auto; }}
        h1 {{ color: #2c5282; }}
        h2 {{ color: #2d3748; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; }}
        .success {{ color: #38a169; font-size: 1.2em; font-weight: bold; }}
        .info {{ background: #ebf8ff; padding: 10px; border-left: 4px solid #3182ce; margin: 10px 0; }}
        .warning {{ background: #fffaf0; padding: 10px; border-left: 4px solid #ed8936; margin: 10px 0; }}
        pre {{ background: #2d3748; color: #e2e8f0; padding: 15px; border-radius: 4px; overflow-x: auto; }}
        table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
        table td {{ padding: 8px; border-bottom: 1px solid #e2e8f0; }}
        table td:first-child {{ font-weight: bold; width: 200px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🎉 Success! Passenger WSGI is Working!</h1>
        
        <p class="success">✓ Your Python application is running correctly via Phusion Passenger</p>
        
        <h2>Environment Information</h2>
        <table>
            <tr>
                <td>Python Version:</td>
                <td>{sys.version}</td>
            </tr>
            <tr>
                <td>Python Executable:</td>
                <td>{sys.executable}</td>
            </tr>
            <tr>
                <td>Application Directory:</td>
                <td>{app_dir}</td>
            </tr>
            <tr>
                <td>Current Working Dir:</td>
                <td>{os.getcwd()}</td>
            </tr>
            <tr>
                <td>Request URI:</td>
                <td>{environ.get('REQUEST_URI', 'N/A')}</td>
            </tr>
            <tr>
                <td>Request Method:</td>
                <td>{environ.get('REQUEST_METHOD', 'N/A')}</td>
            </tr>
        </table>
        
        <h2>File System Check</h2>
        <table>
            <tr>
                <td>Files in app directory:</td>
                <td>{len(os.listdir(app_dir)) if os.path.isdir(app_dir) else 'N/A'} files</td>
            </tr>
            <tr>
                <td>vendor/ exists:</td>
                <td>{'✓ Yes' if os.path.isdir(os.path.join(app_dir, 'vendor')) else '✗ No'}</td>
            </tr>
            <tr>
                <td>templates/ exists:</td>
                <td>{'✓ Yes' if os.path.isdir(os.path.join(app_dir, 'templates')) else '✗ No'}</td>
            </tr>
            <tr>
                <td>netcup_filter.db exists:</td>
                <td>{'✓ Yes' if os.path.exists(os.path.join(app_dir, 'netcup_filter.db')) else '✗ No'}</td>
            </tr>
            <tr>
                <td>.htaccess exists:</td>
                <td>{'✓ Yes' if os.path.exists(os.path.join(app_dir, '.htaccess')) else '✗ No'}</td>
            </tr>
        </table>
        
        <h2>Python Path</h2>
        <pre>{chr(10).join(sys.path[:10])}</pre>
        
        <h2>Directory Listing (first 20 items)</h2>
        <pre>{chr(10).join(sorted(os.listdir(app_dir))[:20]) if os.path.isdir(app_dir) else 'Cannot read directory'}</pre>
        
        <h2>Next Steps</h2>
        <div class="info">
            <strong>✓ Passenger is working!</strong> Now you can:
            <ol>
                <li>Rename this file to <code>passenger_wsgi_hello_backup.py</code></li>
                <li>Rename the original <code>passenger_wsgi.py</code> back or ensure it's the active startup file</li>
                <li>Check that all dependencies are in the <code>vendor/</code> directory</li>
                <li>Try loading the full application</li>
            </ol>
        </div>
        
        <div class="warning">
            <strong>Debugging Tip:</strong> If the full app doesn't work, check for:
            <ul>
                <li>Missing files in vendor/ directory</li>
                <li>Database file permissions (should be writable)</li>
                <li>Log files: netcup_filter.log and netcup_filter_audit.log</li>
            </ul>
        </div>
    </div>
</body>
</html>
"""
    
    return [html.encode('utf-8')]
