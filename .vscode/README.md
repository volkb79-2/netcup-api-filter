# `mcp.json`

Configuration for MCP (Model Context Protocol) server connections.

## Current Setup

The Playwright container runs an MCP server on port 8765 when `MCP_ENABLED=true`.

Port 8765 is **NOT** exposed to the host - MCP is only accessible within the Docker network for security.

## Connection URL

**For both VS Code MCP client and shell**: 
```json
{
	"servers": {
		"playwright": {
			// point to the container name and port where MCP is running
			"url": "http://naf-dev-playwright:8765/mcp",
			"type": "http"
		}
	},
	"inputs": []
}
```
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
curl http://naf-dev-playwright:8765/mcp

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

## Troubleshooting 

**Problem**:
```
2026-01-05 19:26:32.915 [info] Starting server playwright
2026-01-05 19:26:32.915 [info] Connection state: Starting
2026-01-05 19:26:32.915 [info] Starting server from Remote extension host
2026-01-05 19:26:32.962 [info] Connection state: Running
2026-01-05 19:26:33.052 [info] 421 status sending message to http://naf-dev-playwright:8765/mcp, will attempt to fall back to legacy SSE
2026-01-05 19:26:33.055 [info] Connection state: Error 421 status connecting to http://naf-dev-playwright:8765/mcp as SSE: Invalid Host header
```

**Solution**: 
The MCP server has an allowed_hosts list that includes playwright and localhost but NOT naf-dev-playwright. Let me check if we can add it via environment variable or need to update the code:

```python file=tooling/playwright/mcp_server.py
transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=[
        "localhost",
        f"localhost:{MCP_PORT}",
        "playwright",
        f"playwright:{MCP_PORT}",
        "naf-dev-playwright",
        f"naf-dev-playwright:{MCP_PORT}",
        "127.0.0.1",
        f"127.0.0.1:{MCP_PORT}",
        "0.0.0.0",
        f"0.0.0.0:{MCP_PORT}",
    ],
    allowed_origins=[
        "http://localhost",
        f"http://localhost:{MCP_PORT}",
        "http://playwright",
        f"http://playwright:{MCP_PORT}",
        "http://naf-dev-playwright",
        f"http://naf-dev-playwright:{MCP_PORT}",
        "vscode-file://vscode-app",
    ],
)
```

## Note

MCP server is for AI agent exploration only. For production testing, use direct Playwright API (see `tooling/playwright/README.md`).
