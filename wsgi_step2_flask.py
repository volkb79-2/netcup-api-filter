"""WSGI Step 2 - Imports Flask only.
Shows success/failure for vendor/ availability.
"""
import sys
import os
import traceback

app_dir = os.path.dirname(__file__) or os.getcwd()
vendor_dir = os.path.join(app_dir, 'vendor')
if os.path.isdir(vendor_dir):
    sys.path.insert(0, vendor_dir)

ERROR = None
try:
    from flask import Flask
except Exception:
    ERROR = traceback.format_exc()

if ERROR:
    def application(environ, start_response):
        start_response('500 Internal Server Error', [('Content-Type', 'text/html; charset=utf-8')])
        html = f"""<h1>WSGI Step 2 ❌</h1>
        <p>Failed to import Flask.</p>
        <h2>Traceback</h2>
        <pre>{ERROR.replace('<','&lt;').replace('>','&gt;')}</pre>
        <h2>Vendor directory</h2>
        <pre>{vendor_dir} (exists: {os.path.isdir(vendor_dir)})</pre>
        """
        return [html.encode('utf-8')]
else:
    app = Flask(__name__)

    @app.route('/')
    def index():  # pragma: no cover
        return "WSGI Step 2 ✅ - Flask import succeeded."

    application = app
