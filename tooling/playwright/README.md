# Generic Playwright Container for Browser Automation

A reusable Docker container providing Playwright browser automation with three access modes:
- **WebSocket server** for programmatic tests and multi-client access (port 3000)
- **MCP server** for AI agent exploration (port 8765)
- **Direct Playwright API** for in-container testing

## Features

- ✅ Playwright with Chromium pre-installed
- ✅ All system dependencies included
- ✅ Python 3.13 with async support
- ✅ **Multi-client WebSocket service** (port 3000) - NEW!
- ✅ Optional MCP server for AI agents (port 8765)
- ✅ **TLS support with self-signed certificates** - NEW!
- ✅ **Token-based authentication** - NEW!
- ✅ **Session management per client** - NEW!
- ✅ Volume mount for screenshots
- ✅ Generic and reusable across projects

## Quick Start

The Playwright container provides both WebSocket (port 3000) and MCP (port 8765) interfaces.

### Start the Container

```bash
cd tooling/playwright

# Basic mode (no TLS, no auth)
./start-playwright.sh

# With TLS (self-signed certificate)
./start-playwright.sh --tls

# With authentication
./start-playwright.sh --auth

# Full security (TLS + auth)
./start-playwright.sh --tls --auth

# Force rebuild
./start-playwright.sh --rebuild
```

### Connect via WebSocket (Recommended for Tests)

**Python WebSocket Client:**
```python
from ws_client import PlaywrightWSClient
import asyncio

async def main():
    async with PlaywrightWSClient("ws://playwright:3000") as client:
        await client.navigate("https://example.com")
        await client.fill("#username", "admin")
        await client.click("button[type='submit']")
        screenshot = await client.screenshot("test.png")
        print(f"Screenshot: {screenshot['path']}")

asyncio.run(main())
```

**With Authentication:**
```python
async with PlaywrightWSClient(
    "ws://playwright:3000",
    auth_token="your-token-here"
) as client:
    await client.navigate("https://example.com")
```

### Connect via MCP (For AI Agents)

The MCP server is available at `http://playwright:8765/mcp` for AI agent integration.

---

## Usage Modes

### Mode 1: WebSocket Service (NEW - Recommended for Multi-Client)

The standalone WebSocket server allows multiple clients to connect simultaneously.
Each client gets its own browser session.

**Features:**
- ✅ Multi-client support
- ✅ Session isolation per client
- ✅ Full Playwright API (no MCP limitations)
- ✅ Form submissions work correctly
- ✅ JavaScript execution available
- ✅ Optional TLS encryption
- ✅ Optional token authentication

**Start the service:**
```bash
./start-standalone.sh
```

**Use the Python client:**
```python
from ws_client import PlaywrightWSClient
import asyncio

async def test_login():
    async with PlaywrightWSClient("ws://localhost:3000") as client:
        # Login helper method
        result = await client.login(
            url="https://example.com/login",
            username="admin",
            password="secret",
            success_url_pattern="**/dashboard"
        )
        print(f"Logged in: {result['logged_in']}")
        
        # Take screenshot
        await client.screenshot("after_login.png")

asyncio.run(test_login())
```

**WebSocket Protocol:**

All messages are JSON:

```json
// Request
{"id": "msg1", "command": "navigate", "args": {"url": "https://example.com"}}

// Response
{"type": "response", "id": "msg1", "success": true, "data": {"url": "...", "title": "..."}}
```

**Available Commands:**
- Navigation: `navigate`, `reload`, `go_back`, `go_forward`
- Actions: `click`, `fill`, `type`, `press`, `check`, `uncheck`, `hover`, `focus`
- Form: `select_option`, `login` (convenience method)
- Query: `get_url`, `get_content`, `get_text`, `get_attribute`, `get_input_value`
- Wait: `wait_for_selector`, `wait_for_url`, `wait_for_load_state`
- State: `is_visible`, `is_enabled`, `is_checked`, `query_selector`, `query_selector_all`
- Screenshot: `screenshot`
- JavaScript: `evaluate`
- Cookies: `cookies`, `set_cookies`, `clear_cookies`
- Session: `close_session`, `health`

### Mode 2: Direct Playwright (Recommended for In-Container Tests)

Run Playwright directly inside the container:

```python
# test_example.py
import asyncio
from playwright.async_api import async_playwright

async def test_form_submission():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto("https://example.com/login")
        await page.fill("#username", "user")
        await page.fill("#password", "pass")
        await page.click("button[type='submit']")  # ✅ Works!
        
        await page.wait_for_url("**/dashboard")
        print(f"✅ Login successful: {page.url}")
        
        await browser.close()

asyncio.run(test_form_submission())
```

Run it:
```bash
docker compose exec playwright python3 /workspaces/netcup-api-filter/test_example.py
```

### Mode 3: MCP Server (Optional, for AI Agents)

The container can optionally run an MCP server for AI agent exploration:

```bash
# Start with MCP server enabled
MCP_ENABLED=true docker compose up -d
```

**Note**: MCP mode has limitations:
- ❌ Form submissions don't work reliably
- ❌ Limited JavaScript execution
- ✅ Good for navigation and screenshots
- ✅ Simplified API for AI exploration

**Recommendation**: Use Mode 1 (Direct Playwright) for all testing.

#### Accessing MCP Server

**From Devcontainer:**
- VS Code MCP client: `http://172.17.0.1:8765/mcp` (Docker host IP, configured in `.vscode/mcp.json`)
- Shell/scripts: `http://playwright:8765/mcp` (Docker network name)

The devcontainer automatically connects to the shared Docker network (`naf-local` by default) via `.devcontainer/post-create.sh`.

**From Remote Machine:**
For security, the MCP port (8765) is not exposed publicly on production hosts. Use an SSH tunnel:

```bash
# On your local machine, create SSH tunnel to the server
ssh -L 8765:localhost:8765 user@your-server.com -N

# Now MCP is accessible at http://127.0.0.1:8765/mcp
```

## Directory Structure

```
tooling/playwright/
├── README.md                     # This file
├── Dockerfile                    # Container with WebSocket + MCP servers
├── docker-compose.yml            # Container orchestration
├── requirements.root.txt         # Python dependencies
├── requirements.standalone.txt   # Additional service dependencies
├── mcp_server.py                 # MCP server for AI agents
├── ws_server.py                  # WebSocket server for tests
├── ws_client.py                  # Python WebSocket client
├── start_services.py             # Multi-service startup script
├── start-playwright.sh           # Start script (supports --tls, --auth)
├── start-mcp.sh                  # Legacy MCP mode start script
├── test_ws_server.py             # WebSocket server tests
└── vol-playwright-screenshots/   # Screenshot output directory
```

## Configuration

### Environment Variables (Standalone Mode)

```bash
# WebSocket server
WS_PORT=3000                      # WebSocket server port
WS_HOST=0.0.0.0                   # Bind address
WS_AUTH_TOKEN=                    # Authentication token (empty = no auth)
WS_MAX_SESSIONS=10                # Maximum concurrent sessions
WS_SESSION_TIMEOUT=3600           # Session timeout in seconds

# TLS settings
SSL_ENABLED=false                 # Enable TLS
SSL_CERT_PATH=/certs/server.crt   # Certificate path
SSL_KEY_PATH=/certs/server.key    # Key path

# MCP server
MCP_ENABLED=true                  # Enable MCP server
MCP_PORT=8765                     # MCP server port
MCP_SERVER_NAME=playwright        # MCP server name

# Playwright
PLAYWRIGHT_HEADLESS=true          # Run browsers headless
PLAYWRIGHT_BROWSER=chromium       # Browser: chromium, firefox, webkit
```

### Environment Variables (Integrated Mode)

Create a `.env` file from `.env.example` or set these variables:

```bash
# Network configuration (shared with devcontainer)
SHARED_DOCKER_NETWORK=naf-local   # Docker network name (must match .devcontainer/post-create.sh)

# Container settings
PLAYWRIGHT_HEADLESS=true          # Run browsers headless
PLAYWRIGHT_BROWSER=chromium       # Browser: chromium, firefox, webkit
DOCKER_UID=1000                   # User ID for file permissions
DOCKER_GID=1000                   # Group ID for file permissions

# MCP server (optional)
MCP_ENABLED=false                 # Enable MCP server
MCP_PORT=8765                     # MCP server port
MCP_SERVER_NAME=playwright        # MCP server name

# Volume paths (set automatically by post-create.sh)
PHYSICAL_REPO_ROOT=/workspaces/netcup-api-filter  # Host path to repo
PHYSICAL_PLAYWRIGHT_DIR=./vol-playwright-screenshots  # Screenshots directory
```

### Shared Network Configuration

This Playwright container uses a **shared Docker network** that's also used by the devcontainer:
- **Network name**: `naf-local` (netcup-api-filter local network) by default
- **Configured in**: `.devcontainer/post-create.sh` via `get_shared_network_name()`
- **Environment variable**: `SHARED_DOCKER_NETWORK`
- **Purpose**: Allows devcontainer to access Playwright by hostname (`playwright`)

The network is automatically created and connected by `.devcontainer/post-create.sh` when the devcontainer starts.

### Volume Mounts

```yaml
volumes:
  - ./screenshots:/screenshots      # Screenshot output
  - ../../:/workspaces/netcup-api-filter  # Project workspace
```

## Integration with Projects

### For netcup-api-filter

Mount project directory and run tests:

```bash
# From netcup-api-filter root
docker compose -f tooling/playwright/docker-compose.yml run --rm playwright \
  pytest ui_tests/tests -v
```

### For Other Projects

1. Copy `tooling/playwright/` to your project
2. Update volume mounts in `docker-compose.yml`
3. Run your tests inside the container

## Dependencies

All Python packages are defined in `requirements.root.txt`:

```
playwright>=1.56.0       # Browser automation
websockets>=12.0         # WebSocket support (NEW)
pytest>=8.0.0            # Testing framework
pytest-asyncio>=0.23.0   # Async test support
```

For MCP mode (included in requirements.root.txt):
```
fastmcp>=0.9.0          # MCP protocol
fastapi>=0.110.0        # Web framework
uvicorn>=0.30.0         # ASGI server
mcp>=1.22.0             # MCP SDK
```

## Mode Comparison

| Feature | WebSocket | Direct Playwright | MCP |
|---------|-----------|-------------------|-----|
| Multi-client | ✅ Yes | ❌ No | ❌ Single |
| Form Submission | ✅ Works | ✅ Works | ❌ Broken |
| JavaScript | ✅ Full | ✅ Full | ❌ Limited |
| Remote Access | ✅ Yes | ❌ Container only | ✅ Yes |
| TLS Support | ✅ Yes | N/A | ❌ No |
| Authentication | ✅ Token | N/A | ❌ No |
| Session Management | ✅ Per-client | Manual | Single |
| Best For | Tests, CI/CD | Quick scripts | AI exploration |

**Recommendation**: 
- Use **WebSocket** for automated tests and CI/CD
- Use **Direct Playwright** for quick in-container scripts
- Use **MCP** only for AI-assisted exploration

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker compose logs playwright

# Rebuild container
docker compose build --no-cache
```

### Permission Errors

```bash
# Fix screenshot directory permissions
chmod 775 tooling/playwright/screenshots
chown $UID:$GID tooling/playwright/screenshots
```

### Playwright Not Found

```bash
# Verify Playwright is installed
docker compose exec playwright python3 -c "from playwright.async_api import async_playwright; print('OK')"

# Reinstall if needed
docker compose exec playwright pip install playwright
docker compose exec playwright python3 -m playwright install chromium
```

## Best Practices

1. **Run tests inside container** - Don't try to run Playwright locally
2. **Use headless mode** - Faster and more reliable
3. **Mount workspace read-only** - Prevents accidental modifications
4. **Use volume for screenshots** - Persist test artifacts
5. **Keep container generic** - Project-specific code stays outside

## Examples

### Basic Navigation Test

```python
docker compose exec playwright python3 << 'EOF'
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://example.com")
        print(f"Title: {await page.title()}")
        await browser.close()

asyncio.run(test())
EOF
```

### Screenshot Test

```python
docker compose exec playwright python3 << 'EOF'
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://example.com")
        await page.screenshot(path="/screenshots/example.png")
        print("Screenshot saved!")
        await browser.close()

asyncio.run(test())
EOF
```

## License

This is a generic tool that can be used in any project.

## Support

For issues or questions:
1. Check container logs: `docker compose logs`
2. Verify Playwright installation
3. Ensure proper file permissions
4. Review documentation above

---

**Version**: 2.0  
**Last Updated**: 2025-11-26  
**Maintainer**: Generic (adapt per project)

## Changelog

### v2.0 (2025-11-26)
- Added WebSocket server for multi-client support
- Added standalone Docker Compose configuration
- Added TLS support with self-signed certificates
- Added token-based authentication
- Added session management per client
- Added Python WebSocket client library
- Added convenience `login` command for authentication flows
