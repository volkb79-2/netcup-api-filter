#!/bin/bash
set -euo pipefail

# ============================================================================
# Webhosting Deployment Script (Config-Driven)
# ============================================================================
# Workflow: Build → Upload → Deploy → Test → Capture Screenshots
# All configuration comes from .env.defaults (defaults) and .env.webhosting (state)
# CRITICAL: SSH keys must be set up and ssh-agent running with key added
# ============================================================================

# Source workspace environment (REPO_ROOT, etc.)
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
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Webhosting Deployment (Config-Driven)                   ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""

# Configuration
NETCUP_USER="hosting218629"
NETCUP_SERVER="hosting218629.ae98d.netcup.net"
REMOTE_DIR="/netcup-api-filter"
DEPLOY_ZIP="${REPO_ROOT}/deploy.zip"
DEPLOY_LOCAL_DIR="${REPO_ROOT}/deploy"
ENV_FILE="${REPO_ROOT}/.env.webhosting"
SCREENSHOT_DIR="${REPO_ROOT}/deploy-webhosting/screenshots"
SSHFS_MOUNT="/home/vscode/sshfs-${NETCUP_USER}@${NETCUP_SERVER}"

# Step 1: Load configuration
echo -e "${BLUE}Step 1/5: Loading configuration...${NC}"
load_defaults
load_deployment_state "$ENV_FILE"

# Initialize .env.webhosting with defaults if needed
if [[ ! -f "$ENV_FILE" ]]; then
    echo "[CONFIG] Initializing .env.webhosting with defaults..."
    # Client credentials will be read from build_info.json after deployment
    update_deployment_state "$ENV_FILE" \
        "DEPLOYED_ADMIN_USERNAME=${DEFAULT_ADMIN_USERNAME}" \
        "DEPLOYED_ADMIN_PASSWORD=${DEFAULT_ADMIN_PASSWORD}" \
        "UI_BASE_URL=https://naf.vxxu.de" \
        "FLASK_ENV=production"
fi

echo -e "${GREEN}✓ Configuration loaded${NC}"
echo ""

# Step 2: Build deployment package
echo -e "${BLUE}Step 2/5: Building deployment package...${NC}"
"${REPO_ROOT}/build_deployment.py"
echo -e "${GREEN}✓ Build complete${NC}"
echo ""

# Step 3: Upload and deploy to webhosting
echo -e "${BLUE}Step 3/5: Deploying to ${NETCUP_SERVER}...${NC}"

echo "[DEPLOY] Uploading deployment package..."
scp "${DEPLOY_ZIP}" "${NETCUP_USER}@${NETCUP_SERVER}:/"

echo "[DEPLOY] Extracting and restarting application..."
ssh "${NETCUP_USER}@${NETCUP_SERVER}" \
    "cd / && rm -rf ${REMOTE_DIR}/* ${REMOTE_DIR}/.[!.]* ${REMOTE_DIR}/..?* && \
     mkdir -p ${REMOTE_DIR}/tmp/ && \
     unzip -o -u deploy.zip -d ${REMOTE_DIR}/ && \
     touch ${REMOTE_DIR}/tmp/restart.txt"

# CRITICAL: Reset credentials to match fresh database
# The build process creates a new database with dynamically generated client credentials,
# so .env.webhosting must be synchronized to avoid stale credential issues
echo "[CONFIG] Resetting credentials to match fresh database..."

update_deployment_state "$ENV_FILE" \
    "DEPLOYED_ADMIN_USERNAME=${DEFAULT_ADMIN_USERNAME}" \
    "DEPLOYED_ADMIN_PASSWORD=${DEFAULT_ADMIN_PASSWORD}"

# Extract demo client credentials from local build_info.json
# (same credentials are in the deployed database, but we need the plaintext secret_key for testing)
extract_demo_client_credentials "${DEPLOY_LOCAL_DIR}" "$ENV_FILE"

# Record deployment metadata
record_deployment "$ENV_FILE"

echo -e "${GREEN}✓ Deployment complete${NC}"
echo ""

# Step 4: Mount remote filesystem (for logs and screenshots)
echo -e "${BLUE}Step 4/5: Setting up remote filesystem access...${NC}"

if [[ ! -d "$SSHFS_MOUNT" ]]; then
    echo "[SSHFS] Mounting remote filesystem..."
    mkdir -p "$SSHFS_MOUNT"
    if sshfs "${NETCUP_USER}@${NETCUP_SERVER}:${REMOTE_DIR}" "$SSHFS_MOUNT" \
         -o reconnect,ServerAliveInterval=15,ServerAliveCountMax=3; then
        echo -e "${GREEN}✓ Remote filesystem mounted at ${SSHFS_MOUNT}${NC}"
    else
        echo -e "${YELLOW}⚠ Failed to mount remote filesystem (non-critical)${NC}"
    fi
else
    echo "[SSHFS] Remote filesystem already mounted"
fi
echo ""

# Step 5: Run authentication test and capture screenshots
echo -e "${BLUE}Step 5/5: Running authentication test and capturing screenshots...${NC}"
mkdir -p "$SCREENSHOT_DIR"

# Run auth test to set password (updates .env.webhosting automatically)
if run_auth_test "$ENV_FILE" "$SCREENSHOT_DIR"; then
    echo -e "${GREEN}✓ Authentication test passed, password persisted${NC}"
else
    exit_code=$?
    if [[ $exit_code -eq 2 ]] || [[ $exit_code -eq 4 ]]; then
        # Critical error: test file missing or pytest can't find it
        echo -e "${RED}✗ FATAL: Authentication test infrastructure broken${NC}" >&2
        echo -e "${RED}✗ This is a critical error - cannot proceed${NC}" >&2
        echo -e "${RED}✗ Fix: Ensure ui_tests/tests/test_admin_ui.py exists with test_admin_authentication_flow${NC}" >&2
        exit 1
    else
        # Test failed but infrastructure is OK - continue with warning
        echo -e "${YELLOW}⚠ Authentication test failed, continuing with defaults${NC}"
    fi
fi

# Capture screenshots
capture_screenshots "$ENV_FILE" "$SCREENSHOT_DIR"
echo -e "${GREEN}✓ Screenshots captured${NC}"
echo ""

# Summary
echo -e "${GREEN}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  ✓ Webhosting Deployment Complete                        ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "🌐 URL: https://naf.vxxu.de/admin/"
echo "📋 Config: ${ENV_FILE}"
echo "📸 Screenshots: ${SCREENSHOT_DIR}"
echo "🗂️  Remote FS: ${SSHFS_MOUNT}"
echo ""
echo "To run full test suite:"
echo "  export DEPLOYMENT_ENV_FILE=${ENV_FILE} && pytest ui_tests/tests -v"
echo "  # Password changes will be persisted to ${ENV_FILE}"
echo ""
echo "To recapture screenshots:"
echo "  export DEPLOYMENT_ENV_FILE=${ENV_FILE} && python3 ui_tests/capture_ui_screenshots.py"
