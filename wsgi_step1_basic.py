"""WSGI Step 1 - Static success page.
Use this to confirm Passenger + Python wiring works (same as hello world).
"""
import sys
import os

app_dir = os.path.dirname(__file__) or os.getcwd()
python_info = f"{sys.version}\nExecutable: {sys.executable}"

HTML = f"""<!DOCTYPE html>
<html>
<head>
    <title>WSGI Step 1 - Basic</title>
    <style>
        body {{ font-family: Arial, sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px; }}
        h1 {{ color: #38bdf8; }}
        pre {{ background: #1e293b; padding: 12px; border-radius: 6px; overflow-x: auto; }}
    </style>
</head>
<body>
    <h1>WSGI Step 1 ✅</h1>
    <p>Passenger is serving Python successfully.</p>
    <h2>Python Info</h2>
    <pre>{python_info}</pre>
    <h2>Application Directory</h2>
    <pre>{app_dir}</pre>
</body>
</html>
"""

def application(environ, start_response):
    start_response('200 OK', [('Content-Type', 'text/html; charset=utf-8')])
    return [HTML.encode('utf-8')]
