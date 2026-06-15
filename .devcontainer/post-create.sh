#!/bin/bash
# ============================================================================
# Netcup API Filter — Devcontainer Post-Create Setup
# ============================================================================
# Runs after devcontainer is created to set up the development environment.
#
# Base image: ghcr.io/volkb79-2/modern-debian-tools-python-debug-vsc-devcontainer
# That image ships a modern Python (3.13+) and `uv`.  This script creates a
# project venv pinned to Python 3.11 (the production target) via uv so that
# unit-tests and the app run on the same interpreter as production.
#
# Philosophy:
# - Use uv for Python version management and venv creation (fast, reproducible)
# - Project venv at .venv/ (Python 3.11) — VS Code picks it up automatically
# - Fail-fast on critical steps; warn and continue on non-critical ones
# - Idempotent: safe to re-run after a rebuild
# ============================================================================

set -euo pipefail

# Colors for output
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

log_debug() {
    echo -e "${BLUE}[DEBUG]${NC} $*"
}

# Trap to catch any errors and provide debugging info.
# Defined AFTER log_* so the trap body can call log_error safely.
trap 'log_error "Script failed at line $LINENO with exit code $?"; log_error "Last command: $BASH_COMMAND"; exit 1' ERR

# ============================================================================
# ENVIRONMENT DETECTION (DYNAMIC)
# ============================================================================

detect_environment() {
    log_info "Detecting environment characteristics..."

    if [[ -n "${GITHUB_ACTIONS:-}" ]]; then
        ENV_TYPE="github_actions"
        log_debug "GITHUB_ACTIONS='${GITHUB_ACTIONS}' → GitHub Actions environment"
    elif [[ -f "/.dockerenv" ]] && [[ -n "${REMOTE_CONTAINERS:-}" ]]; then
        ENV_TYPE="devcontainer"
        log_debug "REMOTE_CONTAINERS='${REMOTE_CONTAINERS}' → Dev Container environment"
    else
        ENV_TYPE="local"
        log_debug "No special environment variables → Local environment"
    fi

    USER_NAME="$(whoami)"
    USER_UID="$(id -u)"
    USER_GID="$(id -g)"

    DOCKER_GID="$(getent group docker | cut -d: -f3 2>/dev/null || echo '118')"
    if [[ "$DOCKER_GID" == "118" ]] && ! getent group docker >/dev/null 2>&1; then
        log_warn "Docker group not found, using default GID 118"
    fi

    WORKSPACE_DIR="$(pwd)"
    if [[ ! -f "requirements-dev.txt" ]]; then
        log_error "Not in netcup-api-filter repository root (missing requirements-dev.txt)"
        exit 1
    fi

    export ENV_TYPE USER_NAME USER_UID USER_GID DOCKER_GID WORKSPACE_DIR

    log_debug "Environment: $ENV_TYPE"
    log_debug "User: $USER_NAME (UID=$USER_UID, GID=$USER_GID)"
    log_debug "Docker Group GID: $DOCKER_GID"
    log_debug "Workspace: $WORKSPACE_DIR"
}

# ============================================================================
# REPOSITORY PATH MANAGEMENT (CENTRALIZED)
# ============================================================================
# Sets canonical repository paths and writes .env.workspace so ALL downstream
# scripts (run-local-tests.sh, tooling/start-ui-stack.sh, tooling/flask-manager.sh,
# deploy.sh, build_deployment_lib.sh, .vscode/*.sh, etc.) have a consistent
# single source of truth — even when invoked outside this post-create context.

setup_repository_paths() {
    log_info "Setting up repository path management..."

    export REPO_ROOT="$WORKSPACE_DIR"

    # Detect the physical host path for Docker bind mounts.
    # This differs from REPO_ROOT when running inside a devcontainer where
    # the workspace is a bind mount from the host filesystem.
    detect_physical_repo_root() {
        # Priority 1: Manual override (for testing/debugging)
        if [[ -n "${PHYSICAL_REPO_ROOT:-}" ]]; then
            log_debug "Using manual PHYSICAL_REPO_ROOT override: $PHYSICAL_REPO_ROOT" >&2
            echo "$PHYSICAL_REPO_ROOT"
            return
        fi

        # Priority 2: devcontainer.local_folder label (VS Code devcontainer)
        local host_path
        host_path=$(docker ps --format '{{.ID}} {{.Label "devcontainer.local_folder"}}' 2>/dev/null \
            | awk '$2 != "" { print $2; exit }' | head -1)

        if [[ -n "$host_path" ]]; then
            log_debug "Detected via devcontainer.local_folder label: $host_path" >&2
            echo "$host_path"
            return
        fi

        # Priority 3: Fallback to workspace dir (bare metal, SSH, CI/CD)
        log_debug "No devcontainer label found, using workspace dir: $WORKSPACE_DIR" >&2
        echo "$WORKSPACE_DIR"
    }

    export PHYSICAL_REPO_ROOT
    PHYSICAL_REPO_ROOT="$(detect_physical_repo_root)"

    if [[ -z "$PHYSICAL_REPO_ROOT" ]]; then
        log_error "Failed to determine PHYSICAL_REPO_ROOT"
        log_error "Check Docker daemon access and devcontainer configuration"
        return 1
    fi

    # Write .env.workspace — the single source of truth consumed by all scripts.
    # WHY .env.workspace?
    # - Scripts run OUTSIDE post-create.sh context (deploy.sh, run-local-tests.sh, etc.)
    #   need these variables but don't have access to our current shell environment.
    # - New terminal sessions need these values before manual export.
    # - Sibling service containers (e.g. pwmcp-playwright) are reached by container
    #   name over the shared Docker network; DOCKER_NETWORK_INTERNAL carries that name.
    # - Provides a single source of truth for workspace configuration across all tools.
    cat > "$WORKSPACE_DIR/.env.workspace" << EOF
# ============================================================================
# Workspace Environment Configuration (Auto-generated)
# ============================================================================
# Generated by: .devcontainer/post-create.sh
# Purpose: Provides workspace variables to scripts running outside post-create.sh
#
# Used by:
#   - run-local-tests.sh        (REPO_ROOT, PHYSICAL_REPO_ROOT)
#   - tooling/start-ui-stack.sh (DOCKER_NETWORK_INTERNAL)
#   - tooling/flask-manager.sh  (REPO_ROOT, DOCKER_NETWORK_INTERNAL)
#   - deploy.sh                 (REPO_ROOT, PHYSICAL_REPO_ROOT, DOCKER_NETWORK_INTERNAL)
#   - build_deployment_lib.sh   (REPO_ROOT, PHYSICAL_REPO_ROOT)
#   - run-2fa-security-tests.sh (REPO_ROOT)
#   - .vscode/*.sh              (all workspace paths)
#
# Do not edit manually — regenerated on devcontainer rebuild.
# ============================================================================
export ENV_TYPE="$ENV_TYPE"
export USER_NAME="$USER_NAME"
export USER_UID="$USER_UID"
export USER_GID="$USER_GID"
export DOCKER_GID="$DOCKER_GID"
export REPO_ROOT="$REPO_ROOT"
export PHYSICAL_REPO_ROOT="$PHYSICAL_REPO_ROOT"

# Docker container user IDs (for services that need to run as the host user)
export DOCKER_UID="$USER_UID"
EOF

    # Also export REPO_ROOT / PHYSICAL_REPO_ROOT into future bash sessions
    if ! grep -q "PHYSICAL_REPO_ROOT" ~/.bashrc 2>/dev/null; then
        cat >> ~/.bashrc << EOF

# Netcup API Filter — Repository Paths (Auto-added by post-create.sh)
export REPO_ROOT="$REPO_ROOT"
export PHYSICAL_REPO_ROOT="$PHYSICAL_REPO_ROOT"
EOF
    fi

    log_success "Repository paths configured"
    log_debug "REPO_ROOT:          $REPO_ROOT"
    log_debug "PHYSICAL_REPO_ROOT: $PHYSICAL_REPO_ROOT"
    if [[ "$REPO_ROOT" != "$PHYSICAL_REPO_ROOT" ]]; then
        log_debug "Devcontainer environment detected (path mapping active)"
    fi
}

# ============================================================================
# NETWORK CONNECTIVITY (DEVCONTAINER ONLY)
# ============================================================================
# Creates the shared Docker network if absent and connects this devcontainer
# to it so that sibling service containers (e.g. the pwmcp-playwright service)
# are reachable by container name (e.g. ws://pwmcp-playwright:3000/).
#
# The network name is taken from the DOCKER_NETWORK_INTERNAL env var if already
# set (e.g. from a prior .env.workspace source), otherwise falls back to a
# sensible project-specific default.
#
# Appends DOCKER_NETWORK_INTERNAL (and DEVCONTAINER_NAME) to .env.workspace
# so every subsequent script that sources that file gets the right value.
#
# Failure is WARN-only (not fatal) so CI / bare-metal envs without a Docker
# socket don't break during a local run.

setup_network_connectivity() {
    if [[ "$ENV_TYPE" != "devcontainer" ]]; then
        log_debug "Skipping network setup (not devcontainer)"
        return 0
    fi

    log_info "Setting up network connectivity..."
    log_debug "Docker version: $(docker --version 2>&1 || echo 'Docker not available')"

    # Determine the shared network name.
    # Fall through in priority order: env var → project default.
    local network_name="${DOCKER_NETWORK_INTERNAL:-naf-dev-network}"
    log_debug "Network name: $network_name"

    # Create network if it doesn't exist yet
    if ! docker network inspect "$network_name" &>/dev/null; then
        log_info "Creating Docker network: $network_name"
        if ! docker network create "$network_name" 2>/dev/null; then
            log_warn "Failed to create Docker network '$network_name' — network connectivity may be unavailable"
            return 0
        fi
    else
        log_debug "Network $network_name already exists"
    fi

    # Detect this devcontainer's container name via its workspace volume mount
    local container_name
    container_name=$(docker ps --format '{{.Names}}' --filter volume="$WORKSPACE_DIR" 2>/dev/null | head -1)

    if [[ -z "$container_name" ]]; then
        log_warn "Could not detect devcontainer container name — skipping network join"
        log_warn "(Docker socket may not be available or volume path differs)"
        # Still write the network name to .env.workspace so scripts can use it
        cat >> "$WORKSPACE_DIR/.env.workspace" << EOF

# Docker network for reaching sibling service containers by name
export DOCKER_NETWORK_INTERNAL="$network_name"
EOF
        return 0
    fi

    log_debug "Devcontainer container: $container_name"
    export DEVCONTAINER_NAME="$container_name"

    # Connect to network (idempotent — ignore error if already connected)
    if docker network inspect "$network_name" \
            --format '{{range .Containers}}{{.Name}} {{end}}' 2>/dev/null \
            | grep -qw "$container_name"; then
        log_success "Devcontainer already connected to $network_name"
    else
        log_info "Connecting devcontainer ($container_name) to $network_name..."
        if docker network connect "$network_name" "$container_name" 2>/dev/null; then
            log_success "Devcontainer connected to $network_name"
        else
            log_warn "Failed to connect devcontainer to '$network_name' — sibling containers unreachable by name"
            log_warn "Check Docker daemon permissions; re-run post-create.sh to retry"
        fi
    fi

    export DOCKER_NETWORK_INTERNAL="$network_name"

    # Append to .env.workspace (setup_repository_paths must have run first)
    cat >> "$WORKSPACE_DIR/.env.workspace" << EOF

# Docker network for reaching sibling service containers by name
# e.g. ws://\${DEVCONTAINER_NAME}:3000/ or ws://pwmcp-playwright:3000/
export DOCKER_NETWORK_INTERNAL="$network_name"
export DEVCONTAINER_NAME="$DEVCONTAINER_NAME"
EOF
}

# ============================================================================
# PYTHON ENVIRONMENT SETUP — uv + Python 3.11 venv
# ============================================================================
# The base image provides a modern Python (3.13+) and uv.
# Production target is Python 3.11, so we pin the project venv to 3.11 via uv.
#
# Why uv?
#   uv python install 3.11  — downloads and caches CPython 3.11 if not present
#   uv venv --python 3.11   — creates .venv/ using that interpreter
#   uv pip install          — fast dependency resolution into the venv
#
# The resulting .venv/ is what VS Code's python.defaultInterpreterPath points at.

setup_python_environment() {
    log_info "Setting up Python 3.11 project venv via uv..."

    # Prefer uv (ships in the base image); fall back to system python3 with a warning.
    if command -v uv &>/dev/null; then
        log_debug "uv version: $(uv --version 2>&1)"

        # Ensure CPython 3.11 is available (uv downloads it if needed)
        log_info "Ensuring Python 3.11 is available via uv..."
        if ! uv python install 3.11; then
            log_error "uv python install 3.11 failed"
            return 1
        fi

        # Create (or refresh) the project venv at .venv/ pinned to 3.11
        log_info "Creating project venv at .venv/ (Python 3.11)..."
        if ! uv venv --python 3.11 .venv; then
            log_error "uv venv --python 3.11 .venv failed"
            return 1
        fi

        # Install dev dependencies into the venv via uv pip
        local requirements_file="$WORKSPACE_DIR/requirements-dev.txt"
        if [[ ! -f "$requirements_file" ]]; then
            log_error "requirements-dev.txt not found at $requirements_file"
            return 1
        fi
        log_info "Installing dev dependencies into .venv/ ..."
        if ! uv pip install --python .venv/bin/python -r "$requirements_file"; then
            log_error "uv pip install failed"
            return 1
        fi

        # UI tests requirements (optional — warn and continue if absent)
        local ui_req="$WORKSPACE_DIR/ui_tests/requirements.txt"
        if [[ -f "$ui_req" ]]; then
            log_info "Installing ui_tests requirements..."
            if ! uv pip install --python .venv/bin/python -r "$ui_req"; then
                log_warn "ui_tests/requirements.txt install failed (non-critical)"
            fi
        else
            log_debug "ui_tests/requirements.txt not found — skipping"
        fi

        log_success "Project venv ready: $(.venv/bin/python --version 2>&1)"

    else
        # Fallback: system python3 (may not be 3.11 on the modern base image)
        log_warn "uv not found — falling back to system python3 for venv creation"
        log_warn "NOTE: system python3 on this base image may NOT be 3.11; tests may diverge from production"

        local py_bin
        py_bin="$(command -v python3.11 || command -v python3 || echo '')"
        if [[ -z "$py_bin" ]]; then
            log_error "No python3 found; cannot create venv"
            return 1
        fi
        log_debug "Using $py_bin ($(${py_bin} --version 2>&1))"

        "$py_bin" -m venv .venv

        local requirements_file="$WORKSPACE_DIR/requirements-dev.txt"
        if [[ -f "$requirements_file" ]]; then
            .venv/bin/pip install --upgrade pip --quiet
            .venv/bin/pip install -r "$requirements_file" --quiet
        fi

        local ui_req="$WORKSPACE_DIR/ui_tests/requirements.txt"
        if [[ -f "$ui_req" ]]; then
            .venv/bin/pip install -r "$ui_req" --quiet || log_warn "ui_tests install failed (non-critical)"
        fi

        log_success "Fallback venv ready: $(.venv/bin/python --version 2>&1)"
    fi

    # Add venv activation hint to .bashrc (idempotent)
    if ! grep -q "netcup-api-filter venv" ~/.bashrc 2>/dev/null; then
        cat >> ~/.bashrc << 'EOF'

# netcup-api-filter venv — auto-activate when in the workspace
if [[ -f "${WORKSPACE_DIR:-/workspaces/netcup-api-filter}/.venv/bin/activate" ]]; then
    source "${WORKSPACE_DIR:-/workspaces/netcup-api-filter}/.venv/bin/activate"
fi
EOF
        log_debug "Added venv auto-activate to .bashrc"
    fi
}

# ============================================================================
# SSH KEYS AND ALIASES SETUP
# ============================================================================

setup_ssh_and_aliases() {
    log_info "Setting up SSH keys and bash aliases..."

    # Add custom aliases if not already present (check for marker comment)
    if ! grep -q "# Devcontainer Custom Aliases" ~/.bashrc 2>/dev/null; then
        cat >> ~/.bashrc << 'EOF'

# Devcontainer Custom Aliases (added by post-create.sh)

# File viewing and navigation
alias ll='ls -l'
alias la='ls -la'
alias lt='tree -L 2'                    # tree: 2-level directory view
alias ltt='tree -L 3'                   # tree: 3-level directory view
alias cat='bat --paging=never'          # bat: syntax-highlighted cat
alias less='bat --paging=always'        # bat: pager mode

# Search and find
alias grep='rg'                         # ripgrep: fast grep
alias find='fd'                         # fd: fast find
alias fdf='fdfind'                      # fd-find: Debian package name

# Process management
alias ps='htop'                         # htop: interactive process viewer
alias psg='ps aux | grep -i'           # search processes

# Network tools
alias myip='curl -s ifconfig.me'        # get public IP
alias listening='netstat -tuln | grep LISTEN'  # show listening ports
alias ports='ss -tuln'                  # show all ports

# DNS queries
alias dig-short='dig +short'            # dig: short output only
alias dig-trace='dig +trace'            # dig: full DNS trace
alias nsl='nslookup'                    # nslookup: shorthand

# HTTP clients
alias curl-json='curl -H "Content-Type: application/json"'  # JSON curl
alias curl-time='curl -w "\n\nTime: %{time_total}s\n"'    # curl with timing
alias GET='http GET'                    # httpie: GET request
alias POST='http POST'                  # httpie: POST request

# Git shortcuts (in addition to default)
alias gst='git status'                  # git: status
alias gd='git diff'                     # git: diff
alias glog='git log --oneline --graph --all --decorate'  # git: pretty log

# System info
alias diskspace='df -h'                 # disk usage
alias meminfo='free -h'                 # memory info
alias cpuinfo='lscpu'                   # CPU info

# Development tools
alias check='shellcheck'                # shellcheck: linter
alias json='jq .'                       # jq: pretty-print JSON
alias yaml='yq eval'                    # yq: YAML query
alias man='tldr'                        # tldr: simplified man pages

# File manager
alias fm='mc --nosubshell'              # Midnight Commander: no subshell

# SSH filesystem
alias mount-ssh='sshfs'                 # sshfs: shorthand
alias umount-ssh='fusermount -u'        # unmount sshfs
EOF
        log_debug "Added custom bash aliases and shortcuts"
    else
        log_debug "Custom bash aliases already configured"
    fi

    # SSH setup only in devcontainer (not GitHub Actions)
    if [[ "$ENV_TYPE" != "devcontainer" ]]; then
        log_debug "Skipping SSH key setup (not devcontainer environment)"
        return
    fi

    # SSH keys to add to agent (from mounted host ~/.ssh)
    local SSH_KEYS=("netcup-hosting218629-ed25519")
    local ssh_dir="/home/vscode/.ssh-host"

    if [[ -d "$ssh_dir" ]]; then
        log_info "Host SSH keys mounted at $ssh_dir"

        local ssh_agent_file="$HOME/.ssh-agent-info"

        if [[ -f "$ssh_agent_file" ]]; then
            # shellcheck source=/dev/null
            source "$ssh_agent_file" >/dev/null 2>&1
            if kill -0 "${SSH_AGENT_PID:-0}" 2>/dev/null; then
                log_debug "SSH agent already running (PID: $SSH_AGENT_PID)"
            else
                log_debug "Stale SSH agent file found, starting new agent..."
                rm -f "$ssh_agent_file"
            fi
        fi

        if [[ -z "${SSH_AGENT_PID:-}" ]] || ! kill -0 "${SSH_AGENT_PID:-0}" 2>/dev/null; then
            log_debug "Starting persistent SSH agent..."
            ssh-agent -s > "$ssh_agent_file"
            # shellcheck source=/dev/null
            source "$ssh_agent_file" >/dev/null 2>&1
        fi

        if ! grep -q "ssh-agent-info" ~/.bashrc 2>/dev/null; then
            cat >> ~/.bashrc << 'EOF'

# Load SSH agent info for persistent agent across all shells
if [[ -f "$HOME/.ssh-agent-info" ]]; then
    # shellcheck source=/dev/null
    source "$HOME/.ssh-agent-info" >/dev/null 2>&1
fi
EOF
            log_debug "Added SSH agent loading to .bashrc"
        fi

        for key in "${SSH_KEYS[@]}"; do
            if [[ -f "$ssh_dir/$key" ]]; then
                local key_fingerprint
                key_fingerprint=$(ssh-keygen -lf "$ssh_dir/$key" 2>/dev/null | awk '{print $2}')
                if ssh-add -l 2>/dev/null | grep -q "$key_fingerprint"; then
                    log_debug "SSH key $key already loaded"
                else
                    log_info "Adding SSH key: $key"
                    ssh-add "$ssh_dir/$key" 2>/dev/null \
                        && log_success "Added SSH key: $key" \
                        || log_warn "Failed to add SSH key $key (passphrase required?)"
                fi
            else
                log_warn "SSH key $key not found in $ssh_dir"
            fi
        done
    else
        log_debug "SSH directory not mounted at $ssh_dir — skipping SSH key setup"
    fi
}

# ============================================================================
# DEVELOPMENT TOOLS CONFIGURATION
# ============================================================================

setup_development_tools() {
    log_info "Configuring development tools..."

    # Configure Midnight Commander (mc)
    local mc_config_dir="$HOME/.config/mc"
    if command -v mc &>/dev/null; then
        mkdir -p "$mc_config_dir"
        if ! grep -q "alias mc=" ~/.bashrc 2>/dev/null; then
            echo "alias mc='mc --nosubshell'" >> ~/.bashrc
            log_debug "Added mc alias to prevent subshell issues"
        fi
        log_success "Midnight Commander available"
    else
        log_debug "Midnight Commander not available"
    fi

    # Configure bat (cat replacement)
    if command -v bat &>/dev/null || command -v batcat &>/dev/null; then
        local bat_config_dir="$HOME/.config/bat"
        if [[ ! -d "$bat_config_dir" ]]; then
            mkdir -p "$bat_config_dir"
            cat > "$bat_config_dir/config" << 'EOF'
# Bat configuration
--theme="Dracula"
--style="numbers,changes,header"
EOF
            log_debug "Created bat configuration"
        fi
    fi

    log_success "Development tools configured"
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

main() {
    log_info "Starting netcup-api-filter environment setup..."
    log_debug "Script PID: $$"
    log_debug "Working directory: $(pwd)"
    log_debug "User: $(whoami) (UID: $(id -u), GID: $(id -g))"

    detect_environment

    # Repository paths FIRST — setup_network_connectivity appends to .env.workspace
    log_debug "Calling setup_repository_paths..."
    if ! setup_repository_paths; then
        log_error "Repository path setup failed — cannot continue"
        exit 1
    fi

    # Network connectivity AFTER repository paths (appends to .env.workspace)
    log_debug "Calling setup_network_connectivity..."
    if ! setup_network_connectivity; then
        log_warn "Network connectivity setup had issues (non-critical)"
    fi

    log_debug "Calling setup_python_environment..."
    if ! setup_python_environment; then
        log_error "Python environment setup failed — cannot continue"
        exit 1
    fi

    log_debug "Calling setup_ssh_and_aliases..."
    if ! setup_ssh_and_aliases; then
        log_warn "SSH and aliases setup had issues (non-critical)"
    fi

    log_debug "Calling setup_development_tools..."
    if ! setup_development_tools; then
        log_warn "Development tools setup had issues (non-critical)"
    fi

    log_success "Environment setup complete!"
    echo ""
    echo "=== Netcup API Filter Environment ==="
    echo "Environment: $ENV_TYPE"
    echo "User: $USER_NAME (UID=$USER_UID, GID=$USER_GID)"
    echo "Workspace: $WORKSPACE_DIR"
    echo "Python (venv): $("$WORKSPACE_DIR/.venv/bin/python" --version 2>&1 || echo 'venv not found')"
    if [[ -n "${DOCKER_NETWORK_INTERNAL:-}" ]]; then
        echo "Docker network: $DOCKER_NETWORK_INTERNAL"
    fi
    echo ""
    echo "Run unit tests: source .venv/bin/activate && pytest tests/"
    echo "Run app:        source .venv/bin/activate && python -m netcup_api_filter"
    echo ""
    echo "--- Browser / UI tests ---"
    echo "UI/browser tests in this devcontainer use the external pwmcp Playwright"
    echo "service — no browser binaries are installed here (that is intentional)."
    echo ""
    echo "  To use the remote service (recommended):"
    echo "    export PLAYWRIGHT_SERVER_WS=ws://<pwmcp-playwright-container>:3000/"
    echo "    # (sibling container on the shared Docker network \${DOCKER_NETWORK_INTERNAL})"
    echo "    pytest ui_tests/"
    echo ""
    echo "  To use local in-process browsers instead (pulls ~200 MB of binaries):"
    echo "    tooling/setup-playwright.sh"
    echo ""
}

if ! main "$@"; then
    log_error "Netcup API Filter environment setup failed"
    exit 1
fi
