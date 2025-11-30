#!/usr/bin/env bash
set -euo pipefail

# Simple script to start Flask backend and Playwright MCP for UI validation
# This is a lightweight alternative to the full run-ui-validation.sh stack

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# Configuration
FLASK_PORT="${FLASK_PORT:-8000}"
FLASK_HOST="${FLASK_HOST:-0.0.0.0}"
DATABASE_PATH="${DATABASE_PATH:-/workspaces/netcup-api-filter/netcup_filter.db}"
MCP_HTTP_PORT="${MCP_HTTP_PORT:-8765}"
MCP_WS_PORT="${MCP_WS_PORT:-3000}"
GATEWAY_IP=$(ip route | awk '/default/ {print $3; exit}' || echo "172.17.0.1")

FLASK_PID=""
MCP_STARTED=0

cleanup() {
    log_info "Cleaning up..."
    if [[ -n "${FLASK_PID}" ]] && kill -0 "${FLASK_PID}" 2>/dev/null; then
        log_info "Stopping Flask backend (PID: ${FLASK_PID})"
        kill "${FLASK_PID}" 2>/dev/null || true
        wait "${FLASK_PID}" 2>/dev/null || true
    fi
    if [[ "${MCP_STARTED}" == "1" ]]; then
        log_info "Stopping Playwright"
        (cd tooling/playwright && docker compose down) >/dev/null 2>&1 || true
    fi
}

trap cleanup EXIT INT TERM

# Check if database exists
if [[ ! -f "${DATABASE_PATH}" ]]; then
    log_warn "Database not found at ${DATABASE_PATH}"
    log_info "Creating fresh database..."
    python - <<PY
import sys
from pathlib import Path

root = Path("${ROOT_DIR}")
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "src"))

from netcup_api_filter.database import db, create_app
from netcup_api_filter.bootstrap.seeding import seed_default_entities

app = create_app()
with app.app_context():
    db.create_all()
    seed_default_entities()
PY
        if [[ $? -ne 0 ]]; then
        log_error "Failed to create database"
        exit 1
    fi
    log_success "Database created and seeded"
fi

# Start Flask backend
log_info "Starting Flask backend on ${FLASK_HOST}:${FLASK_PORT}"
gunicorn netcup_api_filter.wsgi:app \
    -b "${FLASK_HOST}:${FLASK_PORT}" \
    --workers 1 \
    --log-level info \
    >/dev/null 2>&1 &
FLASK_PID=$!

# Wait for Flask to be ready
log_info "Waiting for Flask backend to be ready..."
for i in {1..30}; do
    if curl -s "http://127.0.0.1:${FLASK_PORT}/admin/login" >/dev/null 2>&1; then
        log_success "Flask backend is ready"
        break
    fi
    if [[ $i -eq 30 ]]; then
        log_error "Flask backend failed to start"
        exit 1
    fi
    sleep 1
done

# Start Playwright
log_info "Starting Playwright container"
cd tooling/playwright

# Start container
docker compose up -d
MCP_STARTED=1
cd "${ROOT_DIR}"

# Wait for Playwright to be ready
log_info "Waiting for Playwright container to be ready..."
for i in {1..30}; do
    if docker exec playwright python3 -c "from playwright.async_api import async_playwright; print('OK')" >/dev/null 2>&1; then
        log_success "Playwright container is ready"
        break
    fi
    if [[ $i -eq 30 ]]; then
        log_error "Playwright container failed to start"
        exit 1
    fi
    sleep 1
done

log_success "======================================"
log_success "UI Validation Stack is Ready!"
log_success "======================================"
echo
log_info "Flask Backend:    http://127.0.0.1:${FLASK_PORT}"
log_info "                  http://${GATEWAY_IP}:${FLASK_PORT}"
echo
log_info "Playwright:       Ready for exec-based testing"
log_info "                  docker exec playwright pytest /workspaces/netcup-api-filter/ui_tests/tests -v"
echo
log_info "Default Login:    admin / admin"
log_info "Test Client:      test_qweqweqwe_vi"
log_info "Test Token:       qweqweqwe-vi-readonly"
echo
log_success "Run tests: docker exec playwright pytest /workspaces/netcup-api-filter/ui_tests/tests -v"
echo
log_info "Press Ctrl+C to stop all services"
echo

# Keep script running
wait "${FLASK_PID}"
