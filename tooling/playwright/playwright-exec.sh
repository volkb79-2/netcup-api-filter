#!/usr/bin/env bash
# Convenience wrapper to execute commands inside the Playwright container
# Usage: ./playwright-exec.sh <command> [args...]
# Example: ./playwright-exec.sh pytest ui_tests/tests -v

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

dotenv_load_if_unset() {
    local dotenv_file="$1"
    [[ -f "$dotenv_file" ]] || return 0

    local line key raw value
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Strip CR for Windows line endings
        line="${line%$'\r'}"
        # Skip blank lines and comments
        [[ -z "${line//[[:space:]]/}" ]] && continue
        [[ "$line" =~ ^[[:space:]]*# ]] && continue

        if [[ "$line" =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
            key="${BASH_REMATCH[1]}"
            raw="${BASH_REMATCH[2]}"

            # Trim surrounding whitespace
            raw="${raw#"${raw%%[![:space:]]*}"}"
            raw="${raw%"${raw##*[![:space:]]}"}"

            # Unquote simple quoted values
            if [[ "$raw" =~ ^\"(.*)\"$ ]]; then
                value="${BASH_REMATCH[1]}"
            elif [[ "$raw" =~ ^\'(.*)\'$ ]]; then
                value="${BASH_REMATCH[1]}"
            else
                value="$raw"
            fi

            # Only set if not already present in the environment
            if [[ -z "${!key+x}" ]]; then
                printf -v "$key" '%s' "$value"
                export "$key"
            fi
        fi
    done < "$dotenv_file"
}

# Source workspace environment for container user/group and network settings
if [[ -f "${PROJECT_ROOT}/.env.workspace" ]]; then
    # shellcheck source=/dev/null
    set -a
    source "${PROJECT_ROOT}/.env.workspace"
    set +a
fi

# Source service names for container naming
if [[ -f "${PROJECT_ROOT}/.env.services" ]]; then
    # shellcheck source=/dev/null
    set -a
    source "${PROJECT_ROOT}/.env.services"
    set +a
fi

# Source Mailpit config (dev/test service). This provides MAILPIT_USERNAME/MAILPIT_PASSWORD
# for tests that need to read emails via the Mailpit API.
dotenv_load_if_unset "${PROJECT_ROOT}/tooling/mailpit/.env"

# Source defaults skeleton (optional) and secrets/overrides (required)
#
# IMPORTANT: Environment variables passed in by the caller must take precedence
# over .env files (config-driven: env overrides defaults).
dotenv_load_if_unset "${PROJECT_ROOT}/.env.defaults"

if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    dotenv_load_if_unset "${PROJECT_ROOT}/.env"
else
    echo "ERROR: ${PROJECT_ROOT}/.env not found (copy .env.defaults and add secrets/overrides)" >&2
    exit 1
fi

# Fail-fast: require essential variables
: "${DOCKER_NETWORK_INTERNAL:?DOCKER_NETWORK_INTERNAL must be set (source .env.workspace)}"
: "${DOCKER_UID:?DOCKER_UID must be set (source .env.workspace)}"
: "${DOCKER_GID:?DOCKER_GID must be set (source .env.workspace)}"

# Get container name from .env.services
CONTAINER_NAME="${SERVICE_PLAYWRIGHT:?SERVICE_PLAYWRIGHT not set (source .env.services)}"

# Check if container is running
if ! docker ps --filter "name=${CONTAINER_NAME}" --filter "status=running" | grep -q "${CONTAINER_NAME}"; then
    echo "ERROR: Playwright container is not running" >&2
    echo "Start it first: cd tooling/playwright && ./start-playwright.sh" >&2
    exit 1
fi

# Prepare environment variables for 'docker exec'
# The -e VAR (without value) passes the host's variable value into the container.
DOCKER_EXEC_ENV=(
    -e DEPLOYMENT_MODE
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
    -e UI_STEP_TIMING
    -e UI_TRACE_ON_SLOW_SECONDS
    -e UI_TRACE_DIR
    -e NETCUP_API_KEY
    -e NETCUP_API_PASSWORD
    -e NETCUP_CUSTOMER_NUMBER
    -e POWERDNS_API_URL
    -e POWERDNS_API_KEY
    -e MOCK_NETCUP_API_URL
    -e MOCK_GEOIP_API_URL
    -e DNS_TEST_DOMAIN
    -e DNS_TEST_SUBDOMAIN_PREFIX
    -e DNS_PROPAGATION_TIMEOUT
    -e DNS_PROPAGATION_POLL_INTERVAL
    -e DNS_CHECK_SERVERS
    -e UI_2FA_EMAIL_TIMEOUT
    -e UI_2FA_EMAIL_POLL_INTERVAL
    -e UI_2FA_CHANNELS
    -e UI_2FA_IMAP_FORCE_RESEND
    -e UI_2FA_IMAP_SKEW_SECONDS
    -e UI_2FA_IMAP_RESEND_SKEW_SECONDS
    -e IMAP_HOST
    -e IMAP_PORT
    -e IMAP_USER
    -e IMAP_PASSWORD
    -e IMAP_USE_TLS
    -e IMAP_MAILBOX
    -e IMAP_MAILBOXES
    -e IMAP_MESSAGE_LOOKBACK
    -e IMAP_TIMEOUT
    -e SERVICE_MAILPIT
    -e MAILPIT_USERNAME
    -e MAILPIT_PASSWORD
    -e MAILPIT_API_URL
    -e MAILPIT_WEB_PORT
    -e MAILPIT_SMTP_PORT

    # Per-test profiling (optional)
    -e PYTEST_PROFILE_ENABLED
    -e PYTEST_PROFILE_DIR
    -e PYTEST_PROFILE_MIN_SECONDS
    -e PYTEST_PROFILE_SORT
    -e PYTEST_PROFILE_TOP
)

# Execute the command in the container
# CRITICAL: Run as the container's non-root user to ensure file permissions
# are correct on the mounted volumes.
docker exec -i \
    --user "${DOCKER_UID}:${DOCKER_GID}" \
    "${DOCKER_EXEC_ENV[@]}" \
    "${CONTAINER_NAME}" \
    sh -c 'cd /workspaces/netcup-api-filter && exec "$@"' -- "$@"
