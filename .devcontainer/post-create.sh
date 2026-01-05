#!/bin/bash
# ============================================================================
# DST-DNS Devcontainer Post-Create Setup
# ============================================================================
# Runs after devcontainer is created to set up the development environment
#
# Philosophy:
# - Dynamic environment detection
# - Global Python packages (no venv required)
# - Fail-fast with clear error messages
# - Path management for Docker bind mounts
# ============================================================================

set -euo pipefail

# Trap to catch any errors and provide debugging info
trap 'log_error "Script failed at line $LINENO with exit code $?"; log_error "Last command: $BASH_COMMAND"; exit 1' ERR

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

# ============================================================================
# ENVIRONMENT DETECTION (DYNAMIC)
# ============================================================================
# Dynamically determine all environment characteristics
# No hardcoded values - everything detected at runtime

detect_environment() {
    log_info "Detecting environment characteristics..."

    # Environment type detection
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

    # Dynamic user detection
    USER_NAME="$(whoami)"
    USER_UID="$(id -u)"
    USER_GID="$(id -g)"

    # Dynamic Docker group detection
    DOCKER_GID="$(getent group docker | cut -d: -f3 2>/dev/null || echo '118')"
    if [[ "$DOCKER_GID" == "118" ]] && ! getent group docker >/dev/null 2>&1; then
        log_warn "Docker group not found, using default GID 118"
    fi

    # Dynamic workspace detection
    WORKSPACE_DIR="$(pwd)"
    if [[ ! -f "global-config.defaults.toml" ]]; then
        log_error "Not in DST-DNS repository root (missing global-config.defaults.toml)"
        exit 1
    fi

    # Export for use by other functions
    export ENV_TYPE USER_NAME USER_UID USER_GID DOCKER_GID WORKSPACE_DIR

    log_debug "Environment: $ENV_TYPE"
    log_debug "User: $USER_NAME (UID=$USER_UID, GID=$USER_GID)"
    log_debug "Docker Group GID: $DOCKER_GID"
    log_debug "Workspace: $WORKSPACE_DIR"
}

# ============================================================================
# PYTHON ENVIRONMENT SETUP (GLOBAL PACKAGES)
# ============================================================================
# Install Python packages globally as current user (not root)
# Provides immediate availability without venv activation
# Works across all environments: devcontainer, GitHub Actions, local

setup_python_environment() {
    log_info "Setting up Python environment (global packages)..."
    log_debug "Python version: $(python --version 2>&1)"
    log_debug "Pip version: $(pip --version 2>&1)"

    # Upgrade pip/setuptools first
    log_debug "Upgrading pip, setuptools, wheel..."
    if ! pip install --user --upgrade pip setuptools wheel --disable-pip-version-check; then
        log_error "Failed to upgrade pip/setuptools"
        return 1
    fi
    log_debug "Pip upgrade completed"

    # Install from requirements-dev.txt (includes production + testing + development packages)
    local requirements_file="$WORKSPACE_DIR/requirements-dev.txt"
    
    if [[ ! -f "$requirements_file" ]]; then
        log_error "requirements-dev.txt not found at $requirements_file"
        log_error "This file should contain all development dependencies"
        return 1
    fi
    
    log_info "Installing Python packages from requirements-dev.txt..."
    log_debug "Requirements file: $requirements_file"
    
    local install_output
    if ! install_output=$(pip install --user -r "$requirements_file" --disable-pip-version-check 2>&1); then
        log_error "Failed to install Python packages"
        log_error "Install output: $install_output"
        log_error "Check pip version and network connectivity"
        log_error "You may need to run: pip install --user --upgrade pip"
        return 1
    fi
    log_debug "Package installation completed"
}

# ============================================================================
# PUBLIC FQDN DETECTION (REVERSE DNS)
# ============================================================================
# Detect public FQDN via reverse DNS for TLS certificate management
# Used by nginx reverse proxy and other tools that need the public hostname

detect_public_fqdn() {
    log_info "Detecting public FQDN via reverse DNS..."

    # Detect public IP
    local public_ip="${FORCE_PUBLIC_IP:-}"
    
    if [[ -z "$public_ip" ]]; then
        local ip_endpoints=(
            "https://api.ipify.org"
            "https://icanhazip.com"
            "https://ifconfig.me/ip"
        )
        
        for endpoint in "${ip_endpoints[@]}"; do
            if public_ip=$(curl -s --max-time 3 "$endpoint" 2>/dev/null | tr -d '[:space:]'); then
                if [[ "$public_ip" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
                    log_debug "Detected IP: $public_ip"
                    break
                fi
            fi
            public_ip=""
        done
    fi

    if [[ -z "$public_ip" ]]; then
        log_warn "Failed to detect public IP, using localhost"
        export PUBLIC_IP="127.0.0.1"
        export PUBLIC_FQDN="localhost"
        return 0
    fi

    export PUBLIC_IP="$public_ip"

    # Perform reverse DNS lookup
    local public_fqdn="${FORCE_FQDN:-}"
    
    if [[ -z "$public_fqdn" ]]; then
        if command -v dig >/dev/null 2>&1; then
            public_fqdn=$(dig +short -x "$public_ip" 2>/dev/null | sed 's/\.$//' | head -1 || echo "")
        elif command -v host >/dev/null 2>&1; then
            public_fqdn=$(host "$public_ip" 2>/dev/null | awk '/domain name pointer/ {print $NF}' | sed 's/\.$//' || echo "")
        fi
    fi

    if [[ -z "$public_fqdn" ]]; then
        log_warn "No reverse DNS record found, using localhost"
        export PUBLIC_FQDN="localhost"
    else
        log_success "Detected FQDN: $public_fqdn"
        export PUBLIC_FQDN="$public_fqdn"
    fi

    # Construct TLS cert paths
    export PUBLIC_TLS_CRT_PEM="/etc/letsencrypt/live/${PUBLIC_FQDN}/fullchain.pem"
    export PUBLIC_TLS_KEY_PEM="/etc/letsencrypt/live/${PUBLIC_FQDN}/privkey.pem"
}

# ============================================================================
# REPOSITORY PATH MANAGEMENT (CENTRALIZED)
# ============================================================================
# Set canonical repository paths for ALL downstream scripts and tools
# These are detected ONCE and exported for consistent use

setup_repository_paths() {
    log_info "Setting up repository path management..."

    export REPO_ROOT="$WORKSPACE_DIR"

    # Function to detect physical host path for Docker bind mounts
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
            | awk -v pwd="$WORKSPACE_DIR" '$2 != "" {
                print $2
                exit
            }' | head -1)

        if [[ -n "$host_path" ]]; then
            log_debug "Detected via devcontainer.local_folder label: $host_path" >&2
            echo "$host_path"
            return
        fi

        # Priority 3: Fallback to workspace dir (bare metal, SSH, CI/CD)
        log_debug "No devcontainer label found, using workspace dir: $WORKSPACE_DIR" >&2
        echo "$WORKSPACE_DIR"
    }

    export PHYSICAL_REPO_ROOT="$(detect_physical_repo_root)"

    if [[ -z "$PHYSICAL_REPO_ROOT" ]]; then
        log_error "Failed to determine PHYSICAL_REPO_ROOT"
        log_error "Check Docker daemon access and devcontainer configuration"
        return 1
    fi

    # Persist for future script invocations
    # WHY .env.workspace?
    # - Scripts run OUTSIDE post-create.sh context (start-mcp.sh, deploy-test-fix-loop.sh, etc.)
    #   need these variables but don't have access to our current shell environment
    # - New terminal sessions need these values before manual export
    # - Docker compose in tooling/playwright/ needs PHYSICAL_REPO_ROOT and DOCKER_NETWORK_INTERNAL
    # - Provides single source of truth for workspace configuration across all tools
    cat > "$WORKSPACE_DIR/.env.workspace" << EOF
# ============================================================================
# Workspace Environment Configuration (Auto-generated)
# ============================================================================
# Generated by: .devcontainer/post-create.sh
# Purpose: Provides workspace variables to scripts running outside post-create.sh
# 
# Used by:
#   - tooling/playwright/start-mcp.sh (needs DOCKER_NETWORK_INTERNAL, PHYSICAL_REPO_ROOT)
#   - .vscode/deploy-test-fix-loop.sh (needs all workspace paths)
#   - .vscode/ensure-mcp-connection.sh (needs DOCKER_NETWORK_INTERNAL)
#   - Any other scripts that need workspace configuration
# 
# Do not edit manually - regenerated on devcontainer rebuild
# ============================================================================
export ENV_TYPE="$ENV_TYPE"
export USER_NAME="$USER_NAME"
export USER_UID="$USER_UID"
export USER_GID="$USER_GID"
export DOCKER_GID="$DOCKER_GID"
export REPO_ROOT="$REPO_ROOT"
export PHYSICAL_REPO_ROOT="$PHYSICAL_REPO_ROOT"

# Docker container user IDs (for playwright and other services)
export DOCKER_UID="$USER_UID"
export DOCKER_GID="$DOCKER_GID"

# Public FQDN and IP (for TLS proxy and external access)
export PUBLIC_IP="${PUBLIC_IP:-127.0.0.1}"
export PUBLIC_FQDN="${PUBLIC_FQDN:-localhost}"
export PUBLIC_TLS_CRT_PEM="${PUBLIC_TLS_CRT_PEM:-/etc/letsencrypt/live/localhost/fullchain.pem}"
export PUBLIC_TLS_KEY_PEM="${PUBLIC_TLS_KEY_PEM:-/etc/letsencrypt/live/localhost/privkey.pem}"
EOF

    # Also append to ~/.bashrc for future shells
    if ! grep -q "PHYSICAL_REPO_ROOT" ~/.bashrc 2>/dev/null; then
        cat >> ~/.bashrc << EOF

# DST-DNS Repository Paths (Auto-added by post-create.sh)
export REPO_ROOT="$REPO_ROOT"
export PHYSICAL_REPO_ROOT="$PHYSICAL_REPO_ROOT"
EOF
    fi

    log_success "Repository paths configured"
    echo ""
    echo "==================================================="
    echo "Repository Paths (Available to All Scripts):"
    echo "==================================================="
    echo "  REPO_ROOT:          $REPO_ROOT"
    echo "  PHYSICAL_REPO_ROOT: $PHYSICAL_REPO_ROOT"
    if [[ "$REPO_ROOT" != "$PHYSICAL_REPO_ROOT" ]]; then
        echo ""
        echo "  ✓ Devcontainer environment detected (path mapping active)"
    else
        echo ""
        echo "  ℹ️  Local environment (no path mapping)"
    fi
    echo "==================================================="
    echo ""
}

# ============================================================================
# NETWORK CONNECTIVITY (DEVCONTAINER ONLY)
# ============================================================================
# Auto-connect devcontainer to deployment network for hostname resolution

setup_network_connectivity() {
    if [[ "$ENV_TYPE" != "devcontainer" ]]; then
        log_debug "Skipping network setup (not devcontainer)"
        return
    fi

    log_info "Setting up network connectivity..."
    log_debug "Docker version: $(docker --version 2>&1 || echo 'Docker not available')"

    # Read network name from config
    if [[ ! -f "global-config.active.toml" ]]; then
        if [[ -f "global-config.defaults.toml" ]]; then
            log_info "Auto-generating global-config.active.toml..."
            if ! cp global-config.defaults.toml global-config.active.toml; then
                log_error "Failed to copy global-config.defaults.toml"
                return 1
            fi
        else
            log_error "Missing global-config.defaults.toml"
            return 1
        fi
    fi

    log_debug "Reading network name from config..."
    local network_name
    network_name=$(timeout 10 python3 -c "
import tomllib
from jinja2 import Template
import sys

try:
    with open('global-config.active.toml', 'rb') as f:
        config = tomllib.load(f)
    
    deployment = config.get('deployment', {})
    network_template = deployment.get('docker_network_name_template') or deployment.get('docker_network_name')
    if not network_template:
        print('ERROR: not defined', file=sys.stderr)  # fallback
        sys.exit(1)
    
    if '{{' in network_template:
        template = Template(network_template)
        result = template.render(deployment=deployment)
        print(result)
    else:
        print(network_template)
except Exception as e:
    print(f'Error reading network: {e}', file=sys.stderr)
    print('ERROR: not defined', file=sys.stderr)  # fallback
    sys.exit(1)
" 2>&1 | tail -1)

    if [[ $? -ne 0 ]]; then
        log_error "Python script execution failed or timed out"
        return 1
    fi

    if [[ -z "$network_name" ]]; then
        log_error "Failed to determine network name from config"
        log_error "Check global-config.active.toml for deployment.docker_network_name_template"
        return 1
    fi

    log_debug "Network name: $network_name"

    # Create network if needed
    log_debug "Checking if network exists..."
    if ! docker network inspect "$network_name" &>/dev/null; then
        log_info "Creating network: $network_name"
        if ! docker network create "$network_name" 2>/dev/null; then
            log_error "Failed to create Docker network '$network_name'"
            log_error "Check Docker daemon permissions and network name"
            return 1
        fi
    else
        log_debug "Network $network_name already exists"
    fi

    # Connect devcontainer to network
    log_debug "Finding devcontainer container..."
    local container_name
    container_name=$(docker ps --format '{{.Names}}' --filter volume="$WORKSPACE_DIR" 2>/dev/null | head -1)

    if [[ -z "$container_name" ]]; then
        log_error "Could not detect devcontainer container"
        log_error "Check Docker daemon access and workspace volume mounting"
        return 1
    fi

    log_debug "Devcontainer container: $container_name"
    
    # Export for use in scripts (e.g., for URLs like http://DEVCONTAINER_NAME:5100)
    export DEVCONTAINER_NAME="$container_name"

    if docker network inspect "$network_name" --format '{{range .Containers}}{{.Name}} {{end}}' 2>/dev/null | grep -q "$container_name"; then
        log_success "Devcontainer already connected to $network_name"
    else
        log_info "Connecting devcontainer to $network_name..."
        if docker network connect "$network_name" "$container_name" 2>/dev/null; then
            log_success "Devcontainer connected to $network_name"
        else
            log_error "Failed to connect devcontainer to network '$network_name'"
            log_error "Check Docker daemon permissions and container name"
            return 1
        fi
    fi
    export DOCKER_NETWORK_INTERNAL="$network_name"
    cat >> "$WORKSPACE_DIR/.env.workspace" << EOF
export DOCKER_NETWORK_INTERNAL="$network_name"
export DEVCONTAINER_NAME="$DEVCONTAINER_NAME"
EOF
}

# ============================================================================
# VS CODE CONFIGURATION
# ============================================================================
# Configure VS Code to use system Python (global packages)

setup_vscode_config() {
    if [[ "$ENV_TYPE" != "devcontainer" ]]; then
        return
    fi

    log_info "Configuring VS Code settings..."

    mkdir -p .vscode

    if [[ ! -f ".vscode/settings.json" ]]; then
        cat > .vscode/settings.json << EOF
{
  "python.defaultInterpreterPath": "python",
  "python.terminal.activateEnvironment": false
}
EOF
        log_success "Created .vscode/settings.json"
    else
        log_debug ".vscode/settings.json already exists"
    fi
}

# ============================================================================
# PATH CONFIGURATION
# ============================================================================
# Add compose-init-up to PATH for convenience

setup_path() {
    local scripts_path="$WORKSPACE_DIR/scripts/compose-init-up"

    if [[ ":$PATH:" != *":$scripts_path:"* ]]; then
        export PATH="$scripts_path:$PATH"
        log_success "Added compose-init-up to PATH"
    else
        log_debug "compose-init-up already in PATH"
    fi
}

# ============================================================================
# SSH KEYS AND ALIASES SETUP
# ============================================================================
# Configure SSH agent and useful bash aliases

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

# Database clients
alias psql-local='psql -h localhost -U postgres'  # quick local psql
alias redis='redis-cli'                 # redis-cli: shorthand
alias db='sqlite3'                      # sqlite3: shorthand

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

    # Ensure SSH keys from host are accessible (if mounted)
    if [[ -d "$ssh_dir" ]]; then
        log_info "Host SSH keys mounted at $ssh_dir"

        # Start ssh-agent and persist for all future shells
        local ssh_agent_file="$HOME/.ssh-agent-info"
        
        # Check if existing agent is still running
        if [[ -f "$ssh_agent_file" ]]; then
            source "$ssh_agent_file" >/dev/null 2>&1
            if kill -0 "$SSH_AGENT_PID" 2>/dev/null; then
                log_debug "SSH agent already running (PID: $SSH_AGENT_PID)"
            else
                log_debug "Stale SSH agent file found, starting new agent..."
                rm -f "$ssh_agent_file"
            fi
        fi
        
        # Start new agent if not running
        if [[ -z "${SSH_AGENT_PID:-}" ]] || ! kill -0 "$SSH_AGENT_PID" 2>/dev/null; then
            log_debug "Starting persistent SSH agent..."
            ssh-agent -s > "$ssh_agent_file"
            source "$ssh_agent_file" >/dev/null 2>&1
            if [[ $? -eq 0 ]]; then
                log_debug "SSH agent started (PID: $SSH_AGENT_PID)"
            else
                log_warn "Failed to start SSH agent"
                return 1
            fi
        fi
        
        # Add SSH agent loading to .bashrc for future shells
        if ! grep -q "ssh-agent-info" ~/.bashrc 2>/dev/null; then
            cat >> ~/.bashrc << 'EOF'

# Load SSH agent info for persistent agent across all shells
if [[ -f "$HOME/.ssh-agent-info" ]]; then
    source "$HOME/.ssh-agent-info" >/dev/null 2>&1
fi
EOF
            log_debug "Added SSH agent loading to .bashrc"
        fi

        # List currently loaded keys (debug output)
        log_debug "Currently loaded SSH keys:"
        if ssh-add -l 2>/dev/null; then
            log_debug "$(ssh-add -l 2>/dev/null | awk '{print "  - " $NF " (" $1 " " $2 ")"}')"
        else
            log_debug "  (none)"
        fi

        # Add each key in the list
        local keys_added=0
        local keys_already_loaded=0
        for key in "${SSH_KEYS[@]}"; do
            if [[ -f "$ssh_dir/$key" ]]; then
                # Get the public key fingerprint for comparison
                local key_fingerprint
                key_fingerprint=$(ssh-keygen -lf "$ssh_dir/$key" 2>/dev/null | awk '{print $2}')
                
                # Check if key is already loaded by comparing fingerprints
                if ssh-add -l 2>/dev/null | grep -q "$key_fingerprint"; then
                    log_debug "SSH key $key already loaded (fingerprint: $key_fingerprint)"
                    ((keys_already_loaded++))
                else
                    log_info "Adding SSH key: $key"
                    if ssh-add "$ssh_dir/$key" 2>/dev/null; then
                        ((keys_added++))
                        log_debug "Successfully added SSH key: $key (fingerprint: $key_fingerprint)"
                    else
                        log_warn "Failed to add SSH key $key (possibly passphrase required or already added)"
                    fi
                fi
            else
                log_warn "SSH key $key not found in mounted directory $ssh_dir"
            fi
        done

        local total_ready=$((keys_added + keys_already_loaded))
        if [[ $total_ready -gt 0 ]]; then
            if [[ $keys_already_loaded -gt 0 ]]; then
                log_success "SSH keys ready: $keys_already_loaded already loaded, $keys_added newly added"
            else
                log_success "Added $keys_added SSH key(s) to agent"
            fi
        else
            log_warn "No SSH keys were successfully added or loaded"
        fi
    else
        log_debug "SSH directory not mounted at $ssh_dir - skipping SSH key setup"
    fi
}

# ============================================================================
# DEVELOPMENT TOOLS CONFIGURATION
# ============================================================================
# Configure additional development tools like Midnight Commander

setup_development_tools() {
    log_info "Configuring development tools..."

    # Configure Midnight Commander (mc)
    local mc_config_dir="$HOME/.config/mc"
    if command -v mc &> /dev/null; then
        if [[ ! -d "$mc_config_dir" ]]; then
            mkdir -p "$mc_config_dir"
            log_debug "Created Midnight Commander config directory"
        fi

        # Create basic mc configuration
        if [[ ! -f "$mc_config_dir/ini" ]]; then
            cat > "$mc_config_dir/ini" << 'EOF'
[Midnight-Commander]
verbose=1
shell_patterns=1
auto_save_setup=1
preallocate_space=0
auto_menu=0
use_internal_view=1
use_internal_edit=1
clear_before_exec=1
confirm_delete=1
confirm_overwrite=1
confirm_execute=0
confirm_history_cleanup=1
confirm_exit=0
confirm_directory_hotlist_delete=1
confirm_view_dir=0
safe_delete=0
safe_overwrite=0
auto_overwrite=0
use_8th_bit_as_meta=0
mouse_move_pages_viewer=1
mouse_close_dialog=0
fast_refresh=0
drop_menus=0
wrap_mode=1
old_esc_mode=0
cd_symlinks=1
show_all_if_ambiguous=0
mark_moves_down=1
show_output_starts_shell=0
xtree_mode=0
file_op_compute_totals=1
classic_progressbar=0
use_netrc=1
ftpfs_always_use_proxy=0
ftpfs_use_passive_connections=1
ftpfs_use_passive_connections_over_proxy=0
ftpfs_use_unix_list_options=1
ftpfs_first_cd_then_ls=1
ignore_ftp_chattr_errors=1
editor_fill_tabs_with_spaces=0
editor_return_does_auto_indent=1
editor_backspace_through_tabs=0
editor_fake_half_tabs=1
editor_option_save_mode=0
editor_option_save_position=1
editor_option_auto_para_formatting=0
editor_option_typewriter_wrap=0
editor_edit_confirm_save=1
editor_syntax_highlighting=1
editor_persistent_selections=1
editor_drop_selection_on_copy=1
editor_cursor_beyond_eol=0
editor_visible_tabs=1
editor_visible_spaces=1
editor_line_state=1
editor_simple_statusbar=0
editor_check_new_line=0
editor_show_right_margin=0
editor_group_undo=1
editor_state_full_filename=0
view_with_aixterm=0
view_with_hexedit=0
find_ignore_dirs=
find_grep_i=0
find_grep_n=0
find_grep_v=0
find_grep_w=0
find_source_pattern=*
find_file_pattern=*
find_with=0
panel_scroll_pages=1
panel_scroll_center=0
panel_scroll_margin=0
panel_show_mini_info=1
panel_show_free_space=1
filetype_mode=1
permission_mode=0
ext_mode=0
panel_smart_wrap=0
panel_hidefiles_mode=2
mix_all_files=0
show_backups=0
show_dot_files=1
select_flags=6
panel_compare_mode=0
panel_compare_case=1
panel_compare_torenamed=0
panel_compare_tosize=0
panel_quick_search_mode=2
statusbar_mode=0
highlight_mode=1
panel_layout=horizontal_equal
panel_split=horizontal
message_visible=1
input_line_size=60
output_lines_shown=1
col_dlg_mode=0
col_dlg_num=0
layout=0
skin=default
EOF
            log_debug "Created Midnight Commander configuration"
        fi

        # Add mc alias if not present
        if ! grep -q "alias mc=" ~/.bashrc 2>/dev/null; then
            echo "alias mc='mc --nosubshell'" >> ~/.bashrc
            log_debug "Added mc alias to prevent subshell issues"
        fi

        log_success "Midnight Commander configured"
    else
        log_debug "Midnight Commander not available"
    fi

    # Configure bat (cat replacement)
    if command -v bat &> /dev/null; then
        # Create bat config if it doesn't exist
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

    # Configure fd (find replacement)
    if command -v fd &> /dev/null; then
        # fd is installed as fd-find on Debian/Ubuntu
        if ! grep -q "alias fd=" ~/.bashrc 2>/dev/null; then
            echo "alias fd='fdfind'" >> ~/.bashrc
            log_debug "Added fd alias for fdfind"
        fi
    fi

    # Configure fzf if available
    if command -v fzf &> /dev/null; then
        # Add fzf key bindings and completion
        if [[ -f "/usr/share/bash-completion/completions/fzf" ]]; then
            source /usr/share/bash-completion/completions/fzf
            log_debug "Loaded fzf bash completion"
        fi
    fi

    log_success "Development tools configured"
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

main() {
    log_info "Starting DST-DNS environment setup..."
    log_debug "Script PID: $$"
    log_debug "Working directory: $(pwd)"
    log_debug "User: $(whoami) (UID: $(id -u), GID: $(id -g))"
    log_debug "Arguments: $@"

    # Check for required tools
    log_debug "Checking for required tools..."
    local required_tools=("python" "pip" "docker")
    for tool in "${required_tools[@]}"; do
        if ! command -v "$tool" &> /dev/null; then
            log_error "Required tool not found: $tool"
            exit 1
        fi
    done
    log_debug "All required tools available"

    # Set up error handling
    set -e  # Exit on any error
    trap 'log_error "Setup failed at line $LINENO with exit code $?"; exit 1' ERR

    log_debug "Calling detect_environment..."
    detect_environment
    log_debug "detect_environment completed"

    log_debug "Calling detect_public_fqdn..."
    if ! detect_public_fqdn; then
        log_warn "Public FQDN detection had issues (non-critical)"
        # Don't exit - FQDN detection failure shouldn't break devcontainer
        export PUBLIC_FQDN="localhost"
        export PUBLIC_IP="127.0.0.1"
    fi
    log_debug "detect_public_fqdn completed"

    log_debug "Calling setup_python_environment..."
    if ! setup_python_environment; then
        log_error "Python environment setup failed"
        exit 1
    fi
    log_debug "setup_python_environment completed"

    log_debug "Calling setup_repository_paths..."
    if ! setup_repository_paths; then
        log_error "Repository path setup failed"
        exit 1
    fi
    log_debug "setup_repository_paths completed"

    log_debug "Calling setup_network_connectivity..."
    if ! setup_network_connectivity; then
        log_error "Network connectivity setup failed"
        exit 1
    fi
    log_debug "setup_network_connectivity completed"

    log_debug "Calling setup_vscode_config..."
    if ! setup_vscode_config; then
        log_error "VS Code configuration failed"
        exit 1
    fi
    log_debug "setup_vscode_config completed"

    log_debug "Calling setup_path..."
    if ! setup_path; then
        log_error "PATH setup failed"
        exit 1
    fi
    log_debug "setup_path completed"

    log_debug "Calling setup_ssh_and_aliases..."
    if ! setup_ssh_and_aliases; then
        log_warn "SSH and aliases setup had issues (non-critical)"
        # Don't exit - SSH setup failure shouldn't break devcontainer
    fi
    log_debug "setup_ssh_and_aliases completed"

    log_debug "Calling setup_development_tools..."
    if ! setup_development_tools; then
        log_warn "Development tools setup had issues (non-critical)"
        # Don't exit - tool setup failure shouldn't break devcontainer
    fi
    log_debug "setup_development_tools completed"

    log_success "Environment setup complete!"
    echo ""
    echo "=== DST-DNS Environment Configuration ==="
    echo "Environment: $ENV_TYPE"
    echo "User: $USER_NAME (UID=$USER_UID, GID=$USER_GID)"
    echo "Docker Group GID: $DOCKER_GID"
    echo "Workspace: $WORKSPACE_DIR"
    echo "Python: $(python --version 2>&1 | head -1)"
    echo ""

    if [[ "$ENV_TYPE" == "devcontainer" ]]; then
        echo "Next steps:"
        echo "  1. Build images: docker buildx bake all-services --load"
        echo "  2. Start services: python3 scripts/start-2node-deployment.py"
        echo "  3. Access services: curl http://controller:8080/health"
        echo ""
        echo "Available aliases: ll, la, lt (tree), cat (bat), grep (rg), find (fd), ps (htop)"
        echo "Available tools: mc (Midnight Commander), yq (YAML processor), fzf, tldr, httpie"
        echo "SSH keys loaded and ready for Git operations"
        echo ""
        echo "For project-specific venv: python3 -m venv .venv && source .venv/bin/activate"
    fi

    log_debug "main() completed successfully"
}

# Catch any unhandled errors in main()
if ! main "$@"; then
    log_error "DST-DNS environment setup failed"
    log_error "Check the output above for specific error messages"
    log_error "Common issues:"
    log_error "  - Missing Docker daemon access"
    log_error "  - Network connectivity issues"
    log_error "  - Python package installation failures"
    log_error "  - Permission issues with Docker group"
    exit 1
fi
