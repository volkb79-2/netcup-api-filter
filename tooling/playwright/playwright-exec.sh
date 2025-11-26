#!/usr/bin/env bash
# Convenience wrapper to execute commands inside the Playwright container
# Usage: ./playwright-exec.sh <command> [args...]
# Example: ./playwright-exec.sh pytest ui_tests/tests -v

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Source workspace environment for network settings
if [[ -f "${PROJECT_ROOT}/.env.workspace" ]]; then
    # shellcheck source=/dev/null
    source "${PROJECT_ROOT}/.env.workspace"
fi

# Fail-fast: require network name
NETWORK="${DOCKER_NETWORK_INTERNAL:?DOCKER_NETWORK_INTERNAL must be set (source .env.workspace)}"

# Check if container is running
if ! docker ps --filter name=playwright --filter status=running | grep -q playwright; then
    echo "ERROR: Playwright container is not running" >&2
    echo "Start it first: cd tooling/playwright && docker compose up -d" >&2
    exit 1
fi

## Playwright container is a pure service - no file access needed
# All credentials and config passed via environment variables
# This makes the container reusable like a network service

# Execute command inside container
# Pass all relevant environment variables (container doesn't access files)
docker exec \
    -e PLAYWRIGHT_HEADLESS="${PLAYWRIGHT_HEADLESS:-true}" \
    -e UI_BASE_URL="${UI_BASE_URL:?UI_BASE_URL must be set}" \
    -e SCREENSHOT_DIR="${SCREENSHOT_DIR:-/screenshots}" \
    -e DEPLOYED_ADMIN_USERNAME="${DEPLOYED_ADMIN_USERNAME:?DEPLOYED_ADMIN_USERNAME must be set}" \
    -e DEPLOYED_ADMIN_PASSWORD="${DEPLOYED_ADMIN_PASSWORD:?DEPLOYED_ADMIN_PASSWORD must be set}" \
    -e DEPLOYED_CLIENT_ID="${DEPLOYED_CLIENT_ID:-}" \
    -e DEPLOYED_CLIENT_SECRET_KEY="${DEPLOYED_CLIENT_SECRET_KEY:-}" \
    playwright "$@"
