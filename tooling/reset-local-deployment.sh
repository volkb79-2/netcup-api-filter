#!/usr/bin/env bash
set -euo pipefail

# Reset local deployment to fresh state
# Useful for quick iteration during testing

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Colors
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }

usage() {
    cat <<EOF
Usage: $0 [OPTIONS]

Reset local deployment to fresh state with default credentials.

Options:
  --skip-rebuild    Keep existing deployment files, only reset database
  --seed-demo       Seed demo data in database
  --no-restart      Don't restart Flask after reset

Examples:
  $0                      # Full reset: rebuild deployment and restart Flask
  $0 --skip-rebuild       # Keep deployment, only reset database
  $0 --seed-demo          # Reset with demo data seeded
EOF
}

# Parse options
SKIP_REBUILD=0
SEED_DEMO=""
NO_RESTART=0

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-rebuild)
            SKIP_REBUILD=1
            shift
            ;;
        --seed-demo)
            SEED_DEMO="--seed-demo"
            shift
            ;;
        --no-restart)
            NO_RESTART=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

cd "${WORKSPACE_DIR}"

log_info "Resetting local deployment..."

# Step 1: Stop Flask
log_info "Stopping Flask..."
"${WORKSPACE_DIR}/tooling/flask-manager.sh" stop || true

# Step 2: Rebuild or just reset database
if [[ ${SKIP_REBUILD} -eq 0 ]]; then
    log_info "Rebuilding deployment..."
    rm -rf deploy/
    python3 build_deployment.py --target local ${SEED_DEMO}
    log_success "Deployment rebuilt"
else
    log_info "Skipping rebuild (--skip-rebuild)"
    
    # Just regenerate database
    if [[ -f deploy/netcup_filter.db ]]; then
        log_warn "Removing existing database..."
        rm -f deploy/netcup_filter.db
    fi
    
    # Re-initialize database (TODO: add a standalone database init script)
    log_info "Database reset not yet implemented for --skip-rebuild"
    log_warn "Consider using full rebuild instead"
fi

# Step 3: Restart Flask
if [[ ${NO_RESTART} -eq 0 ]]; then
    log_info "Starting Flask..."
    "${WORKSPACE_DIR}/tooling/flask-manager.sh" start
    log_success "Flask started"
else
    log_info "Skipping Flask restart (--no-restart)"
fi

log_success "Local deployment reset complete"
log_info ""
log_info "Default credentials:"
log_info "  Username: admin"
log_info "  Password: admin"
log_info ""
log_info "Next steps:"
log_info "  - Run tests: ./run-local-tests.sh"
log_info "  - Check status: ./tooling/flask-manager.sh status"
log_info "  - View logs: ./tooling/flask-manager.sh logs"
