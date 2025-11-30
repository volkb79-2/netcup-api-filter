#!/usr/bin/env bash
# Convenience wrapper to execute commands inside the Playwright container
# Usage: ./playwright-exec.sh <command> [args...]
# Example: ./playwright-exec.sh pytest ui_tests/tests -v

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Source workspace environment for container user/group and network settings
if [[ -f "${PROJECT_ROOT}/.env.workspace" ]]; then
    # shellcheck source=/dev/null
    source "${PROJECT_ROOT}/.env.workspace"
fi

# Fail-fast: require essential variables
: "${DOCKER_NETWORK_INTERNAL:?DOCKER_NETWORK_INTERNAL must be set (source .env.workspace)}"
: "${DOCKER_UID:?DOCKER_UID must be set (source .env.workspace)}"
: "${DOCKER_GID:?DOCKER_GID must be set (source .env.workspace)}"

CONTAINER_NAME="playwright"

# Check if container is running
if ! docker ps --filter "name=${CONTAINER_NAME}" --filter "status=running" | grep -q "${CONTAINER_NAME}"; then
    echo "ERROR: Playwright container is not running" >&2
    echo "Start it first: cd tooling/playwright && ./start-playwright.sh" >&2
    exit 1
fi

# Prepare environment variables for 'docker exec'
# The -e VAR (without value) passes the host's variable value into the container.
DOCKER_EXEC_ENV=(
    -e PLAYWRIGHT_HEADLESS
    -e UI_BASE_URL
    -e SCREENSHOT_DIR
    -e REPO_ROOT
    -e DEPLOY_DIR
    -e DEPLOYMENT_TARGET
    -e DEPLOYMENT_STATE_FILE
    -e DEPLOYED_ADMIN_USERNAME
    -e DEPLOYED_ADMIN_PASSWORD
    -e DEPLOYED_CLIENT_ID
    -e DEPLOYED_CLIENT_SECRET_KEY
    -e UI_ADMIN_USERNAME
    -e UI_ADMIN_PASSWORD
    -e FLASK_ENV
    -e NETCUP_API_KEY
    -e NETCUP_API_PASSWORD
    -e NETCUP_CUSTOMER_NUMBER
)

# Execute the command in the container
# CRITICAL: Run as the container's non-root user to ensure file permissions
# are correct on the mounted volumes.
docker exec -i \
    --user "${DOCKER_UID}:${DOCKER_GID}" \
    "${DOCKER_EXEC_ENV[@]}" \
    "${CONTAINER_NAME}" \
    sh -c 'cd /workspaces/netcup-api-filter && exec "$@"' -- "$@"
