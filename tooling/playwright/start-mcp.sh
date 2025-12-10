#!/usr/bin/env bash
# Start Playwright with MCP server using shared network configuration
# FAIL-FAST: All required variables must be set explicitly
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Load workspace environment (REQUIRED)
if [[ -f "$REPO_ROOT/.env.workspace" ]]; then
    # shellcheck source=/dev/null
    source "$REPO_ROOT/.env.workspace"
    echo "✓ Loaded workspace configuration from .env.workspace"
else
    echo "ERROR: .env.workspace not found" >&2
    echo "       Run: .devcontainer/post-create.sh" >&2
    exit 1
fi

# Load service names (REQUIRED)
if [[ -f "$REPO_ROOT/.env.services" ]]; then
    # shellcheck source=/dev/null
    source "$REPO_ROOT/.env.services"
    echo "✓ Loaded service names from .env.services"
fi

# Verify required variables from .env.workspace
: "${DOCKER_NETWORK_INTERNAL:?DOCKER_NETWORK_INTERNAL not set (run post-create.sh)}"
: "${PHYSICAL_REPO_ROOT:?PHYSICAL_REPO_ROOT not set (run post-create.sh)}"
: "${DOCKER_UID:?DOCKER_UID not set (run post-create.sh)}"
: "${DOCKER_GID:?DOCKER_GID not set (run post-create.sh)}"
: "${SERVICE_PLAYWRIGHT:?SERVICE_PLAYWRIGHT not set (source .env.services)}"

# Set Playwright-specific variables (with clear defaults for MCP use case)
export DOCKER_NETWORK_INTERNAL
export PHYSICAL_REPO_ROOT
export DOCKER_UID
export DOCKER_GID
export PHYSICAL_PLAYWRIGHT_DIR="${PHYSICAL_REPO_ROOT}/tooling/playwright"
export MCP_ENABLED="true"
export MCP_PORT="8765"
export MCP_SERVER_NAME="playwright"
export PLAYWRIGHT_HEADLESS="true"
export PLAYWRIGHT_BROWSER="chromium"

echo ""
echo "Starting Playwright with MCP server:"
echo "  Network: $DOCKER_NETWORK_INTERNAL"
echo "  Workspace: $PHYSICAL_REPO_ROOT"
echo "  MCP: enabled on port $MCP_PORT"
echo "  UID:GID: $DOCKER_UID:$DOCKER_GID"
echo ""

cd "$SCRIPT_DIR"
docker compose up -d

echo ""
echo "✅ Playwright container started!"
echo ""
echo "MCP server: http://${SERVICE_PLAYWRIGHT}:8765/mcp"
echo "  - Accessible from: VS Code Copilot, terminal, scripts"
echo "  - Network: $DOCKER_NETWORK_INTERNAL (Docker DNS resolution)"
echo "  - NOT exposed to host (secure, private network only)"
echo ""
echo "Test connection:"
echo "  curl http://${SERVICE_PLAYWRIGHT}:8765/mcp"
echo ""
echo "If VS Code Copilot shows connection errors:"
echo "  1. Wait 5-10 seconds for MCP server to start"
echo "  2. Reload VS Code window (Cmd/Ctrl+Shift+P → 'Reload Window')"
echo "  3. Check logs: View → Output → GitHub Copilot"
