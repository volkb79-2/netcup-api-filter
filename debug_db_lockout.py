#!/usr/bin/env python3
"""
Debug script to check and clear lockout records from live database.
"""
import sqlite3
import subprocess
import sys
from pathlib import Path

def run_scp(remote_path: str, local_path: str, direction: str = "download"):
    """Run scp command to copy database."""
    if direction == "download":
        cmd = ["scp", "-q", "-o", "StrictHostKeyChecking=no",
               f"hosting218629@hosting218629.ae98d.netcup.net:{remote_path}", local_path]
    else:  # upload
        cmd = ["scp", "-q", "-o", "StrictHostKeyChecking=no",
               local_path, f"hosting218629@hosting218629.ae98d.netcup.net:{remote_path}"]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERROR] SCP failed: {result.stderr}", file=sys.stderr)
        return False
    return True

def check_lockout(db_path: str) -> list:
    """Check for lockout records in database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM system_config WHERE key LIKE '%lockout%' OR key LIKE '%failed_login%';")
    records = cursor.fetchall()
    conn.close()
    return records

def clear_lockout(db_path: str) -> int:
    """Clear lockout records from database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM system_config WHERE key LIKE '%lockout%' OR key LIKE '%failed_login%';")
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return count

def get_recent_login_attempts(db_path: str, limit: int = 10) -> list:
    """Get recent login attempts from audit logs."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # First check what columns exist
    cursor.execute("PRAGMA table_info(audit_logs);")
    columns = cursor.fetchall()
    print(f"[DEBUG] audit_logs columns: {[col[1] for col in columns]}")
    
    # Query with actual columns
    cursor.execute("""
        SELECT timestamp, ip_address, event_type, details 
        FROM audit_logs 
        WHERE event_type LIKE '%login%' 
        ORDER BY timestamp DESC 
        LIMIT ?;
    """, (limit,))
    records = cursor.fetchall()
    conn.close()
    return records

def main():
    remote_db = "/netcup-api-filter/netcup_filter.db"
    local_db = "/tmp/live_db_check.db"
    
    print("=" * 80)
    print("STEP 1: Download and check current lockout status")
    print("=" * 80)
    
    if not run_scp(remote_db, local_db, "download"):
        sys.exit(1)
    
    lockout_records = check_lockout(local_db)
    if lockout_records:
        print(f"Found {len(lockout_records)} lockout records:")
        for key, value in lockout_records:
            print(f"  {key} = {value}")
    else:
        print("No lockout records found")
    
    print("\n" + "=" * 80)
    print("STEP 2: Clear lockout records")
    print("=" * 80)
    
    count = clear_lockout(local_db)
    print(f"Deleted {count} lockout records")
    
    if count > 0:
        print("Uploading cleaned database...")
        if not run_scp(remote_db, local_db, "upload"):
            sys.exit(1)
        print("[SUCCESS] Database updated on server")
    
    print("\n" + "=" * 80)
    print("READY TO TEST")
    print("=" * 80)
    print("Lockout cleared. You can now run: python3 debug_playwright_login.py")

if __name__ == "__main__":
    main()
