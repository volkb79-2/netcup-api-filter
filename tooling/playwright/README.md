# Generic Playwright Container for Browser Automation

A reusable Docker container providing Playwright browser automation with dual access modes:
- **MCP server** for AI agent exploration (optional)
- **Direct Playwright API** for automated testing (primary use)

## Features

- ✅ Playwright with Chromium pre-installed
- ✅ All system dependencies included
- ✅ Python 3.13 with async support
- ✅ Optional MCP server for AI agents
- ✅ Volume mount for screenshots
- ✅ Generic and reusable across projects

## Quick Start

### 1. Configure Environment (Optional)

```bash
cd tooling/playwright
cp .env.example .env
# Edit .env to customize network name, MCP settings, etc.
```

### 2. Build Container

```bash
docker compose build
```

### 3. Start Container

```bash
# Option 1: Use helper script (recommended - auto-loads workspace config)
./start-mcp.sh

# Option 2: Use docker compose directly
docker compose up -d

# Option 3: Enable MCP server explicitly
MCP_ENABLED=true docker compose up -d
```

### 3. Run Tests

```bash
# Run Python script inside container
docker compose exec playwright python3 /workspace/my_test.py

# Or run pytest
docker compose exec playwright pytest /workspace/tests -v
```

## Usage Modes

### Mode 1: Direct Playwright (Recommended for Tests)

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
docker compose exec playwright python3 /workspace/test_example.py
```

### Mode 2: MCP Server (Optional, for AI Agents)

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
├── README.md                 # This file
├── Dockerfile                # Container definition
├── docker-compose.yml        # Container orchestration
├── requirements.root.txt     # Python dependencies
├── mcp_server.py             # Optional MCP server
└── screenshots/              # Screenshot output directory
```

## Configuration

### Environment Variables

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
  - ../../:/workspace              # Project workspace (read-only recommended)
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
pytest>=8.0.0            # Testing framework (if needed)
pytest-asyncio>=0.23.0   # Async test support (if needed)
```

Optional (for MCP mode):
```
fastmcp>=0.9.0          # MCP protocol
fastapi>=0.110.0        # Web framework
uvicorn>=0.30.0         # ASGI server
```

## Why Direct Playwright Instead of MCP?

After extensive testing (10+ iterations), we discovered:

| Feature | MCP Wrapper | Direct Playwright |
|---------|-------------|-------------------|
| Form Submission | ❌ Broken | ✅ Works |
| JavaScript | ❌ Limited | ✅ Full Access |
| Navigation | ✅ Works | ✅ Works |
| Screenshots | ✅ Works | ✅ Works |
| Speed | Slower | Faster |
| Complexity | Higher | Lower |

**Conclusion**: Use Direct Playwright for all automated testing.

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

**Version**: 1.0  
**Last Updated**: 2025-11-22  
**Maintainer**: Generic (adapt per project)
