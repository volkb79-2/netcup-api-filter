#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# DEPRECATED: This script is deprecated in favor of unified deploy.sh
# ============================================================================
# Use instead:
#   ./deploy.sh local --https         # Full deployment with HTTPS
#   ./deploy.sh local --https --skip-tests  # Deploy without tests
#   ./deploy.sh --stop                # Stop all services
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
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

echo ""
log_warn "╔════════════════════════════════════════════════════════════════════╗"
log_warn "║  DEPRECATED: start-local-https.sh                                 ║"
log_warn "║  Use unified deploy.sh instead:                                   ║"
log_warn "║    ./deploy.sh local --https                                      ║"
log_warn "╚════════════════════════════════════════════════════════════════════╝"
echo ""
sleep 3

REPO_ROOT="/workspaces/netcup-api-filter"
cd "$REPO_ROOT"

# Source workspace environment
if [[ ! -f .env.workspace ]]; then
    log_error ".env.workspace not found. Run detect-fqdn.sh first."
    exit 1
fi
source .env.workspace

log_info "Starting local HTTPS deployment..."
log_info "PUBLIC_FQDN: ${PUBLIC_FQDN}"

# Ensure deployment exists
if [[ ! -d deploy-local ]]; then
    log_error "deploy-local/ not found. Run: python3 build_deployment.py --local && unzip -q deploy.zip -d deploy-local"
    exit 1
fi

# Step 1: Start mock services
log_info "Step 1: Starting mock services..."

cd tooling/mailpit
if ! docker ps | grep -q naf-mailpit; then
    source .env
    docker compose up -d
    log_success "Mailpit started"
else
    log_info "Mailpit already running"
fi

cd ../geoip-mock
if ! docker ps | grep -q naf-mock-geoip; then
    source .env
    docker compose up -d
    log_success "GeoIP mock started"
else
    log_info "GeoIP mock already running"
fi

cd ../netcup-api-mock
if ! docker ps | grep -q naf-mock-netcup-api; then
    source .env
    docker compose up -d
    log_success "Netcup API mock started"
else
    log_info "Netcup API mock already running"
fi

cd "$REPO_ROOT"

# Step 2: Start Flask backend
log_info "Step 2: Starting Flask backend..."

# Kill any existing Flask processes
pkill -f "gunicorn.*passenger_wsgi:application" 2>/dev/null || true
sleep 1

cd deploy-local

# Start gunicorn in background
FLASK_ENV=local_test \
LOG_LEVEL=INFO \
gunicorn \
    --config ../gunicorn.conf.py \
    --bind 0.0.0.0:5100 \
    --workers 2 \
    --threads 4 \
    --timeout 120 \
    --access-logfile ../tmp/gunicorn-access.log \
    --error-logfile ../tmp/gunicorn-error.log \
    --log-level info \
    --daemon \
    passenger_wsgi:application

sleep 2

# Verify Flask is running
if curl -sf http://localhost:5100/ > /dev/null; then
    log_success "Flask backend started on :5100"
else
    log_error "Flask backend failed to start"
    tail -20 ../tmp/gunicorn-error.log
    exit 1
fi

cd "$REPO_ROOT"

# Step 3: Configure and start reverse proxy
log_info "Step 3: Starting TLS reverse proxy..."

cd tooling/reverse-proxy

# Render nginx config with current PUBLIC_FQDN
./render-nginx-conf.sh

# Export required variables for docker-compose
export PHYSICAL_REPO_ROOT="${PHYSICAL_REPO_ROOT:?PHYSICAL_REPO_ROOT must be set}"
export DOCKER_GID="${DOCKER_GID:?DOCKER_GID must be set}"
export PUBLIC_FQDN="${PUBLIC_FQDN:?PUBLIC_FQDN must be set}"

# Check if certificates exist on host
if [[ ! -d /etc/letsencrypt/live/${PUBLIC_FQDN} ]]; then
    log_warn "No Let's Encrypt certificates found at /etc/letsencrypt/live/${PUBLIC_FQDN}"
    log_warn "Proxy will start but will fail to serve HTTPS without certificates"
    log_info "To obtain certificates: sudo certbot certonly --standalone -d ${PUBLIC_FQDN}"
fi

# Start proxy (mounts real certs via PHYSICAL_REPO_ROOT and /etc/letsencrypt)
if ! docker ps | grep -q naf-reverse-proxy; then
    docker compose --env-file .env up -d
    log_success "TLS proxy started"
else
    log_info "TLS proxy already running - restarting"
    docker compose --env-file .env restart
fi

cd "$REPO_ROOT"

# Step 4: Start Playwright container (optional)
log_info "Step 4: Starting Playwright container..."

cd tooling/playwright
./start-playwright.sh

cd "$REPO_ROOT"

# Final verification
log_info "Verifying deployment..."

sleep 3

# Test HTTPS endpoint (if proxy is running)
if docker ps | grep -q naf-reverse-proxy; then
    sleep 2  # Give nginx time to fully start
    if curl -sfk "https://${PUBLIC_FQDN}/" > /dev/null; then
        log_success "HTTPS endpoint responsive: https://${PUBLIC_FQDN}/"
    else
        log_warn "HTTPS endpoint not responding"
        log_info "Check: docker logs naf-reverse-proxy"
    fi
fi

# Test HTTP endpoint
if curl -sf http://localhost:5100/ > /dev/null; then
    log_success "HTTP endpoint responsive: http://localhost:5100/"
else
    log_error "HTTP endpoint not responding"
fi

# Summary
echo ""
log_success "========================================="
log_success "Local HTTPS deployment ready!"
log_success "========================================="
echo ""
log_info "Endpoints:"
log_info "  HTTPS (public): https://${PUBLIC_FQDN}/"
log_info "  HTTP (direct):  http://localhost:5100/"
log_info "  Mailpit UI:     https://${PUBLIC_FQDN}/mailpit/ (admin:MailpitDev123!)"
echo ""
log_info "Containers running:"
docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "(NAME|naf-|devcontainer)" || true
echo ""
log_info "Logs:"
log_info "  Flask:  tail -f tmp/gunicorn-error.log"
log_info "  Proxy:  docker logs naf-reverse-proxy -f"
echo ""
log_info "To stop all services:"
log_info "  ./stop-local-https.sh"
echo ""
