#!/bin/sh
# ============================================================================
# PowerDNS Database Initialization Script
# ============================================================================
# Purpose: Automatically initialize SQLite database if it doesn't exist
# Runs as container entrypoint before PowerDNS starts
# ============================================================================

set -e

DB_PATH="/var/lib/powerdns/pdns.sqlite3"
SCHEMA_FILE="/usr/local/share/powerdns/schema.sqlite3.sql"

echo "[init-db] Checking database: $DB_PATH"

if [ ! -f "$DB_PATH" ]; then
    echo "[init-db] Database not found, initializing..."
    
    # Check schema file exists
    if [ ! -f "$SCHEMA_FILE" ]; then
        echo "[init-db] ERROR: Schema file not found: $SCHEMA_FILE"
        echo "[init-db] Ensure schema is mounted in docker-compose.yml"
        exit 1
    fi
    
    # Create database
    echo "[init-db] Creating database with schema from $SCHEMA_FILE"
    sqlite3 "$DB_PATH" < "$SCHEMA_FILE" || {
        echo "[init-db] ERROR: Failed to create database"
        exit 1
    }
    
    # Set permissions (PowerDNS runs as pdns user, UID 953 in the container)
    chmod 666 "$DB_PATH" || echo "[init-db] Warning: Could not set database permissions"
    
    echo "[init-db] Database initialized successfully"
else
    echo "[init-db] Database exists, checking permissions..."
    
    # Ensure database is writable
    if [ ! -w "$DB_PATH" ]; then
        echo "[init-db] Fixing database permissions..."
        chmod 666 "$DB_PATH" || echo "[init-db] Warning: Could not fix permissions"
    fi
    
    echo "[init-db] Database ready"
fi

# Ensure directory is writable (may fail if mounted volume, not critical)
chmod 777 /var/lib/powerdns 2>/dev/null || true

echo "[init-db] Starting PowerDNS..."
exec "$@"
