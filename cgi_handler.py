#!/usr/bin/env python3
"""
CGI Handler for Netcup API Filter
For deployment on shared hosting environments with CGI support
"""
import sys
import os

# Add the application directory to the Python path
sys.path.insert(0, os.path.dirname(__file__))

from wsgiref.handlers import CGIHandler
from filter_proxy import app, load_config

# Load configuration
config_path = os.environ.get("NETCUP_FILTER_CONFIG", "config.yaml")
if not os.path.exists(config_path):
    # Try relative to script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "config.yaml")

load_config(config_path)

# Run as CGI
if __name__ == "__main__":
    CGIHandler().run(app)
