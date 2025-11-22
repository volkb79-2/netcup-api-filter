#!/usr/bin/env python3
"""Script to clear login lockouts from the database."""

import sys
import os

# Add the project root to the path
sys.path.insert(0, '/workspaces/netcup-api-filter')

from database import db, get_system_config, set_system_config
from passenger_wsgi import application as app

def clear_login_lockouts():
    """Clear all login lockout data from the system config."""
    print("Clearing login lockouts...")

    with app.app_context():
        # Get all system config keys
        from database import SystemConfig
        configs = SystemConfig.query.all()

        cleared_count = 0
        for config in configs:
            if config.key.startswith('failed_login_attempts_') or config.key.startswith('login_lockout_'):
                print(f"Clearing {config.key}")
                set_system_config(config.key, {})
                cleared_count += 1

        print(f"Cleared {cleared_count} lockout entries")
        db.session.commit()

if __name__ == "__main__":
    clear_login_lockouts()