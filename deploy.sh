#!/bin/bash
set -euo pipefail

# ============================================================================
# Unified Deployment Script
# ============================================================================
# Handles both local and webhosting deployments with proper phase handling:
#
# Usage:
#   ./deploy.sh                    # Deploy to local (default)
#   ./deploy.sh local              # Deploy to local
#   ./deploy.sh webhosting         # Deploy to webhosting
#   ./deploy.sh local --skip-tests # Deploy without running tests
#   ./deploy.sh local --tests-only # Skip build, just run tests
#
# Phases:
#   1. Build        - Create deploy.zip with fresh database
#   2. Deploy       - Extract locally or upload to webhosting
#   3. Start        - Start Flask (local) or restart Passenger (webhosting)
#   4. Auth         - Run auth test to change default password
#   5. Tests        - Run full test suite (mock tests only for local)
#   6. Screenshots  - Capture UI screenshots for inspection
#
# Configuration:
#   DEPLOYMENT_TARGET env var or first argument: "local" or "webhosting"
#   All credentials from deployment_state.json (no .env files)
# ============================================================================

# Source workspace environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/.env.workspace" ]]; then
    source "${SCRIPT_DIR}/.env.workspace"
fi

: "${REPO_ROOT:=${SCRIPT_DIR}}"
export REPO_ROOT

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Parse arguments
DEPLOYMENT_TARGET="${1:-${DEPLOYMENT_TARGET:-local}}"
shift || true

SKIP_BUILD=false
SKIP_TESTS=false
SKIP_SCREENSHOTS=false
TESTS_ONLY=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-tests)
            SKIP_TESTS=true
            shift
            ;;
        --skip-screenshots)
            SKIP_SCREENSHOTS=true
            shift
            ;;
        --skip-build)
            SKIP_BUILD=true
            shift
            ;;
        --tests-only)
            TESTS_ONLY=true
            SKIP_BUILD=true
            shift
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# Validate target
if [[ "$DEPLOYMENT_TARGET" != "local" && "$DEPLOYMENT_TARGET" != "webhosting" ]]; then
    echo -e "${RED}ERROR: Invalid DEPLOYMENT_TARGET: $DEPLOYMENT_TARGET${NC}" >&2
    echo "Must be 'local' or 'webhosting'" >&2
    exit 1
fi

export DEPLOYMENT_TARGET

# ============================================================================
# Configuration per target
# ============================================================================

case "$DEPLOYMENT_TARGET" in
    local)
        DEPLOY_DIR="${REPO_ROOT}/deploy-local"
        STATE_FILE="${REPO_ROOT}/deployment_state_local.json"
        SCREENSHOT_DIR="${DEPLOY_DIR}/screenshots"
        LOG_DIR="${REPO_ROOT}/tmp"
        LOG_FILE="${LOG_DIR}/local_app.log"
        UI_BASE_URL="http://localhost:5100"
        # Same deploy.zip for both targets - reduces drift
        BUILD_ARGS="--local --build-dir deploy --output deploy.zip"
        ZIP_FILE="${REPO_ROOT}/deploy.zip"
        ;;
    webhosting)
        DEPLOY_DIR="${REPO_ROOT}/deploy"
        STATE_FILE="${REPO_ROOT}/deployment_state_webhosting.json"
        SCREENSHOT_DIR="${REPO_ROOT}/deploy-local/screenshots"
        LOG_DIR="${REPO_ROOT}/tmp"
        UI_BASE_URL="https://naf.vxxu.de"
        # Same deploy.zip for both targets - reduces drift
        BUILD_ARGS="--target webhosting --build-dir deploy --output deploy.zip"
        ZIP_FILE="${REPO_ROOT}/deploy.zip"
        
        # Webhosting connection details
        NETCUP_USER="hosting218629"
        NETCUP_SERVER="hosting218629.ae98d.netcup.net"
        REMOTE_DIR="/netcup-api-filter"
        SSHFS_MOUNT="/home/vscode/sshfs-${NETCUP_USER}@${NETCUP_SERVER}"
        ;;
esac

mkdir -p "$LOG_DIR" "$SCREENSHOT_DIR"

# ============================================================================
# Utility functions
# ============================================================================

log_phase() {
    local phase="$1"
    local description="$2"
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  Phase ${phase}: ${description}${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

log_step() {
    echo -e "${BLUE}→ $1${NC}"
}

log_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

log_error() {
    echo -e "${RED}✗ $1${NC}" >&2
}

check_playwright_container() {
    docker ps --filter "name=playwright" --filter "status=running" | grep -q playwright
}

get_devcontainer_hostname() {
    hostname
}

read_state_value() {
    local key="$1"
    local state_file="${2:-$STATE_FILE}"
    
    if [[ ! -f "$state_file" ]]; then
        echo ""
        return
    fi
    
    python3 -c "
import json
with open('$state_file') as f:
    data = json.load(f)
# Navigate nested keys like 'admin.password'
keys = '$key'.split('.')
val = data
for k in keys:
    val = val.get(k, '') if isinstance(val, dict) else ''
print(val)
" 2>/dev/null || echo ""
}

update_state_value() {
    local key="$1"
    local value="$2"
    local state_file="${3:-$STATE_FILE}"
    
    python3 -c "
import json
from datetime import datetime, timezone

with open('$state_file') as f:
    data = json.load(f)

# Navigate nested keys like 'admin.password'
keys = '$key'.split('.')
target = data
for k in keys[:-1]:
    target = target.setdefault(k, {})
target[keys[-1]] = '$value'

# Update metadata
data['last_updated_at'] = datetime.now(timezone.utc).isoformat()
data['updated_by'] = 'deploy.sh'

with open('$state_file', 'w') as f:
    json.dump(data, f, indent=2)
"
}

stop_flask() {
    log_step "Stopping any running Flask/gunicorn processes..."
    pkill -9 gunicorn 2>/dev/null || true
    sleep 1
}

start_flask_local() {
    stop_flask
    
    log_step "Starting Flask (local mode with mock Netcup API)..."
    cd "$DEPLOY_DIR"
    
    # Copy gunicorn config if available
    if [[ -f "${SCRIPT_DIR}/gunicorn.conf.py" ]]; then
        cp "${SCRIPT_DIR}/gunicorn.conf.py" "${DEPLOY_DIR}/"
    fi
    
    NETCUP_FILTER_DB_PATH="${DEPLOY_DIR}/netcup_filter.db" \
    FLASK_ENV=local_test \
    TEMPLATES_AUTO_RELOAD=true \
    SEND_FILE_MAX_AGE_DEFAULT=0 \
    SECRET_KEY="local-test-secret-key-for-session-persistence" \
    MOCK_NETCUP_API=true \
    SEED_DEMO_CLIENTS=true \
    GUNICORN_WORKERS=2 \
    GUNICORN_THREADS=4 \
    GUNICORN_RELOAD=true \
    GUNICORN_LOGLEVEL=debug \
    gunicorn -c gunicorn.conf.py \
        --daemon \
        --log-file "$LOG_FILE" \
        --error-logfile "$LOG_FILE" \
        --access-logfile "$LOG_FILE" \
        passenger_wsgi:application
    
    # Wait for Flask
    log_step "Waiting for Flask to start..."
    for i in {1..30}; do
        if curl -s http://localhost:5100/admin/login > /dev/null 2>&1; then
            log_success "Flask ready on http://localhost:5100"
            return 0
        fi
        sleep 1
    done
    
    log_error "Flask failed to start - check $LOG_FILE"
    tail -20 "$LOG_FILE" 2>/dev/null || true
    return 1
}

run_in_playwright() {
    local cmd="$*"
    
    if check_playwright_container; then
        local devcontainer_hostname
        devcontainer_hostname=$(get_devcontainer_hostname)
        
        # Export environment for container
        export UI_BASE_URL="http://${devcontainer_hostname}:5100"
        [[ "$DEPLOYMENT_TARGET" == "webhosting" ]] && export UI_BASE_URL="https://naf.vxxu.de"
        export SCREENSHOT_DIR="$SCREENSHOT_DIR"
        export DEPLOYMENT_TARGET="$DEPLOYMENT_TARGET"
        
        # Load credentials from state file
        if [[ -f "$STATE_FILE" ]]; then
            export DEPLOYED_ADMIN_USERNAME=$(read_state_value "admin.username")
            export DEPLOYED_ADMIN_PASSWORD=$(read_state_value "admin.password")
            local primary_client
            primary_client=$(python3 -c "
import json
with open('$STATE_FILE') as f:
    data = json.load(f)
clients = data.get('clients', [])
primary = next((c for c in clients if c.get('is_primary')), clients[0] if clients else {})
print(primary.get('client_id', ''))
print(primary.get('secret_key', ''))
" 2>/dev/null | head -2)
            export DEPLOYED_CLIENT_ID=$(echo "$primary_client" | head -1)
            export DEPLOYED_CLIENT_SECRET_KEY=$(echo "$primary_client" | tail -1)
        fi
        
        "${REPO_ROOT}/tooling/playwright/playwright-exec.sh" $cmd
    else
        log_warning "Playwright container not running - using local execution"
        
        export UI_BASE_URL="http://localhost:5100"
        [[ "$DEPLOYMENT_TARGET" == "webhosting" ]] && export UI_BASE_URL="https://naf.vxxu.de"
        export SCREENSHOT_DIR="$SCREENSHOT_DIR"
        export DEPLOYMENT_TARGET="$DEPLOYMENT_TARGET"
        
        cd "$REPO_ROOT"
        $cmd
    fi
}

# ============================================================================
# Phase 1: Build
# ============================================================================

phase_build() {
    log_phase "1" "Build Deployment Package"
    
    if [[ "$SKIP_BUILD" == "true" ]]; then
        log_warning "Skipping build (--skip-build or --tests-only)"
        return 0
    fi
    
    log_step "Running build_deployment.py $BUILD_ARGS..."
    cd "$REPO_ROOT"
    python3 build_deployment.py $BUILD_ARGS 2>&1 | tail -20
    
    log_success "Build complete: $ZIP_FILE"
}

# ============================================================================
# Phase 2: Deploy
# ============================================================================

phase_deploy() {
    log_phase "2" "Deploy"
    
    if [[ "$TESTS_ONLY" == "true" ]]; then
        log_warning "Skipping deploy (--tests-only)"
        return 0
    fi
    
    case "$DEPLOYMENT_TARGET" in
        local)
            log_step "Extracting to $DEPLOY_DIR..."
            
            # Preserve screenshots directory (may have files from previous runs)
            if [[ -d "$SCREENSHOT_DIR" ]]; then
                log_step "Preserving existing screenshots..."
                mv "$SCREENSHOT_DIR" "${SCREENSHOT_DIR}.bak" 2>/dev/null || true
            fi
            
            rm -rf "$DEPLOY_DIR" 2>/dev/null || true
            mkdir -p "$DEPLOY_DIR/tmp" "$SCREENSHOT_DIR"
            unzip -o -q "$ZIP_FILE" -d "$DEPLOY_DIR/"
            
            # Restore screenshots
            if [[ -d "${SCREENSHOT_DIR}.bak" ]]; then
                # Fix permissions before restoring (Playwright container may have created with different owner)
                sudo chown -R "$(id -u):$(id -g)" "${SCREENSHOT_DIR}.bak" 2>/dev/null || true
                mv "${SCREENSHOT_DIR}.bak"/* "$SCREENSHOT_DIR/" 2>/dev/null || true
                rm -rf "${SCREENSHOT_DIR}.bak"
            fi
            
            # Fix database permissions
            chmod 666 "$DEPLOY_DIR/netcup_filter.db" 2>/dev/null || true
            chmod 777 "$DEPLOY_DIR" 2>/dev/null || true
            
            # Restart Flask to pick up new files
            stop_flask
            log_step "Flask will be started in Phase 3..."
            
            log_success "Deployed to $DEPLOY_DIR"
            ;;
            
        webhosting)
            log_step "Uploading to ${NETCUP_SERVER}..."
            scp "$ZIP_FILE" "${NETCUP_USER}@${NETCUP_SERVER}:/"
            
            log_step "Extracting and restarting on server..."
            ssh "${NETCUP_USER}@${NETCUP_SERVER}" \
                "cd / && rm -rf ${REMOTE_DIR}/* ${REMOTE_DIR}/.[!.]* ${REMOTE_DIR}/..?* && \
                 mkdir -p ${REMOTE_DIR}/tmp/ && \
                 unzip -o -u deploy.zip -d ${REMOTE_DIR}/ && \
                 touch ${REMOTE_DIR}/tmp/restart.txt"
            
            # State file is already created in REPO_ROOT by build_deployment.py
            # (deployment_state_webhosting.json - not deployed, contains secrets)
            log_success "State file: $STATE_FILE"
            
            log_success "Deployed to $NETCUP_SERVER"
            
            # Mount SSHFS if not already mounted
            if [[ ! -d "$SSHFS_MOUNT" ]] || ! mountpoint -q "$SSHFS_MOUNT" 2>/dev/null; then
                log_step "Mounting remote filesystem via SSHFS..."
                mkdir -p "$SSHFS_MOUNT"
                if sshfs "${NETCUP_USER}@${NETCUP_SERVER}:${REMOTE_DIR}" "$SSHFS_MOUNT" \
                     -o reconnect,ServerAliveInterval=15,ServerAliveCountMax=3 2>/dev/null; then
                    log_success "Mounted at $SSHFS_MOUNT"
                else
                    log_warning "SSHFS mount failed (non-critical)"
                fi
            else
                log_success "Remote filesystem already mounted at $SSHFS_MOUNT"
            fi
            ;;
    esac
}

# ============================================================================
# Phase 3: Start
# ============================================================================

phase_start() {
    log_phase "3" "Start Application"
    
    case "$DEPLOYMENT_TARGET" in
        local)
            if [[ "$TESTS_ONLY" == "true" ]]; then
                # Check if Flask is already running
                if curl -s http://localhost:5100/admin/login > /dev/null 2>&1; then
                    log_success "Flask already running"
                    return 0
                fi
            fi
            start_flask_local
            ;;
            
        webhosting)
            log_step "Application restarted via Passenger (touch restart.txt)"
            # Wait for the app to be ready
            log_step "Waiting for application to restart..."
            for i in {1..30}; do
                if curl -s "$UI_BASE_URL/admin/login" > /dev/null 2>&1; then
                    log_success "Application ready at $UI_BASE_URL"
                    return 0
                fi
                sleep 2
            done
            log_warning "Application may still be starting..."
            ;;
    esac
}

# ============================================================================
# Phase 4: Authentication Test
# ============================================================================

phase_auth() {
    log_phase "4" "Authentication Test"
    
    if [[ "$SKIP_TESTS" == "true" ]]; then
        log_warning "Skipping auth test (--skip-tests)"
        return 0
    fi
    
    log_step "Running authentication flow test..."
    
    if run_in_playwright pytest ui_tests/tests/test_admin_ui.py::test_admin_authentication_flow -v --timeout=60; then
        log_success "Authentication test passed"
        
        # Refresh credentials from state file (test updates it)
        if [[ -f "$STATE_FILE" ]]; then
            log_step "New admin password saved to $STATE_FILE"
        fi
    else
        local exit_code=$?
        if [[ $exit_code -eq 2 ]] || [[ $exit_code -eq 4 ]]; then
            log_error "FATAL: Test infrastructure broken (exit code $exit_code)"
            return 1
        else
            log_warning "Auth test failed (exit code $exit_code) - continuing"
        fi
    fi
}

# ============================================================================
# Phase 5: Full Test Suite
# ============================================================================

phase_tests() {
    log_phase "5" "Full Test Suite"
    
    if [[ "$SKIP_TESTS" == "true" ]]; then
        log_warning "Skipping tests (--skip-tests)"
        return 0
    fi
    
    local test_results=()
    local failed_suites=()
    
    # Define test suites with their applicability
    # Format: "suite_name|test_pattern|local_only" (using | as delimiter to allow :: in patterns)
    # Note: Admin UI excludes auth_flow test since Phase 4 already handles it
    local test_suites=(
        "Admin UI|ui_tests/tests/test_admin_ui.py --deselect=ui_tests/tests/test_admin_ui.py::test_admin_authentication_flow|false"
        "API Proxy|ui_tests/tests/test_api_proxy.py|false"
        "Client UI|ui_tests/tests/test_client_ui.py|false"
        "Audit Logs|ui_tests/tests/test_audit_logs.py|false"
        "Config Pages|ui_tests/tests/test_config_pages.py|false"
        "UI Comprehensive|ui_tests/tests/test_ui_comprehensive.py|false"
        "UI Regression|ui_tests/tests/test_ui_regression.py|false"
        "UI UX Validation|ui_tests/tests/test_ui_ux_validation.py|false"
        "Console Errors|ui_tests/tests/test_console_errors.py|false"
        "Create and Login|ui_tests/tests/test_create_and_login.py|false"
        "Isolated Sessions|ui_tests/tests/test_isolated_sessions.py|false"
        # Mock-only tests (local only)
        "Mock API Standalone|ui_tests/tests/test_mock_api_standalone.py|true"
        "E2E with Mock API|ui_tests/tests/test_e2e_with_mock_api.py|true"
        "Client Scenarios Mock|ui_tests/tests/test_client_scenarios_mock.py|true"
        "Mock SMTP|ui_tests/tests/test_mock_smtp.py|true"
    )
    
    for suite in "${test_suites[@]}"; do
        IFS='|' read -r name pattern local_only <<< "$suite"
        
        # Skip local-only tests for webhosting
        if [[ "$DEPLOYMENT_TARGET" == "webhosting" && "$local_only" == "true" ]]; then
            log_step "Skipping $name (local only)"
            test_results+=("$name: SKIPPED (local only)")
            continue
        fi
        
        # Extract just the file path from pattern (first space-separated word)
        local test_file="${pattern%% *}"
        
        # Check if test file exists
        if [[ ! -f "${REPO_ROOT}/${test_file}" ]]; then
            log_warning "Skipping $name (file not found: $test_file)"
            test_results+=("$name: SKIPPED (not found)")
            continue
        fi
        
        log_step "Running $name..."
        
        if run_in_playwright pytest $pattern -v --timeout=120 2>&1 | tail -5; then
            test_results+=("$name: PASSED")
            log_success "$name passed"
        else
            test_results+=("$name: FAILED")
            failed_suites+=("$name")
            log_warning "$name failed"
        fi
    done
    
    # Summary
    echo ""
    echo -e "${CYAN}Test Results Summary:${NC}"
    for result in "${test_results[@]}"; do
        if [[ "$result" == *"PASSED"* ]]; then
            echo -e "  ${GREEN}✓ $result${NC}"
        elif [[ "$result" == *"SKIPPED"* ]]; then
            echo -e "  ${YELLOW}○ $result${NC}"
        else
            echo -e "  ${RED}✗ $result${NC}"
        fi
    done
    
    if [[ ${#failed_suites[@]} -gt 0 ]]; then
        log_warning "${#failed_suites[@]} test suite(s) failed"
        return 1
    else
        log_success "All applicable test suites passed"
    fi
}

# ============================================================================
# Phase 6: Screenshots
# ============================================================================

phase_screenshots() {
    log_phase "6" "UI Screenshots"
    
    if [[ "$SKIP_SCREENSHOTS" == "true" ]]; then
        log_warning "Skipping screenshots (--skip-screenshots)"
        return 0
    fi
    
    log_step "Capturing UI screenshots..."
    
    if run_in_playwright python3 ui_tests/capture_ui_screenshots.py; then
        log_success "Screenshots saved to $SCREENSHOT_DIR"
        
        # List captured screenshots
        local count
        count=$(find "$SCREENSHOT_DIR" -name "*.png" -type f 2>/dev/null | wc -l)
        log_step "Captured $count screenshots"
        
        # Show latest screenshots
        echo ""
        echo -e "${CYAN}Recent screenshots:${NC}"
        ls -lt "$SCREENSHOT_DIR"/*.png 2>/dev/null | head -10 | while read -r line; do
            echo "  $line"
        done
    else
        log_warning "Screenshot capture failed (non-critical)"
    fi
}

# ============================================================================
# Main
# ============================================================================

main() {
    echo ""
    echo -e "${BLUE}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║  Deployment: ${DEPLOYMENT_TARGET^^}${NC}"
    echo -e "${BLUE}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  Target:      ${CYAN}$DEPLOYMENT_TARGET${NC}"
    echo -e "  Deploy Dir:  ${CYAN}$DEPLOY_DIR${NC}"
    echo -e "  State File:  ${CYAN}$STATE_FILE${NC}"
    echo -e "  Screenshots: ${CYAN}$SCREENSHOT_DIR${NC}"
    echo -e "  Base URL:    ${CYAN}$UI_BASE_URL${NC}"
    
    local start_time=$SECONDS
    
    # Run phases
    phase_build || exit 1
    phase_deploy || exit 1
    phase_start || exit 1
    phase_auth || true  # Continue on auth failure
    phase_tests || true  # Continue on test failure
    phase_screenshots || true  # Continue on screenshot failure
    
    local elapsed=$((SECONDS - start_time))
    
    # Cleanup for local deployment - only stop Flask if tests ran
    # When --skip-tests is used, keep Flask running for manual testing
    if [[ "$DEPLOYMENT_TARGET" == "local" && "$SKIP_TESTS" == "false" ]]; then
        stop_flask
    fi
    
    # Final summary
    echo ""
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  ✓ Deployment Complete (${elapsed}s)${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  📁 Deployment:   $DEPLOY_DIR"
    echo -e "  📋 State:        $STATE_FILE"
    echo -e "  📸 Screenshots:  $SCREENSHOT_DIR"
    echo -e "  🌐 URL:          $UI_BASE_URL"
    
    if [[ "$DEPLOYMENT_TARGET" == "webhosting" && -d "$SSHFS_MOUNT" ]]; then
        echo -e "  🗂️  Remote FS:    $SSHFS_MOUNT"
    fi
    
    echo ""
    echo -e "${CYAN}Next steps:${NC}"
    echo "  # Re-run tests only:"
    echo "  ./deploy.sh $DEPLOYMENT_TARGET --tests-only"
    echo ""
    echo "  # Run specific test:"
    echo "  DEPLOYMENT_TARGET=$DEPLOYMENT_TARGET pytest ui_tests/tests/test_admin_ui.py -v"
    echo ""
    echo "  # Recapture screenshots:"
    echo "  DEPLOYMENT_TARGET=$DEPLOYMENT_TARGET python3 ui_tests/capture_ui_screenshots.py"
}

# Ensure Playwright container is started for tests
if ! check_playwright_container && [[ "$SKIP_TESTS" == "false" ]]; then
    log_warning "Playwright container not running"
    log_step "Starting Playwright container..."
    if [[ -f "${REPO_ROOT}/tooling/playwright/start-playwright.sh" ]]; then
        (cd "${REPO_ROOT}/tooling/playwright" && ./start-playwright.sh)
    fi
fi

main "$@"
