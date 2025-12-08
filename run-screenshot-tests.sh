#!/usr/bin/env bash
#
# run-screenshot-tests.sh - Integrated screenshot coverage test runner
#
# This script:
# 1. Builds deployment with demo data seeding
# 2. Starts gunicorn locally
# 3. Runs screenshot coverage tests
# 4. Generates screenshot inventory report
#
# Usage:
#   ./run-screenshot-tests.sh              # Full run
#   ./run-screenshot-tests.sh --skip-build # Skip build, use existing deployment
#   ./run-screenshot-tests.sh --category TestAdminDashboardScreenshots
#
set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# Configuration
WORKSPACE_DIR="/workspaces/netcup-api-filter"
DEPLOY_DIR="${WORKSPACE_DIR}/deploy-local"
SCREENSHOT_DIR="${DEPLOY_DIR}/screenshots"
GUNICORN_PID=""
SKIP_BUILD=0
TEST_CATEGORY=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-build)
            SKIP_BUILD=1
            shift
            ;;
        --category)
            TEST_CATEGORY="$2"
            shift 2
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

cleanup() {
    log_info "Cleaning up..."
    if [[ -n "$GUNICORN_PID" ]] && kill -0 "$GUNICORN_PID" 2>/dev/null; then
        kill "$GUNICORN_PID" 2>/dev/null || true
    fi
    pkill -f 'gunicorn.*passenger_wsgi' 2>/dev/null || true
}
trap cleanup EXIT

# Step 1: Build deployment with demo data
if [[ $SKIP_BUILD -eq 0 ]]; then
    log_info "Building deployment with demo data..."
    cd "${WORKSPACE_DIR}"
    python build_deployment.py --local --seed-demo
    
    log_info "Extracting deployment..."
    rm -rf "${DEPLOY_DIR}"
    unzip -q deploy.zip -d "${DEPLOY_DIR}"
    cp gunicorn.conf.py "${DEPLOY_DIR}/"
fi

# Step 2: Verify deployment exists
if [[ ! -d "${DEPLOY_DIR}" ]]; then
    log_error "Deployment directory not found: ${DEPLOY_DIR}"
    log_info "Run without --skip-build to create deployment"
    exit 1
fi

# Step 3: Start gunicorn
log_info "Starting gunicorn..."
pkill -f 'gunicorn.*passenger_wsgi' 2>/dev/null || true
sleep 1

cd "${DEPLOY_DIR}"
source "${WORKSPACE_DIR}/.env.local" 2>/dev/null || true

# Export required environment variables
export FLASK_ENV=local_test
export SCREENSHOT_DIR="${SCREENSHOT_DIR}"
export SCREENSHOT_FORMAT=webp
export SCREENSHOT_QUALITY=85
export UI_BASE_URL="http://localhost:5100"

# Read admin password from deployment state
if [[ -f "${WORKSPACE_DIR}/deployment_state_local.json" ]]; then
    ADMIN_PASSWORD=$(python3 -c "import json; print(json.load(open('${WORKSPACE_DIR}/deployment_state_local.json'))['admin']['password'])")
    export DEPLOYED_ADMIN_PASSWORD="${ADMIN_PASSWORD}"
else
    # Default for fresh deployment
    export DEPLOYED_ADMIN_PASSWORD="admin"
fi

# Start gunicorn in background
gunicorn --config gunicorn.conf.py passenger_wsgi:application -b 0.0.0.0:5100 &
GUNICORN_PID=$!
log_info "Gunicorn started with PID: ${GUNICORN_PID}"

# Wait for server to be ready
log_info "Waiting for server to be ready..."
for i in {1..30}; do
    if curl -s -o /dev/null "http://localhost:5100/health"; then
        log_success "Server is ready!"
        break
    fi
    if [[ $i -eq 30 ]]; then
        log_error "Server failed to start within 30 seconds"
        exit 1
    fi
    sleep 1
done

# Step 4: Create screenshot directory
mkdir -p "${SCREENSHOT_DIR}"

# Step 5: Run screenshot tests
log_info "Running screenshot coverage tests..."
cd "${WORKSPACE_DIR}"

if [[ -n "${TEST_CATEGORY}" ]]; then
    pytest "ui_tests/tests/test_screenshot_coverage.py::${TEST_CATEGORY}" -v --timeout=300
else
    pytest ui_tests/tests/test_screenshot_coverage.py -v --timeout=300
fi

# Step 6: Generate report
log_info "Screenshot capture complete!"
log_info "Screenshots saved to: ${SCREENSHOT_DIR}"

# Count screenshots
WEBP_COUNT=$(find "${SCREENSHOT_DIR}" -name "*.webp" | wc -l)
PNG_COUNT=$(find "${SCREENSHOT_DIR}" -name "*.png" | wc -l)

echo ""
log_success "=== Screenshot Summary ==="
log_info "WebP files: ${WEBP_COUNT}"
log_info "PNG files: ${PNG_COUNT}"
log_info "Total: $((WEBP_COUNT + PNG_COUNT))"

# List by category
echo ""
log_info "By category:"
for prefix in admin account error reference audit; do
    count=$(find "${SCREENSHOT_DIR}" -name "${prefix}*.webp" | wc -l)
    if [[ $count -gt 0 ]]; then
        echo "  ${prefix}: ${count}"
    fi
done

log_success "Screenshot tests complete!"
