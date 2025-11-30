# Playwright Container Architecture

## Overview

This project uses a **dedicated Playwright container** for all browser automation and UI testing to keep the devcontainer clean and ensure consistent rendering (especially emoji/symbols).

## Quick Start

```bash
# 1. Start Playwright container (auto-detects if rebuild needed)
cd tooling/playwright && ./start-playwright.sh

# 2. Run UI tests
./tooling/playwright/playwright-exec.sh pytest ui_tests/tests -v

# 3. Capture screenshots
./tooling/playwright/playwright-exec.sh python3 ui_tests/capture_ui_screenshots.py

# 4. Stop container when done
docker stop playwright
```

**Note**: The start script automatically:
- Detects if Dockerfile/requirements changed → rebuilds container
- Stops/removes old container if exists
- Restarts running container if already up
- Works from any directory (self-contained)

## Architecture

```
Playwright Container (generic-playwright:latest)
  ├── /workspaces/netcup-api-filter → Project root (read-write)
  ├── /screenshots → deploy-local/screenshots (direct output)
  ├── Network: Shares devcontainer network (e.g., naf-dev-network)
  └── Packages: Comprehensive tooling for testing, debugging, visual regression
```

**Key Components:**

1. **`tooling/playwright/start-playwright.sh`**
   - One-command setup script
   - Auto-configures from `.env.workspace`
   - Generates docker-compose `.env` file
   - **Auto-detects rebuild requirements** (Dockerfile/requirements/mcp_server.py changes)
   - **Automatically rebuilds** if inputs changed
   - **Restarts container** if already running
   - Starts container with correct network/volumes
   - Self-contained (works from any directory)

2. **`tooling/playwright/playwright-exec.sh`**
   - Wrapper for executing commands in container
   - Passes all UI test environment variables
   - Sources `DEPLOYMENT_ENV_FILE` if provided
   - Example: `./playwright-exec.sh pytest ui_tests/tests -v`

3. **`build_deployment_lib.sh::capture_screenshots()`**
   - Automatically detects if Playwright container is running
   - Uses devcontainer hostname for network addressing
   - Falls back to local Playwright with helpful message
   - Example: `http://netcup-api-filter-devcontainer-vb:5100`

## Container Contents

The Playwright container includes comprehensive tooling:

### Browser Automation
- `playwright>=1.56.0` - Browser automation framework
- Chromium browser (bundled with Playwright)

### Testing Frameworks
- `pytest>=8.0.0` - Test framework
- `pytest-xdist>=3.5.0` - Parallel test execution
- `pytest-timeout>=2.2.0` - Test timeouts
- `pytest-rerunfailures>=13.0` - Retry flaky tests
- `pytest-asyncio>=1.3.0` - Async test support

### Visual Regression
- `Pillow>=10.0.0` - Image processing
- `pixelmatch>=0.3.0` - Pixel-level image comparison

### Code Quality
- `ruff>=0.2.0` - Fast Python linter
- `black>=24.0.0` - Code formatter
- `mypy>=1.8.0` - Static type checker

### Debugging
- `ipython>=8.0.0` - Enhanced Python REPL
- `ipdb>=0.13.0` - IPython debugger
- `rich>=13.0.0` - Rich terminal output

### HTTP Clients
- `httpx>=0.27.0` - Async HTTP client
- `requests>=2.32.0` - Sync HTTP client

### Mock Servers
- `Flask>=2.3.0` - Netcup API mock server
- `aiosmtpd>=1.4.4` - SMTP mock server

## Network Addressing

The Playwright container communicates with the Flask server running in the devcontainer via the **shared Docker network**.

**How it works:**

1. Container uses devcontainer hostname (e.g., `netcup-api-filter-devcontainer-vb`)
2. Flask server listens on port 5100 in devcontainer
3. Container accesses Flask via: `http://<devcontainer-hostname>:5100`
4. Network name is dynamic from `.env.workspace` (`DOCKER_NETWORK_INTERNAL`)

**Example:**
```bash
# In build_deployment_lib.sh::capture_screenshots()
devcontainer_hostname=$(hostname)
export UI_BASE_URL="http://${devcontainer_hostname}:5100"
./tooling/playwright/playwright-exec.sh python3 ui_tests/capture_ui_screenshots.py
```

## Volume Mappings

```yaml
volumes:
  - ${PHYSICAL_REPO_ROOT}/..:/workspaces:rw     # Full project access (read-write)
  - ${PHYSICAL_PLAYWRIGHT_DIR}/screenshots:/screenshots  # Direct output to deploy-local/screenshots
```

**Key paths:**

- `/workspaces/netcup-api-filter` → Full project root (read-write access)
- `/screenshots` → Direct mapping to `deploy-local/screenshots/` (output path)
- `PHYSICAL_PLAYWRIGHT_DIR` defaults to `${PHYSICAL_REPO_ROOT}/deploy-local`

## Automatic Detection and Fallback

The `capture_screenshots()` function in `build_deployment_lib.sh` automatically:

1. **Detects** if Playwright container is running
2. **Uses container** if available (preferred method)
3. **Falls back** to local Playwright if container not running
4. **Shows helpful message** guiding user to start container

**Example output:**
```
Playwright container not detected
For better font/emoji rendering, start the Playwright container:
  cd tooling/playwright && ./start-playwright.sh
  Then re-run this script

Falling back to local Playwright installation
```

## Integration with Build Scripts

### `build-and-deploy-local.sh`

The local deployment script automatically uses the Playwright container for screenshots:

```bash
# Inside build-and-deploy-local.sh
source build_deployment_lib.sh
capture_screenshots  # Automatically uses container if available
```

### `build-and-deploy.sh`

The webhosting deployment script also uses the container:

```bash
# Inside build-and-deploy.sh
source build_deployment_lib.sh
capture_screenshots  # Same automatic detection
```

## Requirements Management

### Devcontainer (`requirements-dev.txt`)

**Playwright removed** - no longer clutters devcontainer:

```
pytest>=9.0
pytest-asyncio>=1.3
gunicorn>=21.0.0
-r requirements.webhosting.txt
```

### Playwright Container (`tooling/playwright/requirements.root.txt`)

**Comprehensive tooling** - all browser automation, testing, debugging, and quality tools:

```
playwright>=1.56.0
pytest>=8.0.0
pytest-xdist>=3.5.0
pytest-timeout>=2.2.0
pytest-rerunfailures>=13.0
Pillow>=10.0.0
pixelmatch>=0.3.0
ruff>=0.2.0
black>=24.0.0
mypy>=1.8.0
ipython>=8.0.0
ipdb>=0.13.0
rich>=13.0.0
httpx>=0.27.0
requests>=2.32.0
aiosmtpd>=1.4.4
```

## Emoji Font Support

Both the devcontainer **and** Playwright container include `fonts-noto-color-emoji` for consistent emoji rendering:

**.devcontainer/Dockerfile:**
```dockerfile
RUN apt-get update && apt-get install -y \
    fonts-noto-color-emoji \
    ...
```

**tooling/playwright/Dockerfile:**
```dockerfile
RUN apt-get update && apt-get install -y \
    fonts-noto-color-emoji \
    ...
```

This ensures screenshots captured in the container match browser/production rendering.

## Environment Variables

The `playwright-exec.sh` script automatically passes all relevant environment variables:

**Required:**
- `UI_BASE_URL` - Target URL for tests (e.g., `http://devcontainer-hostname:5100`)

**Optional:**
- `PLAYWRIGHT_HEADLESS` - Run browser in headless mode (default: true)
- `SCREENSHOT_DIR` - Screenshot output directory (default: `/screenshots`)
- `UI_ADMIN_USERNAME` - Admin username for tests
- `UI_ADMIN_PASSWORD` - Admin password for tests
- `UI_CLIENT_ID` - Client ID for tests
- `UI_CLIENT_TOKEN` - Client token for tests
- All `DEPLOYED_*` variables (APP_HOST, APP_URL, etc.)

**Example:**
```bash
export UI_BASE_URL="https://naf.vxxu.de"
export UI_ADMIN_USERNAME="admin"
export UI_ADMIN_PASSWORD="TestAdmin123!"
./tooling/playwright/playwright-exec.sh pytest ui_tests/tests -v
```

## Automatic Rebuild Detection

The `start-playwright.sh` script uses **content-based change detection** to determine if a rebuild is needed:

### How It Works

1. **Hash Calculation**: Combines MD5 hashes of:
   - `Dockerfile` - Container image definition
   - `requirements.root.txt` - Python dependencies
   - `mcp_server.py` - MCP server script

2. **Comparison**: Compares current hash against stored hash in `.build-hash`

3. **Rebuild Triggers**:
   - Image doesn't exist (`generic-playwright:latest`)
   - No `.build-hash` file (first run)
   - Hash mismatch (files changed)

4. **Actions on Rebuild**:
   - Stops and removes existing container
   - Runs `docker compose build --progress=plain`
   - Stores new hash in `.build-hash`
   - Starts container with new image

### Build Context

**Directory**: Always run from `tooling/playwright/` directory for proper build context

```bash
# Correct - self-contained build context
cd tooling/playwright && ./start-playwright.sh

# Also works - script changes to its own directory
./tooling/playwright/start-playwright.sh
```

**Why**: Docker Compose `build.context: .` means build context is `tooling/playwright/` directory, which contains:
- `Dockerfile` - Image definition
- `requirements.root.txt` - Python packages
- `mcp_server.py` - MCP server script

### Docker Build Commands Explained

#### `docker compose build`
- **What**: Builds image using `docker-compose.yml` configuration
- **When**: Preferred for this project (respects compose context, networks, build args)
- **Example**: `docker compose build --progress=plain`
- **Benefits**:
  - Reads `build.context` and `build.dockerfile` from compose file
  - Respects `.env` file for build args
  - Consistent with `docker compose up -d` workflow

#### `docker buildx build`
- **What**: Advanced builder with multi-platform support, caching, BuildKit features
- **When**: For cross-platform builds (linux/amd64, linux/arm64), advanced caching
- **Example**: `docker buildx build --platform linux/amd64,linux/arm64 -t generic-playwright:latest .`
- **Benefits**:
  - Multi-architecture support
  - Better caching strategies
  - Parallel builds
- **Not needed here**: Single-platform container, compose handles our needs

#### `docker buildx bake`
- **What**: Builds multiple images from a "bake file" (JSON/HCL) in one command
- **When**: For complex multi-image projects with shared dependencies
- **Example**: `docker buildx bake -f docker-bake.hcl`
- **Benefits**:
  - Builds multiple related images
  - Shares build context and layers
  - Configurable via HCL/JSON files
- **Not needed here**: Single container, compose file is simpler

**Recommendation**: Stick with `docker compose build` for this project - it's simpler and sufficient.

### Force Rebuild

```bash
# Remove hash file to force rebuild
rm tooling/playwright/.build-hash
./tooling/playwright/start-playwright.sh

# Or use docker compose directly
cd tooling/playwright
docker compose build --no-cache
docker compose up -d
```

### Manual Rebuild (Without Start Script)

```bash
cd tooling/playwright

# Build image
docker compose build --progress=plain

# Stop/remove old container
docker stop playwright && docker rm playwright

# Start new container
docker compose up -d
```

## Troubleshooting

### Container not starting

```bash
# Check Docker network exists
docker network ls | grep naf-dev-network

# Verify environment variables
cat .env.workspace | grep -E "DOCKER_(UID|GID|NETWORK_INTERNAL)|PHYSICAL_REPO_ROOT"

# Start container with debug output
cd tooling/playwright && ./start-playwright.sh
```

### Cannot reach Flask server

```bash
# Check devcontainer hostname
hostname  # Should match what build_deployment_lib.sh uses

# Test connectivity from inside container
docker exec playwright curl -v http://$(hostname):5100/health

# Verify Flask is listening
netstat -tlnp | grep 5100
```

### Fonts/emoji rendering issues

```bash
# Verify fonts installed in container
docker exec playwright dpkg -l | grep fonts-noto-color-emoji

# Rebuild container if needed
cd tooling/playwright
docker compose down
docker compose build --no-cache
./start-playwright.sh
```

### Screenshots not appearing in deploy-local/

```bash
# Check volume mapping
docker inspect playwright | grep -A5 Mounts

# Verify PHYSICAL_PLAYWRIGHT_DIR
source .env.workspace
echo $PHYSICAL_PLAYWRIGHT_DIR  # Should be /path/to/repo/deploy-local

# Check permissions
ls -la deploy-local/screenshots/
```

## Best Practices

1. **Always use container for screenshots** - Ensures consistent font/emoji rendering
2. **Start container once** - Reuse for multiple test runs (faster than rebuilding)
3. **Use automatic detection** - Let build scripts detect and use container automatically
4. **Clean up when done** - Stop container to free resources: `docker stop playwright`
5. **Update requirements** - Keep `tooling/playwright/requirements.root.txt` synced with devcontainer needs

## See Also

- `AGENTS.md` - Complete project overview with Playwright container section
- `PYTHON_PACKAGES.md` - Requirements file documentation
- `tooling/playwright/README.md` - Detailed container setup and usage
- `build_deployment_lib.sh` - Screenshot capture implementation
- `LOCAL_TESTING_GUIDE.md` - Local testing workflows
