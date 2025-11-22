#!/usr/bin/env bash
# Ensure devcontainer is connected to Playwright network
# Run this if MCP connection fails

set -euo pipefail

# Load shared configuration from .env.workspace if available
if [[ -f "/workspaces/netcup-api-filter/.env.workspace" ]]; then
    # shellcheck source=/dev/null
    source "/workspaces/netcup-api-filter/.env.workspace"
fi

# Use network name from TOML config - fail fast if not set
NETWORK="${DOCKER_NETWORK_INTERNAL:?DOCKER_NETWORK_INTERNAL must be set (source .env.workspace)}"
CONTAINER=$(hostname)

echo "Checking network connectivity..."

# Check if network exists
if ! docker network inspect "$NETWORK" &>/dev/null; then
    echo "❌ Network '$NETWORK' does not exist"
    echo "   Start Playwright first: cd tooling/playwright && MCP_ENABLED=true docker compose up -d"
    exit 1
fi

# Check if already connected
if docker inspect "$CONTAINER" --format='{{range $net, $conf := .NetworkSettings.Networks}}{{$net}} {{end}}' | grep -q "$NETWORK"; then
    echo "✅ Already connected to $NETWORK"
else
    echo "Connecting to $NETWORK..."
    docker network connect "$NETWORK" "$CONTAINER"
    echo "✅ Connected"
fi

# Test connection
echo ""
echo "Testing MCP connection..."
if python3 -c "import requests; r = requests.get('http://playwright:8765/mcp', timeout=2); print(f'✅ MCP accessible at http://playwright:8765/mcp')" 2>/dev/null; then
    echo ""
    echo "✅ Setup complete!"
    echo "   MCP URL: http://playwright:8765/mcp"
else
    echo "❌ Cannot reach MCP server"
    echo "   Is Playwright container running?"
    echo "   Check: docker ps --filter name=playwright"
    exit 1
fi
