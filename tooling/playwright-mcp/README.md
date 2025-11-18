# Playwright MCP Test Harness

This folder contains a containerized Model Context Protocol (MCP) server that
wraps the latest Playwright release installed via `pip` on top of
`python:3.13-slim-bookworm`. Once the container is running you can register its
WebSocket endpoint (default `ws://172.17.0.1:8765/mcp` when using the devcontainer;
replace the IP with your Docker host gateway if it differs) with an MCP-aware client
such as VS Code Copilot Chat. The server launches Chromium, keeps one page
open, and provides automation tools for login, navigation, clicks, form
filling, text extraction, and screenshots.

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
| `MCP_PORT` | WebSocket port exposed from the container | `8765` |
| `PLAYWRIGHT_START_URL` | URL opened when the browser boots | `https://naf.vxxu.de/admin/login` |
| `PLAYWRIGHT_HEADLESS` | `true` launches Chromium headless, set to `false` if you want to VNC in | `true` |
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
       - **URL**: `ws://172.17.0.1:8765/mcp` (Docker host gateway inside the devcontainer; change if your host gateway IP differs)
       - If WebSocket isn't supported, try `http://172.17.0.1:8765/mcp` (HTTP endpoint with the same host gateway IP)
    - Tip: inside the devcontainer you can run `ip route | awk '/default/ {print $3; exit}'` to discover the correct gateway IP if it is not `172.17.0.1`.

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

## Stopping and Cleanup

```bash
cd tooling/playwright-mcp
./run.sh down
```

Remove images if desired:

```bash
docker image rm netcup/playwright-mcp:latest
```

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

