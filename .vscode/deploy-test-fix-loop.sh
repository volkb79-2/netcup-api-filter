#!/bin/bash
# Automated deployment, testing, and fixing loop for netcup-api-filter
# Runs build-and-deploy.sh, tests against live URL, and fixes issues until all pass

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

# Configuration
LIVE_URL="https://naf.vxxu.de"
MAX_ITERATIONS=1  # Script runs once; rerun manually after applying fixes.
ITERATION=1
ISSUES_FOUND=true
MCP_CONTAINER_NAME="${MCP_CONTAINER_NAME:-playwright-mcp}"
KEEP_MCP_RUNNING="${KEEP_MCP_RUNNING:-1}"
MCP_STARTED_BY_SCRIPT=false

# Function to run deployment
run_deployment() {
    log_header "ITERATION $ITERATION: DEPLOYMENT PHASE"
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

# Function to run UI tests against live URL with timeout
run_ui_tests() {
    log_header "ITERATION $ITERATION: TESTING PHASE"
    log_info "Running UI tests against live URL: $LIVE_URL (with 60-second timeout)"

    # Set environment variables for live testing
    export UI_BASE_URL="$LIVE_URL"
    export UI_MCP_URL="http://172.17.0.1:8765/mcp"  # Use host IP for MCP in dev container
    export UI_ADMIN_USERNAME="admin"
    export UI_ADMIN_PASSWORD="admin"
    export UI_CLIENT_ID="test_qweqweqwe_vi"
    export UI_CLIENT_TOKEN="qweqweqwe-vi-readonly"
    export UI_CLIENT_DOMAIN="qweqweqwe.vi"
    export UI_SCREENSHOT_PREFIX="live-regression-iteration-$ITERATION"
    export UI_ALLOW_WRITES="1"
    export PLAYWRIGHT_HEADLESS="true"

    # Ensure local MCP server for testing is running (can be reused across iterations)
    log_info "Ensuring local Playwright MCP server is running..."
    pushd tooling/playwright-mcp >/dev/null

    # Create .env for MCP
    cat > .env << EOF
MCP_HTTP_PORT=8765
MCP_WS_PORT=3000
PLAYWRIGHT_START_URL=$LIVE_URL/admin/login
PLAYWRIGHT_HEADLESS=true
EOF

    local existing_mcp
    existing_mcp=$(docker ps -q --filter "name=^${MCP_CONTAINER_NAME}$")
    if [[ -n "$existing_mcp" ]]; then
        log_info "Reusing existing MCP container '$MCP_CONTAINER_NAME'"
    else
        log_info "Starting MCP container '$MCP_CONTAINER_NAME'"
        if ./quick-start.sh up -d; then
            log_success "MCP container started"
            MCP_STARTED_BY_SCRIPT=true
        else
            log_error "Failed to start MCP container"
            popd >/dev/null
            return 1
        fi
    fi

    popd >/dev/null
    if [[ "$KEEP_MCP_RUNNING" == "1" ]]; then
        log_info "KEEP_MCP_RUNNING=1 (container will be left running after tests)"
    fi

    # Wait for MCP to be ready with timeout
    log_info "Waiting for MCP to be ready (30s timeout)..."
    local mcp_attempts=15  # 30 seconds
    local mcp_attempt=1
    while [[ $mcp_attempt -le $mcp_attempts ]]; do
        if curl -s --max-time 2 "http://172.17.0.1:8765/mcp" >/dev/null 2>&1; then
            log_success "MCP server is ready"
            break
        fi
        sleep 2
        ((mcp_attempt++))
    done

    if [[ $mcp_attempt -gt $mcp_attempts ]]; then
        log_error "MCP server failed to start within timeout"
        return 1
    fi

    # Run the UI tests with timeout
    log_info "Running pytest UI tests (60-second timeout)..."
    cd ui_tests

    # Install test dependencies if needed (with timeout)
    timeout 30 pip install -q -r requirements.txt || {
        log_warn "Test dependency installation timed out or failed"
    }

    # Run tests with timeout and capture output
    if timeout 60 pytest tests -v --tb=short 2>&1; then
        log_success "All UI tests passed!"
        ISSUES_FOUND=false
        cd ..
        return 0
    else
        log_warn "UI tests failed or timed out - issues detected"
        cd ..
        return 1
    fi
}

# Function to analyze test failures and suggest fixes
analyze_failures() {
    log_header "ANALYSIS PHASE - ITERATION $ITERATION"
    log_info "Analyzing test failures and identifying issues..."

    # Check for common issues
    local screenshot_dir="tooling/playwright-mcp/screenshots"
    if [[ -d "$screenshot_dir" ]]; then
        local screenshot_count=$(find "$screenshot_dir" -name "*.png" | wc -l)
        log_info "Found $screenshot_count screenshots for analysis"
        if [[ $screenshot_count -gt 0 ]]; then
            log_info "Recent screenshots:"
            find "$screenshot_dir" -name "*.png" -mtime -1 | head -5 | while read -r screenshot; do
                log_info "  - $screenshot"
            done
        fi
    fi

    # Check for error patterns in recent logs
    if [[ -f "tmp/local_app.log" ]]; then
        log_info "Checking application logs for errors..."
        local error_count=$(grep -i "error\|exception\|failed\|traceback" tmp/local_app.log | wc -l)
        if [[ $error_count -gt 0 ]]; then
            log_warn "Found $error_count errors/exceptions in application logs"
            grep -i "error\|exception\|failed\|traceback" tmp/local_app.log | tail -5
        else
            log_info "No obvious errors in application logs"
        fi
    fi

    # Check database connectivity
    log_info "Checking database connectivity..."
    python - <<'PY'
import sys
from sqlalchemy import create_engine, text
sys.path.insert(0, '.')
try:
    from database import get_db_path
    engine = create_engine(f"sqlite:///{get_db_path()}")
    with engine.connect() as conn:
        admin_count = conn.execute(text('SELECT COUNT(*) FROM admin_users')).scalar() or 0
    print(f'✓ Database reachable, {admin_count} admin users found')
except Exception as exc:
    print(f'✗ Database error: {exc}')
PY

    # Check for template compilation issues
    log_info "Checking for template compilation issues..."
    python -c "
import os
import sys
sys.path.insert(0, '.')
from flask import Flask
from jinja2 import Environment, FileSystemLoader

app = Flask(__name__)
app.template_folder = 'templates'

try:
    with app.app_context():
        # Try to load main templates
        env = Environment(loader=FileSystemLoader(app.template_folder))
        templates = ['admin/login.html', 'admin/dashboard.html', 'client/login.html', 'admin_base.html', 'base_modern.html']
        for template in templates:
            template_path = os.path.join(app.template_folder, template)
            if os.path.exists(template_path):
                try:
                    env.get_template(template)
                    print(f'✓ {template} compiles successfully')
                except Exception as e:
                    print(f'✗ {template} compilation error: {e}')
            else:
                print(f'✗ {template} not found')
except Exception as e:
    print(f'✗ Template system error: {e}')
"

    # Check for CSS/JS compilation issues
    log_info "Checking static assets..."
    if [[ -f "static/css/app.css" ]]; then
        if grep -q "error\|invalid\|undefined" static/css/app.css; then
            log_warn "Found potential CSS issues"
            grep -n "error\|invalid\|undefined" static/css/app.css | head -3
        else
            log_info "CSS appears valid"
        fi
    else
        log_warn "static/css/app.css not found"
    fi

    # Check for authentication issues
    log_info "Checking authentication setup..."
    python - <<'PY'
import sys
from sqlalchemy import create_engine, text
sys.path.insert(0, '.')
try:
    from database import get_db_path
    engine = create_engine(f"sqlite:///{get_db_path()}")
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT id, username, LENGTH(password_hash) AS pwd_len
            FROM admin_users
            WHERE username = 'admin'
            LIMIT 1
        """)).first()
    if row:
        print(f'✓ Admin user exists (ID: {row.id})')
        print(f'  Password hash length: {row.pwd_len or 0}')
    else:
        print('✗ Admin user not found')
except Exception as exc:
    print(f'✗ Authentication check error: {exc}')
PY

    # Check MCP server logs
    log_info "Checking MCP server status..."
    if docker ps | grep -q playwright-mcp; then
        log_info "✓ MCP container is running"
        # Check MCP logs for errors
        if docker logs playwright-mcp 2>&1 | grep -i "error\|failed" | tail -3 >/dev/null; then
            log_warn "Found errors in MCP logs:"
            docker logs playwright-mcp 2>&1 | grep -i "error\|failed" | tail -3
        fi
    else
        log_warn "✗ MCP container not running"
    fi

    log_info "Analysis complete - review output above for issues to fix"
}

# Function to cleanup after testing
cleanup_iteration() {
    log_info "Cleaning up after testing..."

    if [[ "$KEEP_MCP_RUNNING" != "1" && "$MCP_STARTED_BY_SCRIPT" == "true" ]]; then
        pushd tooling/playwright-mcp >/dev/null
        ./quick-start.sh down >/dev/null 2>&1 || true
        popd >/dev/null
        MCP_STARTED_BY_SCRIPT=false
    elif [[ "$KEEP_MCP_RUNNING" == "1" ]]; then
        log_info "KEEP_MCP_RUNNING=1 - leaving MCP container running for reuse"
    fi

    # Clean up screenshots from this iteration
    if [[ -d "tooling/playwright-mcp/screenshots" ]]; then
        rm -f tooling/playwright-mcp/screenshots/live-regression-iteration-$ITERATION-*.png 2>/dev/null || true
    fi

    log_info "Cleanup complete"
}

# Main loop
main() {
    log_header "DEPLOY-TEST-ANALYZE TOOL"
    log_info "Target URL: $LIVE_URL"
    log_info "This tool deploys, tests, and analyzes failures once per invocation"
    log_info "Max iterations: $MAX_ITERATIONS"
    log_info "KEEP_MCP_RUNNING=$KEEP_MCP_RUNNING (1=reuse MCP container, 0=tear down after run)"

    local iteration=1
    while [[ $iteration -le $MAX_ITERATIONS ]]; do
        ITERATION=$iteration
        log_header "ITERATION $ITERATION START"

        # Phase 1: Deploy
        if ! run_deployment; then
            log_error "Deployment failed in iteration $iteration"
            ((iteration++))
            continue
        fi

        # Phase 2: Wait for deployment
        if ! wait_for_deployment; then
            log_error "Deployment verification failed in iteration $iteration"
            ((iteration++))
            continue
        fi

        # Phase 3: Test
        if run_ui_tests; then
            log_success "All tests passed in iteration $iteration!"
            ISSUES_FOUND=false
            cleanup_iteration
            break
        else
            log_warn "Tests failed in iteration $iteration - analyzing and retrying"
            ISSUES_FOUND=true
        fi

        # Phase 4: Analyze (only if tests failed)
        if [[ $ISSUES_FOUND == true ]]; then
            analyze_failures
        fi

        # Phase 5: Cleanup
        cleanup_iteration

        ((iteration++))
    done

    # Final result
    if [[ $ISSUES_FOUND == false ]]; then
        log_header "SUCCESS: ALL TESTS PASSED"
        log_success "Deployment and testing completed successfully after $((iteration-1)) iterations"
        log_info "Live application is working correctly at $LIVE_URL"
    else
        log_header "MAX ITERATIONS REACHED: MANUAL FIXES REQUIRED"
        log_warn "Tests failed after $MAX_ITERATIONS iterations - review the analysis output above for issues to fix"
        log_info "After making fixes, re-run this tool to test again"
        log_info "Common fix locations:"
        log_info "  - ui_tests/workflows.py (test logic)"
        log_info "  - admin_ui.py (authentication/password change)"
        log_info "  - templates/ (UI templates)"
        log_info "  - database.py (database setup)"
        exit 1
    fi
}

# Run main function
main "$@"