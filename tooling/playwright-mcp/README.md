# Playwright MCP Test Harness

**⚠️ IMPORTANT: Form submission limitations discovered with MCP mode. See [Dual-Mode Architecture](#dual-mode-architecture) below.**

This folder contains a containerized Model Context Protocol (MCP) server that
wraps the latest Playwright release installed via `pip` on top of
`python:3.13-slim-bookworm`. The server runs in **dual-mode**:

- **HTTP/MCP (Port 8765)**: Simplified API for AI agent exploration (VS Code Copilot)
- **WebSocket/CDP (Port 3000)**: Full Playwright API for automated tests

Once the container is running you can register the MCP endpoint (default 
`http://172.17.0.1:8765/mcp` when using the devcontainer) with an MCP-aware client
such as VS Code Copilot Chat. For automated tests, connect to the WebSocket endpoint
at `ws://localhost:3000` using the Python client in `ui_tests/playwright_client.py`.

## Dual-Mode Architecture

After 10 iterations of testing, we discovered that **MCP mode cannot handle form submissions**.
The dual-mode architecture solves this:

| Feature | WebSocket (3000) | MCP (8765) |
|---------|------------------|------------|
| **Form Submit** | ✅ Works | ❌ Broken |
| **Navigation** | ✅ Works | ✅ Works |
| **Screenshots** | ✅ Works | ✅ Works |
| **JavaScript** | ✅ Available | ❌ Missing |
| **Use For** | **Automated Tests** | AI Exploration |

**Documentation**:
- 📘 [QUICK-REFERENCE.md](../QUICK-REFERENCE.md) - Quick start guide
- 📖 [IMPLEMENTATION-GUIDE.md](../IMPLEMENTATION-GUIDE.md) - Complete implementation
- 📝 [LESSONS-LEARNED.md](../LESSONS-LEARNED.md) - Why dual-mode exists
- 🔧 [playwright_client.py](../../ui_tests/playwright_client.py) - WebSocket client

**Quick Test**: Run `python3 tooling/validate-playwright-websocket.py` after starting the server.

## Prerequisites

- Docker with BuildKit/Buildx enabled (Docker Desktop >= 4.27 or
  `docker buildx create --use`).
- The `docker-compose` plugin for convenience (Compose V2).

## Building

```bash
cd tooling/playwright-mcp
# Multi-platform example (linux/amd64 and linux/arm64 `--platform linux/amd64,linux/arm64 `)
docker buildx build \
  --platform linux/amd64\
  -t netcup/playwright-mcp:latest \
  -f Dockerfile \
  ../../
```

The Dockerfile installs Playwright via `pip` and runs
`python -m playwright install --with-deps chromium` so you always get the
newest browser build supported by PyPI.

For local iterative work you can also run `docker compose build` inside the same
directory—the compose file already points to the correct build context.

## Running

```bash
cd tooling/playwright-mcp
# Start in the background so MCP clients can connect (dynamic user setup)
./run.sh up -d
```

**Note**: The `run.sh` script automatically detects your user and group IDs to ensure proper file permissions for screenshots. If you prefer to use docker compose directly, make sure to set the `UID` and `GID` environment variables:

```bash
export UID=$(id -u) GID=$(id -g)
docker compose up -d
```

Environment variables you can override:

| Variable | Description | Default |
| --- | --- | --- |
| `MCP_SERVER_NAME` | Name reported to MCP clients | `netcup-playwright` |
| `MCP_HTTP_PORT` | HTTP port exposed from the container | `8765` |
| `MCP_WS_PORT` | WebSocket port exposed from the container | `3000` |
| `PLAYWRIGHT_START_URL` | URL opened when the browser boots | `http://172.17.0.1:8000/admin/login` |
| `PLAYWRIGHT_HEADLESS` | `true` launches Chromium headless, set to `false` for visual debugging | `false` |
| `PLAYWRIGHT_SCREENSHOT_DIR` | Where screenshots are persisted inside the container | `/screenshots` |
| `UID` | User ID for file permissions (auto-detected) | `1000` |
| `GID` | Group ID for file permissions (auto-detected) | `1000` |

Screenshots are written to `tooling/playwright-mcp/screenshots/` on the host via
the Compose volume mapping.


## How to Connect VS Code to Playwright for Webpage Testing

To enable webpage testing via VS Code Copilot Chat using this MCP server:

1. **Ensure VS Code Copilot Chat supports MCP servers**: You need a recent version of VS Code with Copilot Chat that includes MCP support. If not available, you may need to use an extension or wait for the feature.

2. **Configure the MCP Server in VS Code**:
   - Open VS Code settings (Ctrl/Cmd + ,)
   - Search for "MCP" or "Model Context Protocol"
   - Add a new MCP server with:
     - **Name**: `netcup-playwright` (or your choice)
     - **URL**: `http://172.17.0.1:8765/mcp` (HTTP endpoint; default port)
     - **Alternative**: `ws://172.17.0.1:3000/mcp` (WebSocket endpoint)
     - If you're using a different gateway IP, run: `ip route | awk '/default/ {print $3; exit}'` inside the devcontainer
   - Tip: Both HTTP and WebSocket transports are supported simultaneously

3. **Verify Connection**:
   - Restart VS Code or reload the Copilot Chat window
   - The server should appear in the MCP servers list
   - Test with a command like: `@netcup-playwright goto https://example.com`

4. **Available Tools for Testing**:
   - `goto(url)` - Navigate to a URL
   - `click(selector)` - Click elements
   - `fill(selector, value)` - Fill form inputs
   - `text(selector)` - Extract text
   - `screenshot(name)` - Take screenshots
   - `reset()` - Restart the browser

5. Once connected, use chat commands such as `@netcup-playwright goto
   https://naf.vxxu.de/admin/` or `@netcup-playwright fill "input[name=username]"
   "admin"`.

## Available Tools

The MCP server exposes the following tool names:

- `goto(url)` – Navigate to a URL.
- `click(selector)` – Click the first element matching a CSS selector.
- `fill(selector, value, press_enter=False)` – Type text into inputs/textareas.
- `text(selector)` – Read inner text from the first matching selector.
- `screenshot(name="capture")` – Save a PNG to the shared screenshot folder.
- `reset(start_url=None)` – Fully restart the browser context.

A resource called `page://current` is also published so clients can query the
currently loaded URL/title.

## Standalone Deployment (Shared Service)

For a shared MCP service accessible from multiple projects/machines:

### Basic Standalone Setup
```bash
cd tooling/playwright-mcp
# Remove network_mode host for portability
docker compose up -d
```

The service will be available at:
- HTTP: `http://localhost:8765/mcp`
- WebSocket: `ws://localhost:3000/mcp`

### Secure Remote Access
For internet-accessible deployment with authentication:

1. **Generate SSL certificates** (replace `your-mcp-host.com`):
   ```bash
   mkdir ssl auth
   openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
     -keyout ssl/mcp.key -out ssl/mcp.crt
   ```

2. **Create basic auth**:
   ```bash
   # Install apache2-utils or httpd-tools
   htpasswd -c auth/.htpasswd yourusername
   ```

3. **Deploy with security**:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.override.yml up -d
   ```

4. **Access remotely**:
   - URL: `https://your-mcp-host.com/mcp`
   - VS Code will prompt for basic auth credentials

### Multiple Sessions
The server now supports multiple concurrent browser sessions. Each MCP client connection gets its own isolated browser context and page, preventing interference between users.

- **Session Isolation**: Each client has a private browser context
- **Automatic Cleanup**: Sessions are cleaned up when pages close or on server shutdown
- **Screenshot Namespacing**: Screenshots include session IDs to avoid conflicts
- **Resource Usage**: Monitor memory usage with multiple concurrent sessions

For high-traffic deployments, consider:
- Resource limits per context
- Session timeouts
- Load balancing across multiple server instances

## MCP Protocol Support
- **HTTP**: Primary transport (FastMCP)
- **WebSocket**: Mentioned in docs but not implemented; stick with HTTP for now

## ✅ Screenshot Feature Fixed!

The screenshot functionality is now working correctly. Here's what I fixed:

### **Issues Identified & Resolved:**

1. **Permission Problems**: The screenshots directory was owned by `root:root` instead of the proper user/group
2. **Docker User Mapping**: The container wasn't running with the correct user/group IDs to match the host
3. **Volume Mount Permissions**: The bind mount didn't have proper group permissions

### **Changes Made:**

1. **Updated docker-compose.yml**:
   - Added dynamic user mapping with `user: "${UID:-1000}:${GID:-1000}"`
   - Added environment variables for UID/GID detection
   - Removed obsolete `version` field

2. **Created run.sh script**:
   - Automatically detects host user and group IDs
   - Sets environment variables for docker-compose
   - Provides consistent way to run the container

3. **Fixed Directory Permissions**:
   - Recreated the screenshots directory with proper ownership (`vb:docker`)
   - Set permissions to `775` (rwxrwxr-x)

4. **Enhanced Dockerfile**:
   - Added runtime directory creation with proper permissions
   - Ensures `/screenshots` directory exists with correct permissions

5. **Improved Server Code**:
   - Added runtime permission setting in the screenshot function
   - Ensures directory permissions are maintained during operation

