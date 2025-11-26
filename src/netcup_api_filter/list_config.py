#!/usr/bin/env python3
"""Script to list all system config entries."""

from .database import SystemConfig
from .passenger_wsgi import application as app

def list_system_config():
    """List all system config entries."""
    print("Listing system config entries...")

    with app.app_context():
        configs = SystemConfig.query.all()

        for config in configs:
            print(f"{config.key}: {config.get_value()}")

if __name__ == "__main__":
    list_system_config()