#!/bin/bash
# Shared deployment utilities for netcup-api-filter
# Used by both build-and-deploy-local.sh and build-and-deploy.sh

# Source this file to get shared functions
# Usage: source "$(dirname "$0")/build_deployment_lib.sh"

# ============================================================================
# ENVIRONMENT LOADING
# ============================================================================

load_defaults() {
    local repo_root="${REPO_ROOT:?REPO_ROOT must be set}"
    local defaults_file="${repo_root}/.env.defaults"
    local env_file="${repo_root}/.env"

    # Load committed defaults skeleton first (no secrets)
    if [[ -f "${defaults_file}" ]]; then
        set -a
        source "${defaults_file}"
        set +a
        echo "[CONFIG] Loaded defaults from ${defaults_file}"
    fi

    # Load secrets/overrides (required for local build/deploy)
    if [[ ! -f "${env_file}" ]]; then
        echo "ERROR: .env not found at ${env_file}" >&2
        echo "Create it by copying .env.defaults and adding secrets/overrides." >&2
        return 1
    fi

    set -a
    source "${env_file}"
    set +a
    echo "[CONFIG] Loaded env overrides from ${env_file}"
}

load_deployment_state() {
    local env_file="$1"
    
    if [[ ! -f "$env_file" ]]; then
        echo "[CONFIG] No deployment state file at $env_file - using defaults only"
        return 0
    fi
    
    # Source deployment state (overrides defaults)
    set -a
    source "$env_file"
    set +a
    
    echo "[CONFIG] Loaded deployment state from $env_file"
}

update_deployment_state() {
    local env_file="$1"
    shift
    
    # Read existing content
    local temp_file=$(mktemp)
    if [[ -f "$env_file" ]]; then
        cp "$env_file" "$temp_file"
    fi
    
    # Update key-value pairs passed as arguments (key=value format)
    for pair in "$@"; do
        local key="${pair%%=*}"
        local value="${pair#*=}"
        
        if grep -q "^${key}=" "$temp_file" 2>/dev/null; then
            # Update existing key
            sed -i "s|^${key}=.*|${key}=${value}|" "$temp_file"
        else
            # Add new key
            echo "${key}=${value}" >> "$temp_file"
        fi
    done
    
    mv "$temp_file" "$env_file"
    echo "[CONFIG] Updated deployment state: $*"
}

# ============================================================================
# DATABASE PERMISSIONS
# ============================================================================

fix_database_permissions() {
    local db_path="$1"
    local deploy_dir="$(dirname "$db_path")"
    
    if [[ ! -f "$db_path" ]]; then
        echo "[ERROR] Database not found at $db_path" >&2
        return 1
    fi
    
    chmod 666 "$db_path"
    chmod 777 "$deploy_dir"
    echo "[DB] Fixed permissions: $db_path"
}

# ============================================================================
# FLASK MANAGEMENT
# ============================================================================

stop_flask() {
    echo "[FLASK] Stopping any running gunicorn processes..."
    pkill -9 gunicorn || true
    sleep 1
}

start_flask_local() {
    local deploy_dir="$1"
    local db_path="$2"
    local log_file="${3:-${REPO_ROOT}/tmp/local_app.log}"
    
    stop_flask
    
    echo "[FLASK] Starting Flask backend (local mode with mock Netcup API)..."
    cd "$deploy_dir"
    
    NETCUP_FILTER_DB_PATH="$db_path" \
    FLASK_ENV=local_test \
    SECRET_KEY="local-test-secret-key-for-session-persistence" \
    MOCK_NETCUP_API=true \
    SEED_DEMO_CLIENTS=true \
    gunicorn -b 0.0.0.0:5100 \
        --daemon \
        --log-file "$log_file" \
        --error-logfile "$log_file" \
        --access-logfile "$log_file" \
        passenger_wsgi:application
    
    # Wait for Flask to be ready
    echo "[FLASK] Waiting for Flask to start..."
    for i in {1..20}; do
        if curl -s http://localhost:5100/admin/login > /dev/null 2>&1; then
            echo "[FLASK] ✓ Flask ready on http://localhost:5100"
            return 0
        fi
        sleep 1
    done
    
    echo "[ERROR] Flask failed to start - check logs at $log_file" >&2
    return 1
}

# ============================================================================
# DEMO CLIENT CREDENTIAL EXTRACTION
# ============================================================================

extract_demo_client_credentials() {
    local deploy_dir="$1"
    local env_file="$2"
    
    echo "[CONFIG] Extracting demo client credentials from build_info.json..."
    
    local build_info_path="${deploy_dir}/build_info.json"
    if [[ ! -f "$build_info_path" ]]; then
        echo "[CONFIG] ⚠ build_info.json not found, skipping client credential update"
        return 0
    fi
    
    # Extract first demo client credentials using jq
    if ! command -v jq &> /dev/null; then
        echo "[CONFIG] ⚠ jq not installed, skipping client credential extraction"
        return 0
    fi
    
    local client_id
    local secret_key
    
    client_id=$(jq -r '.demo_clients[0].client_id // empty' "$build_info_path")
    secret_key=$(jq -r '.demo_clients[0].secret_key // empty' "$build_info_path")
    
    if [[ -z "$client_id" || -z "$secret_key" ]]; then
        echo "[CONFIG] ⚠ No demo client credentials found in build_info.json"
        return 0
    fi
    
    echo "[CONFIG] Updating ${env_file} with demo client credentials..."
    update_deployment_state "$env_file" \
        "DEPLOYED_CLIENT_ID=${client_id}" \
        "DEPLOYED_CLIENT_SECRET_KEY=${secret_key}"
    
    echo "[CONFIG] ✓ Demo client credentials updated: client_id=${client_id}"
}

# ============================================================================
# SCREENSHOT CAPTURE
# ============================================================================

capture_screenshots() {
    local env_file="$1"
    local screenshot_dir_host="$2"
    
    echo "[SCREENSHOTS] Capturing UI screenshots..."
    # Ensure the host directory exists
    mkdir -p "$screenshot_dir_host"
    
    # Check if Playwright container is available
    if docker ps --filter name=playwright --filter status=running | grep -q playwright; then
        echo "[SCREENSHOTS] Using Playwright container for screenshot capture"
        
        # Get devcontainer hostname for network access
        local devcontainer_hostname
        devcontainer_hostname=$(hostname)
        
        # Save host REPO_ROOT for script execution
        local host_repo_root="${REPO_ROOT:?REPO_ROOT must be set}"
        
        # Load deployment credentials from env file
        local deployed_admin_password
        local deployed_client_id
        local deployed_client_token
        
        deployed_admin_password=$(grep '^DEPLOYED_ADMIN_PASSWORD=' "$env_file" | cut -d= -f2)
        deployed_client_id=$(grep '^DEPLOYED_CLIENT_ID=' "$env_file" | cut -d= -f2)
        deployed_client_token=$(grep '^DEPLOYED_CLIENT_SECRET_KEY=' "$env_file" | cut -d= -f2)
        
        # Export environment for container execution
        # The paths are now identical between devcontainer and playwright container
        export UI_BASE_URL="http://${devcontainer_hostname}:5100"
        export SCREENSHOT_DIR="$screenshot_dir_host"
        export DEPLOYED_ADMIN_USERNAME="admin"
        export DEPLOYED_ADMIN_PASSWORD="${deployed_admin_password}"
        export DEPLOYED_CLIENT_ID="${deployed_client_id}"
        export DEPLOYED_CLIENT_SECRET_KEY="${deployed_client_token}"
        
        echo "[SCREENSHOTS] Target URL: ${UI_BASE_URL}"
        echo "[SCREENSHOTS] Screenshot DIR: ${SCREENSHOT_DIR}"
        
        echo "[SCREENSHOTS] Waiting for Playwright container to be ready..."
        
        # Run screenshot capture inside container
        "${host_repo_root}/tooling/playwright/playwright-exec.sh" \
            python3 ui_tests/capture_ui_screenshots.py
        
        echo "[SCREENSHOTS] ✓ Screenshots saved to $screenshot_dir_host (via container)"
    else
        echo "[SCREENSHOTS] WARNING: Playwright container not running, using local Playwright"
        echo "[SCREENSHOTS] Tip: Start container for better emoji/font support:"
        echo "[SCREENSHOTS]   cd tooling/playwright && docker compose up -d"
        
        # Fallback to local execution
        export REPO_ROOT="${REPO_ROOT:?REPO_ROOT must be set}"
        export DEPLOYMENT_ENV_FILE="$env_file"
        export SCREENSHOT_DIR="$screenshot_dir_host"
        
        # Export deployment state
        set -a
        source "$env_file"
        set +a
        
        python3 "${REPO_ROOT}/ui_tests/capture_ui_screenshots.py"
        
        echo "[SCREENSHOTS] ✓ Screenshots saved to $screenshot_dir_host (local)"
    fi
}

# ============================================================================
# TEST RUNNER
# ============================================================================

run_tests() {
    local env_file="$1"
    local test_pattern="${2:-ui_tests/tests}"
    
    echo "[TESTS] Running tests with config from $env_file..."
    
    # Export test environment
    set -a
    source "$env_file"
    set +a
    
    # Run pytest with environment loaded
    pytest "$test_pattern" -v
    
    local exit_code=$?
    if [[ $exit_code -eq 0 ]]; then
        echo "[TESTS] ✓ All tests passed"
    else
        echo "[TESTS] ✗ Tests failed with exit code $exit_code" >&2
    fi
    
    return $exit_code
}

run_auth_test() {
    local env_file="$1"
    local screenshot_dir="${2:-${REPO_ROOT}/tmp/screenshots}"
    
    echo "[TESTS] Running authentication test to set password..."
    
    # Verify test file exists (fail-fast policy)
    local test_file="${REPO_ROOT:?REPO_ROOT must be set}/ui_tests/tests/test_admin_ui.py"
    if [[ ! -f "$test_file" ]]; then
        echo "[TESTS] ✗ ERROR: Test file not found: $test_file" >&2
        echo "[TESTS] ✗ Cannot proceed without authentication test" >&2
        return 2
    fi
    
    # Export test environment (including screenshot directory for test screenshots)
    mkdir -p "$screenshot_dir"
    
    # Check if Playwright container is running
    if docker ps --filter name=playwright --filter status=running | grep -q playwright; then
        echo "[TESTS] Using Playwright container for auth test"
        
        # The container has /workspaces mapped to the physical repo root's parent.
        # Paths are now consistent.
        export SCREENSHOT_DIR="$screenshot_dir" 
        export DEPLOYMENT_ENV_FILE="$env_file"
        export REPO_ROOT="${REPO_ROOT}" # Pass through for playwright-exec
        
        # Load state for passing to container
        set -a
        source "$env_file"
        set +a
        
        # Get devcontainer hostname for network access
        local devcontainer_hostname
        devcontainer_hostname=$(hostname)
        export UI_BASE_URL="http://${devcontainer_hostname}:5100"

        echo "[TESTS] Waiting for Playwright container to be ready..."

        # Run test inside container
        "${REPO_ROOT}/tooling/playwright/playwright-exec.sh" \
            pytest ui_tests/tests/test_admin_ui.py::test_admin_authentication_flow -v

    else
        echo "[TESTS] Using local execution for auth test"
        export SCREENSHOT_DIR="$screenshot_dir"
        export DEPLOYMENT_ENV_FILE="$env_file"
        export REPO_ROOT="${REPO_ROOT}"
        set -a
        source "$env_file"
        set +a
        
        # Run only the auth flow test (from REPO_ROOT for correct path resolution)
        cd "${REPO_ROOT}"
        pytest ui_tests/tests/test_admin_ui.py::test_admin_authentication_flow -v
    fi
    
    local exit_code=$?
    if [[ $exit_code -eq 0 ]]; then
        echo "[TESTS] ✓ Password changed and persisted to $env_file"
    elif [[ $exit_code -eq 4 ]]; then
        echo "[TESTS] ✗ ERROR: pytest could not find test (exit code 4)" >&2
    else
        echo "[TESTS] ⚠ Authentication test failed (exit code $exit_code)" >&2
    fi
    
    return $exit_code
}

# ============================================================================
# DEPLOYMENT METADATA
# ============================================================================

record_deployment() {
    local env_file="$1"
    
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    local commit=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    local build_id="${timestamp}_${commit}"
    
    update_deployment_state "$env_file" \
        "DEPLOYED_AT=$timestamp" \
        "DEPLOYED_COMMIT=$commit" \
        "DEPLOYED_BUILD_ID=$build_id"
    
    echo "[DEPLOY] Recorded deployment: $build_id"
}
