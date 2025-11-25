#!/bin/bash
# Shared deployment utilities for netcup-api-filter
# Used by both build-and-deploy-local.sh and build-and-deploy.sh

# Source this file to get shared functions
# Usage: source "$(dirname "$0")/deployment-lib.sh"

# ============================================================================
# ENVIRONMENT LOADING
# ============================================================================

load_defaults() {
    local defaults_file="${REPO_ROOT:?REPO_ROOT must be set}/.env.defaults"
    
    if [[ ! -f "$defaults_file" ]]; then
        echo "ERROR: .env.defaults not found at $defaults_file" >&2
        return 1
    fi
    
    # Source defaults (use set -a to export all variables)
    set -a
    source "$defaults_file"
    set +a
    
    echo "[CONFIG] Loaded defaults from $defaults_file"
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
# SCREENSHOT CAPTURE
# ============================================================================

capture_screenshots() {
    local env_file="$1"
    local screenshot_dir="$2"
    
    echo "[SCREENSHOTS] Capturing UI screenshots..."
    mkdir -p "$screenshot_dir"
    
    # Export environment for screenshot script (fail-fast: require explicit values)
    export REPO_ROOT="${REPO_ROOT:?REPO_ROOT must be set}"
    export DEPLOYMENT_ENV_FILE="$env_file"
    export SCREENSHOT_DIR="$screenshot_dir"
    
    # Export deployment state
    set -a
    source "$env_file"
    set +a
    
    python3 "${REPO_ROOT}/capture_ui_screenshots.py"
    
    echo "[SCREENSHOTS] ✓ Screenshots saved to $screenshot_dir"
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
    export SCREENSHOT_DIR="$screenshot_dir"
    export DEPLOYMENT_ENV_FILE="$env_file"
    set -a
    source "$env_file"
    set +a
    
    # Run only the auth flow test (from REPO_ROOT for correct path resolution)
    cd "${REPO_ROOT}"
    pytest ui_tests/tests/test_admin_ui.py::test_admin_authentication_flow -v
    
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
