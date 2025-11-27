#!/usr/bin/env bash
# Start Playwright Standalone Service
# ====================================
#
# This script starts the standalone Playwright service container
# with optional TLS and authentication.
#
# Usage:
#   ./start-standalone.sh                    # Basic mode (no TLS, no auth)
#   ./start-standalone.sh --tls              # With TLS (self-signed)
#   ./start-standalone.sh --auth             # With token auth
#   ./start-standalone.sh --tls --auth       # Full security
#
# Environment Variables:
#   WS_AUTH_TOKEN: Authentication token (auto-generated if --auth)
#   SSL_ENABLED: Enable TLS (set by --tls)
#   WS_PORT: WebSocket port (default: 3000)
#   MCP_PORT: MCP server port (default: 8765)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     Playwright Standalone Service                        ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# Parse arguments
ENABLE_TLS=false
ENABLE_AUTH=false
REBUILD=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --tls)
            ENABLE_TLS=true
            shift
            ;;
        --auth)
            ENABLE_AUTH=true
            shift
            ;;
        --rebuild)
            REBUILD=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --tls      Enable TLS with self-signed certificate"
            echo "  --auth     Enable token authentication"
            echo "  --rebuild  Force rebuild of container"
            echo "  --help     Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Configuration
export SSL_ENABLED="${SSL_ENABLED:-$ENABLE_TLS}"
export WS_PORT="${WS_PORT:-3000}"
export MCP_PORT="${MCP_PORT:-8765}"
export MCP_ENABLED="${MCP_ENABLED:-true}"
export PLAYWRIGHT_HEADLESS="${PLAYWRIGHT_HEADLESS:-true}"
export PLAYWRIGHT_BROWSER="${PLAYWRIGHT_BROWSER:-chromium}"

# Generate auth token if requested and not already set
if [[ "$ENABLE_AUTH" == "true" && -z "${WS_AUTH_TOKEN:-}" ]]; then
    WS_AUTH_TOKEN=$(openssl rand -hex 32)
    export WS_AUTH_TOKEN
    echo -e "${YELLOW}Generated auth token: ${WS_AUTH_TOKEN}${NC}"
    echo ""
fi

# Display configuration
echo -e "${GREEN}Configuration:${NC}"
echo "  WebSocket port:  $WS_PORT"
echo "  MCP port:        $MCP_PORT"
echo "  TLS:             $SSL_ENABLED"
echo "  Authentication:  ${ENABLE_AUTH}"
echo "  Browser:         $PLAYWRIGHT_BROWSER (headless: $PLAYWRIGHT_HEADLESS)"
echo ""

cd "$SCRIPT_DIR"

# Build if needed
if [[ "$REBUILD" == "true" ]]; then
    echo -e "${BLUE}Rebuilding container...${NC}"
    docker compose -f docker-compose.standalone.yml build --no-cache
fi

# Stop existing container
if docker ps -a --format '{{.Names}}' | grep -q '^playwright-standalone$'; then
    echo -e "${YELLOW}Stopping existing container...${NC}"
    docker compose -f docker-compose.standalone.yml down
fi

# Start services
echo -e "${BLUE}Starting Playwright Standalone Service...${NC}"
docker compose -f docker-compose.standalone.yml up -d

# Wait for services to be ready
echo -e "${BLUE}Waiting for services to start...${NC}"
sleep 3

# Check if container is running
if ! docker ps --filter name=playwright-standalone | grep -q playwright-standalone; then
    echo -e "${RED}ERROR: Container failed to start${NC}"
    echo "Check logs: docker compose -f docker-compose.standalone.yml logs"
    exit 1
fi

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Playwright Standalone Service Started Successfully!     ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# Connection info
WS_PROTOCOL="ws"
MCP_PROTOCOL="http"
if [[ "$SSL_ENABLED" == "true" ]]; then
    WS_PROTOCOL="wss"
    MCP_PROTOCOL="https"
fi

echo -e "${BLUE}Connection URLs:${NC}"
echo "  WebSocket:  ${WS_PROTOCOL}://localhost:${WS_PORT}"
echo "  MCP:        ${MCP_PROTOCOL}://localhost:${MCP_PORT}/mcp"
echo ""

if [[ -n "${WS_AUTH_TOKEN:-}" ]]; then
    echo -e "${YELLOW}Authentication Required:${NC}"
    echo "  Token: ${WS_AUTH_TOKEN}"
    echo ""
    echo "  Save token to environment:"
    echo "    export WS_AUTH_TOKEN=${WS_AUTH_TOKEN}"
    echo ""
fi

echo -e "${BLUE}Quick Test:${NC}"
echo "  # Python WebSocket client test"
echo "  python3 -c \"import asyncio, websockets; asyncio.run(websockets.connect('${WS_PROTOCOL}://localhost:${WS_PORT}'))\""
echo ""
echo "  # View logs"
echo "  docker compose -f docker-compose.standalone.yml logs -f"
echo ""
echo "  # Stop service"
echo "  docker compose -f docker-compose.standalone.yml down"
echo ""
