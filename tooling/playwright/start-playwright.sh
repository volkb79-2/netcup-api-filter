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
#   ./start-standalone.sh --rebuild          # Force rebuild
#
# Environment Variables:
#   WS_AUTH_TOKEN: Authentication token (auto-generated if --auth)
#   SSL_ENABLED: Enable TLS (set by --tls)
#   WS_PORT: WebSocket port (default: 3000)
#   MCP_PORT: MCP server port (default: 8765)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Source workspace environment (PHYSICAL_REPO_ROOT, DOCKER_NETWORK_INTERNAL)
if [[ -f "${PROJECT_ROOT}/.env.workspace" ]]; then
    # shellcheck source=/dev/null
    source "${PROJECT_ROOT}/.env.workspace"
else
    echo -e "${RED}ERROR: .env.workspace not found${NC}" >&2
    echo "Run .devcontainer/post-create.sh first" >&2
    exit 1
fi

# Source service names for container naming
if [[ -f "${PROJECT_ROOT}/.env.services" ]]; then
    # shellcheck source=/dev/null
    source "${PROJECT_ROOT}/.env.services"
fi

# Fail-fast: require workspace environment
: "${PHYSICAL_REPO_ROOT:?PHYSICAL_REPO_ROOT must be set (source .env.workspace)}"
: "${DOCKER_NETWORK_INTERNAL:?DOCKER_NETWORK_INTERNAL must be set (source .env.workspace)}"
: "${SERVICE_PLAYWRIGHT:?SERVICE_PLAYWRIGHT must be set (source .env.services)}"

# REPO_ROOT is the container-side path where PHYSICAL_REPO_ROOT gets mounted
export REPO_ROOT="${REPO_ROOT:-/workspaces/netcup-api-filter}"

# Export for docker-compose
export PHYSICAL_REPO_ROOT
export DOCKER_NETWORK_INTERNAL

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

# Configuration with defaults
export SSL_ENABLED="${SSL_ENABLED:-$ENABLE_TLS}"
export WS_PORT="${WS_PORT:-3000}"
export WS_EXTERNAL_PORT="${WS_EXTERNAL_PORT:-3000}"
export MCP_PORT="${MCP_PORT:-8765}"
export MCP_EXTERNAL_PORT="${MCP_EXTERNAL_PORT:-8765}"
export MCP_ENABLED="${MCP_ENABLED:-true}"
export WS_MAX_SESSIONS="${WS_MAX_SESSIONS:-10}"
export WS_SESSION_TIMEOUT="${WS_SESSION_TIMEOUT:-3600}"
export PLAYWRIGHT_HEADLESS="${PLAYWRIGHT_HEADLESS:-true}"
export PLAYWRIGHT_BROWSER="${PLAYWRIGHT_BROWSER:-chromium}"
export WS_AUTH_TOKEN="${WS_AUTH_TOKEN:-}"

# Generate auth token if requested and not already set
if [[ "$ENABLE_AUTH" == "true" && -z "${WS_AUTH_TOKEN}" ]]; then
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

# Build hash tracking for smart rebuilds
BUILD_HASH_FILE="${SCRIPT_DIR}/.build-hash"

calculate_build_hash() {
    {
        cat "${SCRIPT_DIR}/Dockerfile"
        cat "${SCRIPT_DIR}/requirements.root.txt"
        cat "${SCRIPT_DIR}/mcp_server.py"
    } | md5sum | cut -d' ' -f1
}

needs_rebuild() {
    local current_hash
    current_hash=$(calculate_build_hash)
    
    if ! docker image inspect playwright-playwright:latest &>/dev/null; then
        echo -e "${YELLOW}Image not found - build required${NC}"
        echo "${current_hash}" > "${BUILD_HASH_FILE}"
        return 0
    fi
    
    if [[ ! -f "${BUILD_HASH_FILE}" ]]; then
        echo -e "${YELLOW}No build hash found - rebuild recommended${NC}"
        echo "${current_hash}" > "${BUILD_HASH_FILE}"
        return 0
    fi
    
    local stored_hash
    stored_hash=$(cat "${BUILD_HASH_FILE}")
    
    if [[ "${current_hash}" != "${stored_hash}" ]]; then
        echo -e "${YELLOW}Build inputs changed - rebuild required${NC}"
        echo "${current_hash}" > "${BUILD_HASH_FILE}"
        return 0
    fi
    
    return 1
}

# Build if needed
if [[ "$REBUILD" == "true" ]] || needs_rebuild; then
    echo -e "${BLUE}Building Playwright container...${NC}"
    
    if docker ps -a --format '{{.Names}}' | grep -q '^playwright$'; then
        echo -e "${YELLOW}Stopping existing container...${NC}"
        docker compose -f docker-compose.yml down
    fi
    
    docker compose -f docker-compose.yml build --progress=plain
    echo -e "${GREEN}✓ Container built successfully${NC}"
    echo ""
else
    echo -e "${GREEN}✓ Container image up-to-date${NC}"
    echo ""
fi

# Stop existing container if running
if docker ps --format '{{.Names}}' | grep -q '^playwright$'; then
    echo -e "${YELLOW}Restarting existing container...${NC}"
    docker compose -f docker-compose.yml restart
    RESTART_MODE=true
else
    RESTART_MODE=false
fi

# Start services
if [[ "${RESTART_MODE}" == "false" ]]; then
    echo -e "${BLUE}Starting Playwright Standalone Service...${NC}"
    docker compose -f docker-compose.yml up -d
fi

# Wait for services to be ready
echo -e "${BLUE}Waiting for services to start...${NC}"
sleep 5

# Check if container is running
if ! docker ps --filter "name=${SERVICE_PLAYWRIGHT}" | grep -q "${SERVICE_PLAYWRIGHT}"; then
    echo -e "${RED}ERROR: Container failed to start${NC}"
    echo "Check logs: docker compose -f docker-compose.yml logs"
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
echo "  docker compose -f docker-compose.yml logs -f"
echo ""
echo "  # Stop service"
echo "  docker compose -f docker-compose.yml down"
echo ""
