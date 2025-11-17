"""WSGI Step 3 - Imports filter_proxy but does not touch database or other modules.
Helps isolate issues within our application package.
"""
import sys
import os
import traceback

app_dir = os.path.dirname(__file__) or os.getcwd()
sys.path.insert(0, app_dir)
vendor_dir = os.path.join(app_dir, 'vendor')
if os.path.isdir(vendor_dir):
    sys.path.insert(0, vendor_dir)

ERROR = None
try:
    import filter_proxy  # noqa: F401
except Exception:
    ERROR = traceback.format_exc()

if ERROR:
    def application(environ, start_response):
        start_response('500 Internal Server Error', [('Content-Type', 'text/html; charset=utf-8')])
        html = f"""<h1>WSGI Step 3 ❌</h1>
        <p>Importing <code>filter_proxy</code> failed.</p>
        <pre>{ERROR.replace('<','&lt;').replace('>','&gt;')}</pre>
        <p>Python path (first 5 entries):</p>
        <pre>{os.linesep.join(sys.path[:5])}</pre>
        """
        return [html.encode('utf-8')]
else:
    def application(environ, start_response):
        start_response('200 OK', [('Content-Type', 'text/plain; charset=utf-8')])
        return [b"WSGI Step 3 ✅ - filter_proxy module imported successfully."]
