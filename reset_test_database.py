#!/usr/bin/env python3
"""Reset live database to initial seeded state for testing.

NOTE: Only use this when you need to force a complete database reset.
Normally, tests should work with the existing database state - the first
test run after deployment will change password from 'admin' to 'TestAdmin123!',
and subsequent runs will use TestAdmin123!.

Use this script when:
- Database is in an unknown/corrupt state
- Account is locked out
- You need to test the initial password change flow specifically
"""
import subprocess
import sqlite3
import sys

try:
    import bcrypt
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "bcrypt"], check=True)
    import bcrypt

REMOTE_DB = "hosting218629@hosting218629.ae98d.netcup.net:/netcup-api-filter/netcup_filter.db"
LOCAL_DB = "/tmp/reset_for_tests.db"

def main():
    print("[INFO] Downloading live database...")
    subprocess.run([
        "scp", "-q", "-o", "StrictHostKeyChecking=no",
        REMOTE_DB, LOCAL_DB
    ], check=True)
    
    conn = sqlite3.connect(LOCAL_DB)
    cursor = conn.cursor()
    
    # Reset admin password to 'admin'
    print("[INFO] Resetting admin password to 'admin' with must_change_password=1...")
    new_hash = bcrypt.hashpw(b'admin', bcrypt.gensalt()).decode('utf-8')
    cursor.execute("""
        UPDATE admin_users 
        SET password_hash = ?, must_change_password = 1 
        WHERE username = 'admin';
    """, (new_hash,))
    
    # Clear lockouts
    cursor.execute("DELETE FROM system_config WHERE key LIKE '%lockout%' OR key LIKE '%failed_login%';")
    deleted = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    print(f"[INFO] Cleared {deleted} lockout records")
    print("[INFO] Uploading reset database...")
    
    subprocess.run([
        "scp", "-q", "-o", "StrictHostKeyChecking=no",
        LOCAL_DB, REMOTE_DB
    ], check=True)
    
    print("[SUCCESS] Database reset to initial test state")
    print("[INFO] admin/admin with must_change_password=1")
    print("[INFO] Ready for test execution")

if __name__ == "__main__":
    main()
