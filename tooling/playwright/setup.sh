#!/usr/bin/env bash
# Generic Playwright container setup script

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# Detect physical host path for bind mounts (Docker daemon needs host paths)
detect_physical_path() {
    local container_path="$1"
    
    # Priority 1: Manual override
    if [[ -n "${PHYSICAL_REPO_ROOT:-}" ]]; then
        echo "$PHYSICAL_REPO_ROOT/tooling/playwright"
        return
    fi
    
    # Priority 2: Devcontainer label (VS Code sets this)
    # Try to get label from current container (if we're in one)
    local current_hostname=$(hostname 2>/dev/null)
    local devcontainer_label=""
    
    if [[ -n "$current_hostname" ]]; then
        devcontainer_label=$(docker inspect "$current_hostname" --format '{{index .Config.Labels "devcontainer.local_folder"}}' 2>&1 | grep -v "^\[DEBUG\]" | grep -v "^$" || true)
    fi
    
    # If not found, try to find any devcontainer with matching path
    if [[ -z "$devcontainer_label" ]]; then
        devcontainer_label=$(docker ps -q | xargs -I {} docker inspect {} --format '{{index .Config.Labels "devcontainer.local_folder"}}' 2>/dev/null | grep -v "^$" | head -1 || true)
    fi
    
    if [[ -n "$devcontainer_label" ]]; then
        echo "$devcontainer_label/tooling/playwright"
        return
    fi
    
    # Priority 3: Fallback to container path (bare metal, SSH, CI/CD)
    echo "$container_path"
}

# Detect user/group IDs (UID is readonly, use alternatives)
export DOCKER_UID=$(id -u)
export DOCKER_GID=$(getent group docker | cut -d: -f3 || echo 1000)

# Detect physical path for bind mount
PHYSICAL_SCRIPT_DIR=$(detect_physical_path "$SCRIPT_DIR")

log_info "Setting up Playwright container..."
log_info "User ID: $DOCKER_UID, Group ID: $DOCKER_GID"
log_info "Container path: $SCRIPT_DIR"
log_info "Physical path: $PHYSICAL_SCRIPT_DIR"

# Export physical path for docker-compose
export PHYSICAL_PLAYWRIGHT_DIR="$PHYSICAL_SCRIPT_DIR"

# Note: Screenshots directory is handled by init container
# Created as bind mount using physical host path

# Build container
log_info "Building Docker container..."
docker compose build

# Start container
log_info "Starting container..."
docker compose up -d

# Wait for container to be ready
log_info "Waiting for container..."
sleep 2

# Verify Playwright is available
log_info "Verifying Playwright installation..."
if docker compose exec playwright python3 -c "from playwright.async_api import async_playwright; print('Playwright OK')" 2>&1 | grep -q "Playwright OK"; then
    log_success "Playwright is ready!"
else
    log_error "Playwright verification failed"
    exit 1
fi

log_success "Setup complete!"
echo
log_info "Screenshots location:"
log_info "  Container: /screenshots"
log_info "  Physical: $PHYSICAL_SCRIPT_DIR/vol-playwright-screenshots"
log_info "  Devcontainer: $SCRIPT_DIR/vol-playwright-screenshots"
echo
log_info "Usage:"
echo "  # Run Python script:"
echo "  docker compose exec playwright python3 /workspace/your_script.py"
echo
echo "  # Run pytest:"
echo "  docker compose exec playwright pytest /workspace/tests -v"
echo
echo "  # Interactive shell:"
echo "  docker compose exec playwright /bin/bash"
echo
log_info "Stop container: docker compose down"
