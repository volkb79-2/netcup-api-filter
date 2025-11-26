# MCP and FUSE Configuration Changes

> Part of the active documentation set in `/docs`. See `docs/README.md` for context.

## Summary

Implemented MCP server for Playwright container and added FUSE support to devcontainer.

## Changes Made

### 1. MCP Server Implementation

**Created `/workspaces/netcup-api-filter/tooling/playwright/mcp_server.py`**
- FastAPI-based MCP server for Playwright browser automation
- Provides REST API endpoints for AI agent exploration
- Automatically starts when `MCP_ENABLED=true`

**Key Endpoints:**
- `GET /` - Health check
- `GET /mcp` - MCP protocol information
- `POST /mcp/navigate` - Navigate to URL
- `POST /mcp/screenshot` - Take screenshot
- `GET /mcp/content` - Get page HTML
- `POST /mcp/click` - Click element
- `POST /mcp/fill` - Fill form field
- `POST /mcp/evaluate` - Execute JavaScript

### 2. Playwright Container Updates

**Updated `tooling/playwright/docker-compose.yml`:**
- Exposed port 8765 bound to `127.0.0.1` only (security)
- Modified command to run MCP server when `MCP_ENABLED=true`
- Container now auto-starts MCP server or runs in background mode

**Updated `tooling/playwright/Dockerfile`:**
- Added `COPY mcp_server.py` to include script at build time
- No longer creates empty placeholder file

**Updated `tooling/playwright/requirements.txt`:**
- Added FastAPI >= 0.110.0
- Added uvicorn[standard] >= 0.30.0
- Added pydantic >= 2.7.0

### 3. FUSE Support for Devcontainer

**Updated `.devcontainer/devcontainer.json`:**
- Added `--cap-add SYS_ADMIN` capability
- Added `--device /dev/fuse` device mapping
- Enables sshfs for remote filesystem mounting

**Note:** FUSE requires:
1. Docker host must have FUSE installed (`apt-get install fuse`)
2. `/dev/fuse` device must exist on host
3. Devcontainer must be rebuilt after these changes

### 4. Documentation Updates

**Updated `.vscode/README.md`:**
- Documented MCP connection URLs: `http://172.17.0.1:8765/mcp` (VS Code), `http://playwright:8765/mcp` (shell)
- Explained Docker networking vs. Docker host IP access
- Listed all MCP endpoints
- Added testing instructions

## Usage

### Starting MCP Server

```bash
cd tooling/playwright
MCP_ENABLED=true docker compose up -d
```

### Testing MCP Connection

```bash
# From devcontainer shell (Docker network)
curl http://playwright:8765/mcp

# From VS Code context (Docker host IP)
curl http://172.17.0.1:8765/mcp

# Should return JSON with server info
```

### Connecting from VS Code

1. Devcontainer and Playwright share Docker network (configured in `global-config.active.toml`)
2. Port 8765 is exposed on Docker host (`0.0.0.0:8765`)
3. MCP server URL for VS Code: `http://172.17.0.1:8765/mcp` (configured in `.vscode/mcp.json`)
4. Uses Docker host IP because VS Code server runs inside devcontainer
5. Shell access uses Docker network: `http://playwright:8765/mcp`
6. Note: `127.0.0.1:8765` does NOT work - it refers to the devcontainer's localhost, not Docker host

**Network Configuration:**
- Network name is read from `global-config.active.toml` by `.devcontainer/post-create.sh`
- Exported as `DOCKER_NETWORK_INTERNAL` (default: `naf-dev-network`)
- Both devcontainer and Playwright use this network for connectivity
- Network is created automatically by `post-create.sh` on devcontainer startup

### Using FUSE/sshfs

After rebuilding devcontainer with FUSE support:

```bash
# Mount remote filesystem
mkdir -p /tmp/remote
sshfs user@server:/path /tmp/remote

# Access files
ls /tmp/remote

# Unmount
fusermount -u /tmp/remote
```

## Verification

### MCP Server Status

```bash
# Check container logs
docker logs playwright

# Should see:
# INFO: Uvicorn running on http://0.0.0.0:8765
```

### FUSE Availability

```bash
# Check FUSE device
ls -l /dev/fuse

# Should show:
# crw-rw-rw- 1 root root 10, 229 ...
```

## Current Status

- ✅ MCP server implemented and running
- ✅ Port 8765 forwarded by VS Code  
- ✅ MCP endpoints responding correctly
- ✅ FUSE configuration added to devcontainer
- ⚠️ FUSE requires devcontainer rebuild to take effect
- ⚠️ FUSE requires `/dev/fuse` on Docker host

## Next Steps

1. **To activate FUSE support:**
   - Ensure Docker host has FUSE: `apt-get install fuse`
   - Rebuild devcontainer: "Dev Containers: Rebuild Container"
   - Verify: `ls -l /dev/fuse`

2. **To use MCP in VS Code:**
   - Ensure network connection: `bash .vscode/ensure-mcp-connection.sh`
   - Open Copilot Chat
   - Click settings → Add MCP Server
   - Type: HTTP
   - URL: `http://playwright:8765/mcp`
   - Server should connect successfully

3. **To rebuild Playwright with MCP:**
   ```bash
   cd tooling/playwright
   docker compose down
   docker compose build
   MCP_ENABLED=true docker compose up -d
   ```

## Troubleshooting

### MCP Connection Refused

- Run network helper: `bash .vscode/ensure-mcp-connection.sh`
- Check if container is running: `docker ps | grep playwright`
- Check container logs: `docker logs playwright`
- Verify network connection: `docker network inspect playwright_default`
- Restart container: `docker restart playwright`

### FUSE Not Available

- Check Docker host: `ls -l /dev/fuse` (run on host, not in container)
- Install on host: `sudo apt-get install fuse`
- Rebuild devcontainer after host changes
- Verify inside container: `ls -l /dev/fuse`

### MCP Server Crashes

- Check dependencies: `docker exec playwright pip list | grep -E '(fastapi|uvicorn)'`
- View full logs: `docker logs playwright --tail 100`
- Rebuild container: `docker compose build --no-cache`

## Files Modified

- ✅ `tooling/playwright/mcp_server.py` (created)
- ✅ `tooling/playwright/docker-compose.yml`
- ✅ `tooling/playwright/Dockerfile`
- ✅ `tooling/playwright/requirements.txt`
- ✅ `.devcontainer/devcontainer.json`
- ✅ `.vscode/README.md`
- ✅ `.vscode/mcp.json` (already correct)

## Related Documentation

- `tooling/playwright/README.md` - Playwright container usage
- `AGENTS.md` - FUSE documentation
- `.vscode/README.md` - MCP connection guide
