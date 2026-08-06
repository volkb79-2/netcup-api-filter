#!/bin/bash
# Manual cleanup script for corrupted/stale Python virtual environment
# Run this if you encounter venv-related issues with the devcontainer

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(dirname "$SCRIPT_DIR")"

cd "$WORKSPACE_DIR"

echo "[INFO] Cleaning up Python virtual environment..."

if [ -d ".venv" ]; then
    echo "[INFO] Removing existing .venv directory..."
    rm -rf .venv
    echo "[SUCCESS] Removed .venv"
else
    echo "[INFO] No .venv directory found"
fi

echo ""
echo "[INFO] To rebuild the virtual environment:"
echo "  Rebuild the devcontainer (VS Code: 'Dev Containers: Rebuild Container')"
echo ""
