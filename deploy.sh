#!/bin/bash
set -euo pipefail

# ============================================================================
# Unified Deployment Script
# ============================================================================
# Handles both local and webhosting deployments with proper phase handling:
#
# Usage:
#   ./deploy.sh                    # Deploy to local with mocks (default)
#   ./deploy.sh local              # Deploy to local with mocks
#   ./deploy.sh local --mode live  # Deploy to local using live services
#   ./deploy.sh webhosting         # Deploy to webhosting (live mode)
#   ./deploy.sh local --skip-tests # Deploy without running tests
#   ./deploy.sh local --tests-only # Skip build, just run tests
#   ./deploy.sh local --https      # Use TLS proxy for HTTPS testing
#
# Modes:
#   mock  - Use mocked services (Netcup API, SMTP, GeoIP) - default for local
#   live  - Use real services (from config) - default for webhosting
#
# Phases:
#   0. Infrastructure - Start Playwright, TLS proxy, mock services
#   1. Build          - Create deploy.zip with fresh database
#   2. Deploy         - Extract locally or upload to webhosting
#   3. Start          - Start Flask (local) or restart Passenger (webhosting)
#   4. Auth           - Run auth test to change default password
#   5. Tests          - Run full test suite via Playwright container
#   6. Screenshots    - Capture ALL UI pages (admin + client portal)
#
# Configuration:
#   DEPLOYMENT_TARGET env var or first argument: "local" or "webhosting"
#   DEPLOYMENT_MODE env var or --mode flag: "mock" or "live"
#   All credentials from deployment_state.json (no .env files)
# ============================================================================

# Source workspace environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/.env.workspace" ]]; then
    source "${SCRIPT_DIR}/.env.workspace"
fi

# Source service names (central configuration)
if [[ -f "${SCRIPT_DIR}/.env.services" ]]; then
    source "${SCRIPT_DIR}/.env.services"
fi

: "${REPO_ROOT:=${SCRIPT_DIR}}"
export REPO_ROOT

# Map service names to container names (from .env.services)
CONTAINER_PLAYWRIGHT="${SERVICE_PLAYWRIGHT:?missing SERVICE_PLAYWRIGHT}"
CONTAINER_REVERSE_PROXY="${SERVICE_REVERSE_PROXY:?missing SERVICE_REVERSE_PROXY}"
CONTAINER_MAILPIT="${SERVICE_MAILPIT:?missing SERVICE_MAILPIT}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Parse arguments
DEPLOYMENT_TARGET="${1:-local}"

# Handle --help and --stop first (before shift)
if [[ "$DEPLOYMENT_TARGET" == "--help" ]] || [[ "$DEPLOYMENT_TARGET" == "-h" ]]; then
    cat << 'EOF'
Unified Deployment Script for Netcup API Filter

USAGE:
    ./deploy.sh [TARGET] [OPTIONS]

TARGETS:
    local        Deploy to local environment (default)
    webhosting   Deploy to remote webhosting server

OPTIONS:
    --mode MODE        Set service mode: "mock" or "live" (default: mock for local, live for webhosting)
    --skip-tests       Deploy without running test suite
    --skip-screenshots Skip screenshot capture phase
    --skip-build       Skip build phase (use existing deploy.zip)
    --skip-infra       Skip infrastructure setup (Playwright, mock services)
    --tests-only       Skip build/deploy, run tests only (implies --skip-build)
    --http             Disable TLS proxy, use plain HTTP (default: HTTPS via TLS proxy)
    --stop             Stop all deployment services and clean up containers
    -h, --help         Show this help message

EXAMPLES:
    ./deploy.sh                          # Local deployment with mocks + HTTPS (default)
    ./deploy.sh local                    # Same as above
    ./deploy.sh local --mode live        # Local deployment using real services
    ./deploy.sh local --skip-tests       # Deploy locally without tests
    ./deploy.sh local --tests-only       # Run tests only (no rebuild)
    ./deploy.sh local --http             # Local with plain HTTP (no TLS proxy)
    ./deploy.sh --stop                   # Stop all services and clean up
    ./deploy.sh webhosting               # Deploy to production webhosting
    ./deploy.sh webhosting --skip-tests  # Deploy to production without tests

DEPLOYMENT PHASES:
    0. Infrastructure  Start Playwright container, TLS proxy (default), mock services (if mock mode)
    1. Build           Create deploy.zip with fresh database and vendored dependencies
    2. Deploy          Extract locally or upload to webhosting
    3. Start           Start Flask (local) or restart Passenger (webhosting)
    4. Journey         Run journey tests (fresh deployment documentation + auth)
    5. Tests           Run validation test suite
    6. Screenshots     Capture all UI pages for documentation

CONFIGURATION:
    State files:       deployment_state_local.json, deployment_state_webhosting.json
    Environment:       .env.defaults (defaults), .env.workspace (workspace config)
    TLS Proxy:         tooling/reverse-proxy/.env (for --https mode, sourced from .env.workspace)

MOCK SERVICES (local mock mode):
    Mailpit            SMTP testing at http://localhost:8025
    Mock Netcup API    Simulated DNS API responses
    Mock GeoIP         IP geolocation testing

For more details, see docs/DEPLOY_ARCHITECTURE.md
EOF
    exit 0
fi

# Store --stop flag to handle after functions are loaded
STOP_SERVICES_ONLY=false
if [[ "$DEPLOYMENT_TARGET" == "--stop" ]]; then
    STOP_SERVICES_ONLY=true
    # Don't exit yet - need to load functions first
fi

shift || true

SKIP_BUILD=false
SKIP_TESTS=false
SKIP_SCREENSHOTS=false
TESTS_ONLY=false
SKIP_INFRA=false
USE_HTTPS=true  # HTTPS is default for local deployments
DEPLOYMENT_MODE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-tests)
            SKIP_TESTS=true
            shift
            ;;
        --skip-screenshots)
            SKIP_SCREENSHOTS=true
            shift
            ;;
        --skip-build)
            SKIP_BUILD=true
            shift
            ;;
        --skip-infra)
            SKIP_INFRA=true
            shift
            ;;
        --tests-only)
            TESTS_ONLY=true
            SKIP_BUILD=true
            shift
            ;;
        --mode)
            DEPLOYMENT_MODE="$2"
            shift 2
            ;;
        --http)
            USE_HTTPS=false
            shift
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# Validate target (skip if --stop mode)
if [[ "$STOP_SERVICES_ONLY" != "true" ]]; then
    if [[ "$DEPLOYMENT_TARGET" != "local" && "$DEPLOYMENT_TARGET" != "webhosting" ]]; then
        echo -e "${RED}ERROR: Invalid DEPLOYMENT_TARGET: $DEPLOYMENT_TARGET${NC}" >&2
        echo "Must be 'local' or 'webhosting'" >&2
        exit 1
    fi
fi

# Set default mode based on target
if [[ -z "$DEPLOYMENT_MODE" ]]; then
    if [[ "$DEPLOYMENT_TARGET" == "local" ]]; then
        DEPLOYMENT_MODE="mock"
    else
        DEPLOYMENT_MODE="live"
    fi
fi

# Validate mode
if [[ "$DEPLOYMENT_MODE" != "mock" && "$DEPLOYMENT_MODE" != "live" ]]; then
    echo -e "${RED}ERROR: Invalid DEPLOYMENT_MODE: $DEPLOYMENT_MODE${NC}" >&2
    echo "Must be 'mock' or 'live'" >&2
    exit 1
fi

export DEPLOYMENT_TARGET
export DEPLOYMENT_MODE

# ============================================================================
# Load Configuration from .env.defaults (Single Source of Truth)
# ============================================================================

load_env_defaults() {
    local env_file="${REPO_ROOT}/.env.defaults"
    if [[ -f "$env_file" ]]; then
        # Export only variable assignments, skip functions and control structures
        # Use a temp file to avoid process substitution EOF issues
        local temp_env=$(mktemp)
        grep -v '^#' "$env_file" | \
            grep -v '^$' | \
            grep '=' | \
            grep -vE '^\s*(if|then|else|fi|function|{|}|\()' > "$temp_env" || true
        if [[ -s "$temp_env" ]]; then
            set -a
            source "$temp_env"
            set +a
        fi
        rm -f "$temp_env"
    fi
}

# Only load env if not in --stop mode
if [[ "$STOP_SERVICES_ONLY" != "true" ]]; then
    load_env_defaults
fi

# Load TLS proxy config if available
load_proxy_config() {
    local proxy_env="${REPO_ROOT}/tooling/reverse-proxy/.env"
    if [[ -f "$proxy_env" ]]; then
        # Use a temp file to avoid process substitution EOF issues
        local temp_env=$(mktemp)
        grep -v '^#' "$proxy_env" | grep -v '^$' | grep '=' > "$temp_env" || true
        if [[ -s "$temp_env" ]]; then
            set -a
            source "$temp_env"
            set +a
        fi
        rm -f "$temp_env"
    fi
}

# ============================================================================
# Configuration per target (Config-Driven - NO HARDCODED VALUES)
# ============================================================================

# Skip all configuration for --stop mode
if [[ "$STOP_SERVICES_ONLY" != "true" ]]; then

# Default ports from .env.defaults (must be set there)
LOCAL_FLASK_PORT="${LOCAL_FLASK_PORT:?LOCAL_FLASK_PORT not set - check .env.defaults}"
WEBHOSTING_URL="${WEBHOSTING_URL:?WEBHOSTING_URL not set - check .env.defaults}"

case "$DEPLOYMENT_TARGET" in
    local)
        DEPLOY_DIR="${REPO_ROOT}/deploy-local"
        STATE_FILE="${REPO_ROOT}/deployment_state_local.json"
        SCREENSHOT_DIR="${DEPLOY_DIR}/screenshots"
        LOG_DIR="${REPO_ROOT}/tmp"
        LOG_FILE="${LOG_DIR}/local_app.log"
        
        # Get devcontainer hostname for Playwright container to connect
        DEVCONTAINER_HOSTNAME=$(hostname)
        
        # Determine URL based on --https flag (explicit only)
        # Note: LOCAL_USE_HTTPS from .env.defaults is IGNORED unless --https flag used
        if [[ "$USE_HTTPS" == "true" ]]; then
            load_proxy_config
            LOCAL_TLS_DOMAIN="${LOCAL_TLS_DOMAIN:?LOCAL_TLS_DOMAIN not set - check tooling/reverse-proxy/.env}"
            LOCAL_TLS_BIND_HTTPS="${LOCAL_TLS_BIND_HTTPS:?LOCAL_TLS_BIND_HTTPS not set - check tooling/reverse-proxy/.env}"
            UI_BASE_URL="https://${LOCAL_TLS_DOMAIN}:${LOCAL_TLS_BIND_HTTPS}"
        else
            # Use devcontainer hostname so Playwright container can connect
            UI_BASE_URL="http://${DEVCONTAINER_HOSTNAME}:${LOCAL_FLASK_PORT}"
        fi
        
        # Same deploy.zip for both targets - reduces drift
        BUILD_ARGS="--local --build-dir deploy --output deploy.zip"
        ZIP_FILE="${REPO_ROOT}/deploy.zip"
        ;;
    webhosting)
        DEPLOY_DIR="${REPO_ROOT}/deploy"
        STATE_FILE="${REPO_ROOT}/deployment_state_webhosting.json"
        SCREENSHOT_DIR="${REPO_ROOT}/deploy-local/screenshots"
        LOG_DIR="${REPO_ROOT}/tmp"
        UI_BASE_URL="${WEBHOSTING_URL}"
        # Same deploy.zip for both targets - reduces drift
        BUILD_ARGS="--target webhosting --build-dir deploy --output deploy.zip"
        ZIP_FILE="${REPO_ROOT}/deploy.zip"
        
        # Webhosting connection details (must be set in .env.defaults)
        NETCUP_USER="${NETCUP_SSH_USER:?NETCUP_SSH_USER not set - check .env.defaults}"
        NETCUP_SERVER="${NETCUP_SSH_HOST:?NETCUP_SSH_HOST not set - check .env.defaults}"
        REMOTE_DIR="${NETCUP_REMOTE_DIR:?NETCUP_REMOTE_DIR not set - check .env.defaults}"
        SSHFS_MOUNT="/home/vscode/sshfs-${NETCUP_USER}@${NETCUP_SERVER}"
        ;;
esac

mkdir -p "$LOG_DIR" "$SCREENSHOT_DIR"

fi  # End of STOP_SERVICES_ONLY check

# ============================================================================
# Utility functions
# ============================================================================

log_phase() {
    local phase="$1"
    local description="$2"
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  Phase ${phase}: ${description}${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

log_step() {
    echo -e "${BLUE}→ $1${NC}"
}

log_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

log_error() {
    echo -e "${RED}✗ $1${NC}" >&2
}

check_playwright_container() {
    docker ps --filter "name=${CONTAINER_PLAYWRIGHT}" --filter "status=running" | grep -q "${CONTAINER_PLAYWRIGHT}"
}

get_devcontainer_hostname() {
    hostname
}

read_state_value() {
    local key="$1"
    local state_file="${2:-$STATE_FILE}"
    
    if [[ ! -f "$state_file" ]]; then
        echo ""
        return
    fi
    
    python3 -c "
import json
with open('$state_file') as f:
    data = json.load(f)
# Navigate nested keys like 'admin.password'
keys = '$key'.split('.')
val = data
for k in keys:
    val = val.get(k, '') if isinstance(val, dict) else ''
print(val)
" 2>/dev/null || echo ""
}

update_state_value() {
    local key="$1"
    local value="$2"
    local state_file="${3:-$STATE_FILE}"
    
    python3 -c "
import json
from datetime import datetime, timezone

with open('$state_file') as f:
    data = json.load(f)

# Navigate nested keys like 'admin.password'
keys = '$key'.split('.')
target = data
for k in keys[:-1]:
    target = target.setdefault(k, {})
target[keys[-1]] = '$value'

# Update metadata
data['last_updated_at'] = datetime.now(timezone.utc).isoformat()
data['updated_by'] = 'deploy.sh'

with open('$state_file', 'w') as f:
    json.dump(data, f, indent=2)
"
}

stop_flask() {
    log_step "Stopping any running Flask/gunicorn processes..."
    pkill -9 gunicorn 2>/dev/null || true
    sleep 1
}

start_flask_local() {
    stop_flask
    
    local flask_env_desc="mock mode"
    local mock_api="true"
    
    if [[ "$DEPLOYMENT_MODE" == "live" ]]; then
        flask_env_desc="live mode (real services)"
        mock_api="false"
    fi
    
    log_step "Starting Flask (local deployment, ${flask_env_desc})..."
    cd "$DEPLOY_DIR"
    
    # Copy gunicorn config if available
    if [[ -f "${SCRIPT_DIR}/gunicorn.conf.py" ]]; then
        cp "${SCRIPT_DIR}/gunicorn.conf.py" "${DEPLOY_DIR}/"
    fi
    
    NETCUP_FILTER_DB_PATH="${DEPLOY_DIR}/netcup_filter.db" \
    FLASK_ENV=local_test \
    TEMPLATES_AUTO_RELOAD=true \
    SEND_FILE_MAX_AGE_DEFAULT=0 \
    SECRET_KEY="local-test-secret-key-for-session-persistence" \
    MOCK_NETCUP_API="${mock_api}" \
    DEPLOYMENT_MODE="${DEPLOYMENT_MODE}" \
    SEED_DEMO_CLIENTS=true \
    GUNICORN_WORKERS=2 \
    GUNICORN_THREADS=4 \
    GUNICORN_RELOAD=true \
    GUNICORN_LOGLEVEL=debug \
    gunicorn -c gunicorn.conf.py \
        --daemon \
        --log-file "$LOG_FILE" \
        --error-logfile "$LOG_FILE" \
        --access-logfile "$LOG_FILE" \
        passenger_wsgi:application
    
    # Wait for Flask
    log_step "Waiting for Flask to start..."
    for i in {1..30}; do
        if curl -s "http://localhost:${LOCAL_FLASK_PORT}/admin/login" > /dev/null 2>&1; then
            log_success "Flask ready on http://localhost:${LOCAL_FLASK_PORT}"
            return 0
        fi
        sleep 1
    done
    
    log_error "Flask failed to start - check $LOG_FILE"
    tail -20 "$LOG_FILE" 2>/dev/null || true
    return 1
}

run_in_playwright() {
    local cmd="$*"
    
    if check_playwright_container; then
        local devcontainer_hostname
        devcontainer_hostname=$(get_devcontainer_hostname)
        
        # Export environment for container (config-driven URLs)
        if [[ "$USE_HTTPS" == "true" ]]; then
            export UI_BASE_URL="${UI_BASE_URL}"  # Already set to HTTPS URL
        else
            export UI_BASE_URL="http://${devcontainer_hostname}:${LOCAL_FLASK_PORT}"
        fi
        [[ "$DEPLOYMENT_TARGET" == "webhosting" ]] && export UI_BASE_URL="${WEBHOSTING_URL}"
        export SCREENSHOT_DIR="$SCREENSHOT_DIR"
        export DEPLOYMENT_TARGET="$DEPLOYMENT_TARGET"
        export DEPLOYMENT_MODE="$DEPLOYMENT_MODE"
        export DEPLOYMENT_STATE_FILE="$STATE_FILE"
        
        # Source service names from .env.services for tests
        # Tests need SERVICE_MAILPIT to restore correct hostname after email config tests
        if [[ -f "${REPO_ROOT}/.env.services" ]]; then
            set -a
            source "${REPO_ROOT}/.env.services"
            set +a
            export SERVICE_MAILPIT
        fi
        
        # Source Mailpit credentials from container config (NO HARDCODED DEFAULTS)
        if [[ -f "${REPO_ROOT}/tooling/mailpit/.env" ]]; then
            set -a  # Export all variables
            source "${REPO_ROOT}/tooling/mailpit/.env"
            set +a
            # Explicitly export Mailpit variables for docker exec
            export MAILPIT_USERNAME
            export MAILPIT_PASSWORD
            # MAILPIT_API_URL from .env.services (centralized service names)
            export MAILPIT_API_URL
        fi
        
        # Load credentials from state file
        if [[ -f "$STATE_FILE" ]]; then
            export DEPLOYED_ADMIN_USERNAME=$(read_state_value "admin.username")
            export DEPLOYED_ADMIN_PASSWORD=$(read_state_value "admin.password")
            local primary_client
            primary_client=$(python3 -c "
import json
with open('$STATE_FILE') as f:
    data = json.load(f)
clients = data.get('clients', [])
primary = next((c for c in clients if c.get('is_primary')), clients[0] if clients else {})
print(primary.get('client_id', ''))
print(primary.get('secret_key', ''))
" 2>/dev/null | head -2)
            export DEPLOYED_CLIENT_ID=$(echo "$primary_client" | head -1)
            export DEPLOYED_CLIENT_SECRET_KEY=$(echo "$primary_client" | tail -1)
        fi
        
        "${REPO_ROOT}/tooling/playwright/playwright-exec.sh" $cmd
    else
        log_warning "Playwright container not running - using local execution"
        
        export UI_BASE_URL="http://localhost:${LOCAL_FLASK_PORT}"
        [[ "$DEPLOYMENT_TARGET" == "webhosting" ]] && export UI_BASE_URL="${WEBHOSTING_URL}"
        export SCREENSHOT_DIR="$SCREENSHOT_DIR"
        export DEPLOYMENT_TARGET="$DEPLOYMENT_TARGET"
        export DEPLOYMENT_STATE_FILE="$STATE_FILE"
        
        cd "$REPO_ROOT"
        $cmd
    fi
}

# ============================================================================
# Phase 0: Infrastructure Setup
# ============================================================================

start_playwright_container() {
    log_step "Starting Playwright container..."
    if check_playwright_container; then
        log_success "Playwright container already running"
        return 0
    fi
    
    if [[ -f "${REPO_ROOT}/tooling/playwright/start-playwright.sh" ]]; then
        (cd "${REPO_ROOT}/tooling/playwright" && ./start-playwright.sh)
        
        # Wait for container to be ready
        for i in {1..30}; do
            if check_playwright_container; then
                log_success "Playwright container ready"
                return 0
            fi
            sleep 1
        done
        log_error "Playwright container failed to start"
        return 1
    else
        log_error "Playwright start script not found"
        return 1
    fi
}

start_mock_services() {
    log_step "Starting mock services (Mailpit, Mock Netcup API, Mock GeoIP)..."
    
    # Start Mailpit
    if [[ -d "${REPO_ROOT}/tooling/mailpit" ]]; then
        (cd "${REPO_ROOT}/tooling/mailpit" && docker compose up -d 2>/dev/null) || log_warning "Mailpit start failed (may already be running)"
    fi
    
    # Start Mock Netcup API
    if [[ -d "${REPO_ROOT}/tooling/netcup-api-mock" ]]; then
        (cd "${REPO_ROOT}/tooling/netcup-api-mock" && docker compose up -d 2>/dev/null) || log_warning "Mock Netcup API start failed (may already be running)"
    fi
    
    # Start Mock GeoIP
    if [[ -d "${REPO_ROOT}/tooling/geoip-mock" ]]; then
        (cd "${REPO_ROOT}/tooling/geoip-mock" && docker compose up -d 2>/dev/null) || log_warning "Mock GeoIP start failed (may already be running)"
    fi
    
    log_success "Mock services started"
}

stop_mock_services() {
    log_step "Stopping mock services..."
    (cd "${REPO_ROOT}/tooling/mailpit" && docker compose down 2>/dev/null) || true
    (cd "${REPO_ROOT}/tooling/netcup-api-mock" && docker compose down 2>/dev/null) || true
    (cd "${REPO_ROOT}/tooling/geoip-mock" && docker compose down 2>/dev/null) || true
}

start_powerdns_backend() {
    log_step "Starting PowerDNS backend..."
    
    local powerdns_dir="${REPO_ROOT}/tooling/backend-powerdns"
    
    if [[ ! -d "${powerdns_dir}" ]]; then
        log_warning "PowerDNS backend not configured (${powerdns_dir} not found)"
        return 0
    fi
    
    # Check if API key is set
    source "${REPO_ROOT}/.env.defaults"
    if [[ -z "${POWERDNS_API_KEY:-}" ]]; then
        log_warning "PowerDNS API key not set (POWERDNS_API_KEY in .env.defaults)"
        log_step "Generate key: openssl rand -hex 32"
        return 0
    fi
    
    # Create data directory if missing
    mkdir -p "${powerdns_dir}/data"
    
    # Start container
    (cd "${powerdns_dir}" && docker compose up -d 2>/dev/null) || log_warning "PowerDNS start failed (may already be running)"
    
    # Wait for health check
    local waited=0
    while [[ $waited -lt 10 ]]; do
        if docker ps --filter "name=${SERVICE_POWERDNS:-naf-dev-powerdns}" --filter "health=healthy" | grep -q "${SERVICE_POWERDNS:-naf-dev-powerdns}"; then
            log_success "PowerDNS backend ready"
            return 0
        fi
        sleep 1
        waited=$((waited + 1))
    done
    
    log_warning "PowerDNS health check timeout (container may still be starting)"
}

stop_powerdns_backend() {
    log_step "Stopping PowerDNS backend..."
    (cd "${REPO_ROOT}/tooling/backend-powerdns" && docker compose down 2>/dev/null) || true
}

start_tls_proxy() {
    log_step "Starting TLS proxy (nginx with Let's Encrypt certs)..."
    
    local proxy_dir="${REPO_ROOT}/tooling/reverse-proxy"
    
    if [[ ! -f "${proxy_dir}/.env" ]]; then
        log_error "TLS proxy not configured: ${proxy_dir}/.env not found"
        log_step "Run: ./detect-fqdn.sh --update-workspace"
        return 1
    fi
    
    # Auto-detect PUBLIC_FQDN if not already in .env.workspace
    if [[ ! -f "${REPO_ROOT}/.env.workspace" ]] || ! grep -q "PUBLIC_FQDN" "${REPO_ROOT}/.env.workspace"; then
        log_step "Auto-detecting PUBLIC_FQDN via reverse DNS..."
        if "${REPO_ROOT}/detect-fqdn.sh" --update-workspace; then
            log_success "PUBLIC_FQDN detected and saved to .env.workspace"
        else
            log_warning "FQDN detection failed - using localhost as fallback"
        fi
    fi
    
    # Load workspace environment (now guaranteed to exist with PUBLIC_FQDN)
    source "${REPO_ROOT}/.env.workspace"
    
    # Render nginx config from template
    if [[ -f "${proxy_dir}/render-nginx-conf.sh" ]]; then
        log_step "Rendering nginx configuration..."
        (cd "${proxy_dir}" && ./render-nginx-conf.sh) || {
            log_error "Failed to render nginx config"
            return 1
        }
    fi
    
    # Export required variables for docker-compose (from .env.workspace)
    export PHYSICAL_REPO_ROOT="${PHYSICAL_REPO_ROOT:?PHYSICAL_REPO_ROOT must be set}"
    export DOCKER_GID="${DOCKER_GID:?DOCKER_GID must be set}"
    export PUBLIC_FQDN="${PUBLIC_FQDN:?PUBLIC_FQDN must be set}"
    
    # CRITICAL: Certificate accessibility check
    # Devcontainer CANNOT access /etc/letsencrypt (host filesystem isolation)
    # nginx container CAN access via docker group mount (user: 0:${DOCKER_GID})
    # TLS certificate verification happens implicitly during nginx startup:
    # - If certs missing/unreadable: nginx fails immediately with clear error
    # - If certs valid: nginx starts successfully and serves HTTPS
    # - Devcontainer cannot check HOST /etc/letsencrypt (filesystem isolation)
    # - nginx container reads via docker group (GID ${DOCKER_GID})
    
    log_step "Starting TLS proxy (will fail if certs inaccessible)..."
    log_step "(Certificates: /etc/letsencrypt/live/${PUBLIC_FQDN}/ on HOST, read via docker group)"
    
    # We'll verify by starting nginx - if certs are missing/unreadable, nginx will fail
    # with clear error. No need for devcontainer to check what it cannot access.
    
    # Start proxy via docker-compose
    if [[ -f "${proxy_dir}/docker-compose.yml" ]]; then
        log_step "Starting TLS proxy container..."
        if docker ps | grep -q "${CONTAINER_REVERSE_PROXY}"; then
            log_step "TLS proxy already running - restarting..."
            (cd "${proxy_dir}" && docker compose --env-file .env restart) || {
                log_error "Failed to restart TLS proxy"
                return 1
            }
        else
            (cd "${proxy_dir}" && docker compose --env-file .env up -d) || {
                log_error "Failed to start TLS proxy"
                return 1
            }
        fi
        
        # Wait for proxy to be ready
        local proxy_url="${UI_BASE_URL}/admin/login"
        log_step "Waiting for TLS proxy at ${proxy_url}..."
        
        # Give nginx a moment to start (bind ports, load config)
        sleep 2
        
        for i in {1..60}; do
            if curl -sk "${proxy_url}" > /dev/null 2>&1; then
                log_success "TLS proxy ready at ${proxy_url}"
                # Extra 2 seconds for stability (ensure backend is fully responsive)
                sleep 2
                return 0
            fi
            sleep 1
        done
        
        # After 60 seconds, check if proxy is running but backend unreachable
        if docker ps | grep -q "${CONTAINER_REVERSE_PROXY}"; then
            log_error "TLS proxy running but not responsive at ${proxy_url}"
            log_error "Check: docker logs ${CONTAINER_REVERSE_PROXY}"
        else
            log_error "TLS proxy container not running"
        fi
        return 1
    else
        log_error "TLS proxy docker-compose.yml not found"
        return 1
    fi
}

stop_tls_proxy() {
    log_step "Stopping TLS proxy..."
    local proxy_dir="${REPO_ROOT}/tooling/reverse-proxy"
    if [[ -f "${proxy_dir}/docker-compose.yml" ]]; then
        (cd "${proxy_dir}" && docker compose --env-file .env down 2>/dev/null) || true
    fi
}

phase_infrastructure() {
    log_phase "0" "Infrastructure Setup"
    
    if [[ "$SKIP_INFRA" == "true" ]]; then
        log_warning "Skipping infrastructure setup (--skip-infra)"
        return 0
    fi
    
    # Always start Playwright for tests and screenshots
    if [[ "$SKIP_TESTS" == "false" ]] || [[ "$SKIP_SCREENSHOTS" == "false" ]]; then
        start_playwright_container || {
            log_error "Failed to start Playwright - tests and screenshots will fail"
            return 1
        }
    fi
    
    # Start mock services BEFORE TLS proxy (nginx config references naf-dev-mailpit)
    if [[ "$DEPLOYMENT_MODE" == "mock" && "$DEPLOYMENT_TARGET" == "local" ]]; then
        start_mock_services
    fi
    
    # Start PowerDNS backend (optional - skip if not configured)
    if [[ "$DEPLOYMENT_TARGET" == "local" ]]; then
        start_powerdns_backend
    fi
    
    # Start TLS proxy for HTTPS mode (default for local, use --http to disable)
    # MUST come after mock services so nginx can resolve upstream hostnames
    if [[ "$USE_HTTPS" == "true" && "$DEPLOYMENT_TARGET" == "local" ]]; then
        start_tls_proxy || {
            log_error "Failed to start TLS proxy - HTTPS testing will fail"
            log_step "Use --http flag to skip TLS proxy if certificates not available"
            return 1
        }
    fi
    
    log_success "Infrastructure ready"
}

# ============================================================================
# Phase 1: Build
# ============================================================================

phase_build() {
    log_phase "1" "Build Deployment Package"
    
    if [[ "$SKIP_BUILD" == "true" ]]; then
        log_warning "Skipping build (--skip-build or --tests-only)"
        return 0
    fi
    
    log_step "Running build_deployment.py $BUILD_ARGS..."
    cd "$REPO_ROOT"
    python3 build_deployment.py $BUILD_ARGS 2>&1 | tail -20
    
    log_success "Build complete: $ZIP_FILE"
}

# ============================================================================
# Phase 2: Deploy
# ============================================================================

phase_deploy() {
    log_phase "2" "Deploy"
    
    if [[ "$TESTS_ONLY" == "true" ]]; then
        log_warning "Skipping deploy (--tests-only)"
        return 0
    fi
    
    case "$DEPLOYMENT_TARGET" in
        local)
            log_step "Extracting to $DEPLOY_DIR..."
            
            rm -rf "$DEPLOY_DIR" 2>/dev/null || true
            mkdir -p "$DEPLOY_DIR/tmp" "$SCREENSHOT_DIR"
            unzip -o -q "$ZIP_FILE" -d "$DEPLOY_DIR/"
            
            # Fix database permissions
            chmod 666 "$DEPLOY_DIR/netcup_filter.db" 2>/dev/null || true
            chmod 777 "$DEPLOY_DIR" 2>/dev/null || true
            
            # Restart Flask to pick up new files
            stop_flask
            log_step "Flask will be started in Phase 3..."
            
            log_success "Deployed to $DEPLOY_DIR"
            ;;
            
        webhosting)
            log_step "Uploading to ${NETCUP_SERVER}..."
            scp "$ZIP_FILE" "${NETCUP_USER}@${NETCUP_SERVER}:/"
            
            log_step "Extracting and restarting on server..."
            ssh "${NETCUP_USER}@${NETCUP_SERVER}" \
                "cd / && rm -rf ${REMOTE_DIR}/* ${REMOTE_DIR}/.[!.]* ${REMOTE_DIR}/..?* && \
                 mkdir -p ${REMOTE_DIR}/tmp/ && \
                 unzip -o -u deploy.zip -d ${REMOTE_DIR}/ && \
                 touch ${REMOTE_DIR}/tmp/restart.txt"
            
            # State file is already created in REPO_ROOT by build_deployment.py
            # (deployment_state_webhosting.json - not deployed, contains secrets)
            log_success "State file: $STATE_FILE"
            
            log_success "Deployed to $NETCUP_SERVER"
            
            # Mount SSHFS if not already mounted
            if [[ ! -d "$SSHFS_MOUNT" ]] || ! mountpoint -q "$SSHFS_MOUNT" 2>/dev/null; then
                log_step "Mounting remote filesystem via SSHFS..."
                mkdir -p "$SSHFS_MOUNT"
                if sshfs "${NETCUP_USER}@${NETCUP_SERVER}:${REMOTE_DIR}" "$SSHFS_MOUNT" \
                     -o reconnect,ServerAliveInterval=15,ServerAliveCountMax=3 2>/dev/null; then
                    log_success "Mounted at $SSHFS_MOUNT"
                else
                    log_warning "SSHFS mount failed (non-critical)"
                fi
            else
                log_success "Remote filesystem already mounted at $SSHFS_MOUNT"
            fi
            ;;
    esac
}

# ============================================================================
# Phase 3: Start
# ============================================================================

phase_start() {
    log_phase "3" "Start Application"
    
    case "$DEPLOYMENT_TARGET" in
        local)
            if [[ "$TESTS_ONLY" == "true" ]]; then
                # Check if Flask is already running
                if curl -s "http://localhost:${LOCAL_FLASK_PORT}/admin/login" > /dev/null 2>&1; then
                    log_success "Flask already running"
                    return 0
                fi
            fi
            start_flask_local
            ;;
            
        webhosting)
            log_step "Application restarted via Passenger (touch restart.txt)"
            # Wait for the app to be ready
            log_step "Waiting for application to restart..."
            for i in {1..30}; do
                if curl -s "$UI_BASE_URL/admin/login" > /dev/null 2>&1; then
                    log_success "Application ready at $UI_BASE_URL"
                    return 0
                fi
                sleep 2
            done
            log_warning "Application may still be starting..."
            ;;
    esac
}

# ============================================================================
# Phase 4: Journey Tests (Fresh Deployment Documentation)
# ============================================================================

# Track journey test result for Phase 5 summary
JOURNEY_TESTS_RESULT=""

phase_journey() {
    log_phase "4" "Journey Tests (Fresh Deployment)"
    
    if [[ "$SKIP_TESTS" == "true" ]]; then
        log_warning "Skipping journey tests (--skip-tests)"
        JOURNEY_TESTS_RESULT="SKIPPED"
        return 0
    fi
    
    # Journey Tests run FIRST on fresh database to:
    # 1. Document the fresh deployment experience
    # 2. Perform first login with default credentials
    # 3. Complete the mandatory password change
    # 4. Capture screenshots of initial state
    # 5. Set up the admin authentication for subsequent tests
    
    log_step "Running journey tests on fresh deployment..."
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  JOURNEY TESTS: Fresh deployment documentation${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    
    if run_in_playwright pytest ui_tests/tests/test_journey_master.py -v --timeout=300 2>&1 | tail -20; then
        log_success "Journey tests passed - admin authenticated"
        JOURNEY_TESTS_RESULT="PASSED"
        
        # Refresh credentials from state file (journey tests update it)
        if [[ -f "$STATE_FILE" ]]; then
            log_step "Admin password saved to $STATE_FILE"
        fi
    else
        local exit_code=$?
        JOURNEY_TESTS_RESULT="FAILED"
        if [[ $exit_code -eq 2 ]] || [[ $exit_code -eq 4 ]]; then
            log_error "FATAL: Test infrastructure broken (exit code $exit_code)"
            return 1
        else
            log_warning "Journey tests failed (exit code $exit_code) - continuing"
        fi
    fi
}

# ============================================================================
# Phase 5: Validation Tests
# ============================================================================

phase_tests() {
    log_phase "5" "Validation Tests"
    
    if [[ "$SKIP_TESTS" == "true" ]]; then
        log_warning "Skipping tests (--skip-tests)"
        return 0
    fi
    
    local test_results=()
    local failed_suites=()
    
    # Include Journey Tests result from Phase 4
    if [[ "$JOURNEY_TESTS_RESULT" == "PASSED" ]]; then
        test_results+=("Journey Tests: PASSED")
    elif [[ "$JOURNEY_TESTS_RESULT" == "FAILED" ]]; then
        test_results+=("Journey Tests: FAILED")
        failed_suites+=("Journey Tests")
    elif [[ "$JOURNEY_TESTS_RESULT" == "SKIPPED" ]]; then
        test_results+=("Journey Tests: SKIPPED")
    fi
    
    # =========================================================================
    # Validation Tests (run after Journey Tests have authenticated)
    # These use the admin session established by Journey Tests
    # =========================================================================
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  VALIDATION TESTS: System state verification${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    
    # Define test suites with their applicability
    # Format: "suite_name|test_pattern|mode" 
    # mode: "all" (always run), "mock" (mock mode only), "live" (live mode only)
    # Note: Admin UI excludes auth_flow test since Journey Tests handle authentication
    local test_suites=(
        # Core UI validation tests (always run)
        "Admin UI|ui_tests/tests/test_admin_ui.py --deselect=ui_tests/tests/test_admin_ui.py::test_admin_authentication_flow|all"
        "API Proxy|ui_tests/tests/test_api_proxy.py|all"
        "Audit Logs|ui_tests/tests/test_audit_logs.py|all"
        "Audit Export|ui_tests/tests/test_audit_export.py|all"
        "Config Pages|ui_tests/tests/test_config_pages.py|all"
        "UI Comprehensive|ui_tests/tests/test_ui_comprehensive.py|all"
        "UI Regression|ui_tests/tests/test_ui_regression.py|all"
        "UI UX Validation|ui_tests/tests/test_ui_ux_validation.py|all"
        "UI Interactive|ui_tests/tests/test_ui_interactive.py|all"
        "UI Functional|ui_tests/tests/test_ui_functional.py|all"
        "User Journeys|ui_tests/tests/test_user_journeys.py|all"
        "Console Errors|ui_tests/tests/test_console_errors.py|all"
        "Bulk Operations|ui_tests/tests/test_bulk_operations.py|all"
        "Accessibility|ui_tests/tests/test_accessibility.py|all"
        "Mobile Responsive|ui_tests/tests/test_mobile_responsive.py|all"
        "Performance|ui_tests/tests/test_performance.py|all"
        "Security|ui_tests/tests/test_security.py|all"
        "Recovery Codes|ui_tests/tests/test_recovery_codes.py|all"
        "Registration E2E|ui_tests/tests/test_registration_e2e.py|all"
        
        # Mock-only tests (require mock services)
        "Mock API Standalone|ui_tests/tests/test_mock_api_standalone.py|mock"
        "Mock SMTP|ui_tests/tests/test_mock_smtp.py|mock"
        "Mock GeoIP|ui_tests/tests/test_mock_geoip.py|mock"
        "DDNS Quick Update|ui_tests/tests/test_ddns_quick_update.py|mock"
        
        # Live API tests (require real Netcup API configured)
        "UI Flow E2E|ui_tests/tests/test_ui_flow_e2e.py|live"
        "API Security|ui_tests/tests/test_api_security.py|live"
        "Live DNS Verification|ui_tests/tests/test_live_dns_verification.py|live"
        "Live Email Verification|ui_tests/tests/test_live_email_verification.py|live"
    )
    
    for suite in "${test_suites[@]}"; do
        IFS='|' read -r name pattern mode <<< "$suite"
        
        # Check mode applicability
        case "$mode" in
            all)
                # Always run
                ;;
            mock)
                if [[ "$DEPLOYMENT_MODE" != "mock" ]]; then
                    log_step "Skipping $name (mock mode only)"
                    test_results+=("$name: SKIPPED (mock mode only)")
                    continue
                fi
                ;;
            live)
                if [[ "$DEPLOYMENT_MODE" != "live" ]]; then
                    log_step "Skipping $name (live mode only)"
                    test_results+=("$name: SKIPPED (live mode only)")
                    continue
                fi
                ;;
        esac
        
        # Extract just the file path from pattern (first space-separated word)
        local test_file="${pattern%% *}"
        
        # Check if test file exists
        if [[ ! -f "${REPO_ROOT}/${test_file}" ]]; then
            log_warning "Skipping $name (file not found: $test_file)"
            test_results+=("$name: SKIPPED (not found)")
            continue
        fi
        
        log_step "Running $name..."
        
        if run_in_playwright pytest $pattern -v --timeout=120 2>&1 | tail -5; then
            test_results+=("$name: PASSED")
            log_success "$name passed"
        else
            test_results+=("$name: FAILED")
            failed_suites+=("$name")
            log_warning "$name failed"
        fi
    done
    
    # Summary
    echo ""
    echo -e "${CYAN}Test Results Summary:${NC}"
    for result in "${test_results[@]}"; do
        if [[ "$result" == *"PASSED"* ]]; then
            echo -e "  ${GREEN}✓ $result${NC}"
        elif [[ "$result" == *"SKIPPED"* ]]; then
            echo -e "  ${YELLOW}○ $result${NC}"
        else
            echo -e "  ${RED}✗ $result${NC}"
        fi
    done
    
    if [[ ${#failed_suites[@]} -gt 0 ]]; then
        log_warning "${#failed_suites[@]} test suite(s) failed"
        return 1
    else
        log_success "All applicable test suites passed"
    fi
}

# ============================================================================
# Phase 6: Screenshots
# ============================================================================

phase_screenshots() {
    log_phase "6" "UI Screenshots"
    
    if [[ "$SKIP_SCREENSHOTS" == "true" ]]; then
        log_warning "Skipping screenshots (--skip-screenshots)"
        return 0
    fi
    
    # Note: Journey tests (Phase 4) already capture screenshots during execution
    # This phase runs the comprehensive capture script for any additional coverage
    
    log_step "Capturing additional UI screenshots (supplementing journey captures)..."
    
    if run_in_playwright python3 ui_tests/capture_ui_screenshots.py; then
        log_success "Screenshots saved to $SCREENSHOT_DIR"
        
        # Count all screenshots (journey + comprehensive)
        local count
        count=$(find "$SCREENSHOT_DIR" -name "*.png" -o -name "*.webp" -type f 2>/dev/null | wc -l)
        log_step "Total screenshots: $count"
        
        # Show journey report if available
        if [[ -f "$SCREENSHOT_DIR/journey_report.json" ]]; then
            log_step "Journey report available: $SCREENSHOT_DIR/journey_report.json"
        fi
    else
        log_warning "Screenshot capture failed (non-critical)"
    fi
}

# ============================================================================
# Cleanup / Stop All Services
# ============================================================================

stop_all_services() {
    echo ""
    echo -e "${BLUE}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║  Stopping All Deployment Services${NC}"
    echo -e "${BLUE}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    # Source workspace environment if available
    if [[ -f "${REPO_ROOT}/.env.workspace" ]]; then
        source "${REPO_ROOT}/.env.workspace"
    fi
    
    # 1. Stop Flask backend
    log_step "Stopping Flask backend..."
    pkill -f "gunicorn.*passenger_wsgi:application" 2>/dev/null && log_success "Flask stopped" || log_step "Flask not running"
    
    # 2. Stop TLS reverse proxy
    log_step "Stopping TLS reverse proxy..."
    local proxy_dir="${REPO_ROOT}/tooling/reverse-proxy"
    if [[ -f "${proxy_dir}/docker-compose.yml" ]]; then
        (cd "${proxy_dir}" && docker compose --env-file .env down 2>/dev/null) && log_success "TLS proxy stopped" || log_step "TLS proxy not running"
    fi
    
    # 3. Stop Mailpit
    log_step "Stopping Mailpit..."
    (cd "${REPO_ROOT}/tooling/mailpit" && docker compose down 2>/dev/null) && log_success "Mailpit stopped" || log_step "Mailpit not running"
    
    # 4. Stop Mock Netcup API
    log_step "Stopping Mock Netcup API..."
    (cd "${REPO_ROOT}/tooling/netcup-api-mock" && docker compose down 2>/dev/null) && log_success "Mock Netcup API stopped" || log_step "Mock Netcup API not running"
    
    # 5. Stop Mock GeoIP
    log_step "Stopping Mock GeoIP..."
    (cd "${REPO_ROOT}/tooling/geoip-mock" && docker compose down 2>/dev/null) && log_success "Mock GeoIP stopped" || log_step "Mock GeoIP not running"
    
    # 6. Stop PowerDNS backend
    log_step "Stopping PowerDNS backend..."
    (cd "${REPO_ROOT}/tooling/backend-powerdns" && docker compose down 2>/dev/null) && log_success "PowerDNS stopped" || log_step "PowerDNS not running"
    
    # 7. Stop Playwright container
    log_step "Stopping Playwright container..."
    docker stop "${CONTAINER_PLAYWRIGHT}" 2>/dev/null && log_success "Playwright stopped" || log_step "Playwright not running"
    
    # Show remaining naf- containers (if any)
    echo ""
    local remaining
    remaining=$(docker ps --filter "name=naf-" --format "{{.Names}}" 2>/dev/null)
    if [[ -n "$remaining" ]]; then
        log_warning "Some naf- containers still running:"
        docker ps --filter "name=naf-" --format "table {{.Names}}\t{{.Status}}"
    else
        log_success "All naf- containers stopped"
    fi
    
    echo ""
    log_success "========================================="
    log_success "All services stopped"
    log_success "========================================="
    echo ""
    log_step "To restart:"
    echo "  ./deploy.sh local              # Fresh deployment with tests"
    echo "  ./deploy.sh local --skip-tests # Deployment without tests"
    echo "  ./deploy.sh local --tests-only # Tests only (reuse existing deployment)"
    echo ""
}

# ============================================================================
# Main
# ============================================================================

main() {
    echo ""
    echo -e "${BLUE}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║  Deployment: ${DEPLOYMENT_TARGET^^} (${DEPLOYMENT_MODE} mode)${NC}"
    echo -e "${BLUE}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  Target:      ${CYAN}$DEPLOYMENT_TARGET${NC}"
    echo -e "  Mode:        ${CYAN}$DEPLOYMENT_MODE${NC}"
    echo -e "  Deploy Dir:  ${CYAN}$DEPLOY_DIR${NC}"
    echo -e "  State File:  ${CYAN}$STATE_FILE${NC}"
    echo -e "  Screenshots: ${CYAN}$SCREENSHOT_DIR${NC}"
    echo -e "  Base URL:    ${CYAN}$UI_BASE_URL${NC}"
    
    local start_time=$SECONDS
    
    # Run phases (Phase 0 first!)
    phase_infrastructure || exit 1
    phase_build || exit 1
    phase_deploy || exit 1
    phase_start || exit 1
    phase_journey || true  # Continue on journey test failure
    phase_tests || true  # Continue on test failure
    phase_screenshots || true  # Continue on screenshot failure
    
    local elapsed=$((SECONDS - start_time))
    
    # Cleanup for local deployment - only stop Flask if tests ran
    # When --skip-tests is used, keep Flask running for manual testing
    # if [[ "$DEPLOYMENT_TARGET" == "local" && "$SKIP_TESTS" == "false" ]]; then
    #     stop_flask
    # fi
    
    # Final summary
    echo ""
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  ✓ Deployment Complete (${elapsed}s)${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  📁 Deployment:   $DEPLOY_DIR"
    echo -e "  📋 State:        $STATE_FILE"
    echo -e "  📸 Screenshots:  $SCREENSHOT_DIR"
    echo -e "  🌐 URL:          $UI_BASE_URL"
    echo -e "  🔧 Mode:         $DEPLOYMENT_MODE"
    
    if [[ "$DEPLOYMENT_TARGET" == "webhosting" && -d "$SSHFS_MOUNT" ]]; then
        echo -e "  🗂️  Remote FS:    $SSHFS_MOUNT"
    fi
    
    echo ""
    echo -e "${CYAN}Next steps:${NC}"
    echo "  # Re-run tests only:"
    echo "  ./deploy.sh $DEPLOYMENT_TARGET --tests-only"
    echo ""
    echo "  # Stop all services:"
    echo "  ./deploy.sh --stop"
    echo ""
    echo "  # Run specific test:"
    echo "  DEPLOYMENT_TARGET=$DEPLOYMENT_TARGET pytest ui_tests/tests/test_admin_ui.py -v"
    echo ""
    echo "  # Recapture screenshots:"
    echo "  DEPLOYMENT_TARGET=$DEPLOYMENT_TARGET python3 ui_tests/capture_ui_screenshots.py"
}

# Handle --stop flag (after all functions loaded)
if [[ "$STOP_SERVICES_ONLY" == "true" ]]; then
    stop_all_services
    exit 0
fi

# Run main (Phase 0 handles Playwright startup now)
main "$@"
