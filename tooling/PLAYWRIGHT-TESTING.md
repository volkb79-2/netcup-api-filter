# Playwright UI Testing and Browser Automation Guide

**Date**: November 22, 2025  
**Version**: 3.0  
**Purpose**: Comprehensive guide for UI testing and browser automation using Playwright in netcup-api-filter, including dual-mode architecture (MCP + WebSocket), security, and flexible deployment

**Project**: netcup-api-filter - DNS management proxy with Flask backend and modern UI

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture and Connection Methods](#architecture-and-connection-methods)
3. [Standalone Playwright Instance](#standalone-playwright-instance)
4. [Setup and Configuration](#setup-and-configuration)
5. [AI Integration](#ai-integration)
6. [Screenshot Management](#screenshot-management)
7. [Volume Management](#volume-management)
8. [Multi-Session Architecture](#multi-session-architecture)
9. [Security and Access Control](#security-and-access-control)
10. [Testing Patterns and Best Practices](#testing-patterns-and-best-practices)
11. [CI/CD Integration](#cicd-integration)
12. [Troubleshooting](#troubleshooting)
13. [Deployment Models Comparison](#deployment-models-comparison)

---

## Overview

Playwright is a powerful browser automation framework enabling comprehensive UI testing and interaction across multiple browsers (Chromium, Firefox, WebKit). In netcup-api-filter, Playwright serves multiple purposes:

### Lessons Learned from Real-World Implementation

After 10 iterations of testing, we discovered critical limitations with the MCP-only approach:

1. **Form Submission Problem**: The Playwright MCP server wrapper doesn't properly support form submissions:
   - `browser.submit()` doesn't trigger POST requests
   - `browser.click()` on submit buttons doesn't trigger form submissions
   - Parameter `press_enter` not supported in MCP schema
   - No JavaScript execution via `evaluate()` method

2. **Solution**: Dual-mode architecture supporting both MCP (for AI agents) and direct WebSocket access (for programmatic tests)

3. **Best Practice**: Use direct Playwright WebSocket for automated tests, reserve MCP for AI-assisted manual exploration

- **E2E Testing**: Full user journey validation for webapp-ui
- **UI Regression Testing**: Visual and functional verification
- **AI-Assisted Development**: Browser automation for Copilot and agents
- **Screenshot Generation**: Visual documentation and debugging
- **Cross-Browser Compatibility**: Consistent behavior validation

### Key Features

- 🚀 **Fast and reliable** - Auto-waiting, network interception, screenshot/video capture
- 🌐 **Cross-browser** - Chromium, Firefox, WebKit engines
- � **Developer-friendly** - Rich debugging tools and test generation
- 🤖 **Dual-mode architecture** - Both MCP (AI agents) and WebSocket (programmatic tests)
- 🔒 **Secure** - Token authentication, Docker network isolation
- ⚡ **Form handling** - Direct browser automation bypasses MCP limitations
- 📊 **Real testing** - Validates actual Flask routes and UI interactions

---

## Architecture and Connection Methods

### Core Components - Dual Mode Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Playwright Server (Docker Container)                        │
│                                                               │
│  ┌────────────────┐         ┌──────────────────┐           │
│  │  MCP Server    │         │  WebSocket Server│           │
│  │  Port: 8765    │         │  Port: 3000      │           │
│  │  HTTP/SSE      │         │  ws://           │           │
│  └────────────────┘         └──────────────────┘           │
│         │                            │                       │
│         │        ┌───────────────────┴──────┐               │
│         │        │                           │               │
│         ▼        ▼                           ▼               │
│    ┌─────────────────────────────────────────────┐          │
│    │   Playwright Core (Python)                   │          │
│    │   - Chromium, Firefox, WebKit                │          │
│    │   - Full browser automation capabilities     │          │
│    └─────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────┘
         │                            │
         ▼                            ▼
┌──────────────────┐        ┌──────────────────┐
│  AI Agents /     │        │  Automated Tests │
│  Copilot Chat    │        │  (pytest)        │
│  MCP Protocol    │        │  WebSocket API   │
│  ✅ Exploration  │        │  ✅ Full Control │
│  ❌ Form submit  │        │  ✅ Form submit  │
└──────────────────┘        └──────────────────┘
```

### Connection Methods Comparison

| Method | Port | Protocol | Use Case | Form Support | Limitations | Setup |
|--------|------|----------|----------|--------------|-------------|-------|
| **WebSocket** | 3000 | ws:// | Automated tests, pytest | ✅ Full | None | Simple |
| **MCP HTTP** | 8765 | http+sse | AI agents, Copilot | ❌ Broken | No form submit | Simple |
| **MCP WS** | 3001 | ws+mcp | AI-native workflows | ❌ Broken | No form submit | Complex |

**Recommendation**: Use WebSocket (port 3000) for automated testing, MCP (port 8765) only for AI exploration

---

## Standalone Playwright Instance

### What is a Standalone Playwright Instance?

A standalone Playwright instance is a dedicated server running Playwright that can be accessed by multiple clients, projects, and environments simultaneously. It provides centralized browser automation capabilities without embedding Playwright in each project.

### Architecture Options

#### Option 1: Integrated Instance (Current DST-DNS)

```
┌────────────────────────────────────────────────┐
│  DST-DNS Repository                             │
│  ┌──────────────────────────────────────────┐  │
│  │  tools/testing Container                  │  │
│  │  - Playwright installed                   │  │
│  │  - Browser binaries                       │  │
│  │  - Test scripts                           │  │
│  │  - Volumes for results                    │  │
│  └──────────────────────────────────────────┘  │
│         │                                        │
│         ▼                                        │
│  dstdns-network (internal)                      │
│         │                                        │
│         ├─→ webapp-ui:80                        │
│         ├─→ controller:8080                     │
│         └─→ Other services                      │
└────────────────────────────────────────────────┘
```

**✅ Pros**:
- **Simple setup** - Everything in one repository
- **Tight integration** - Direct access to DST-DNS services
- **Version control** - Tests and code evolve together
- **No network overhead** - Same Docker network
- **Easy debugging** - All logs in one place
- **Resource isolation** - Container limits prevent interference

**❌ Cons**:
- **Resource duplication** - Each project needs Playwright
- **Large container** - Browser binaries add ~1GB
- **Rebuild overhead** - Browser updates require container rebuild
- **No sharing** - Can't reuse across projects
- **Limited concurrency** - One container, limited parallelism

#### Option 2: Standalone Shared Instance

```
┌────────────────────────────────────────────────┐
│  Standalone Playwright Server                   │
│  ┌──────────────────────────────────────────┐  │
│  │  Playwright Server (Port 3000/8765)      │  │
│  │  - Multi-client support                   │  │
│  │  - Session management                     │  │
│  │  - Authentication layer                   │  │
│  │  - Resource pooling                       │  │
│  └──────────────────────────────────────────┘  │
└─────────────┬──────────────────────────────────┘
              │
              ├─→ DST-DNS Project (ws://server:3000)
              ├─→ Project B (ws://server:3000)
              ├─→ Project C (ws://server:3000)
              └─→ VS Code Copilot (ws://server:3000)
```

**✅ Pros**:
- **Resource efficiency** - Single Playwright installation
- **Centralized management** - One place to update browsers
- **Multi-project support** - Shared across all projects
- **Consistent environment** - Same browser versions everywhere
- **Better scaling** - Dedicated resources for testing
- **Cost-effective** - Reduce infrastructure duplication

**❌ Cons**:
- **Network dependency** - Requires stable network connectivity
- **Security complexity** - Must implement authentication/encryption
- **Single point of failure** - All tests depend on one service
- **Version conflicts** - Different projects may need different Playwright versions
- **Network latency** - Remote connection overhead
- **Management overhead** - Requires monitoring, maintenance, backup

### Setting Up a Standalone Playwright Instance

#### Step 1: Create Standalone Container

```dockerfile
# standalone-playwright/Dockerfile
FROM mcr.microsoft.com/playwright:v1.40.0-focal

# Install system dependencies
RUN apt-get update && apt-get install -y \
    nginx \
    supervisor \
    openssl \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy server configuration
COPY server-config.js /app/
COPY supervisor.conf /etc/supervisor/conf.d/playwright.conf

# Install additional dependencies
RUN npm install -g playwright-server

# Generate self-signed certificates (for development)
RUN openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /app/server.key \
    -out /app/server.crt \
    -subj "/C=US/ST=State/L=City/O=Org/CN=playwright-server"

# Expose ports
EXPOSE 3000 8765

# Start supervisor
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf"]
```

#### Step 2: Server Configuration

```javascript
// standalone-playwright/server-config.js
const { chromium, firefox, webkit } = require('playwright');
const express = require('express');
const https = require('https');
const fs = require('fs');

class PlaywrightServer {
  constructor() {
    this.sessions = new Map();
    this.maxSessions = parseInt(process.env.MAX_SESSIONS || '10');
    this.sessionTimeout = parseInt(process.env.SESSION_TIMEOUT || '3600000');
  }

  async initialize() {
    // Pre-launch browsers for faster session creation
    this.browserPool = {
      chromium: await chromium.launch({ headless: true }),
      firefox: await firefox.launch({ headless: true }),
      webkit: await webkit.launch({ headless: true })
    };

    console.log('[INFO] Playwright server initialized with browser pool');
  }

  async createSession(sessionId, browserType = 'chromium') {
    if (this.sessions.size >= this.maxSessions) {
      throw new Error('Max sessions reached');
    }

    const browser = this.browserPool[browserType];
    const context = await browser.newContext();
    const page = await context.newPage();

    this.sessions.set(sessionId, {
      context,
      page,
      browserType,
      createdAt: Date.now(),
      lastUsed: Date.now()
    });

    // Auto-cleanup after timeout
    setTimeout(() => this.cleanupSession(sessionId), this.sessionTimeout);

    return { sessionId, browserType };
  }

  async cleanupSession(sessionId) {
    const session = this.sessions.get(sessionId);
    if (session) {
      await session.context.close();
      this.sessions.delete(sessionId);
      console.log(`[INFO] Session ${sessionId} cleaned up`);
    }
  }

  getSession(sessionId) {
    const session = this.sessions.get(sessionId);
    if (session) {
      session.lastUsed = Date.now();
      return session;
    }
    return null;
  }
}

// Express API
const app = express();
app.use(express.json());

const server = new PlaywrightServer();

app.post('/api/session/create', async (req, res) => {
  try {
    const { browserType = 'chromium' } = req.body;
    const sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const result = await server.createSession(sessionId, browserType);
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/session/:sessionId/navigate', async (req, res) => {
  try {
    const { sessionId } = req.params;
    const { url } = req.body;
    const session = server.getSession(sessionId);
    
    if (!session) {
      return res.status(404).json({ error: 'Session not found' });
    }

    await session.page.goto(url);
    res.json({ status: 'success', url });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.get('/api/session/:sessionId/screenshot', async (req, res) => {
  try {
    const { sessionId } = req.params;
    const session = server.getSession(sessionId);
    
    if (!session) {
      return res.status(404).json({ error: 'Session not found' });
    }

    const screenshot = await session.page.screenshot();
    res.set('Content-Type', 'image/png');
    res.send(screenshot);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.delete('/api/session/:sessionId', async (req, res) => {
  try {
    const { sessionId } = req.params;
    await server.cleanupSession(sessionId);
    res.json({ status: 'success' });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Health check
app.get('/health', (req, res) => {
  res.json({ 
    status: 'healthy',
    sessions: server.sessions.size,
    maxSessions: server.maxSessions
  });
});

// Initialize and start server
(async () => {
  await server.initialize();
  
  // HTTPS server
  const httpsServer = https.createServer({
    key: fs.readFileSync('/app/server.key'),
    cert: fs.readFileSync('/app/server.crt')
  }, app);

  httpsServer.listen(3000, '0.0.0.0', () => {
    console.log('[INFO] Playwright HTTPS server listening on port 3000');
  });

  // HTTP server (optional, for development)
  if (process.env.ENABLE_HTTP === 'true') {
    app.listen(8765, '0.0.0.0', () => {
      console.log('[INFO] Playwright HTTP server listening on port 8765');
    });
  }
})();
```

#### Step 3: Docker Compose Configuration

```yaml
# standalone-playwright/docker-compose.yml
services:
  playwright-server:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: playwright-server
    hostname: playwright-server
    ports:
      - "3000:3000"  # HTTPS
      - "8765:8765"  # HTTP (optional)
    environment:
      - MAX_SESSIONS=20
      - SESSION_TIMEOUT=3600000  # 1 hour
      - ENABLE_HTTP=false  # Disable HTTP, use HTTPS only
    volumes:
      - ./vol-screenshots:/app/screenshots:rw
      - ./vol-videos:/app/videos:rw
      - ./vol-traces:/app/traces:rw
    networks:
      - playwright-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "https://localhost:3000/health", "--insecure"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

networks:
  playwright-network:
    external: true
```

#### Step 4: Authentication Layer

```javascript
// standalone-playwright/auth-middleware.js
const jwt = require('jsonwebtoken');
const bcrypt = require('bcrypt');

const JWT_SECRET = process.env.JWT_SECRET || 'change-me-in-production';
const USERS = new Map(); // In production, use database

// Simple token-based auth middleware
function authMiddleware(req, res, next) {
  const token = req.headers.authorization?.replace('Bearer ', '');
  
  if (!token) {
    return res.status(401).json({ error: 'Authentication required' });
  }

  try {
    const decoded = jwt.verify(token, JWT_SECRET);
    req.user = decoded;
    next();
  } catch (error) {
    return res.status(401).json({ error: 'Invalid token' });
  }
}

// Login endpoint
app.post('/api/auth/login', async (req, res) => {
  const { username, password } = req.body;
  const user = USERS.get(username);

  if (!user || !(await bcrypt.compare(password, user.passwordHash))) {
    return res.status(401).json({ error: 'Invalid credentials' });
  }

  const token = jwt.sign(
    { username, roles: user.roles },
    JWT_SECRET,
    { expiresIn: '24h' }
  );

  res.json({ token, expiresIn: '24h' });
});

// Apply to protected routes
app.use('/api/session', authMiddleware);
```

#### Step 5: Client Usage from DST-DNS

```python
# DST-DNS integration
import aiohttp
import asyncio

class PlaywrightClient:
    def __init__(self, server_url: str, auth_token: str):
        self.server_url = server_url
        self.auth_token = auth_token
        self.session_id = None

    async def create_session(self, browser_type: str = 'chromium'):
        async with aiohttp.ClientSession() as session:
            headers = {'Authorization': f'Bearer {self.auth_token}'}
            async with session.post(
                f'{self.server_url}/api/session/create',
                json={'browserType': browser_type},
                headers=headers
            ) as resp:
                data = await resp.json()
                self.session_id = data['sessionId']
                return self.session_id

    async def navigate(self, url: str):
        if not self.session_id:
            raise ValueError('No active session')
        
        async with aiohttp.ClientSession() as session:
            headers = {'Authorization': f'Bearer {self.auth_token}'}
            async with session.post(
                f'{self.server_url}/api/session/{self.session_id}/navigate',
                json={'url': url},
                headers=headers
            ) as resp:
                return await resp.json()

    async def screenshot(self) -> bytes:
        if not self.session_id:
            raise ValueError('No active session')
        
        async with aiohttp.ClientSession() as session:
            headers = {'Authorization': f'Bearer {self.auth_token}'}
            async with session.get(
                f'{self.server_url}/api/session/{self.session_id}/screenshot',
                headers=headers
            ) as resp:
                return await resp.read()

    async def close(self):
        if self.session_id:
            async with aiohttp.ClientSession() as session:
                headers = {'Authorization': f'Bearer {self.auth_token}'}
                await session.delete(
                    f'{self.server_url}/api/session/{self.session_id}',
                    headers=headers
                )

# Usage example
async def test_ui():
    client = PlaywrightClient(
        server_url='https://playwright-server:3000',
        auth_token=os.getenv('PLAYWRIGHT_AUTH_TOKEN')
    )
    
    try:
        await client.create_session('chromium')
        await client.navigate('http://webapp-ui:80')
        screenshot = await client.screenshot()
        
        with open('test-screenshot.png', 'wb') as f:
            f.write(screenshot)
    finally:
        await client.close()
```

### Security Considerations for Standalone Instance

#### Authentication Strategies

1. **Token-Based** (Recommended for APIs):
   ```bash
   # Generate secure token
   export PLAYWRIGHT_TOKEN=$(openssl rand -hex 32)
   
   # Use in client
   curl -H "Authorization: Bearer $PLAYWRIGHT_TOKEN" \
     https://playwright-server:3000/api/session/create
   ```

2. **OAuth 2.0** (Enterprise):
   - Integrate with corporate SSO
   - Use OAuth providers (GitHub, Google, Azure AD)
   - Scoped access per project

3. **mTLS** (Maximum Security):
   - Client certificates required
   - Mutual authentication
   - Per-client certificate management

4. **VPN/Network Isolation** (Simple):
   - Only accessible within VPN
   - No authentication needed
   - Network-level security

#### Network Security

```nginx
# nginx reverse proxy with rate limiting
upstream playwright_backend {
    server playwright-server:3000;
}

limit_req_zone $binary_remote_addr zone=playwright_limit:10m rate=10r/s;

server {
    listen 443 ssl http2;
    server_name playwright.yourdomain.com;

    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;

    # Rate limiting
    limit_req zone=playwright_limit burst=20 nodelay;

    location / {
        proxy_pass https://playwright_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

#### Access Control Lists

```javascript
// IP-based access control
const ALLOWED_IPS = new Set([
  '10.0.0.0/8',      // Internal network
  '172.16.0.0/12',   // Docker networks
  '192.168.1.100',   // Specific developer IP
]);

function ipCheckMiddleware(req, res, next) {
  const clientIP = req.headers['x-forwarded-for'] || req.connection.remoteAddress;
  
  if (!isIPAllowed(clientIP, ALLOWED_IPS)) {
    return res.status(403).json({ error: 'Access denied' });
  }
  
  next();
}

app.use(ipCheckMiddleware);
```

### Resource Management

```javascript
// Resource monitoring and limits
class ResourceManager {
  constructor() {
    this.metrics = {
      totalSessions: 0,
      activeSessions: 0,
      peakSessions: 0,
      totalScreenshots: 0,
      memoryUsage: 0
    };
  }

  checkResources() {
    const usage = process.memoryUsage();
    this.metrics.memoryUsage = usage.heapUsed / 1024 / 1024; // MB

    // Alert if memory high
    if (this.metrics.memoryUsage > 2048) { // 2GB
      console.warn(`[WARN] High memory usage: ${this.metrics.memoryUsage}MB`);
    }

    // Alert if too many sessions
    if (this.metrics.activeSessions > this.maxSessions * 0.8) {
      console.warn(`[WARN] High session count: ${this.metrics.activeSessions}`);
    }
  }

  logMetrics() {
    console.log('[METRICS]', JSON.stringify(this.metrics));
  }
}

// Monitor every minute
setInterval(() => resourceManager.checkResources(), 60000);
setInterval(() => resourceManager.logMetrics(), 300000); // 5 minutes
```

### Backup and Recovery

```bash
#!/bin/bash
# backup-playwright-state.sh

BACKUP_DIR="/backup/playwright"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Backup volumes
docker run --rm \
  -v playwright-screenshots:/data/screenshots:ro \
  -v playwright-videos:/data/videos:ro \
  -v $BACKUP_DIR:/backup \
  alpine:latest \
  tar czf /backup/playwright_${TIMESTAMP}.tar.gz /data

# Cleanup old backups (keep 30 days)
find $BACKUP_DIR -name "playwright_*.tar.gz" -mtime +30 -delete

echo "[INFO] Backup completed: playwright_${TIMESTAMP}.tar.gz"
```

---

## Setup and Configuration

### DST-DNS Testing Container (Integrated)

```bash
# Start testing container
./scripts/testing-exec.sh --start

# Install browsers (if not already done)
./scripts/testing-exec.sh "npx playwright install"

# Start Playwright server
./scripts/testing-exec.sh "npx playwright run-server --port 3000"
```

### Configuration File

```typescript
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/ui',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : 4,
  reporter: [
    ['html', { outputFolder: 'playwright-report' }],
    ['junit', { outputFile: 'test-results/junit.xml' }],
    ['json', { outputFile: 'test-results/results.json' }]
  ],
  use: {
    baseURL: process.env.BASE_URL || 'http://webapp-ui:80',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    headless: true,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
    {
      name: 'mobile-chrome',
      use: { ...devices['Pixel 5'] },
    },
    {
      name: 'mobile-safari',
      use: { ...devices['iPhone 12'] },
    },
  ],
  webServer: {
    command: 'npm run start',
    port: 3000,
    reuseExistingServer: !process.env.CI,
  },
});
```

---

## AI Integration

### VS Code Copilot Chat Integration

```bash
# Start Playwright server for Copilot
docker exec -it DST-DNS-testing playwright server --host 0.0.0.0 --port 3000

# In Copilot Chat:
# "Navigate to http://webapp-ui:80 and take a screenshot"
# "Click the create task button and verify the form appears"
# "Test the login flow with credentials test/test123"
```

### GitHub Actions with AI Agents

```yaml
# .github/workflows/ui-tests-ai.yml
name: AI-Assisted UI Tests

on: [push, pull_request]

jobs:
  ui-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Build and Deploy Stack
        run: |
          docker buildx bake all-services --load
          python deploy-local.py

      - name: Start Playwright Server
        run: |
          docker exec DST-DNS-testing playwright server --host 0.0.0.0 --port 3000 &
          sleep 5

      - name: Run AI-Generated Tests
        env:
          PLAYWRIGHT_SERVER: ws://localhost:3000
        run: |
          # AI agent can connect and run tests
          docker exec DST-DNS-testing pytest tests/ui/ -v

      - name: Upload Test Results
        uses: actions/upload-artifact@v3
        with:
          name: test-results
          path: tools/testing/vol-testing-results/
```

---

## Screenshot Management

### Capture Strategies

```python
# Python test with screenshot management
import pytest
from playwright.sync_api import Page, expect
from pathlib import Path
from datetime import datetime

class ScreenshotManager:
    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def capture(self, page: Page, name: str, full_page: bool = False):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{name}_{timestamp}.png"
        path = self.base_path / filename

        page.screenshot(path=str(path), full_page=full_page)
        return path

    def capture_element(self, element, name: str):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{name}_{timestamp}.png"
        path = self.base_path / filename

        element.screenshot(path=str(path))
        return path

@pytest.fixture
def screenshot_manager():
    return ScreenshotManager(Path("/app/screenshots"))

def test_with_screenshots(page: Page, screenshot_manager):
    page.goto("http://webapp-ui:80")
    
    # Full page screenshot
    screenshot_manager.capture(page, "homepage", full_page=True)
    
    # Element screenshot
    modal = page.locator(".modal")
    screenshot_manager.capture_element(modal, "modal")
```

### Storage Configuration

```yaml
# Volume configuration for screenshots
services:
  testing:
    volumes:
      - ${PHYSICAL_REPO_ROOT}/tools/testing/vol-screenshots:/app/screenshots:rw
      - ${PHYSICAL_REPO_ROOT}/tools/testing/vol-videos:/app/videos:rw
      - ${PHYSICAL_REPO_ROOT}/tools/testing/vol-traces:/app/traces:rw
```

### Consumption Patterns

```python
# AI analysis of screenshots
import anthropic
import base64

def analyze_screenshot_with_ai(screenshot_path: str, question: str):
    client = anthropic.Anthropic()
    
    with open(screenshot_path, 'rb') as f:
        image_data = base64.standard_b64encode(f.read()).decode('utf-8')
    
    message = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": question
                    }
                ],
            }
        ],
    )
    
    return message.content[0].text

# Usage
result = analyze_screenshot_with_ai(
    "screenshots/error_page.png",
    "Does this page show any error messages? What's the error?"
)
```

---

## Volume Management

### Purpose and Structure

```
tools/testing/
├── vol-screenshots/         # Screenshot storage
│   ├── failures/           # Failed test screenshots
│   ├── manual/             # Manual captures
│   └── regression/         # Visual regression baselines
├── vol-videos/              # Video recordings
│   └── test-recordings/    # Per-test videos
├── vol-traces/              # Playwright traces
│   └── failed-tests/       # Traces for debugging
├── vol-cache/               # Browser cache
│   └── playwright/         # Browser binaries
└── vol-results/             # Test results
    ├── html-report/        # HTML test reports
    ├── junit/              # JUnit XML reports
    └── json/               # JSON test results
```

### Lifecycle Management

```bash
#!/bin/bash
# cleanup-test-artifacts.sh

# Configuration
RETENTION_DAYS=7
SCREENSHOT_DIR="tools/testing/vol-screenshots"
VIDEO_DIR="tools/testing/vol-videos"
TRACE_DIR="tools/testing/vol-traces"

# Clean old screenshots (keep failures longer)
find "$SCREENSHOT_DIR/manual" -name "*.png" -mtime +$RETENTION_DAYS -delete
find "$SCREENSHOT_DIR/failures" -name "*.png" -mtime +30 -delete

# Clean videos
find "$VIDEO_DIR" -name "*.webm" -mtime +$RETENTION_DAYS -delete

# Clean traces
find "$TRACE_DIR" -name "*.zip" -mtime +$RETENTION_DAYS -delete

# Clean old test results
find "tools/testing/vol-results" -name "*.xml" -mtime +30 -delete

echo "[INFO] Cleanup completed"
```

---

## Multi-Session Architecture

### Session Manager Implementation

```typescript
// session-manager.ts
import { Browser, BrowserContext, Page, chromium, firefox, webkit } from 'playwright';

export interface Session {
  id: string;
  browser: Browser;
  context: BrowserContext;
  page: Page;
  createdAt: Date;
  lastUsed: Date;
  metadata: Record<string, any>;
}

export class SessionManager {
  private sessions: Map<string, Session> = new Map();
  private maxSessions: number;
  private sessionTimeout: number;

  constructor(maxSessions: number = 10, sessionTimeout: number = 3600000) {
    this.maxSessions = maxSessions;
    this.sessionTimeout = sessionTimeout;
    
    // Auto-cleanup inactive sessions
    setInterval(() => this.cleanupInactiveSessions(), 60000);
  }

  async createSession(
    browserType: 'chromium' | 'firefox' | 'webkit' = 'chromium',
    options: any = {}
  ): Promise<string> {
    if (this.sessions.size >= this.maxSessions) {
      throw new Error(`Maximum sessions (${this.maxSessions}) reached`);
    }

    const sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    // Launch browser
    let browser: Browser;
    switch (browserType) {
      case 'firefox':
        browser = await firefox.launch(options);
        break;
      case 'webkit':
        browser = await webkit.launch(options);
        break;
      default:
        browser = await chromium.launch(options);
    }

    const context = await browser.newContext();
    const page = await context.newPage();

    this.sessions.set(sessionId, {
      id: sessionId,
      browser,
      context,
      page,
      createdAt: new Date(),
      lastUsed: new Date(),
      metadata: {}
    });

    console.log(`[INFO] Session created: ${sessionId} (${browserType})`);
    return sessionId;
  }

  getSession(sessionId: string): Session | undefined {
    const session = this.sessions.get(sessionId);
    if (session) {
      session.lastUsed = new Date();
    }
    return session;
  }

  async closeSession(sessionId: string): Promise<void> {
    const session = this.sessions.get(sessionId);
    if (session) {
      await session.context.close();
      await session.browser.close();
      this.sessions.delete(sessionId);
      console.log(`[INFO] Session closed: ${sessionId}`);
    }
  }

  private cleanupInactiveSessions(): void {
    const now = Date.now();
    for (const [sessionId, session] of this.sessions.entries()) {
      const inactiveTime = now - session.lastUsed.getTime();
      if (inactiveTime > this.sessionTimeout) {
        this.closeSession(sessionId);
        console.log(`[INFO] Inactive session cleaned up: ${sessionId}`);
      }
    }
  }

  getSessionCount(): number {
    return this.sessions.size;
  }

  getAllSessions(): Session[] {
    return Array.from(this.sessions.values());
  }
}
```

### Usage Example

```typescript
// test-multi-session.ts
import { SessionManager } from './session-manager';

const manager = new SessionManager(20, 1800000); // 20 sessions, 30 min timeout

async function runParallelTests() {
  const sessionIds: string[] = [];

  try {
    // Create multiple sessions
    for (let i = 0; i < 5; i++) {
      const sessionId = await manager.createSession('chromium');
      sessionIds.push(sessionId);
    }

    // Run tests in parallel
    await Promise.all(sessionIds.map(async (sessionId) => {
      const session = manager.getSession(sessionId);
      if (session) {
        await session.page.goto('http://webapp-ui:80');
        await session.page.screenshot({ 
          path: `screenshots/test_${sessionId}.png` 
        });
      }
    }));

  } finally {
    // Cleanup all sessions
    await Promise.all(sessionIds.map(id => manager.closeSession(id)));
  }
}
```

---

## Security and Access Control

### Comprehensive Security Checklist

#### Development Environment

- [ ] Use localhost-only binding (`127.0.0.1`)
- [ ] Docker network isolation (no external ports)
- [ ] No authentication required (acceptable for dev)
- [ ] Regular cleanup of test artifacts
- [ ] Monitor resource usage

#### Staging/Testing Environment

- [ ] Token-based authentication enabled
- [ ] TLS encryption (valid certificates)
- [ ] Rate limiting configured
- [ ] Session timeouts enforced
- [ ] Audit logging enabled
- [ ] IP allowlist configured

#### Production Environment

- [ ] OAuth 2.0 or mTLS authentication
- [ ] Strong TLS encryption (TLS 1.3)
- [ ] Rate limiting and DDoS protection
- [ ] Comprehensive audit logs
- [ ] Network segmentation
- [ ] Regular security updates
- [ ] Monitoring and alerting
- [ ] Backup and disaster recovery

### Implementation Examples

#### Token-Based Authentication

```python
# client.py
import os
import aiohttp

class SecurePlaywrightClient:
    def __init__(self, server_url: str):
        self.server_url = server_url
        self.token = os.getenv('PLAYWRIGHT_AUTH_TOKEN')
        
        if not self.token:
            raise ValueError('PLAYWRIGHT_AUTH_TOKEN not set')

    async def _request(self, method: str, path: str, **kwargs):
        headers = kwargs.get('headers', {})
        headers['Authorization'] = f'Bearer {self.token}'
        kwargs['headers'] = headers

        async with aiohttp.ClientSession() as session:
            async with session.request(method, f'{self.server_url}{path}', **kwargs) as resp:
                if resp.status == 401:
                    raise Exception('Authentication failed')
                return await resp.json()

    async def create_session(self):
        return await self._request('POST', '/api/session/create')
```

#### SSH Tunneling for Secure Access

```bash
# Secure remote access via SSH tunnel
ssh -L 3000:localhost:3000 user@playwright-server

# Then connect locally
const browser = await chromium.connectOverCDP('ws://localhost:3000');
```

#### VPN Configuration

```bash
# WireGuard VPN configuration
# /etc/wireguard/wg0.conf

[Interface]
PrivateKey = YOUR_PRIVATE_KEY
Address = 10.0.0.2/24

[Peer]
PublicKey = PLAYWRIGHT_SERVER_PUBLIC_KEY
Endpoint = playwright-server.yourdomain.com:51820
AllowedIPs = 10.0.0.1/32  # Playwright server IP
PersistentKeepalive = 25
```

---

## Testing Patterns and Best Practices

### Page Object Model

```typescript
// pages/TaskPage.ts
import { Page, Locator } from '@playwright/test';

export class TaskPage {
  readonly page: Page;
  readonly domainInput: Locator;
  readonly scanButton: Locator;
  readonly taskStatus: Locator;
  readonly taskResults: Locator;

  constructor(page: Page) {
    this.page = page;
    this.domainInput = page.locator('[data-testid="domain-input"]');
    this.scanButton = page.locator('[data-testid="scan-button"]');
    this.taskStatus = page.locator('[data-testid="task-status"]');
    this.taskResults = page.locator('[data-testid="task-results"]');
  }

  async goto() {
    await this.page.goto('/');
  }

  async createTask(domain: string) {
    await this.domainInput.fill(domain);
    await this.scanButton.click();
  }

  async waitForCompletion() {
    await this.page.waitForSelector('[data-testid="task-completed"]');
  }

  async getStatus(): Promise<string> {
    return await this.taskStatus.textContent() || '';
  }

  async getResults(): Promise<string> {
    return await this.taskResults.textContent() || '';
  }
}

// Usage in tests
import { test, expect } from '@playwright/test';
import { TaskPage } from './pages/TaskPage';

test('create and verify DNS task', async ({ page }) => {
  const taskPage = new TaskPage(page);
  
  await taskPage.goto();
  await taskPage.createTask('example.com');
  await taskPage.waitForCompletion();
  
  const status = await taskPage.getStatus();
  expect(status).toBe('Completed');
});
```

### Visual Regression Testing

```typescript
// visual-regression.spec.ts
import { test, expect } from '@playwright/test';

test('homepage visual regression', async ({ page }) => {
  await page.goto('/');
  
  // Take screenshot and compare with baseline
  await expect(page).toHaveScreenshot('homepage.png', {
    maxDiffPixels: 100,  // Allow minor differences
    threshold: 0.2,       // 20% threshold
  });
});

test('responsive design check', async ({ page }) => {
  // Desktop
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto('/');
  await expect(page).toHaveScreenshot('homepage-desktop.png');

  // Tablet
  await page.setViewportSize({ width: 768, height: 1024 });
  await expect(page).toHaveScreenshot('homepage-tablet.png');

  // Mobile
  await page.setViewportSize({ width: 375, height: 667 });
  await expect(page).toHaveScreenshot('homepage-mobile.png');
});
```

### Performance Testing

```typescript
// performance.spec.ts
import { test, expect } from '@playwright/test';

test('page load performance', async ({ page }) => {
  // Start performance monitoring
  await page.goto('/', { waitUntil: 'networkidle' });

  // Measure performance metrics
  const metrics = await page.evaluate(() => {
    const perf = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming;
    return {
      domContentLoaded: perf.domContentLoadedEventEnd - perf.domContentLoadedEventStart,
      loadComplete: perf.loadEventEnd - perf.loadEventStart,
      firstPaint: performance.getEntriesByName('first-paint')[0]?.startTime || 0,
      firstContentfulPaint: performance.getEntriesByName('first-contentful-paint')[0]?.startTime || 0,
    };
  });

  console.log('[PERF]', metrics);

  // Assert performance thresholds
  expect(metrics.domContentLoaded).toBeLessThan(2000); // 2 seconds
  expect(metrics.firstContentfulPaint).toBeLessThan(1500); // 1.5 seconds
});
```

---

## CI/CD Integration

### GitHub Actions Complete Example

```yaml
# .github/workflows/ui-tests-complete.yml
name: Comprehensive UI Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  ui-test:
    runs-on: ubuntu-latest
    
    strategy:
      matrix:
        browser: [chromium, firefox, webkit]
        shard: [1, 2, 3, 4]
    
    steps:
      - uses: actions/checkout@v3

      - name: Setup Docker Buildx
        uses: docker/setup-buildx-action@v2

      - name: Build DST-DNS Images
        run: |
          docker buildx bake all-services --load
          docker buildx bake testing --load

      - name: Start DST-DNS Stack
        run: |
          python deploy-local.py
          
          # Wait for services
          timeout 120 bash -c 'until curl -f http://localhost:8080/health; do sleep 2; done'

      - name: Start Testing Container
        run: |
          ./scripts/testing-exec.sh --start

      - name: Run UI Tests
        env:
          BROWSER: ${{ matrix.browser }}
          SHARD: ${{ matrix.shard }}
        run: |
          ./scripts/testing-exec.sh "npx playwright test \
            --project=$BROWSER \
            --shard=$SHARD/4 \
            --reporter=html,junit \
            --output=test-results/$BROWSER-shard$SHARD"

      - name: Upload Test Results
        uses: actions/upload-artifact@v3
        if: always()
        with:
          name: test-results-${{ matrix.browser }}-${{ matrix.shard }}
          path: tools/testing/vol-results/

      - name: Upload Screenshots
        uses: actions/upload-artifact@v3
        if: failure()
        with:
          name: screenshots-${{ matrix.browser }}-${{ matrix.shard }}
          path: tools/testing/vol-screenshots/

      - name: Upload Videos
        uses: actions/upload-artifact@v3
        if: failure()
        with:
          name: videos-${{ matrix.browser }}-${{ matrix.shard }}
          path: tools/testing/vol-videos/

      - name: Cleanup
        if: always()
        run: |
          python stop-local.py
          ./scripts/testing-exec.sh --stop
```

---

## Troubleshooting

### Common Issues and Solutions

#### Connection Refused

```bash
# Check if server is running
docker ps | grep testing

# Check logs
docker logs DST-DNS-testing

# Restart server
docker restart DST-DNS-testing

# Test connectivity
curl -v ws://localhost:3000
```

#### Browser Launch Failures

```bash
# Install system dependencies
./scripts/testing-exec.sh "npx playwright install-deps"

# Reinstall browsers
./scripts/testing-exec.sh "npx playwright install --force"

# Check available memory
docker stats DST-DNS-testing
```

#### Screenshot Failures

```bash
# Check permissions
ls -la tools/testing/vol-screenshots/

# Create directory if missing
mkdir -p tools/testing/vol-screenshots/

# Check disk space
df -h
```

#### Session Timeouts

```typescript
// Increase timeout in tests
test.setTimeout(120000); // 2 minutes

// Or in config
export default defineConfig({
  timeout: 60000, // 1 minute per test
});
```

### Debug Mode

```bash
# Run tests in debug mode with headed browser
./scripts/testing-exec.sh "DEBUG=pw:api npx playwright test --headed --debug"

# Run with trace
./scripts/testing-exec.sh "npx playwright test --trace on"

# View trace
./scripts/testing-exec.sh "npx playwright show-trace trace.zip"
```

---

## Deployment Models Comparison

### Summary Table

| Aspect | Integrated (Current) | Standalone Shared | Hybrid |
|--------|---------------------|-------------------|--------|
| **Setup Complexity** | ⭐⭐☆☆☆ Simple | ⭐⭐⭐⭐☆ Complex | ⭐⭐⭐☆☆ Moderate |
| **Resource Efficiency** | ⭐⭐☆☆☆ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐☆ |
| **Security** | ⭐⭐⭐☆☆ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐☆ |
| **Scalability** | ⭐⭐☆☆☆ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐☆ |
| **Maintenance** | ⭐⭐⭐⭐⭐ Easy | ⭐⭐☆☆☆ Complex | ⭐⭐⭐☆☆ Moderate |
| **Multi-Project** | ❌ No | ✅ Yes | ⚠️ Partial |
| **Network Overhead** | ✅ None | ❌ Medium | ⚠️ Low |
| **Cost** | 💰 Per-project | 💰💰 Initial setup | 💰💰 Moderate |

### Recommendation by Use Case

#### **Use Integrated Instance** When:
- Single project development
- Team size < 5 developers
- Simple testing requirements
- Quick setup needed
- Low budget constraints

#### **Use Standalone Instance** When:
- Multiple projects sharing resources
- Team size > 10 developers
- Complex testing requirements
- Enterprise environment
- Cost optimization priority
- Consistent test environment needed

#### **Use Hybrid Approach** When:
- Mix of projects (some need isolation, some can share)
- Development (integrated) + CI/CD (standalone)
- Gradual migration path
- Testing different configurations

### Migration Path: Integrated → Standalone

**Phase 1: Preparation (Week 1)**
1. Set up standalone Playwright server
2. Configure authentication and security
3. Create client libraries for projects
4. Document migration process

**Phase 2: Parallel Running (Weeks 2-3)**
1. Run both systems in parallel
2. Migrate low-risk tests first
3. Monitor performance and stability
4. Adjust resource allocations

**Phase 3: Full Migration (Week 4)**
1. Migrate remaining tests
2. Decommission integrated instances
3. Update documentation
4. Train team on new system

**Phase 4: Optimization (Ongoing)**
1. Fine-tune resource allocation
2. Implement advanced features
3. Continuous monitoring and improvement

---

## Conclusion

Playwright provides powerful UI testing and browser automation capabilities for DST-DNS. The choice between integrated and standalone deployment depends on your specific needs:

**For DST-DNS (Current)**: The integrated testing container provides the best balance of simplicity, performance, and development experience. It's ideal for our single-project architecture with Docker network integration.

**For Multi-Project Environments**: A standalone Playwright server with proper authentication, security, and resource management enables efficient resource sharing and centralized management across multiple projects.

**Key Takeaways**:
- ✅ Use integrated for simple, single-project setups
- ✅ Use standalone for multi-project, enterprise environments
- ✅ Implement proper security regardless of deployment model
- ✅ Monitor resources and adjust limits as needed
- ✅ Automate cleanup and maintenance tasks
- ✅ Document access patterns and best practices
- ✅ Test thoroughly before production deployment

**Next Steps**:
1. Review current DST-DNS testing setup
2. Evaluate need for standalone instance
3. Implement security best practices
4. Create runbooks for common operations
5. Set up monitoring and alerting
6. Train team on Playwright usage

---

## References

- [Playwright Documentation](https://playwright.dev/)
- [DST-DNS Architecture Overview](ARCHITECTURE-OVERVIEW.md)
- [Testing Overview](TESTING-OVERVIEW.md)
- [Docker Build and Bake](DOCKER-BUILD-AND-BAKE.md)
- [Compose Init Up Guide](COMPOSE-INIT-UP.md)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [GitHub Actions for Playwright](https://github.com/microsoft/playwright-github-action)

---

**Document Version History**:
- v2.0 (November 21, 2025): Merged PLAYWRIGHT-UI-TESTING-GUIDE.md and PLAYWRIGHT-UI-TESTING.md, added standalone instance setup, enhanced security guidance, deployment comparison
- v1.0 (November 19, 2025): Initial separate documents
