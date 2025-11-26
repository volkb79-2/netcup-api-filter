# Network Configuration Consolidation

## Changes Summary

Consolidated Docker network configuration to use **single source of truth**: `DOCKER_NETWORK_INTERNAL` from `global-config.active.toml`.

## What Changed

### Removed: `SHARED_DOCKER_NETWORK`
- ❌ Was a duplicate/redundant variable
- ❌ Hardcoded default: `naf-local`
- ❌ Not synced with TOML configuration

### Kept: `DOCKER_NETWORK_INTERNAL`
- ✅ Already exists in code since beginning
- ✅ Read from `global-config.active.toml`
- ✅ Properly templated with Jinja2
- ✅ Exported to `.env.workspace` by `post-create.sh`

## Network Name Resolution

### From TOML Config

**File**: `global-config.active.toml`
```toml
[deployment]
project_name = "naf"
environment_tag = "dev"
docker_network_name_template = "{{deployment.project_name}}-{{deployment.environment_tag}}-network"
```

**Result**: `naf-dev-network`

### Code Path

```bash
# 1. post-create.sh reads global-config.active.toml
python3 -c "
import tomllib
from jinja2 import Template

with open('global-config.active.toml', 'rb') as f:
    config = tomllib.load(f)

deployment = config.get('deployment', {})
network_template = deployment.get('docker_network_name_template')

if '{{' in network_template:
    template = Template(network_template)
    result = template.render(deployment=deployment)
    print(result)  # → naf-dev-network
"

# 2. Exports to environment
export DOCKER_NETWORK_INTERNAL="naf-dev-network"

# 3. Writes to .env.workspace
echo 'export DOCKER_NETWORK_INTERNAL="naf-dev-network"' >> .env.workspace

# 4. Scripts load from .env.workspace
source .env.workspace
docker compose up  # → uses ${DOCKER_NETWORK_INTERNAL:-naf-dev-network}
```

## Files Updated

### Configuration Files
- ✅ `tooling/playwright/docker-compose.yml` → `${DOCKER_NETWORK_INTERNAL:-naf-dev-network}`
- ✅ `.devcontainer/post-create.sh` → comments updated
- ✅ `.vscode/ensure-mcp-connection.sh` → `${DOCKER_NETWORK_INTERNAL:-naf-dev-network}`
- ✅ `tooling/playwright/start-mcp.sh` → `${DOCKER_NETWORK_INTERNAL:-naf-dev-network}`

### Documentation Files
- ✅ `ENV_WORKSPACE.md` → all references updated
- ✅ `MCP_FUSE_SETUP.md` → network explanation updated
- ✅ `DOCKER_NETWORKS.md` → examples use DOCKER_NETWORK_INTERNAL
- ❌ `SHARED_NETWORK.md` → **DELETED** (outdated)

### Removed Files
- ❌ `SHARED_NETWORK.md` (replaced by DOCKER_NETWORKS.md)
- ❌ `demo-env-inheritance.sh` (temporary test script)
- ❌ `test-env-availability.sh` (temporary test script)

## Why This is Better

### Before (with SHARED_DOCKER_NETWORK)
```bash
# Two separate configurations:
1. TOML config: docker_network_name_template = "..."
2. Hardcoded: SHARED_DOCKER_NETWORK=naf-local

# Problems:
- Duplicate configuration
- Can get out of sync
- Ignores TOML-based naming
```

### After (with DOCKER_NETWORK_INTERNAL)
```bash
# Single source of truth:
TOML config → Python parsing → DOCKER_NETWORK_INTERNAL → All scripts

# Benefits:
- One configuration source
- Always in sync
- Respects project naming from TOML
```

## Migration Guide

### For Scripts

**Before**:
```bash
export SHARED_DOCKER_NETWORK="${SHARED_DOCKER_NETWORK:-naf-local}"
```

**After**:
```bash
export DOCKER_NETWORK_INTERNAL="${DOCKER_NETWORK_INTERNAL:-naf-dev-network}"
```

### For Docker Compose

**Before**:
```yaml
networks:
  default:
    name: ${SHARED_DOCKER_NETWORK:-naf-local}
```

**After**:
```yaml
networks:
  default:
    name: ${DOCKER_NETWORK_INTERNAL:-naf-dev-network}
```

### For Documentation

**Before**:
> "Network name is set by SHARED_DOCKER_NETWORK (default: naf-local)"

**After**:
> "Network name is read from global-config.active.toml via DOCKER_NETWORK_INTERNAL (default: naf-dev-network)"

## Testing

### Verify Network Name

```bash
# Check .env.workspace
grep DOCKER_NETWORK_INTERNAL /workspaces/netcup-api-filter/.env.workspace
# Expected: export DOCKER_NETWORK_INTERNAL="naf-dev-network"

# Check actual network
docker network ls | grep naf
# Expected: naf-dev-network   bridge    local
```

### Test Connectivity

```bash
# Ensure devcontainer connected
bash .vscode/ensure-mcp-connection.sh
# Expected: ✅ Already connected to naf-dev-network

# Start Playwright with MCP
cd tooling/playwright
MCP_ENABLED=true ./start-mcp.sh
# Expected: Network: naf-dev-network

# Test MCP access
curl http://playwright:8765/mcp
# Expected: {"protocol":"MCP","version":"1.0",...}
```

## Benefits

1. **Single Source of Truth**: Network name comes from TOML config only
2. **Consistent Naming**: Uses project's naming convention (project-env-network)
3. **No Duplication**: Removed redundant SHARED_DOCKER_NETWORK variable
4. **Proper Templating**: Leverages Jinja2 templates from TOML config
5. **Already Implemented**: DOCKER_NETWORK_INTERNAL existed, just cleaned up docs

## Related Documentation

- `ENV_WORKSPACE.md` - Explains why .env.workspace is needed
- `DOCKER_NETWORKS.md` - Comprehensive Docker networking guide
- `MCP_FUSE_SETUP.md` - MCP server and FUSE setup
- `global-config.active.toml` - Source of network name configuration
