#!/bin/bash
# Dev Container post-create script
# Automatically sets up Python environment with required dependencies
#
# Changes:
# - Avoid hard-coded /workspaces/DST-DNS path.
# - Introduce WORKSPACE_DIR top-level variable which defaults to the current repo root (dynamic).
# - All references to the workspace path now use WORKSPACE_DIR and can be overridden by exporting WORKSPACE_DIR before running this script.
#
# If you prefer a static path instead of using the dynamic default, set:
#   export WORKSPACE_DIR="/workspaces/dstdns"
#
set -e

# Top-level, easily-changeable workspace path:
# - By default, use the directory the script runs in (dynamic behavior).
# - You may override by exporting WORKSPACE_DIR in the environment before running the script,
#   or edit this value here to force a specific path.

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# SSH keys to add to agent (from mounted host ~/.ssh)
SSH_KEYS=("netcup-hosting218629-ed25519")

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



# Function to get physical host path (for devcontainer environments)
get_physical_host_path() {
    local current_path="$1"
    
    # Check if we're in a devcontainer by looking for the local_folder label
    local host_path=""
    host_path=$(docker ps --format '{{.ID}} {{.Label "devcontainer.local_folder"}}' 2>/dev/null | awk '$2 != "" {print $2; exit}') || true
    
    if [ -n "$host_path" ] && [ "$host_path" != "$current_path" ]; then
        # We're in a devcontainer and found the physical host path
        # Log to stderr to avoid interfering with return value
        log_info "Detected devcontainer environment" >&2
        log_info "  devcontainer repo-path: $current_path" >&2
        log_info "  physical repo-root: $host_path" >&2
        echo "$host_path"
        return 0
    fi
    
    # Not in devcontainer or couldn't detect, use current path
    echo "$current_path"
}

WORKSPACE_DIR="${WORKSPACE_DIR:-$(pwd)}"

log_info "[INFO] Using WORKSPACE_DIR: $WORKSPACE_DIR"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PHYSICAL_REPO_ROOT=$(get_physical_host_path "$REPO_ROOT")

get_physical_host_path "$REPO_ROOT"


log_info "[INFO] Python: Upgrading pip..."
### upgrade core packages without redundant new version message
pip install --upgrade pip setuptools wheel  --disable-pip-version-check

log_info "[INFO] Python: Installing packages..."
### we run as normal user thus pip: `Defaulting to user installation because normal site-packages is not writeable`
pip install --user -r .devcontainer/requirements.txt 


log_info "[INFO] Python environment setup complete!"
log_info "[INFO]   Virtual environment (or not): $(which python)"
log_info "[INFO]   Python version: $(python --version)"
log_info "[INFO]   Installed packages:"
pip list 


log_info "[INFO] determined FQDN: $(dig +short -x $(curl -s  api.ipify.org))"
log_success "[SUCCESS] Dev container setup complete!"

# Add useful aliases
echo "alias ll='ls -l'" >> ~/.bashrc
echo "alias la='ls -la'" >> ~/.bashrc


ssh_dir="/home/vscode/.ssh-host"

# Ensure SSH keys from host are accessible (if mounted)
if [ -d "$ssh_dir" ]; then
    log_info "[INFO] Host SSH keys mounted at $ssh_dir"
    # Start ssh-agent once
    eval "$(ssh-agent -s)"
    # Add each key in the list
    for key in "${SSH_KEYS[@]}"; do
        if [ -f "$ssh_dir/$key" ]; then
            log_info "[INFO] Adding SSH key: $key"
            ssh-add "$ssh_dir/$key" 2>/dev/null || log_warn "Failed to add SSH key $key (possibly passphrase required)"
        else
            log_warn "[WARN] SSH key $key not found in mounted directory $ssh_dir"
        fi
    done
fi

