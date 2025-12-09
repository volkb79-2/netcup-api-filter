#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# DEPRECATED: This script is deprecated in favor of unified deploy.sh --stop
# ============================================================================
# Use instead:
#   ./deploy.sh --stop     # Stop all services and containers
#
# This script remains for backward compatibility but will be removed in future.
# ============================================================================

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }

echo ""
log_warn "╔════════════════════════════════════════════════════════════════════╗"
log_warn "║  DEPRECATED: stop-local-https.sh                                  ║"
log_warn "║  Use unified deploy.sh instead:                                   ║"
log_warn "║    ./deploy.sh --stop                                             ║"
log_warn "╚════════════════════════════════════════════════════════════════════╝"
echo ""
sleep 2

log_info "Stopping local HTTPS deployment..."

# Stop Flask
log_info "Stopping Flask backend..."
pkill -f "gunicorn.*passenger_wsgi:application" 2>/dev/null || true
log_success "Flask stopped"

# Stop reverse proxy
log_info "Stopping TLS reverse proxy..."
cd /workspaces/netcup-api-filter/tooling/reverse-proxy
docker compose --env-file proxy.env down 2>/dev/null || true
log_success "TLS proxy stopped"

# Stop mock services
log_info "Stopping mock services..."
cd /workspaces/netcup-api-filter/tooling/mailpit
docker compose down 2>/dev/null || true

cd /workspaces/netcup-api-filter/tooling/geoip-mock
docker compose down 2>/dev/null || true

cd /workspaces/netcup-api-filter/tooling/netcup-api-mock
docker compose down 2>/dev/null || true

log_success "Mock services stopped"

# Stop Playwright (optional)
log_info "Stopping Playwright container..."
docker stop naf-playwright 2>/dev/null || true
log_success "Playwright stopped"

cd /workspaces/netcup-api-filter

log_success "========================================="
log_success "All services stopped"
log_success "========================================="
