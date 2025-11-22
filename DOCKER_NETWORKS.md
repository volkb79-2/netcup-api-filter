# Docker Network Types - Explained

## Overview

Docker provides multiple network drivers, each with different characteristics for container connectivity, DNS resolution, and accessibility.

## Network Drivers

### 1. Bridge (Default)

**Type**: Software-defined network on the host

**Characteristics**:
- ✅ Isolated from host network
- ✅ Container-to-container communication within same bridge
- ✅ Automatic DNS resolution between containers (by container name)
- ✅ Port mapping to host required for external access
- ❌ Cannot access containers directly from host without port mapping

**IP Address Assignment**:
- Docker assigns subnet (e.g., `172.18.0.0/16`)
- Each container gets unique IP (e.g., `172.18.0.2`, `172.18.0.3`)
- IP addresses are **dynamic** - don't rely on them

**DNS Resolution**:
```bash
# Inside container A on bridge network 'mynet'
curl http://container-b:8080/health
# ✓ Works - Docker DNS resolves 'container-b' to its IP
```

**External Access (Port Mapping)**:
```yaml
# Option 1: Expose publicly (INSECURE)
ports:
  - "8080:80"  # Binds to 0.0.0.0:8080 → accessible from anywhere

# Option 2: Expose to localhost only (more secure)
ports:
  - "127.0.0.1:8080:80"  # Only accessible from host machine

# Option 3: NO port mapping (most secure)
# No ports directive → only accessible within Docker network
```

**Use Case**: **Our setup** - `naf-dev-network` bridge network
- Devcontainer + Playwright on same bridge network
- Playwright accessible by name: `http://playwright:8765`
- **NO port exposure** → MCP server private (secure)

### 2. Host

**Type**: Container uses host's network stack directly

**Characteristics**:
- ✅ No network isolation - container sees host network
- ✅ No port mapping needed - direct host port access
- ✅ Better performance (no NAT overhead)
- ❌ Port conflicts possible
- ❌ Less secure - container has full host network access

**IP Address Assignment**:
- Container uses **host's IP addresses**
- No separate container IP

**DNS Resolution**:
- Uses host's DNS configuration (`/etc/resolv.conf`)
- No Docker DNS - can't resolve other containers by name

**External Access**:
```yaml
network_mode: host
# Container port 80 is directly on host port 80
# No port mapping needed or possible
```

**Use Case**: High-performance network I/O, monitoring tools
- Example: `docker run --network host nginx`
- Nginx listens on host's port 80 directly

### 3. None

**Type**: No networking

**Characteristics**:
- ❌ No network interfaces (except loopback)
- ❌ Complete network isolation
- ✅ Maximum security for offline workloads

**Use Case**: Batch processing, data transformation without network

### 4. Overlay

**Type**: Multi-host network for Docker Swarm

**Characteristics**:
- ✅ Spans multiple Docker hosts
- ✅ Container communication across hosts
- ✅ Encrypted traffic between hosts
- 🔧 Requires Docker Swarm mode

**IP Address Assignment**:
- Uses VXLAN tunneling
- Each container gets IP from overlay subnet

**DNS Resolution**:
- Swarm provides DNS for service discovery
- Service name resolves to all replicas (load balanced)

**Use Case**: Multi-host container orchestration (alternative to Kubernetes)

### 5. Macvlan

**Type**: Assign MAC address to container

**Characteristics**:
- ✅ Container appears as physical device on network
- ✅ Direct access to physical network
- ✅ Useful for legacy apps expecting physical network
- 🔧 Requires promiscuous mode on host interface
- ❌ Complex configuration

**IP Address Assignment**:
- Container gets IP from physical network DHCP
- Or assign static IP from physical subnet

**Use Case**: Network appliances, VMs replacement

## Our Configuration: Bridge Network

### Network: `naf-dev-network` (Bridge Driver)

```yaml
# tooling/playwright/docker-compose.yml
networks:
  default:
    name: ${DOCKER_NETWORK_INTERNAL:-naf-dev-network}
    driver: bridge
```

Network name is read from `global-config.active.toml` by `.devcontainer/post-create.sh`.

### Architecture

```
Physical Host (e.g., 192.168.1.100)
│
├─ docker0 bridge (172.17.0.1)        ← Default Docker bridge
│  └─ [Other containers]
│
└─ naf-dev-network bridge (172.18.0.1)  ← Our custom bridge from TOML config
   ├─ devcontainer (172.18.0.2)       ← Auto-assigned IP
   │  └─ Can access: playwright:8765, 172.18.0.3:8765
   │
   └─ playwright (172.18.0.3)         ← Auto-assigned IP
      └─ Port 8765 exposed → 172.17.0.1:8765 (Docker host IP)
```

### DNS Resolution

**Within `naf-dev-network` network**:
```bash
# From devcontainer
curl http://playwright:8765/mcp
# ✓ Works - Docker DNS resolves 'playwright' → 172.18.0.3

# From playwright container
curl http://devcontainer-name:8080
# ✓ Works - Docker DNS resolves container name → 172.18.0.2
```

**From host or outside bridge**:
```bash
# From host machine
curl http://playwright:8765
# ✗ Fails - no DNS resolution outside Docker network

curl http://172.18.0.3:8765
# ✗ Fails - bridge network is isolated

curl http://172.17.0.1:8765
# ✓ Works - port exposed via docker0 bridge
```

### IP Address Details

| Component | IP Address | Notes |
|-----------|-----------|-------|
| Docker Host | `172.17.0.1` (docker0) | Gateway for default bridge |
| Docker Host | `172.18.0.1` (naf-dev-network) | Gateway for our bridge (from TOML config) |
| Devcontainer | `172.18.0.2` | Dynamic, assigned by Docker |
| Playwright | `172.18.0.3` | Dynamic, assigned by Docker |

**⚠️ Warning**: Container IPs are **not stable**. Use container names, not IPs.

### Port Accessibility Matrix

| From | To | URL | Works? | Why |
|------|-----|-----|--------|-----|
| Devcontainer | Playwright | `http://playwright:8765` | ✅ | Same bridge, DNS works |
| Devcontainer | Playwright | `http://172.18.0.3:8765` | ✅ | Same bridge, direct IP (don't rely on this) |
| VS Code Server (in devcontainer) | Playwright | `http://playwright:8765` | ✅ | Same network, DNS works |
| Devcontainer | Localhost | `http://127.0.0.1:8765` | ❌ | Refers to devcontainer's own localhost |
| Host Machine | Playwright | `http://localhost:8765` | ❌ | No port mapping (secure) |
| Host Machine | Playwright | `http://playwright:8765` | ❌ | No DNS outside Docker |
| External Network | Playwright | `http://host-ip:8765` | ❌ | No port mapping (secure) |

**Note**: Our setup uses NO port mapping for security. MCP server is only accessible within Docker network.

## Docker Compose: `external: true` vs Regular Networks

### Regular Network (Default)
```yaml
networks:
  mynet:
    name: mynetwork
    driver: bridge
```
- Docker Compose **creates** the network if it doesn't exist
- Docker Compose **owns** the network
- `docker compose down` **removes** the network
- ⚠️ If network already exists: **conflict/error**

### External Network (`external: true`)
```yaml
networks:
  mynet:
    name: mynetwork
    external: true
```
- Docker Compose **connects to existing** network
- Docker Compose **does not own** the network
- `docker compose down` **leaves network intact**
- ✅ Network can be shared across multiple compose projects
- ✅ Network can be created by external scripts (e.g., post-create.sh)

### When to Use `external: true`

✅ **Use external:true when:**
- Network is created by another process (devcontainer post-create.sh)
- Network needs to persist across compose projects
- Multiple compose files share the same network
- Network lifecycle managed externally

❌ **Don't use external:true when:**
- This compose file should create/manage the network
- Network is only used by this compose project
- You want `docker compose down` to clean up everything

### Example: Our MCP Setup

```yaml
# tooling/playwright/docker-compose.yml
networks:
  default:
    name: ${DOCKER_NETWORK_INTERNAL:-naf-dev-network}
    external: true  # Network created by .devcontainer/post-create.sh
```

**Why external:true here?**
1. `.devcontainer/post-create.sh` creates `naf-dev-network` on startup
2. Devcontainer auto-connects to `naf-dev-network`
3. Playwright needs to join the **same** network
4. `docker compose down` shouldn't destroy network (devcontainer still needs it)

## Why Bridge Network for Our Use Case?

### Requirements
1. ✅ Devcontainer must access Playwright by name
2. ✅ VS Code (inside devcontainer) must access MCP server
3. ✅ Isolation from other Docker networks
4. ✅ Controlled external access (only expose needed ports)

### Why Not Other Drivers?

**Host Network**:
- ❌ No isolation - all ports conflict with host
- ❌ No DNS resolution between containers
- ❌ Less secure

**None**:
- ❌ No network access at all
- ❌ Can't communicate between containers

**Overlay**:
- ❌ Overkill - we're on single host
- ❌ Requires Docker Swarm

**Macvlan**:
- ❌ Too complex for our needs
- ❌ Requires physical network configuration

### Bridge Advantages for Us

✅ **DNS Resolution**: Access Playwright by name (`playwright:8765`)  
✅ **Isolation**: Our containers on private network  
✅ **Controlled Exposure**: Only expose MCP port (8765) to host  
✅ **Standard**: Works on all Docker installations  
✅ **Simple**: No special configuration needed  

## Network Configuration Best Practices

### 1. Use Named Networks

❌ **Bad** (Default network):
```yaml
services:
  app:
    image: myapp
# Uses default bridge - no custom DNS
```

✅ **Good** (Custom bridge):
```yaml
services:
  app:
    image: myapp
    networks:
      - mynet

networks:
  mynet:
    name: my-custom-network
    driver: bridge
```

### 2. Don't Rely on IP Addresses

❌ **Bad**:
```bash
curl http://172.18.0.3:8080
```

✅ **Good**:
```bash
curl http://playwright:8080
```

### 3. Minimize Port Exposure (Security)

❌ **Bad** (Public exposure):
```yaml
ports:
  - "8765:8765"  # Binds to 0.0.0.0 - accessible from anywhere!
```

⚠️ **Better** (Localhost only):
```yaml
ports:
  - "127.0.0.1:8765:8765"  # Only accessible from host machine
```

✅ **Best** (No exposure - network only):
```yaml
# No ports directive at all
# Containers communicate via Docker network only
# Most secure - not accessible outside network
```

### 4. Use `external: true` for Existing Networks

❌ **Bad** (Creates new network):
```yaml
networks:
  mynet:
    name: existing-network  # Tries to create, may conflict
```

✅ **Good** (Uses existing network):
```yaml
networks:
  mynet:
    name: existing-network
    external: true  # Connects to existing network
```

### 5. Use Environment Variables for Network Names

❌ **Bad** (Hardcoded):
```yaml
networks:
  default:
    name: mynetwork
```

✅ **Good** (Configurable):
```yaml
networks:
  default:
    name: ${DOCKER_NETWORK_INTERNAL:-mynetwork}
    external: true  # Use existing network from post-create.sh
```

## Debugging Network Issues

### Check Container Network

```bash
# Show all networks
docker network ls

# Inspect specific network
docker network inspect naf-local

# See which containers are connected
docker network inspect naf-local --format '{{range .Containers}}{{.Name}} {{end}}'
```

### Check Container IP

```bash
# Get container IP
docker inspect playwright --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'

# Get all IPs (if multiple networks)
docker inspect playwright --format '{{json .NetworkSettings.Networks}}' | jq
```

### Test Connectivity

```bash
# From devcontainer
docker exec devcontainer ping playwright
docker exec devcontainer curl http://playwright:8765/mcp

# Check DNS resolution
docker exec devcontainer nslookup playwright
docker exec devcontainer getent hosts playwright
```

### Check Port Exposure

```bash
# List exposed ports
docker port playwright

# Should show: 8765/tcp -> 0.0.0.0:8765

# Test from host
curl http://localhost:8765/mcp
curl http://172.17.0.1:8765/mcp
```

## Common Issues

### "Could not resolve host: playwright"

**Cause**: Containers not on same custom bridge network

**Solution**:
```bash
# Connect devcontainer to network
docker network connect naf-local devcontainer-name

# Or use ensure-mcp-connection.sh
bash .vscode/ensure-mcp-connection.sh
```

### "Connection refused to 127.0.0.1:8765"

**Cause**: `127.0.0.1` refers to container's own localhost, not Docker host

**Solution**:
```bash
# Use Docker host IP instead
curl http://172.17.0.1:8765
```

### "No route to host"

**Cause**: Trying to access container IP from outside bridge network

**Solution**:
```bash
# Use exposed port on Docker host
curl http://172.17.0.1:8765

# Or connect your container to the same network
docker network connect naf-local my-container
```

## Summary

| Feature | Bridge | Host | None | Overlay | Macvlan |
|---------|--------|------|------|---------|---------|
| **Isolation** | ✅ Yes | ❌ No | ✅ Complete | ✅ Yes | ✅ Yes |
| **DNS** | ✅ Container names | ❌ Host DNS only | ❌ No network | ✅ Service names | ⚠️ External only |
| **Port Mapping** | ✅ Needed | ❌ Direct | ❌ N/A | ✅ Needed | ❌ Direct |
| **Performance** | ⚠️ Good | ✅ Best | N/A | ⚠️ Good | ✅ Best |
| **Multi-host** | ❌ No | ❌ No | N/A | ✅ Yes | ⚠️ Complex |
| **Use Case** | Default, most apps | Network perf tools | Offline batch | Swarm/k8s | Legacy apps |

**Our choice**: **Bridge** (`naf-local`) - Perfect balance of isolation, DNS, and simplicity.
