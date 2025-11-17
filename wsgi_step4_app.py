"""WSGI Step 4 - Binds to filter_proxy.app without running init_db/setup_admin.
Use when Step 3 works to ensure Flask app object loads.
"""
import sys
import os
import traceback

app_dir = os.path.dirname(__file__) or os.getcwd()
sys.path.insert(0, app_dir)
vendor_dir = os.path.join(app_dir, 'vendor')
if os.path.isdir(vendor_dir):
    sys.path.insert(0, vendor_dir)

try:
    from filter_proxy import app as flask_app
except Exception:
    error = traceback.format_exc()

    def application(environ, start_response):  # pragma: no cover
        start_response('500 Internal Server Error', [('Content-Type', 'text/html; charset=utf-8')])
        html = f"""<h1>WSGI Step 4 ❌</h1>
        <p>Failed to import <code>filter_proxy.app</code>.</p>
        <pre>{error.replace('<','&lt;').replace('>','&gt;')}</pre>
        """
        return [html.encode('utf-8')]
else:
    application = flask_app
