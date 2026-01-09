#!/bin/bash
set -euo pipefail

# Run complete local test suite against production-like deployment
# This mirrors the webhosting environment exactly
#
# Options:
#   --with-mocks    Start mock services (Mailpit, GeoIP, Netcup API mocks)
#   --skip-build    Skip rebuilding deployment if deploy-local exists
#   [test_path]     Optional: specific test path (default: ui_tests/tests)

# NO HARDCODED PATHS - use REPO_ROOT from environment
WORKSPACE_DIR="${REPO_ROOT:?REPO_ROOT must be set (source .env.workspace)}"
DEPLOY_LOCAL_DIR="${WORKSPACE_DIR}/deploy-local"

# Parse arguments
WITH_MOCKS=0
SKIP_BUILD=0
TEST_PATH=""

for arg in "$@"; do
    case $arg in
        --with-mocks)
            WITH_MOCKS=1
            ;;
        --skip-build)
            SKIP_BUILD=1
            ;;
        -*)
            echo "Unknown option: $arg"
            exit 1
            ;;
        *)
            TEST_PATH="$arg"
            ;;
    esac
done

# Colors for output
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Local Test Suite (Production Parity) ===${NC}"
echo ""

# 0. Start mock services if requested
if [ "$WITH_MOCKS" -eq 1 ]; then
    echo -e "${BLUE}Starting mock services (Mailpit, GeoIP, Netcup API)...${NC}"
    "${WORKSPACE_DIR}/tooling/mailpit/docker compose up -d && tooling/geoip-mock/docker compose up -d && tooling/netcup-api-mock/docker compose up -d" --wait
    echo ""
fi

# 1. Build and extract deployment (same as webhosting gets)
if [ ! -d "${DEPLOY_LOCAL_DIR}" ] || [ "$SKIP_BUILD" -eq 0 ]; then
    if [ -d "${DEPLOY_LOCAL_DIR}" ] && [ "$SKIP_BUILD" -eq 1 ]; then
        echo -e "${GREEN}✓ Using existing deploy-local (--skip-build)${NC}"
    else
        echo -e "${YELLOW}Building fresh deployment...${NC}"
        cd "${WORKSPACE_DIR}"
        # Use --local flag to ensure deployment_state_local.json is created with fresh credentials
        ./build_deployment.py --local 2>&1 | grep -E "^[0-9]|Database initialized|Created admin" || true
        rm -rf "${DEPLOY_LOCAL_DIR}"
        mkdir -p "${DEPLOY_LOCAL_DIR}"
        unzip -o -q deploy.zip -d "${DEPLOY_LOCAL_DIR}/"
        echo -e "${GREEN}✓ Deployment extracted${NC}"
    fi
else
    echo -e "${GREEN}✓ Using existing deploy-local${NC}"
fi

echo ""

# 2. Start Flask using the Flask manager
echo -e "${BLUE}Starting Flask...${NC}"
"${WORKSPACE_DIR}/tooling/flask-manager.sh" stop || true
DEPLOY_DIR="${DEPLOY_LOCAL_DIR}" "${WORKSPACE_DIR}/tooling/flask-manager.sh" start

echo ""

# 4. Note: httpx-based audit (admin_ux_audit.py) was deprecated in favor of Playwright
# The httpx audit had CSRF and state management limitations that Playwright handles properly.
# All page coverage is now done via Playwright tests in ui_tests/tests/.

echo ""

# 5. Run tests
echo -e "${BLUE}Running complete test suite...${NC}"
cd "${WORKSPACE_DIR}"

# Set deployment target for the test config module
export DEPLOYMENT_TARGET="local"

# Set environment variables for the test suite itself
if docker ps --filter "name=playwright" --format "{{.Names}}" | grep -q "playwright"; then
    # When running in container, connect to devcontainer hostname and use container's mount path
    DEVCONTAINER_HOSTNAME=$(hostname)
    export UI_BASE_URL="http://${DEVCONTAINER_HOSTNAME}:5100"
    export SCREENSHOT_DIR="/screenshots"
else
    # When running locally, connect to localhost and use local path
    export UI_BASE_URL="http://127.0.0.1:5100"
    export SCREENSHOT_DIR="${DEPLOY_LOCAL_DIR}/screenshots"
fi

# Check if Playwright container is running
if docker ps --filter "name=playwright" --format "{{.Names}}" | grep -q "playwright"; then
    echo -e "${GREEN}✓ Playwright container detected. Running tests inside container...${NC}"
    
    # Use the canonical executor script to run tests
    # The workspace is mounted at /workspaces/netcup-api-filter in the container
    # We use the wrapper script which handles user permissions and environment variables
    echo -e "${BLUE}Running tests in Playwright container...${NC}"
    "${WORKSPACE_DIR}/tooling/playwright/playwright-exec.sh" pytest "${TEST_PATH:-ui_tests/tests}" -v

else
    echo -e "${YELLOW}Playwright container not running. Running tests locally...${NC}"
    # Run tests locally if Playwright container is not available
    pytest "${TEST_PATH:-ui_tests/tests}" -v --tb=short
fi

TEST_EXIT_CODE=$?

# 6. Cleanup
echo ""
echo -e "${BLUE}Stopping Flask...${NC}"
"${WORKSPACE_DIR}/tooling/flask-manager.sh" stop || true

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed${NC}"
else
    echo -e "${YELLOW}Tests failed - check logs:${NC}"
    echo "  Flask logs: ${WORKSPACE_DIR}/tmp/flask.log"
fi

exit $TEST_EXIT_CODE
