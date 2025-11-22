#!/usr/bin/env python3
"""Script to list all system config entries."""

import sys
import os

# Add the project root to the path
sys.path.insert(0, '/workspaces/netcup-api-filter')

from database import db, get_system_config, set_system_config
from passenger_wsgi import application as app

def list_system_config():
    """List all system config entries."""
    print("Listing system config entries...")

    with app.app_context():
        # Get all system config keys
        from database import SystemConfig
        configs = SystemConfig.query.all()

        for config in configs:
            print(f"{config.key}: {config.get_value()}")

if __name__ == "__main__":
    list_system_config()