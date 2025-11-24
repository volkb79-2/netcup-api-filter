#!/usr/bin/env python3
"""Script to clear login lockouts - standalone version for remote execution."""

import sys
import os

# Ensure we're in the right directory
os.chdir('/netcup-api-filter')
sys.path.insert(0, '/netcup-api-filter')

from database import db, set_system_config, SystemConfig
from passenger_wsgi import application as app

def main():
    print("Content-Type: text/plain\n")
    print("Clearing login lockouts...\n")
    
    with app.app_context():
        configs = SystemConfig.query.all()
        cleared = 0
        for config in configs:
            if config.key.startswith('failed_login_attempts_') or config.key.startswith('login_lockout_'):
                print(f"Clearing {config.key}")
                set_system_config(config.key, {})
                cleared += 1
        db.session.commit()
        print(f"\nCleared {cleared} lockout entries")
        print("Done!")

if __name__ == "__main__":
    main()
