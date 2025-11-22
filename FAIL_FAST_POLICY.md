# Fail-Fast Policy

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
```

**After (fail-fast):**
```python
def get_required_config(key):
    value = os.environ.get(key)
    if not value:
        raise ValueError(f"{key} must be set")
    return value

DATABASE_PATH = get_required_config('DATABASE_PATH')
```

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

### Scripts (Completed)
- ✅ `.vscode/deploy-test-fix-loop.sh` - Added prerequisite checks, removed MAX_ITERATIONS
- ✅ `.vscode/copilot-cmd.sh` - No PLAN_FILE default
- ✅ `.vscode/ensure-mcp-connection.sh` - NETWORK required
- ✅ `tooling/start-ui-stack.sh` - All config required
- ✅ `tooling/run-ui-validation.sh` - All test vars required
- ✅ `tooling/local_proxy/_proxy_lib.sh` - Function params required

### Config Files (Completed)
- ✅ `tooling/playwright/docker-compose.yml` - All env vars required
- ✅ `tooling/local_proxy/docker-compose.yml` - All vars required

### Still Using Defaults (Acceptable)
- `global-config.defaults.toml` - Template file (not executed)
- `config.example.yaml` - Example file (not executed)

## See Also

- `AGENTS.md` - Agent workflow and safe command patterns
- `.vscode/deploy-test-fix-loop.sh` - Reference implementation
- `DOCKER_NETWORKS.md` - Network configuration best practices
- `ENV_WORKSPACE.md` - Environment variable management
