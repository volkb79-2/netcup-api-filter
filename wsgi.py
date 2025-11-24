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

from filter_proxy import app, load_config
from database import init_db
from admin_ui import setup_admin_ui

# Initialize database (sets up secret key and creates tables)
init_db(app)

# Setup admin UI
setup_admin_ui(app)

# Load configuration
config_path = os.environ.get("NETCUP_FILTER_CONFIG", "config.yaml")
if os.path.exists(config_path):
    load_config(config_path)

# WSGI application
application = app

if __name__ == "__main__":
    # For testing
    app.run()
