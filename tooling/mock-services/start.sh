#!/bin/bash
# Start mock services for E2E testing
# Usage: ./start-mock-services.sh [--wait]
#
# Services:
#   - Mailpit (SMTP on 1025, API on 8025)
#   - Mock GeoIP (Flask on 5556)
#   - Mock Netcup API (Flask on 5555)
#
# Access from devcontainer/tests via container hostnames:
#   http://mailpit:8025, http://mock-geoip:5556, http://mock-netcup-api:5555

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[OK]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }

# Load environment from .env.workspace if available
if [[ -f "${SCRIPT_DIR}/../../.env.workspace" ]]; then
    # shellcheck disable=SC1091
    set -a && source "${SCRIPT_DIR}/../../.env.workspace" && set +a
fi

# Required environment variables
: "${DOCKER_NETWORK_INTERNAL:?DOCKER_NETWORK_INTERNAL must be set (source .env.workspace)}"
: "${PHYSICAL_REPO_ROOT:?PHYSICAL_REPO_ROOT must be set (source .env.workspace)}"

# Export for docker-compose
export DOCKER_NETWORK_INTERNAL
export PHYSICAL_REPO_ROOT

# Check if services are already running
if docker ps --filter "name=mailpit" --format "{{.Names}}" | grep -q "mailpit"; then
    log_warn "Mock services already running"
    docker ps --filter "name=mailpit" --filter "name=mock-geoip" --filter "name=mock-netcup" --format "table {{.Names}}\t{{.Status}}"
    exit 0
fi

log_info "Starting mock services..."
docker compose up -d

# Wait for services if requested
if [[ "${1:-}" == "--wait" ]]; then
    log_info "Waiting for services to be healthy..."
    
    for i in {1..30}; do
        all_healthy=true
        
        for service in mailpit mock-geoip mock-netcup-api; do
            status=$(docker inspect --format='{{.State.Health.Status}}' "$service" 2>/dev/null || echo "starting")
            if [[ "$status" != "healthy" ]]; then
                all_healthy=false
            fi
        done
        
        if $all_healthy; then
            break
        fi
        
        sleep 1
    done
    
    if $all_healthy; then
        log_success "All services healthy"
    else
        log_warn "Some services may not be fully ready"
    fi
fi

# Show status
echo ""
docker ps --filter "name=mailpit" --filter "name=mock-geoip" --filter "name=mock-netcup" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo ""
log_success "Mock services started. Access via container hostnames:"
echo "  - Mailpit API:      http://mailpit:8025"
echo "  - Mailpit SMTP:     mailpit:1025"
echo "  - Mock GeoIP:       http://mock-geoip:5556"
echo "  - Mock Netcup API:  http://mock-netcup-api:5555"
