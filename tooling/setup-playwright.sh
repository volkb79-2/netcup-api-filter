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

# Header
log_header "╔════════════════════════════════════════════════════════════════════╗"
log_header "║  Playwright Dual-Mode Setup & Validation                          ║"
log_header "║  WebSocket (testing) + MCP (AI exploration)                        ║"
log_header "╚════════════════════════════════════════════════════════════════════╝"
echo

# Step 1: Start Playwright server
log_header "Step 1: Starting Playwright Server"
log_info "Starting dual-mode server (WebSocket:3000, MCP:8765)..."

cd tooling/playwright-mcp
if [[ -f "./run.sh" ]]; then
    ./run.sh up -d
else
    export UID=$(id -u)
    export GID=$(id -g)
    docker compose up -d
fi

if [[ $? -eq 0 ]]; then
    log_success "Playwright server started"
else
    log_error "Failed to start Playwright server"
    exit 1
fi

cd "${WORKSPACE_DIR}"
echo

# Step 2: Wait for server to be ready
log_header "Step 2: Waiting for Server to be Ready"
log_info "Checking WebSocket endpoint (ws://localhost:3000)..."

MAX_RETRIES=30
RETRY_COUNT=0
SERVER_READY=false

while [[ $RETRY_COUNT -lt $MAX_RETRIES ]]; do
    if curl -s --max-time 2 http://localhost:8765/health > /dev/null 2>&1; then
        SERVER_READY=true
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo -n "."
    sleep 1
done
echo

if [[ "$SERVER_READY" == "true" ]]; then
    log_success "Server is ready"
else
    log_error "Server failed to start within ${MAX_RETRIES} seconds"
    log_info "Check logs: docker logs playwright-mcp"
    exit 1
fi

echo

# Step 3: Validate WebSocket client
log_header "Step 3: Validating WebSocket Client"
log_info "Running validation suite (6 tests)..."
echo

if python3 tooling/validate-playwright-websocket.py; then
    log_success "All validation tests passed!"
else
    log_error "Some validation tests failed"
    log_info "Check output above for details"
    exit 1
fi

echo

# Step 4: Summary
log_header "╔════════════════════════════════════════════════════════════════════╗"
log_header "║  Setup Complete!                                                   ║"
log_header "╚════════════════════════════════════════════════════════════════════╝"
echo

log_success "Playwright dual-mode server is running"
echo
log_info "WebSocket endpoint: ws://localhost:3000 (for automated tests)"
log_info "MCP endpoint: http://172.17.0.1:8765/mcp (for AI agents)"
echo

log_header "Next Steps:"
echo
echo "  1. Write tests using WebSocket client:"
echo "     ${GREEN}from ui_tests.playwright_client import playwright_session${NC}"
echo
echo "  2. Run existing tests:"
echo "     ${GREEN}pytest ui_tests/tests -v${NC}"
echo
echo "  3. Use AI exploration with Copilot:"
echo "     ${GREEN}Register http://172.17.0.1:8765/mcp in VS Code MCP settings${NC}"
echo
echo "  4. Stop server when done:"
echo "     ${GREEN}cd tooling/playwright-mcp && docker compose down${NC}"
echo

log_header "Documentation:"
echo "  📘 tooling/QUICK-REFERENCE.md       - Quick start guide"
echo "  📖 tooling/IMPLEMENTATION-GUIDE.md  - Complete implementation"
echo "  📝 tooling/LESSONS-LEARNED.md       - Why dual-mode exists"
echo "  🔧 ui_tests/playwright_client.py    - WebSocket client library"
echo

log_header "Validation Script:"
echo "  Run anytime: ${GREEN}python3 tooling/validate-playwright-websocket.py${NC}"
echo
