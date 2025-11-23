#!/bin/bash
# Automated deployment and testing for netcup-api-filter
# Prerequisites check → deploy → test (fail-fast) → agent-driven fixes
#
# FAIL-FAST POLICY: No defaults, no fallbacks - missing configuration = immediate error
# Agents fix issues iteratively by re-running this script after applying fixes

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

log_header() {
    echo -e "${BLUE}================================================================================${NC}"
    echo -e "${BLUE}$*${NC}"
    echo -e "${BLUE}================================================================================${NC}"
}

# REQUIRED Configuration - no defaults, fail fast
LIVE_URL="${LIVE_URL:?LIVE_URL must be set (e.g., https://naf.vxxu.de)}"
PLAYWRIGHT_CONTAINER_NAME="${PLAYWRIGHT_CONTAINER_NAME:?PLAYWRIGHT_CONTAINER_NAME must be set}"
KEEP_PLAYWRIGHT_RUNNING="${KEEP_PLAYWRIGHT_RUNNING:?KEEP_PLAYWRIGHT_RUNNING must be set (0 or 1)}"

# Runtime state
PLAYWRIGHT_STARTED_BY_SCRIPT=false

# ============================================================================
# PREREQUISITE CHECKS (fail-fast)
# ============================================================================

check_prerequisites() {
    log_header "PREREQUISITE CHECKS"
    local all_checks_passed=true

    # Check 1: Required environment variables
    log_info "Checking required environment variables..."
    local required_vars=(
        "LIVE_URL"
        "PLAYWRIGHT_CONTAINER_NAME"
        "KEEP_PLAYWRIGHT_RUNNING"
        "UI_BASE_URL"
        "UI_ADMIN_USERNAME"
        "UI_ADMIN_PASSWORD"
        "UI_CLIENT_ID"
        "UI_CLIENT_TOKEN"
        "UI_CLIENT_DOMAIN"
    )
    
    for var in "${required_vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            log_error "Missing required variable: $var"
            all_checks_passed=false
        else
            log_info "✓ $var is set"
        fi
    done

    # Check 2: Docker availability
    log_info "Checking Docker availability..."
    if ! command -v docker &>/dev/null; then
        log_error "Docker command not found"
        all_checks_passed=false
    elif ! docker info &>/dev/null; then
        log_error "Docker daemon not accessible"
        all_checks_passed=false
    else
        log_success "✓ Docker is available"
    fi

    # Check 3: Docker network
    log_info "Checking Docker network..."
    if [[ -z "${DOCKER_NETWORK_INTERNAL:-}" ]]; then
        log_error "DOCKER_NETWORK_INTERNAL not set (source .env.workspace)"
        all_checks_passed=false
    elif ! docker network inspect "$DOCKER_NETWORK_INTERNAL" &>/dev/null; then
        log_error "Docker network '$DOCKER_NETWORK_INTERNAL' does not exist"
        all_checks_passed=false
    else
        log_success "✓ Docker network '$DOCKER_NETWORK_INTERNAL' exists"
    fi

    # Check 4: build-and-deploy.sh exists and is executable
    log_info "Checking build-and-deploy.sh..."
    if [[ ! -f "./build-and-deploy.sh" ]]; then
        log_error "build-and-deploy.sh not found in current directory"
        all_checks_passed=false
    elif [[ ! -x "./build-and-deploy.sh" ]]; then
        log_error "build-and-deploy.sh is not executable"
        all_checks_passed=false
    else
        log_success "✓ build-and-deploy.sh is executable"
    fi

    # Check 5: SSH connectivity to deployment target
    log_info "Checking SSH connectivity..."
    local ssh_config_vars=(
        "NETCUP_USER"
        "NETCUP_SERVER"
    )
    
    local ssh_configured=true
    for var in "${ssh_config_vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            log_warn "$var not set - cannot verify SSH connectivity"
            ssh_configured=false
        fi
    done
    
    if [[ "$ssh_configured" == "true" ]]; then
        if ssh -o ConnectTimeout=5 -o BatchMode=yes "$NETCUP_USER@$NETCUP_SERVER" "exit" &>/dev/null; then
            log_success "✓ SSH connectivity verified"
        else
            log_error "Cannot connect to $NETCUP_USER@$NETCUP_SERVER (check SSH keys)"
            all_checks_passed=false
        fi
    fi

    # Check 6: Playwright docker-compose.yml exists
    log_info "Checking Playwright docker-compose.yml..."
    if [[ ! -f "tooling/playwright/docker-compose.yml" ]]; then
        log_error "tooling/playwright/docker-compose.yml not found"
        all_checks_passed=false
    else
        log_success "✓ Playwright docker-compose.yml exists"
    fi

    # Check 7: UI tests directory exists
    log_info "Checking UI tests directory..."
    if [[ ! -d "ui_tests/tests" ]]; then
        log_error "ui_tests/tests directory not found"
        all_checks_passed=false
    else
        log_success "✓ UI tests directory exists"
    fi

    # Check 8: .env.workspace sourced
    log_info "Checking .env.workspace..."
    if [[ -f ".env.workspace" ]]; then
        log_success "✓ .env.workspace exists"
    else
        log_error ".env.workspace not found (run post-create.sh)"
        all_checks_passed=false
    fi

    # Final verdict
    if [[ "$all_checks_passed" == "false" ]]; then
        log_error "Prerequisites check FAILED - fix issues above before continuing"
        return 1
    fi

    log_success "All prerequisites passed!"
    return 0
}

# ============================================================================
# DEPLOYMENT PHASE
# ============================================================================

run_deployment() {
    log_header "DEPLOYMENT PHASE"
    log_info "Building and deploying to live server..."

    if ! ./build-and-deploy.sh; then
        log_error "Deployment failed!"
        return 1
    fi

    log_success "Deployment completed successfully"
    return 0
}

# Function to wait for deployment to be live
wait_for_deployment() {
    log_info "Waiting for deployment to be live at $LIVE_URL..."

    local max_attempts=30
    local attempt=1

    while [[ $attempt -le $max_attempts ]]; do
        log_info "Checking deployment status (attempt $attempt/$max_attempts)..."

        if curl -s -k "$LIVE_URL/admin/login" | grep -q "login"; then
            log_success "Deployment is live and responding!"
            return 0
        fi

        sleep 10
        ((attempt++))
    done

    log_error "Deployment failed to respond after $max_attempts attempts"
    return 1
}

# ============================================================================
# TESTING PHASE
# ============================================================================

start_mock_servers() {
    log_info "Starting mock servers for E2E testing..."

    # Start mock Netcup API server in background
    log_info "Starting mock Netcup API server on port 5555..."
    docker exec -d "${PLAYWRIGHT_CONTAINER_NAME}" \
        bash -c "cd /workspace && python3 -m ui_tests.mock_netcup_api" >/dev/null 2>&1 || {
        log_warn "Mock Netcup API may already be running or failed to start"
    }

    # Start mock SMTP server in background
    log_info "Starting mock SMTP server on port 1025..."
    docker exec -d "${PLAYWRIGHT_CONTAINER_NAME}" \
        bash -c "cd /workspace && python3 -c 'import asyncio; from ui_tests.mock_smtp_server import MockSMTPServer; \
                  s = MockSMTPServer(\"127.0.0.1\", 1025); \
                  asyncio.run(s.start()); \
                  asyncio.get_event_loop().run_forever()'" >/dev/null 2>&1 || {
        log_warn "Mock SMTP server may already be running or failed to start"
    }

    # Give servers time to start
    sleep 2

    # Verify mock servers are accessible
    log_info "Verifying mock servers..."
    if docker exec "${PLAYWRIGHT_CONTAINER_NAME}" \
        python3 -c "import requests; r=requests.get('http://127.0.0.1:5555', timeout=5); assert r.status_code" >/dev/null 2>&1; then
        log_success "✓ Mock Netcup API is responding on port 5555"
    else
        log_warn "Mock Netcup API may not be responding (tests may skip DNS operations)"
    fi

    # SMTP check uses telnet-style connection test
    if docker exec "${PLAYWRIGHT_CONTAINER_NAME}" \
        python3 -c "import socket; s=socket.socket(); s.settimeout(5); s.connect(('127.0.0.1', 1025)); s.close()" >/dev/null 2>&1; then
        log_success "✓ Mock SMTP server is listening on port 1025"
    else
        log_warn "Mock SMTP server may not be listening (tests may skip email operations)"
    fi
}

stop_mock_servers() {
    log_info "Stopping mock servers..."
    
    # Kill mock servers by port (they run as background processes)
    docker exec "${PLAYWRIGHT_CONTAINER_NAME}" bash -c \
        "pkill -f 'mock_netcup_api' || true; \
         pkill -f 'mock_smtp_server' || true; \
         fuser -k 5555/tcp 2>/dev/null || true; \
         fuser -k 1025/tcp 2>/dev/null || true" >/dev/null 2>&1 || true
    
    log_info "Mock servers stopped"
}

run_ui_tests() {
    log_header "TESTING PHASE"
    log_info "Running UI tests against: $UI_BASE_URL"

    # Verify all test environment variables are set (fail-fast)
    local test_vars=(
        "UI_BASE_URL"
        "UI_ADMIN_USERNAME"
        "UI_ADMIN_PASSWORD"
        "UI_CLIENT_ID"
        "UI_CLIENT_TOKEN"
        "UI_CLIENT_DOMAIN"
    )
    
    for var in "${test_vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            log_error "Missing required test variable: $var"
            return 1
        fi
    done

    # Optional variables with explicit checks
    export UI_SCREENSHOT_PREFIX="${UI_SCREENSHOT_PREFIX:?UI_SCREENSHOT_PREFIX must be set}"
    export UI_ALLOW_WRITES="${UI_ALLOW_WRITES:?UI_ALLOW_WRITES must be set (0 or 1)}"
    export PLAYWRIGHT_HEADLESS="${PLAYWRIGHT_HEADLESS:?PLAYWRIGHT_HEADLESS must be set (true or false)}"

    # Ensure Playwright container is running (can be reused across iterations)
    log_info "Ensuring Playwright container is running..."
    
    # Source workspace environment to get PHYSICAL_REPO_ROOT
    if [[ -f ".env.workspace" ]]; then
        source .env.workspace
        log_info "Using PHYSICAL_REPO_ROOT: ${PHYSICAL_REPO_ROOT}"
    fi
    
    pushd tooling/playwright >/dev/null

    local existing_playwright
    existing_playwright=$(docker ps -q --filter "name=^${PLAYWRIGHT_CONTAINER_NAME}$")
    if [[ -n "$existing_playwright" ]]; then
        log_info "Reusing existing Playwright container '$PLAYWRIGHT_CONTAINER_NAME'"
    else
        log_info "Starting Playwright container '$PLAYWRIGHT_CONTAINER_NAME'"
        if docker compose up -d; then
            log_success "Playwright container started"
            PLAYWRIGHT_STARTED_BY_SCRIPT=true
        else
            log_error "Failed to start Playwright container"
            popd >/dev/null
            return 1
        fi
    fi

    popd >/dev/null
    if [[ "$KEEP_PLAYWRIGHT_RUNNING" == "1" ]]; then
        log_info "KEEP_PLAYWRIGHT_RUNNING=1 (container will be left running after tests)"
    fi

    # Wait for Playwright to be ready with timeout
    log_info "Waiting for Playwright container to be ready (30s timeout)..."
    local playwright_attempts=15  # 30 seconds
    local playwright_attempt=1
    while [[ $playwright_attempt -le $playwright_attempts ]]; do
        if docker exec "${PLAYWRIGHT_CONTAINER_NAME}" python3 -c "from playwright.async_api import async_playwright; print('OK')" >/dev/null 2>&1; then
            log_success "Playwright container is ready"
            break
        fi
        sleep 2
        ((playwright_attempt++))
    done

    if [[ $playwright_attempt -gt $playwright_attempts ]]; then
        log_error "Playwright container failed to be ready within timeout"
        return 1
    fi

    # Run the UI tests inside the Playwright container
    log_info "Running pytest UI tests inside Playwright container..."
    cd /workspaces/netcup-api-filter

    # Install test dependencies (all requirements should be in Dockerfile now)
    log_info "Verifying UI test dependencies in Playwright container..."
    if ! docker exec -u root "${PLAYWRIGHT_CONTAINER_NAME}" \
        bash -c "pip list | grep -q Flask && pip list | grep -q aiosmtpd && pip list | grep -q httpx" >/dev/null 2>&1; then
        log_warn "Some test dependencies may be missing - installing from requirements.root.txt"
        docker exec -u root "${PLAYWRIGHT_CONTAINER_NAME}" \
            bash -c "cd /workspace && pip install -q -r /app/requirements.root.txt" || log_warn "Dependency installation had warnings"
    else
        log_success "✓ Test dependencies verified"
    fi

    # Start mock servers for E2E tests
    start_mock_servers

    # Run tests inside container (fail-fast - no retries, no analysis)
    log_info "Running pytest UI tests inside Playwright container..."
    local test_result=0
    if docker exec \
        -e UI_BASE_URL="$UI_BASE_URL" \
        -e UI_ADMIN_USERNAME="$UI_ADMIN_USERNAME" \
        -e UI_ADMIN_PASSWORD="$UI_ADMIN_PASSWORD" \
        -e UI_CLIENT_ID="$UI_CLIENT_ID" \
        -e UI_CLIENT_TOKEN="$UI_CLIENT_TOKEN" \
        -e UI_CLIENT_DOMAIN="$UI_CLIENT_DOMAIN" \
        -e UI_SCREENSHOT_PREFIX="$UI_SCREENSHOT_PREFIX" \
        -e UI_ALLOW_WRITES="$UI_ALLOW_WRITES" \
        -e PLAYWRIGHT_HEADLESS="$PLAYWRIGHT_HEADLESS" \
        -e PYTHONPATH="/workspace" \
        "${PLAYWRIGHT_CONTAINER_NAME}" \
        bash -c "cd /workspace && python3 -m pytest ui_tests/tests -v --tb=short" 2>&1; then
        log_success "All UI tests passed!"
        test_result=0
    else
        log_error "UI tests FAILED - see output above for details"
        log_info "Agent should analyze failures and re-run this script after fixes"
        test_result=1
    fi

    # Stop mock servers
    stop_mock_servers

    return $test_result
}

# ============================================================================
# CLEANUP
# ============================================================================

cleanup() {
    log_info "Cleaning up..."

    # Always stop mock servers (they're cheap to restart)
    if docker ps --format '{{.Names}}' | grep -q "^${PLAYWRIGHT_CONTAINER_NAME}$"; then
        stop_mock_servers
    fi

    if [[ "$KEEP_PLAYWRIGHT_RUNNING" != "1" && "$PLAYWRIGHT_STARTED_BY_SCRIPT" == "true" ]]; then
        log_info "Stopping Playwright container..."
        pushd tooling/playwright >/dev/null
        docker compose down >/dev/null 2>&1 || true
        popd >/dev/null
        PLAYWRIGHT_STARTED_BY_SCRIPT=false
    elif [[ "$KEEP_PLAYWRIGHT_RUNNING" == "1" ]]; then
        log_info "KEEP_PLAYWRIGHT_RUNNING=1 - leaving Playwright container running"
    fi

    log_info "Cleanup complete"
}

# ============================================================================
# MAIN EXECUTION (simplified - no loops, no analysis)
# ============================================================================

main() {
    log_header "DEPLOY-TEST TOOL (FAIL-FAST MODE)"
    log_info "Target URL: $LIVE_URL"
    log_info "Policy: Check prerequisites → Deploy → Test → Exit"
    log_info "         Agent re-runs after applying fixes"
    log_info ""
    log_info "KEEP_PLAYWRIGHT_RUNNING=$KEEP_PLAYWRIGHT_RUNNING"

    # Phase 1: Prerequisites (fail-fast)
    if ! check_prerequisites; then
        log_error "Prerequisites check failed - fix issues above"
        exit 1
    fi

    # Phase 2: Deploy
    if ! run_deployment; then
        log_error "Deployment failed"
        cleanup
        exit 1
    fi

    # Phase 3: Wait for deployment
    if ! wait_for_deployment; then
        log_error "Deployment verification failed"
        cleanup
        exit 1
    fi

    # Phase 4: Test (fail-fast - no retries)
    if run_ui_tests; then
        log_header "SUCCESS: ALL TESTS PASSED"
        log_success "Deployment and testing completed successfully"
        log_info "Live application is working correctly at $LIVE_URL"
        cleanup
        exit 0
    else
        log_header "TESTS FAILED"
        log_error "UI tests failed - see pytest output above"
        log_info ""
        log_info "Agent workflow:"
        log_info "  1. Analyze pytest output and error messages"
        log_info "  2. Analyze screenshots in: tooling/playwright/vol-playwright-screenshots/"
        log_info "  3. Apply fixes to code/templates/config"
        log_info "  4. Re-run this script: ./.vscode/deploy-test-fix-loop.sh"
        log_info ""
        log_info "Common fix locations:"
        log_info "  - ui_tests/workflows.py (test logic)"
        log_info "  - admin_ui.py (authentication/routes)"
        log_info "  - templates/ (UI templates)"
        log_info "  - database.py (database schema)"
        cleanup
        exit 1
    fi
}

# Run main function
main "$@"