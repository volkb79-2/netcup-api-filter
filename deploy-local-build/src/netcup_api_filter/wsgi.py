"""
WSGI Application Entry Point
For deployment on shared hosting environments with WSGI support

NOTE: For Phusion Passenger (Netcup webhosting), use passenger_wsgi.py instead.
This file is kept for backward compatibility with other WSGI servers.
"""
import sys
import os

# Add the application directory to the Python path
sys.path.insert(0, os.path.dirname(__file__))

from .filter_proxy import app, load_config
from .database import init_db
from .admin_ui import setup_admin_ui

# Initialize database (sets up secret key and creates tables)
init_db(app)

# Setup admin UI
setup_admin_ui(app)

# Load configuration (fail-fast: require explicit config or use documented default)
config_path = os.environ.get("NETCUP_FILTER_CONFIG")
if not config_path:
    # Fall back to config.yaml (documented default) but warn
    config_path = "config.yaml"
    print(f"[CONFIG] WARNING: NETCUP_FILTER_CONFIG not set, using default: {config_path}", file=sys.stderr)
    print(f"[CONFIG] Set explicitly: export NETCUP_FILTER_CONFIG=path/to/config.yaml", file=sys.stderr)

if os.path.exists(config_path):
    load_config(config_path)
else:
    print(f"[CONFIG] ERROR: Config file not found: {config_path}", file=sys.stderr)
    print(f"[CONFIG] Set NETCUP_FILTER_CONFIG to point to valid config file", file=sys.stderr)

# WSGI application
application = app

if __name__ == "__main__":
    # For testing
    app.run()
