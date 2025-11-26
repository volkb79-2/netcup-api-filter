#!/bin/bash
set -euo pipefail

# ============================================================================
# Local Deployment Script (Config-Driven, Integrated Testing & Screenshots)
# ============================================================================
# Workflow: Build → Deploy → Start Flask → Run Auth Test → Capture Screenshots
# All configuration comes from .env.defaults (defaults) and .env.local (state)
# ============================================================================

# Source workspace environment (REPO_ROOT, DEVCONTAINER_NAME, etc.)
if [[ -f "${REPO_ROOT:-.}/.env.workspace" ]]; then
    source "${REPO_ROOT}/.env.workspace"
fi

: "${REPO_ROOT:?REPO_ROOT must be set (source .env.workspace)}"

# Source shared deployment functions
source "${REPO_ROOT}/build_deployment_lib.sh"

# Colors for output
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Local Deployment (Config-Driven)                        ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""

# Configuration
DEPLOY_LOCAL_DIR="${REPO_ROOT}/deploy-local"
DEPLOY_ZIP="${REPO_ROOT}/deploy.zip"
DB_PATH="${DEPLOY_LOCAL_DIR}/netcup_filter.db"
ENV_FILE="${REPO_ROOT}/.env.local"
SCREENSHOT_DIR="${DEPLOY_LOCAL_DIR}/screenshots"
LOG_FILE="${REPO_ROOT}/tmp/local_app.log"

# Step 1: Load configuration
echo -e "${BLUE}Step 1/5: Loading configuration...${NC}"
load_defaults
load_deployment_state "$ENV_FILE"

# Initialize .env.local with defaults if needed
if [[ ! -f "$ENV_FILE" ]]; then
    echo "[CONFIG] Initializing .env.local with defaults..."
    # Read generated credentials from build_info.json (will be populated after build)
    update_deployment_state "$ENV_FILE" \
        "DEPLOYED_ADMIN_USERNAME=${DEFAULT_ADMIN_USERNAME}" \
        "DEPLOYED_ADMIN_PASSWORD=${DEFAULT_ADMIN_PASSWORD}" \
        "UI_BASE_URL=http://localhost:5100" \
        "FLASK_ENV=local_test"
fi

echo -e "${GREEN}✓ Configuration loaded${NC}"
echo ""

# Step 2: Build deployment package
echo -e "${BLUE}Step 2/5: Building deployment package...${NC}"
"${REPO_ROOT}/build_deployment.py"
echo -e "${GREEN}✓ Build complete${NC}"
echo ""

# Step 3: Extract and deploy
echo -e "${BLUE}Step 3/5: Deploying to ${DEPLOY_LOCAL_DIR}...${NC}"
rm -rf "${DEPLOY_LOCAL_DIR}"
mkdir -p "${DEPLOY_LOCAL_DIR}/tmp"
mkdir -p "${SCREENSHOT_DIR}"

unzip -o -q "${DEPLOY_ZIP}" -d "${DEPLOY_LOCAL_DIR}/"

# Fix database permissions
fix_database_permissions "$DB_PATH"

echo -e "${BLUE}[CONFIG] Resetting admin credentials to defaults from .env.defaults${NC}"
update_deployment_state "$ENV_FILE" \
    "DEPLOYED_ADMIN_USERNAME=${DEFAULT_ADMIN_USERNAME}" \
    "DEPLOYED_ADMIN_PASSWORD=${DEFAULT_ADMIN_PASSWORD}"

# Extract demo client credentials from build_info.json
extract_demo_client_credentials "${DEPLOY_LOCAL_DIR}" "$ENV_FILE"

# Record deployment metadata
record_deployment "$ENV_FILE"

echo -e "${GREEN}✓ Deployment extracted${NC}"
echo ""

# Step 4: Start Flask and run authentication test
echo -e "${BLUE}Step 4/5: Starting Flask and running authentication test...${NC}"
start_flask_local "$DEPLOY_LOCAL_DIR" "$DB_PATH" "$LOG_FILE"

# Run auth test to set password (updates .env.local automatically)
if run_auth_test "$ENV_FILE" "$SCREENSHOT_DIR"; then
    echo -e "${GREEN}✓ Authentication test passed, password persisted${NC}"
else
    exit_code=$?
    if [[ $exit_code -eq 2 ]] || [[ $exit_code -eq 4 ]]; then
        # Critical error: test file missing or pytest can't find it
        echo -e "${RED}✗ FATAL: Authentication test infrastructure broken${NC}" >&2
        echo -e "${RED}✗ This is a critical error - cannot proceed${NC}" >&2
        echo -e "${RED}✗ Fix: Ensure ui_tests/tests/test_admin_ui.py exists with test_admin_authentication_flow${NC}" >&2
        stop_flask
        exit 1
    else
        # Test failed but infrastructure is OK - continue with warning
        echo -e "${YELLOW}⚠ Authentication test failed, continuing with defaults${NC}"
    fi
fi
echo ""

# Step 5: Capture screenshots
echo -e "${BLUE}Step 5/5: Capturing UI screenshots...${NC}"
capture_screenshots "$ENV_FILE" "$SCREENSHOT_DIR"
echo -e "${GREEN}✓ Screenshots captured${NC}"
echo ""

# Summary
echo -e "${GREEN}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  ✓ Local Deployment Complete                             ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "📁 Deployment: ${DEPLOY_LOCAL_DIR}"
echo "🗄️  Database: ${DB_PATH}"
echo "📸 Screenshots: ${SCREENSHOT_DIR}"
echo "📋 Config: ${ENV_FILE}"
echo "📜 Logs: ${LOG_FILE}"
echo ""
echo "🌐 URL: http://localhost:5100/admin/"
echo ""
echo "To run full test suite:"
echo "  export DEPLOYMENT_ENV_FILE=${ENV_FILE} && pytest ui_tests/tests -v"
echo "  # Password changes will be persisted to ${ENV_FILE}"
echo ""
echo "To recapture screenshots:"
echo "  export DEPLOYMENT_ENV_FILE=${ENV_FILE} && python3 ui_tests/capture_ui_screenshots.py"
