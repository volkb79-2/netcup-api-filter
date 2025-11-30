# Testing Tooling

Browser automation and UI testing infrastructure for netcup-api-filter.

## Quick Start

```bash
cd tooling/playwright
./setup.sh
```

## Documentation

- **[playwright/README.md](playwright/README.md)** - Generic Playwright container setup and usage
- **[PLAYWRIGHT-TESTING.md](PLAYWRIGHT-TESTING.md)** - Comprehensive testing guide

## Architecture

```
┌─────────────────────────────────────┐
│   Playwright Container (Docker)     │
│                                     │
│   ┌───────────────────────────┐   │
│   │   Playwright + Chromium   │   │
│   │   Port 3000 (WebSocket)   │   │
│   └───────────────────────────┘   │
└─────────────────────────────────────┘
              │
              ▼
    ┌──────────────────┐
    │  Automated Tests │
    │  (pytest)        │
    └──────────────────┘
```

## Usage Examples

### Run Test Script

```bash
# Execute Python script inside container
docker exec playwright python3 /workspaces/netcup-api-filter/ui_tests/test_example.py

# Or with docker compose
docker compose -f tooling/playwright/docker-compose.yml exec playwright \
  python3 /workspaces/netcup-api-filter/ui_tests/test_example.py
```

### Run Pytest Suite

```bash
docker exec playwright pytest /workspaces/netcup-api-filter/ui_tests/tests -v
```

### Interactive Shell

```bash
docker exec -it playwright /bin/bash
```

### Take Screenshots

Screenshots are saved to `tooling/playwright/vol-playwright-screenshots/` and accessible from the devcontainer:

```python
import asyncio
from playwright.async_api import async_playwright

async def screenshot_example():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://example.com")
        await page.screenshot(path="/screenshots/example.png")
        await browser.close()

asyncio.run(screenshot_example())
```

Access screenshot:
```bash
ls -lh tooling/playwright/vol-playwright-screenshots/
```

## Container Management

### Start
```bash
cd tooling/playwright
docker compose up -d
```

### Stop
```bash
docker compose down
```

### Rebuild
```bash
docker compose build --no-cache
docker compose up -d
```

### View Logs
```bash
docker logs playwright
```

## Troubleshooting

### Container Won't Start
```bash
# Check logs
docker logs playwright

# Rebuild
cd tooling/playwright
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Permission Issues with Screenshots
The init container automatically sets permissions. If issues persist:
```bash
# Restart to reinitialize
cd tooling/playwright
docker compose down
./setup.sh
```

### Import Errors
Playwright and dependencies are pre-installed in the container. If you need additional packages:
```bash
docker exec playwright pip install <package-name>
```

---

**See also**: [playwright/README.md](playwright/README.md) for detailed container documentation
