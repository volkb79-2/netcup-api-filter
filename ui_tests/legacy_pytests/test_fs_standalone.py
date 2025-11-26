"""Standalone filesystem test - accessible via HTTP"""
import sys
import os

# Add deployment path
sys.path.insert(0, '/netcup-api-filter')

# Change to deployment directory
os.chdir('/netcup-api-filter')

from netcup_api_filter.utils import test_filesystem_access
import json

def application(environ, start_response):
    """WSGI application for filesystem test"""
    status = '200 OK'
    headers = [('Content-Type', 'application/json')]
    
    try:
        results = test_filesystem_access()
        output = json.dumps(results, indent=2)
    except Exception as e:
        output = json.dumps({
            "error": str(e), 
            "type": type(e).__name__,
            "traceback": __import__('traceback').format_exc()
        }, indent=2)
    
    start_response(status, headers)
    return [output.encode('utf-8')]
