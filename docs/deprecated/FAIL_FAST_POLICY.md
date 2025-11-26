# Fail-Fast Policy

> **Status:** Archived reference. Use `CONFIGURATION_GUIDE.md` for the current fail-fast requirements and workflow.

## Overview

**This project enforces a strict FAIL-FAST policy**: Missing configuration causes immediate errors instead of falling back to defaults. This surfaces configuration issues early and ensures reproducible deployments.

## Rationale

### ❌ Problems with Defaults

```bash
# BAD: Silent fallback hides misconfiguration
PORT="${PORT:-8000}"  # Silently uses 8000 if PORT unset
docker run -p ${PORT}:8000 myapp  # Might bind wrong port
```

**Issues:**
- Configuration errors go unnoticed
- Different environments have different behaviors
- Debugging is harder (which default was used?)
- Tests pass locally but fail in production

### ✅ Benefits of Fail-Fast

```bash
# GOOD: Explicit requirement surfaces issues immediately
PORT="${PORT:?PORT must be set}"
docker run -p ${PORT}:8000 myapp  # Fails fast with clear error
```

**Benefits:**
- Configuration problems detected immediately
- Same behavior across all environments
- Clear error messages guide fixes
- Prevents silent misconfigurations

## Implementation

### Shell Scripts

**Before (with defaults):**
```bash
DATABASE_PATH="${DATABASE_PATH:-/tmp/default.db}"
NETWORK="${NETWORK:-mynetwork}"
PORT="${PORT:-8000}"
```

**After (fail-fast):**
```bash
DATABASE_PATH="${DATABASE_PATH:?DATABASE_PATH must be set}"
NETWORK="${NETWORK:?NETWORK must be set (source .env.workspace)}"
PORT="${PORT:?PORT must be set}"
```

### Docker Compose

**Before (with defaults):**
```yaml
environment:
  DOCKER_UID: "${DOCKER_UID:-1000}"
  MCP_ENABLED: "${MCP_ENABLED:-false}"

volumes:
  - ${REPO_ROOT:-/workspaces/project}:/workspace

networks:
  default:
    name: ${NETWORK:-mynetwork}
```

**After (fail-fast):**
```yaml
environment:
  DOCKER_UID: "${DOCKER_UID:?DOCKER_UID must be set}"
  MCP_ENABLED: "${MCP_ENABLED:?MCP_ENABLED must be set (true or false)}"

volumes:
  - ${REPO_ROOT:?REPO_ROOT must be set}:/workspace

networks:
  default:
    name: ${NETWORK:?NETWORK must be set (source .env.workspace)}
```

### Python Config

**Before (with defaults):**
```python
def get_config(key, default=None):
    return os.environ.get(key, default)

DATABASE_PATH = get_config('DATABASE_PATH', '/tmp/default.db')
config_path = os.environ.get("CONFIG_FILE", "config.yaml")  # Silent default ❌
```

**After (fail-fast):**
```python
def get_required_config(key, hint=None):
    """Get required config value or raise clear error."""
    value = os.environ.get(key)
    if not value:
        hint_text = f" ({hint})" if hint else ""
        raise ValueError(f"{key} must be set{hint_text}")
    return value

DATABASE_PATH = get_required_config('DATABASE_PATH')

# For values that have documented defaults, warn loudly
config_path = os.environ.get("CONFIG_FILE")
if not config_path:
    config_path = "config.yaml"
    print(f"[CONFIG] WARNING: CONFIG_FILE not set, using documented default: {config_path}", file=sys.stderr)
    print(f"[CONFIG] Set explicitly: export CONFIG_FILE=path/to/config.yaml", file=sys.stderr)
```

#### Python Path Resolution (CRITICAL)

**❌ FORBIDDEN - Hardcoded Absolute Paths:**
```python
# These violate portability and fail-fast policy
env_local_path = Path("/workspaces/netcup-api-filter/.env.local")
screenshot_dir = "/workspaces/netcup-api-filter/tmp/screenshots"
workspace_root = "/workspaces/netcup-api-filter"
```

**✅ CORRECT - Environment-Driven Paths:**
```python
import os
import sys
from pathlib import Path

# Require REPO_ROOT from environment (set by .env.workspace)
repo_root = os.environ.get('REPO_ROOT')
if not repo_root:
    # Only allow calculated fallback with loud warning
    repo_root = os.path.dirname(os.path.dirname(__file__))
    print(f"[CONFIG] WARNING: REPO_ROOT not set, calculated: {repo_root}", file=sys.stderr)
    print(f"[CONFIG] Set explicitly: export REPO_ROOT=/path/to/repo", file=sys.stderr)

# Build relative paths
env_local_path = Path(repo_root) / ".env.local"
screenshot_dir = Path(repo_root) / "tmp" / "screenshots"

# For critical paths, fail if environment variable missing
screenshot_dir = os.environ.get('SCREENSHOT_DIR')
if not screenshot_dir:
    raise RuntimeError(
        "SCREENSHOT_DIR must be set. "
        "Export SCREENSHOT_DIR=/path/to/screenshots or source .env.workspace"
    )
```

#### Files Updated for Python Fail-Fast

**Core Application:**
- ✅ `wsgi.py` - Config path with WARNING on default
- ✅ `cgi_handler.py` - Config path with WARNING + error handling

**Testing Infrastructure:**
- ✅ `ui_tests/config.py` - Credentials require .env.defaults, test settings warn on defaults
- ✅ `ui_tests/workflows.py` - REPO_ROOT required with warning fallback
- ✅ `ui_tests/browser.py` - SCREENSHOT_DIR required, no silent getcwd() fallback
- ✅ `ui_tests/playwright_client.py` - PLAYWRIGHT_HEADLESS warns on default
- ✅ `capture_ui_screenshots.py` - REPO_ROOT required, deployment env file with warnings

**Tooling (Development utilities - defaults acceptable):**
- `tooling/local_proxy/local_app.py` - Local dev defaults (LOCAL_ADMIN_PASSWORD, etc.)
- `tooling/playwright/mcp_server.py` - MCP server defaults (port 8765, chromium, etc.)

**Key Principle**: Core application and testing code must fail-fast. Development tooling may have sensible defaults if clearly documented.

## Configuration Sources

### 1. `.env.workspace`
Created by `.devcontainer/post-create.sh`, contains environment-specific values:

```bash
ENV_TYPE=devcontainer
USER_UID=1000
DOCKER_GID=999
PHYSICAL_REPO_ROOT=/home/user/repos/netcup-api-filter
DOCKER_NETWORK_INTERNAL=naf-dev-network
```

**Usage:**
```bash
# Source before running commands
source .env.workspace
./tooling/start-ui-stack.sh
```

### 2. `global-config.active.toml`
Single source of truth for project configuration:

```toml
[deployment]
project_name = "naf"
environment_tag = "dev"
docker_network_name_template = "{{deployment.project_name}}-{{deployment.environment_tag}}-network"
log_level = "DEBUG"
```

### 3. Script-Specific `.env` Files
Example: `tooling/local_proxy/proxy.env`

```bash
LOCAL_TLS_DOMAIN=naf.localtest.me
LOCAL_APP_HOST=host.docker.internal
LOCAL_APP_PORT=5100
LE_CERT_BASE=/etc/letsencrypt
```

## Error Messages

Clear error messages guide users to the fix:

```bash
# ❌ Vague error
bash: NETWORK: unbound variable

# ✅ Helpful error
NETWORK: NETWORK must be set (source .env.workspace)
```

**Message format:**
```bash
VARIABLE_NAME: <what went wrong> (<how to fix>)
```

**Examples:**
```bash
DOCKER_UID:?DOCKER_UID must be set
PORT:?PORT must be set (usually 8000)
DATABASE_PATH:?DATABASE_PATH must be set (e.g., /tmp/test.db)
NETWORK:?NETWORK must be set (source .env.workspace)
```

## Migration Checklist

When removing a default:

- [ ] Identify all scripts/configs using this variable
- [ ] Change `${VAR:-default}` to `${VAR:?VAR must be set (hint)}`
- [ ] Update documentation with required variables
- [ ] Add prerequisite check if applicable
- [ ] Test that error message is clear
- [ ] Update related scripts to export the variable

## Common Patterns

### Optional vs Required

```bash
# Required - fail if not set
PORT="${PORT:?PORT must be set}"

# Optional with explicit check
if [[ -n "${DEBUG:-}" ]]; then
    set -x  # Enable debugging
fi
```

### Computed Defaults (Acceptable)

```bash
# Detect network from environment (fail if detection fails)
if [[ -z "${HOST_GATEWAY_IP:-}" ]]; then
    HOST_GATEWAY_IP="$(ip route | awk '/default/ {print $3; exit}')"
fi
if [[ -z "$HOST_GATEWAY_IP" ]]; then
    echo "ERROR: HOST_GATEWAY_IP cannot be determined" >&2
    exit 1
fi
```

### Function Parameters

```bash
# BAD: Silent defaults
function deploy() {
    local env="${1:-production}"
}

# GOOD: Explicit requirement
function deploy() {
    local env="${1:?env parameter required (staging|production)}"
}
```

## Prerequisites Checks

Scripts should verify prerequisites before execution:

```bash
check_prerequisites() {
    local all_good=true
    
    # Check required variables
    for var in NETWORK PORT DATABASE_PATH; do
        if [[ -z "${!var:-}" ]]; then
            echo "ERROR: $var not set" >&2
            all_good=false
        fi
    done
    
    # Check Docker
    if ! command -v docker &>/dev/null; then
        echo "ERROR: docker not found" >&2
        all_good=false
    fi
    
    # Check network exists
    if ! docker network inspect "$NETWORK" &>/dev/null; then
        echo "ERROR: network '$NETWORK' does not exist" >&2
        all_good=false
    fi
    
    if [[ "$all_good" == "false" ]]; then
        return 1
    fi
}
```

## Testing

### Unit Tests

```bash
#!/bin/bash
# test_fail_fast.sh

test_fails_without_required_var() {
    unset MY_VAR
    if ./my_script.sh 2>&1 | grep -q "MY_VAR must be set"; then
        echo "PASS: Script fails fast on missing MY_VAR"
    else
        echo "FAIL: Script should fail on missing MY_VAR"
        exit 1
    fi
}

test_succeeds_with_var() {
    export MY_VAR="value"
    if ./my_script.sh; then
        echo "PASS: Script succeeds with MY_VAR set"
    else
        echo "FAIL: Script should succeed with MY_VAR set"
        exit 1
    fi
}

test_fails_without_required_var
test_succeeds_with_var
```

## Agent Workflow

When agents encounter configuration errors:

1. **Read error message**: `NETWORK: NETWORK must be set (source .env.workspace)`
2. **Identify fix**: Need to source `.env.workspace`
3. **Apply fix**: Add `source .env.workspace` before command
4. **Re-run**: Script now has required configuration
5. **Iterate**: Repeat for any new errors

**Example:**
```bash
# Agent sees error:
$ ./deploy.sh
NETWORK: NETWORK must be set (source .env.workspace)

# Agent applies fix:
$ source .env.workspace && ./deploy.sh
# Success!
```

## Files Updated

### Shell Scripts (Completed)
- ✅ `.vscode/deploy-test-fix-loop.sh` - Added prerequisite checks, removed MAX_ITERATIONS
- ✅ `.vscode/copilot-cmd.sh` - No PLAN_FILE default
- ✅ `.vscode/ensure-mcp-connection.sh` - NETWORK required
- ✅ `tooling/start-ui-stack.sh` - All config required
- ✅ `tooling/run-ui-validation.sh` - All test vars required
- ✅ `tooling/local_proxy/_proxy_lib.sh` - Function params required
- ✅ `deployment-lib.sh` - Exports REPO_ROOT with fail-fast check

### Python Files (Completed)
- ✅ `wsgi.py` - Config path with WARNING on default
- ✅ `cgi_handler.py` - Config path with WARNING + error handling
- ✅ `ui_tests/config.py` - Removed hardcoded credential defaults, requires .env.defaults
- ✅ `ui_tests/workflows.py` - REPO_ROOT required with warning fallback
- ✅ `ui_tests/browser.py` - SCREENSHOT_DIR required, no silent getcwd() fallback
- ✅ `ui_tests/playwright_client.py` - PLAYWRIGHT_HEADLESS warns on default
- ✅ `capture_ui_screenshots.py` - REPO_ROOT required, deployment env with warnings

### Config Files (Completed)
- ✅ `tooling/playwright/docker-compose.yml` - All env vars required
- ✅ `tooling/local_proxy/docker-compose.yml` - All vars required

### Template Files (Defaults Acceptable)
- `global-config.defaults.toml` - Template file (not executed)
- `config.example.yaml` - Example file (not executed)
- `.env.defaults` - Default values file (documented source of truth)

### Development Tooling (Sensible Defaults Allowed)
- `tooling/local_proxy/local_app.py` - Local dev server with LOCAL_* defaults
- `tooling/playwright/mcp_server.py` - MCP server with port/browser defaults

## See Also

- `AGENTS.md` - Agent workflow and safe command patterns
- `.vscode/deploy-test-fix-loop.sh` - Reference implementation
- `DOCKER_NETWORKS.md` - Network configuration best practices
- `ENV_WORKSPACE.md` - Environment variable management
