# `mcp.json`

Configuration for MCP (Model Context Protocol) server connections.

## Current Setup

The Playwright container runs an MCP server on port 8765 when `MCP_ENABLED=true`.

Port 8765 is **NOT** exposed to the host - MCP is only accessible within the Docker network for security.

## Connection URL

**For both VS Code MCP client and shell**: `http://playwright:8765/mcp`
- Uses Docker network hostname (containers on same network)
- Works from VS Code MCP client, terminal, and scripts
- No port exposure needed - private network communication only

This works because:
1. Both devcontainer and Playwright are on `DOCKER_NETWORK_INTERNAL` (from global-config.active.toml)
2. Docker provides DNS resolution within the network (`playwright` → container IP)
3. No port mapping to host → MCP server is NOT publicly accessible (secure)
4. Network is created by `.devcontainer/post-create.sh` on startup

## Starting MCP Server

```bash
cd tooling/playwright
MCP_ENABLED=true docker compose up -d
```

## Testing Connection

```bash
# From devcontainer (Docker network - works for both shell and VS Code)
curl http://playwright:8765/mcp

# Should return JSON with server info
# Note: http://127.0.0.1:8765 will NOT work (not exposed to host)
```

## Available Endpoints

- `GET /` - Server health check
- `GET /mcp` - MCP protocol information
- `POST /mcp/navigate` - Navigate to URL
- `POST /mcp/screenshot` - Take screenshot
- `GET /mcp/content` - Get page HTML
- `POST /mcp/click` - Click element
- `POST /mcp/fill` - Fill input field
- `POST /mcp/evaluate` - Execute JavaScript

## Note

MCP server is for AI agent exploration only. For production testing, use direct Playwright API (see `tooling/playwright/README.md`).
