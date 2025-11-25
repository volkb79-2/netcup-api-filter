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

# Load configuration (fail-fast: require explicit config or use documented default)
config_path = os.environ.get("NETCUP_FILTER_CONFIG")
if not config_path:
    # Fall back to config.yaml (documented default) but warn
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "config.yaml")
    print(f"[CONFIG] WARNING: NETCUP_FILTER_CONFIG not set, using default: {config_path}", file=sys.stderr)
    print(f"[CONFIG] Set explicitly: export NETCUP_FILTER_CONFIG=path/to/config.yaml", file=sys.stderr)

if os.path.exists(config_path):
    load_config(config_path)
else:
    print(f"[CONFIG] ERROR: Config file not found: {config_path}", file=sys.stderr)
    print(f"[CONFIG] Set NETCUP_FILTER_CONFIG to point to valid config file", file=sys.stderr)
    sys.exit(1)

# Run as CGI
if __name__ == "__main__":
    CGIHandler().run(app)
