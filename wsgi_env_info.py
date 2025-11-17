"""WSGI Environment Inspector
Renders detailed information about the runtime Passenger provides.
"""
import os
import sys
import json
import platform

app_dir = os.path.dirname(__file__) or os.getcwd()
python_info = {
    "version": sys.version,
    "executable": sys.executable,
    "platform": platform.platform(),
}

path_preview = sys.path[:10]

ENV_KEYS = [
    "HOME",
    "PWD",
    "USER",
    "PATH",
    "PYTHONHOME",
    "PYTHONPATH",
    "LD_LIBRARY_PATH",
    "PASSENGER_APP_ENV",
]

def render_table(data):
    rows = ''.join(f"<tr><th>{key}</th><td><pre>{value}</pre></td></tr>" for key, value in data.items())
    return f"<table>{rows}</table>"

ENV_INFO = {key: os.environ.get(key, '<unset>') for key in ENV_KEYS}

HTML_HEADER = """<!DOCTYPE html>
<html>
<head>
    <title>WSGI Environment Inspector</title>
    <style>
        body { font-family: 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; padding: 24px; }
        h1 { color: #38bdf8; }
        table { border-collapse: collapse; width: 100%; margin-bottom: 24px; }
        th, td { border: 1px solid #1e293b; padding: 8px; text-align: left; }
        th { width: 220px; background: #1e293b; }
        pre { margin: 0; white-space: pre-wrap; word-break: break-all; }
        .card { background: #1e293b; padding: 16px; border-radius: 8px; margin-bottom: 20px; }
        code { background: #1f2937; padding: 2px 6px; border-radius: 4px; }
    </style>
</head>
<body>
    <h1>WSGI Environment Inspector</h1>
"""

HTML_FOOTER = """</body></html>"""

WHEN_PATH = ''.join(f"<li>{line}</li>" for line in path_preview)

def application(environ, start_response):
    start_response('200 OK', [('Content-Type', 'text/html; charset=utf-8')])
    runtime_card = f"<div class='card'><h2>Python Runtime</h2>{render_table(python_info)}</div>"
    env_card = f"<div class='card'><h2>Key Environment Variables</h2>{render_table(ENV_INFO)}</div>"
    path_card = f"<div class='card'><h2>sys.path (first 10 entries)</h2><ol>{WHEN_PATH}</ol></div>"
    req_info = {
        'REQUEST_METHOD': environ.get('REQUEST_METHOD'),
        'PATH_INFO': environ.get('PATH_INFO'),
        'SCRIPT_NAME': environ.get('SCRIPT_NAME'),
        'SERVER_NAME': environ.get('SERVER_NAME'),
        'SERVER_PORT': environ.get('SERVER_PORT'),
    }
    request_card = f"<div class='card'><h2>Request Info</h2>{render_table(req_info)}</div>"
    body = HTML_HEADER + runtime_card + env_card + path_card + request_card + HTML_FOOTER
    return [body.encode('utf-8')]
