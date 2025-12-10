#!/usr/bin/env bash
set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

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
    echo -e "${MAGENTA}${1}${NC}"
}

WORKSPACE_DIR="/workspaces/netcup-api-filter"
cd "${WORKSPACE_DIR}"

# Load workspace environment
if [[ -f "${WORKSPACE_DIR}/.env.workspace" ]]; then
    # shellcheck source=/dev/null
    source "${WORKSPACE_DIR}/.env.workspace"
fi

# Load service names
if [[ -f "${WORKSPACE_DIR}/.env.services" ]]; then
    # shellcheck source=/dev/null
    source "${WORKSPACE_DIR}/.env.services"
fi

# Fail-fast: require essential variables
: "${DOCKER_NETWORK_INTERNAL:?DOCKER_NETWORK_INTERNAL must be set (run post-create.sh)}"
: "${SERVICE_PLAYWRIGHT:?SERVICE_PLAYWRIGHT must be set (source .env.services)}"

# Header
log_header "╔════════════════════════════════════════════════════════════════════╗"
log_header "║  Playwright Dual-Mode Setup & Validation                          ║"
log_header "║  WebSocket (testing) + MCP (AI exploration)                        ║"
log_header "╚════════════════════════════════════════════════════════════════════╝"
echo

# Step 1: Start Playwright server
log_header "Step 1: Starting Playwright Container"
log_info "Starting Playwright container for browser automation..."

cd tooling/playwright
export UID=$(id -u)
export GID=$(id -g)
docker compose up -d

if [[ $? -eq 0 ]]; then
    log_success "Playwright server started"
else
    log_error "Failed to start Playwright server"
    exit 1
fi

cd "${WORKSPACE_DIR}"
echo

# Step 2: Wait for container to be ready
log_header "Step 2: Waiting for Container to be Ready"
log_info "Checking Playwright availability..."

MAX_RETRIES=30
RETRY_COUNT=0
CONTAINER_READY=false

while [[ $RETRY_COUNT -lt $MAX_RETRIES ]]; do
    if docker exec "${SERVICE_PLAYWRIGHT}" python3 -c "from playwright.async_api import async_playwright; print('OK')" > /dev/null 2>&1; then
        CONTAINER_READY=true
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo -n "."
    sleep 1
done
echo

if [[ "$CONTAINER_READY" == "true" ]]; then
    log_success "Container is ready"
else
    log_error "Container failed to start within ${MAX_RETRIES} seconds"
    log_info "Check logs: docker logs ${SERVICE_PLAYWRIGHT}"
    exit 1
fi

echo

# Step 3: Validate Playwright
log_header "Step 3: Validating Playwright"
log_info "Running basic Playwright test..."
echo

if docker exec "${SERVICE_PLAYWRIGHT}" python3 -c "import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto('https://example.com')
        print(f'✅ Navigated to: {page.url}')
        await browser.close()

asyncio.run(test())"; then
    log_success "Playwright validation passed!"
else
    log_error "Playwright validation failed"
    log_info "Check output above for details"
    exit 1
fi

echo

# Step 4: Summary
log_header "╔════════════════════════════════════════════════════════════════════╗"
log_header "║  Setup Complete!                                                   ║"
log_header "╚════════════════════════════════════════════════════════════════════╝"
echo

log_success "Playwright container is running"
echo
log_info "Container: playwright (ready for exec-based commands)"
echo

log_header "Next Steps:"
echo
echo "  1. Run tests inside container:"
echo "     ${GREEN}docker exec ${SERVICE_PLAYWRIGHT} pytest /workspaces/netcup-api-filter/ui_tests/tests -v${NC}"
echo
echo "  2. Run Python scripts:"
echo "     ${GREEN}docker exec ${SERVICE_PLAYWRIGHT} python3 /workspaces/netcup-api-filter/my_script.py${NC}"
echo
echo "  3. Interactive shell:"
echo "     ${GREEN}docker exec -it ${SERVICE_PLAYWRIGHT} bash${NC}"
echo
echo "  4. Stop container when done:"
echo "     ${GREEN}cd tooling/playwright && docker compose down${NC}"
echo

log_header "Documentation:"
echo "  📘 tooling/playwright/README.md     - Container documentation"
echo "  📖 tooling/PLAYWRIGHT-TESTING.md    - Testing guide"
echo "  🔧 ui_tests/tests/                  - Test suite"
echo
