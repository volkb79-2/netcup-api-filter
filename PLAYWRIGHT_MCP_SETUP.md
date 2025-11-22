# Playwright MCP Setup Guide

## Overview

The Playwright MCP (Model Context Protocol) server allows VS Code Copilot Chat to interact with web pages for testing. This guide explains the networking requirements and how to troubleshoot connectivity issues.

## Network Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Docker Host                                                  │
│                                                              │
│  ┌──────────────────┐         ┌──────────────────┐         │
│  │  Devcontainer    │         │  Playwright      │         │
│  │  (vscode user)   │◄───────►│  Container       │         │
│  │                  │         │                  │         │
│  │  Port: N/A       │         │  Port: 8765/mcp  │         │
│  │  Network: bridge │         │  Port: 3000/ws   │         │
│  └──────────────────┘         └──────────────────┘         │
│         │                              │                    │
│         └──────────────┬───────────────┘                    │
│                   Docker Bridge                             │
│                   172.17.0.1                                 │
└─────────────────────────────────────────────────────────────┘
                         │
                    VS Code MCP Client
                    Connects to http://172.17.0.1:8765/mcp
```

## Prerequisites

1. **Docker network connectivity**: Both devcontainer and playwright container must be on the same Docker network
2. **Port forwarding**: The MCP port (8765) must be exposed to the host
3. **FUSE kernel module** (for sshfs): Required on the host system for mounting remote filesystems

## Setup Instructions

### 1. Install FUSE on Host (for sshfs support)

**On the Docker host** (not inside the devcontainer):

```bash
# Ubuntu/Debian
sudo apt-get update && sudo apt-get install -y fuse

# Fedora/RHEL
sudo dnf install -y fuse

# Check if FUSE is available
ls -l /dev/fuse
```

**Note**: FUSE requires kernel module support and must be installed on the host. The devcontainer already has `sshfs` installed but needs `/dev/fuse` from the host.

### 2. Start Playwright Container with Correct Network

The playwright container should be started with:
- Port 8765 exposed to host
- Connected to the same Docker network as the devcontainer (if needed)
- Proper user permissions for file access

```bash
# Check devcontainer's network
docker inspect <devcontainer-name> | grep NetworkMode

# Start playwright container
cd /workspaces/netcup-api-filter/tooling/playwright
docker compose up -d

# Verify port is exposed
docker ps | grep playwright
# Should show: 0.0.0.0:8765->8765/tcp
```

### 3. Configure VS Code MCP Client

Update `.vscode/mcp.json`:

```json
{
    "servers": {
        "playwright-container": {
            "url": "http://172.17.0.1:8765/mcp",
            "type": "http"
        }
    },
    "inputs": []
}
```

**Network address options**:
- `http://172.17.0.1:8765/mcp` - Docker bridge IP (works from host and other containers)
- `http://localhost:8765/mcp` - Only works if running VS Code on the host
- `http://playwright:8765/mcp` - Only works if both containers share a custom Docker network

### 4. Verify Connectivity

```bash
# From inside devcontainer
curl -v http://172.17.0.1:8765/mcp

# Or test from host
curl -v http://localhost:8765/mcp
```

**Expected response**: JSON with MCP protocol information or a proper HTTP error (not connection refused).

## Troubleshooting

### Error: "Connection state: Error - fetch failed"

**Symptoms**:
```
2025-11-22 19:57:10.149 [info] Connection state: Error Error sending message to http://172.17.0.1:8765/mcp: TypeError: fetch failed
```

**Causes & Solutions**:

1. **Container not running**:
   ```bash
   docker ps | grep playwright
   # If not running: docker compose up -d
   ```

2. **Port not exposed**:
   ```bash
   docker ps | grep playwright
   # Should show: 0.0.0.0:8765->8765/tcp
   # If not: check docker-compose.yml ports section
   ```

3. **Wrong network configuration**:
   - If devcontainer is on a custom network, playwright must be on the same network
   - Check: `docker network inspect <network-name>`
   - Fix: Add to docker-compose.yml:
     ```yaml
     networks:
       naf-local:
         external: true
     ```

4. **Firewall blocking**:
   ```bash
   # Check if port is listening
   netstat -tlnp | grep 8765
   # Or
   ss -tlnp | grep 8765
   ```

5. **Service not started inside container**:
   ```bash
   docker exec playwright ps aux | grep python
   # Should show the MCP server process
   
   # Check logs
   docker logs playwright
   ```

### Error: "FUSE device not found"

**Symptoms**:
```bash
sshfs: fuse: device not found, try 'modprobe fuse' first
```

**Solution**: Install FUSE on the Docker host (see step 1 above). The devcontainer cannot load kernel modules; this must be done on the host.

### Playwright Container Doesn't Respond

```bash
# Check if service is listening
docker exec playwright netstat -tlnp

# Check logs for errors
docker logs playwright --tail 50

# Restart container
docker restart playwright

# Rebuild if needed
cd tooling/playwright
docker compose build
docker compose up -d
```

## Testing the Setup

### 1. Quick Connectivity Test

```bash
# Test Playwright container readiness
docker exec playwright python3 -c "from playwright.async_api import async_playwright; print('OK')"

# Expected: "OK" output
```

### 2. Full WebSocket Test

```bash
cd /workspaces/netcup-api-filter
python3 tooling/validate-playwright-websocket.py
```

### 3. MCP from VS Code

1. Open Copilot Chat
2. Try a command like: `@playwright navigate to https://example.com`
3. Check the OUTPUT panel → "GitHub Copilot Chat - MCP" for connection logs

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_HTTP_PORT` | `8765` | MCP server HTTP port |
| `MCP_WS_PORT` | `3000` | WebSocket port for full Playwright API |
| `PLAYWRIGHT_HEADLESS` | `false` | Run browser headless |
| `PLAYWRIGHT_START_URL` | `http://172.17.0.1:8000/admin/login` | Initial page |

### Docker Network Modes

- **bridge** (default): Containers isolated, use `172.17.0.1` to reach host
- **host**: Container shares host network, use `localhost`
- **custom**: Join devcontainer network for direct container-to-container communication

## Additional Resources

- [Playwright README](tooling/playwright/README.md) - Detailed usage guide
- [UI Testing Guide](UI_GUIDE.md) - Integration with test suite
- [Docker networking docs](https://docs.docker.com/network/) - Docker network concepts

## Common Workflows

### Normal Testing

```bash
# Fresh install with latest code (resets database)
./build-and-deploy.sh

# Run tests inside Playwright container
cd tooling/playwright
docker compose up -d
docker exec playwright pytest /workspace/ui_tests/tests -v
```

### MCP-Assisted Debugging (Optional)

```bash
# Start playwright with MCP enabled
cd tooling/playwright
MCP_ENABLED=true docker compose up -d

# Access via SSH tunnel (port 8765 not exposed publicly)
ssh -L 8765:localhost:8765 user@your-server.com -N

# Use Copilot Chat for interactive debugging
# @playwright navigate to https://naf.vxxu.de/admin/login
# @playwright fill #username with admin
# @playwright screenshot
```

### Mounting Remote Filesystem (sshfs)

**Note**: Requires FUSE on Docker host!

```bash
# Inside devcontainer
mkdir -p /tmp/remote-webspace
sshfs -o StrictHostKeyChecking=no \
  user@host:/path/to/dir \
  /tmp/remote-webspace

# Access files
ls /tmp/remote-webspace

# Unmount when done
fusermount -u /tmp/remote-webspace
```
