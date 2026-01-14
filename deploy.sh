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
#   ./deploy.sh local --failfast   # Stop immediately on first error
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
    set -a
    source "${SCRIPT_DIR}/.env.workspace"
    set +a
fi

# Source service names (central configuration)
if [[ -f "${SCRIPT_DIR}/.env.services" ]]; then
    set -a
    source "${SCRIPT_DIR}/.env.services"
    set +a
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
    --skip-journey-tests Skip Phase 4 Journey tests (recommended for --tests-only iteration after first successful run)
    --failfast         Stop on first error (do not continue after test/journey/screenshot failures)
    --profile          Print timing information per phase/suite
    --pytest-workers N Enable pytest-xdist parallelism (e.g. "auto" or "4")
    --pytest-durations N  Show N slowest tests (pytest --durations)
    --http             Disable TLS proxy, use plain HTTP (default: HTTPS via TLS proxy)
    --preserve-secret-key  Extract SECRET_KEY before deploy, restore after (webhosting only)
    --bundle-app-config    Include app-config.toml in deployment (if exists)
    --stop             Stop all deployment services and clean up containers
    -h, --help         Show this help message

EXAMPLES:
    ./deploy.sh                          # Local deployment with mocks + HTTPS (default)
    ./deploy.sh local                    # Same as above
    ./deploy.sh local --mode live        # Local deployment using real services
    ./deploy.sh local --skip-tests       # Deploy locally without tests
    ./deploy.sh local --tests-only       # Run tests only (no rebuild)
    ./deploy.sh local --tests-only --skip-journey-tests  # Faster iteration (skip Phase 4)
    ./deploy.sh local --http             # Local with plain HTTP (no TLS proxy)
    ./deploy.sh --stop                   # Stop all services and clean up
    ./deploy.sh webhosting               # Deploy to production webhosting (fresh DB)
    ./deploy.sh webhosting --skip-tests  # Deploy to production without tests
    ./deploy.sh webhosting --preserve-secret-key  # Deploy but keep existing SECRET_KEY (sessions survive)
    ./deploy.sh webhosting --bundle-app-config  # Include app-config.toml in deployment (manual config)

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
    Environment:       .env (secrets/overrides), .env.defaults (defaults skeleton), .env.workspace (workspace config)
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
SKIP_JOURNEY_TESTS=false
USE_HTTPS=true  # HTTPS is default for local deployments
DEPLOYMENT_MODE=""
PRESERVE_SECRET_KEY=false
BUNDLE_APP_CONFIG=false
FAILFAST=false
PROFILE=false
PYTEST_WORKERS=""
PYTEST_DURATIONS=""

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
        --skip-journey-tests)
            SKIP_JOURNEY_TESTS=true
            shift
            ;;
        --preserve-secret-key)
            PRESERVE_SECRET_KEY=true
            shift
            ;;
        --bundle-app-config)
            BUNDLE_APP_CONFIG=true
            shift
            ;;
        --failfast)
            FAILFAST=true
            shift
            ;;
        --profile)
            PROFILE=true
            shift
            ;;
        --pytest-workers)
            PYTEST_WORKERS="$2"
            shift 2
            ;;
        --pytest-durations)
            PYTEST_DURATIONS="$2"
            shift 2
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

export DEPLOY_FAILFAST="$FAILFAST"

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
# Load Configuration from .env + .env.defaults (Config-Driven)
# ============================================================================

load_env_files() {
    local defaults_file="${REPO_ROOT}/.env.defaults"
    local env_file="${REPO_ROOT}/.env"

    # Environment must override both .env.defaults and .env.
    # Snapshot current exported environment so we can restore it after sourcing.
    # This preserves explicit overrides like PYTEST_PROFILE_*.
    declare -A _env_snapshot=()
    local _var
    while IFS= read -r _var; do
        # Indirect expansion is safe here; variable names come from compgen -e
        _env_snapshot["${_var}"]="${!_var}"
    done < <(compgen -e)

    # Load defaults first (committed skeleton, no secrets)
    if [[ -f "${defaults_file}" ]]; then
        set -a
        source "${defaults_file}"
        set +a
    fi

    # Load secrets/overrides (gitignored, required for local/live)
    if [[ ! -f "${env_file}" ]]; then
        echo -e "${RED}ERROR: .env not found at ${env_file}${NC}" >&2
        echo "Create it by copying .env.defaults and adding secrets/overrides." >&2
        exit 1
    fi

    set -a
    source "${env_file}"
    set +a

    # Restore original environment (explicit caller overrides win)
    for _var in "${!_env_snapshot[@]}"; do
        export "${_var}=${_env_snapshot[${_var}]}"
    done
}

# Only load env if not in --stop mode
if [[ "$STOP_SERVICES_ONLY" != "true" ]]; then
    load_env_files
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

# Default ports from .env/.env.defaults (must be set)
LOCAL_FLASK_PORT="${LOCAL_FLASK_PORT:?LOCAL_FLASK_PORT not set - check .env or .env.defaults}"
WEBHOSTING_URL="${WEBHOSTING_URL:?WEBHOSTING_URL not set - check .env or .env.defaults}"

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
        # Note: LOCAL_USE_HTTPS from .env/.env.defaults is IGNORED unless --https flag used
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
        BUILD_ARGS="--target local --build-dir deploy-local --output deploy-local.zip --seed-demo"
        if [[ "${BUNDLE_APP_CONFIG}" == "true" ]]; then
            BUILD_ARGS="${BUILD_ARGS} --bundle-app-config"
        fi
        ZIP_FILE="${REPO_ROOT}/deploy-local.zip"
        ;;
    webhosting)
        DEPLOY_DIR="${REPO_ROOT}/deploy-webhosting"
        STATE_FILE="${REPO_ROOT}/deployment_state_webhosting.json"
        SCREENSHOT_DIR="${DEPLOY_DIR}/screenshots"
        LOG_DIR="${REPO_ROOT}/tmp"
        UI_BASE_URL="${WEBHOSTING_URL}"
        BUILD_ARGS="--target webhosting --build-dir deploy-webhosting --output deploy.zip --seed-demo"
        if [[ "${BUNDLE_APP_CONFIG}" == "true" ]]; then
            BUILD_ARGS="${BUILD_ARGS} --bundle-app-config"
        fi
        ZIP_FILE="${REPO_ROOT}/deploy.zip"
        
        # Webhosting connection details (must be set in .env)
        WEBHOSTING_SSH_USER="${WEBHOSTING_SSH_USER:?WEBHOSTING_SSH_USER not set - check .env}"
        WEBHOSTING_SSH_SERVER="${WEBHOSTING_SSH_HOST:?WEBHOSTING_SSH_HOST not set - check .env}"
        WEBHOSTING_REMOTE_DIR="${WEBHOSTING_REMOTE_DIR:?WEBHOSTING_REMOTE_DIR not set - check .env}"
        SSHFS_MOUNT="/home/vscode/sshfs-${WEBHOSTING_SSH_USER}@${WEBHOSTING_SSH_SERVER}"
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

format_duration_seconds() {
    local seconds="$1"
    if [[ "$seconds" -lt 60 ]]; then
        echo "${seconds}s"
        return 0
    fi
    local minutes=$((seconds / 60))
    local remaining=$((seconds % 60))
    echo "${minutes}m${remaining}s"
}

log_timing() {
    local label="$1"
    local seconds="$2"
    if [[ "${PROFILE}" == "true" ]]; then
        log_step "[TIMING] ${label}: $(format_duration_seconds "${seconds}")"
    fi
}

build_pytest_extra_args() {
    local extra=()

    if [[ -n "${PYTEST_WORKERS}" ]]; then
        extra+=("-n" "${PYTEST_WORKERS}")
    fi

    if [[ -n "${PYTEST_DURATIONS}" ]]; then
        extra+=("--durations=${PYTEST_DURATIONS}" "--durations-min=1.0")
    fi

    echo "${extra[@]}"
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

    # Fail-fast for critical config (config-driven; set in .env)
    : "${SECRET_KEY:?SECRET_KEY not set - check .env}"
    
    # Copy gunicorn config if available
    if [[ -f "${SCRIPT_DIR}/gunicorn.conf.py" ]]; then
        cp "${SCRIPT_DIR}/gunicorn.conf.py" "${DEPLOY_DIR}/"
    fi
    
    NETCUP_FILTER_DB_PATH="${DEPLOY_DIR}/netcup_filter.db" \
    FLASK_ENV=local_test \
    TEMPLATES_AUTO_RELOAD=true \
    SEND_FILE_MAX_AGE_DEFAULT=0 \
    MOCK_NETCUP_API="${mock_api}" \
    DEPLOYMENT_MODE="${DEPLOYMENT_MODE}" \
    SEED_DEMO_CLIENTS=true \
    GUNICORN_DAEMON=true \
    GUNICORN_ACCESS_LOG="$LOG_FILE" \
    GUNICORN_ERROR_LOG="$LOG_FILE" \
    gunicorn -c gunicorn.conf.py passenger_wsgi:application
    
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
    
    # Check if API key is set (loaded from .env at script start)
    if [[ -z "${POWERDNS_API_KEY:-}" ]]; then
        log_warning "PowerDNS API key not set (POWERDNS_API_KEY in .env)"
        log_step "Generate key: openssl rand -hex 32"
        return 0
    fi
    
    # Export required variables for docker compose
    export POWERDNS_API_KEY
    export SERVICE_POWERDNS
    export DOCKER_NETWORK_INTERNAL
    export PHYSICAL_REPO_ROOT
    
    # Start containers (init container runs first, then PowerDNS)
    log_step "Running init container to prepare database..."
    (cd "${powerdns_dir}" && docker compose up -d 2>/dev/null) || log_warning "PowerDNS start failed (may already be running)"
    
    # Wait for health check
    local waited=0
    while [[ $waited -lt 30 ]]; do
        if docker ps --filter "name=${SERVICE_POWERDNS:-naf-dev-powerdns}" --filter "health=healthy" | grep -q "${SERVICE_POWERDNS:-naf-dev-powerdns}"; then
            log_success "PowerDNS backend ready"
            return 0
        fi
        # Check if container is restarting (indicates failure)
        if docker ps --filter "name=${SERVICE_POWERDNS:-naf-dev-powerdns}" --format "{{.Status}}" | grep -q "Restarting"; then
            log_error "PowerDNS container is restarting (check logs: docker logs ${SERVICE_POWERDNS:-naf-dev-powerdns})"
            return 1
        fi
        sleep 1
        waited=$((waited + 1))
    done
    
    log_warning "PowerDNS health check timeout (container may still be starting)"
    log_step "Check logs: docker logs ${SERVICE_POWERDNS:-naf-dev-powerdns}"
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
        log_step "Check tooling/reverse-proxy/.env configuration"
        return 1
    fi
    
    # Load workspace environment (PUBLIC_FQDN set by post-create.sh)
    if [[ -f "${REPO_ROOT}/.env.workspace" ]]; then
        source "${REPO_ROOT}/.env.workspace"
    fi
    
    # Check for PUBLIC_FQDN
    if [[ -z "${PUBLIC_FQDN:-}" ]]; then
        log_warning "PUBLIC_FQDN not set (should be auto-detected by post-create.sh)"
        log_step "Rebuild devcontainer to regenerate .env.workspace"
        return 1
    fi
    
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
    if [[ "$FAILFAST" == "true" ]]; then
        python3 build_deployment.py $BUILD_ARGS
    else
        python3 build_deployment.py $BUILD_ARGS 2>&1 | tail -20
    fi
    
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
            # ================================================================
            # Webhosting Deployment Strategy:
            # ================================================================
            # By default, deployment replaces EVERYTHING (fresh install):
            #   - Old directory contents wiped (rm -rf)
            #   - New deployment extracted (fresh database with admin/admin)
            #   - App restarts with pristine state
            #
            # With --preserve-secret-key:
            #   - Extract SECRET_KEY from existing DB before wipe
            #   - Deploy fresh database (new admin credentials, etc.)
            #   - Restore ONLY the SECRET_KEY to new DB
            #   - Result: Fresh deployment + stable sessions (no re-login)
            # ================================================================
            
            # Extract SECRET_KEY from existing database if requested
            SAVED_SECRET_KEY=""
            if [[ "$PRESERVE_SECRET_KEY" == "true" ]]; then
                log_step "Extracting SECRET_KEY from existing database..."
                SAVED_SECRET_KEY=$(ssh "${WEBHOSTING_SSH_USER}@${WEBHOSTING_SSH_SERVER}" \
                    "python3 -c \"import sqlite3; \
                     conn = sqlite3.connect('${WEBHOSTING_REMOTE_DIR}/netcup_filter.db'); \
                     cursor = conn.cursor(); \
                     cursor.execute('SELECT value FROM settings WHERE key=\\\"secret_key\\\"'); \
                     result = cursor.fetchone(); \
                     print(result[0] if result else ''); \
                     conn.close()\" 2>/dev/null || echo ''")
                
                if [[ -n "$SAVED_SECRET_KEY" ]]; then
                    log_success "Extracted SECRET_KEY (${#SAVED_SECRET_KEY} chars)"
                else
                    log_warning "No existing SECRET_KEY found (will generate new one)"
                fi
            fi
            
            log_step "Uploading to ${WEBHOSTING_SSH_SERVER}..."
            scp "$ZIP_FILE" "${WEBHOSTING_SSH_USER}@${WEBHOSTING_SSH_SERVER}:/"
            
            log_step "Extracting and restarting on server..."
            ssh "${WEBHOSTING_SSH_USER}@${WEBHOSTING_SSH_SERVER}" \
                "cd / && rm -rf ${WEBHOSTING_REMOTE_DIR}/* ${WEBHOSTING_REMOTE_DIR}/.[!.]* ${WEBHOSTING_REMOTE_DIR}/..?* && \
                 mkdir -p ${WEBHOSTING_REMOTE_DIR}/tmp/ && \
                 unzip -o -u deploy.zip -d ${WEBHOSTING_REMOTE_DIR}/ && \
                 touch ${WEBHOSTING_REMOTE_DIR}/tmp/restart.txt"
            
            # Restore SECRET_KEY to new database if it was extracted
            if [[ "$PRESERVE_SECRET_KEY" == "true" && -n "$SAVED_SECRET_KEY" ]]; then
                log_step "Restoring SECRET_KEY to new database..."
                ssh "${WEBHOSTING_SSH_USER}@${WEBHOSTING_SSH_SERVER}" \
                    "python3 -c \"import sqlite3; \
                     from datetime import datetime; \
                     conn = sqlite3.connect('${WEBHOSTING_REMOTE_DIR}/netcup_filter.db'); \
                     cursor = conn.cursor(); \
                     cursor.execute('INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)', \
                                    ('secret_key', '${SAVED_SECRET_KEY}', datetime.now().isoformat())); \
                     conn.commit(); \
                     conn.close()\" 2>/dev/null"
                
                log_success "Restored SECRET_KEY to new database"
            fi
            
            # State file is already created in REPO_ROOT by build_deployment.py
            # (deployment_state_webhosting.json - not deployed, contains secrets)
            log_success "State file: $STATE_FILE"
            
            log_success "Deployed to $WEBHOSTING_SSH_SERVER"
            
            # Mount SSHFS if not already mounted
            if [[ ! -d "$SSHFS_MOUNT" ]] || ! mountpoint -q "$SSHFS_MOUNT" 2>/dev/null; then
                log_step "Mounting remote filesystem via SSHFS..."
                mkdir -p "$SSHFS_MOUNT"
                if sshfs "${WEBHOSTING_SSH_USER}@${WEBHOSTING_SSH_SERVER}:${WEBHOSTING_REMOTE_DIR}" "$SSHFS_MOUNT" \
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

    if [[ "$SKIP_JOURNEY_TESTS" == "true" ]]; then
        # Journey tests are primarily for first-run documentation + initial password change.
        # For iterative runs (especially --tests-only), skipping saves several minutes.
        if [[ ! -f "$STATE_FILE" ]]; then
            log_error "--skip-journey-tests requires an existing state file: $STATE_FILE"
            log_step "Run once without --skip-journey-tests to generate credentials."
            return 1
        fi
        log_warning "Skipping journey tests (--skip-journey-tests)"
        JOURNEY_TESTS_RESULT="SKIPPED"
        return 0
    fi
    
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
    
    local phase_start=$SECONDS
    local pytest_extra_args
    pytest_extra_args=$(build_pytest_extra_args)

    if [[ "$FAILFAST" == "true" ]]; then
        if run_in_playwright pytest ui_tests/tests/test_journey_master.py ${pytest_extra_args} -v --timeout=300; then
            log_success "Journey tests passed - admin authenticated"
            JOURNEY_TESTS_RESULT="PASSED"
            if [[ -f "$STATE_FILE" ]]; then
                log_step "Admin password saved to $STATE_FILE"
            fi
            log_timing "Journey tests" $((SECONDS - phase_start))
            return 0
        fi
        local exit_code=$?
        JOURNEY_TESTS_RESULT="FAILED"
        log_error "Journey tests failed (exit code $exit_code) --failfast enabled"
        log_timing "Journey tests" $((SECONDS - phase_start))
        return 1
    fi

    if run_in_playwright pytest ui_tests/tests/test_journey_master.py ${pytest_extra_args} -v --timeout=300 2>&1 | tail -20; then
        log_success "Journey tests passed - admin authenticated"
        JOURNEY_TESTS_RESULT="PASSED"
        if [[ -f "$STATE_FILE" ]]; then
            log_step "Admin password saved to $STATE_FILE"
        fi
        log_timing "Journey tests" $((SECONDS - phase_start))
        return 0
    fi

    local exit_code=$?
    JOURNEY_TESTS_RESULT="FAILED"
    if [[ $exit_code -eq 2 ]] || [[ $exit_code -eq 4 ]]; then
        log_error "FATAL: Test infrastructure broken (exit code $exit_code)"
        return 1
    fi
    log_warning "Journey tests failed (exit code $exit_code) - continuing"
    log_timing "Journey tests" $((SECONDS - phase_start))
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
    local pytest_extra_args
    pytest_extra_args=$(build_pytest_extra_args)
    local phase_start=$SECONDS
    
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
        "Backends UI|ui_tests/tests/test_backends_ui.py|all"
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
        "API Security|ui_tests/tests/test_api_security.py|all"
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
        local suite_start=$SECONDS
        
        if [[ "$FAILFAST" == "true" ]]; then
            if run_in_playwright pytest $pattern ${pytest_extra_args} -v --timeout=120; then
                test_results+=("$name: PASSED")
                log_success "$name passed"
                log_timing "$name" $((SECONDS - suite_start))
            else
                test_results+=("$name: FAILED")
                failed_suites+=("$name")
                log_error "$name failed --failfast enabled"
                log_timing "$name" $((SECONDS - suite_start))
                return 1
            fi
        elif run_in_playwright pytest $pattern ${pytest_extra_args} -v --timeout=120 2>&1 | tail -5; then
            test_results+=("$name: PASSED")
            log_success "$name passed"
            log_timing "$name" $((SECONDS - suite_start))
        else
            test_results+=("$name: FAILED")
            failed_suites+=("$name")
            log_warning "$name failed"
            log_timing "$name" $((SECONDS - suite_start))
        fi
    done

    log_timing "Phase 5 (validation tests)" $((SECONDS - phase_start))
    
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
        if [[ "$FAILFAST" == "true" ]]; then
            log_error "Screenshot capture failed --failfast enabled"
            return 1
        fi
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
    # Try docker compose first (graceful), then fallback to direct container stop
    if [[ -f "${proxy_dir}/docker-compose.yml" ]]; then
        # Source workspace environment for PUBLIC_FQDN and other required vars
        if [[ -f "${REPO_ROOT}/.env.workspace" ]]; then
            set -a
            source "${REPO_ROOT}/.env.workspace"
            set +a
        fi
        if (cd "${proxy_dir}" && docker compose --env-file .env down 2>/dev/null); then
            log_success "TLS proxy stopped"
        else
            # Fallback: stop container directly if docker compose fails (missing env vars)
            if docker stop naf-dev-reverse-proxy 2>/dev/null && docker rm naf-dev-reverse-proxy 2>/dev/null; then
                log_success "TLS proxy stopped (direct)"
            else
                log_step "TLS proxy not running"
            fi
        fi
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
    local powerdns_dir="${REPO_ROOT}/tooling/backend-powerdns"
    if [[ -d "${powerdns_dir}" && -f "${powerdns_dir}/docker-compose.yml" ]]; then
        # Load environment variables needed by docker-compose
        if [[ -f "${REPO_ROOT}/.env" ]]; then
            set -a
            source "${REPO_ROOT}/.env"
            set +a
        fi
        if [[ -f "${REPO_ROOT}/.env.services" ]]; then
            set -a
            source "${REPO_ROOT}/.env.services"
            set +a
        fi
        if [[ -f "${REPO_ROOT}/.env.workspace" ]]; then
            set -a
            source "${REPO_ROOT}/.env.workspace"
            set +a
        fi
        
        # Export required variables for docker-compose
        export POWERDNS_API_KEY SERVICE_POWERDNS DOCKER_NETWORK_INTERNAL PHYSICAL_REPO_ROOT
        export POWERDNS_CONTAINER_NAME="${SERVICE_POWERDNS}"
        export DOCKER_GID ENV_TAG
        export PDNS_AUTH_API PDNS_AUTH_WEBSERVER PDNS_AUTH_WEBSERVER_ADDRESS
        export PDNS_AUTH_WEBSERVER_PORT="${PDNS_AUTH_WEBSERVER_PORT:-8081}"
        export PDNS_AUTH_WEBSERVER_ALLOW_FROM PDNS_LAUNCH PDNS_GSQLITE3_DATABASE
        export PDNS_LOGLEVEL PDNS_LOG_DNS_QUERIES PDNS_LOG_DNS_DETAILS
        export PDNS_DISABLE_AXFR PDNS_ALLOW_AXFR_IPS
        export PDNS_DEFAULT_SOA_NAME PDNS_DEFAULT_SOA_MAIL
        
        # Stop containers (both PowerDNS and init container)
        if (cd "${powerdns_dir}" && docker compose down 2>/dev/null); then
            log_success "PowerDNS stopped"
        else
            # Fallback: stop containers directly
            if docker stop "${SERVICE_POWERDNS}" 2>/dev/null && docker rm "${SERVICE_POWERDNS}" 2>/dev/null; then
                log_success "PowerDNS stopped (direct)"
            else
                log_step "PowerDNS not running"
            fi
            # Stop init container if exists
            docker stop "${SERVICE_POWERDNS}-init" 2>/dev/null && docker rm "${SERVICE_POWERDNS}-init" 2>/dev/null || true
        fi
    else
        log_step "PowerDNS not configured (${powerdns_dir} not found)"
    fi
    
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
    if [[ "${PROFILE}" == "true" ]]; then
        echo -e "  Profile:     ${CYAN}enabled${NC}"
    fi
    if [[ -n "${PYTEST_WORKERS}" ]]; then
        echo -e "  Pytest -n:   ${CYAN}${PYTEST_WORKERS}${NC}"
    fi
    if [[ -n "${PYTEST_DURATIONS}" ]]; then
        echo -e "  Pytest durations: ${CYAN}${PYTEST_DURATIONS}${NC}"
    fi
    
    local start_time=$SECONDS
    
    # Run phases (Phase 0 first!)
    local phase_timer_start
    phase_timer_start=$SECONDS
    phase_infrastructure || exit 1
    log_timing "Phase 0 (infrastructure)" $((SECONDS - phase_timer_start))

    phase_timer_start=$SECONDS
    phase_build || exit 1
    log_timing "Phase 1 (build)" $((SECONDS - phase_timer_start))

    phase_timer_start=$SECONDS
    phase_deploy || exit 1
    log_timing "Phase 2 (deploy)" $((SECONDS - phase_timer_start))

    phase_timer_start=$SECONDS
    phase_start || exit 1
    log_timing "Phase 3 (start)" $((SECONDS - phase_timer_start))

    if [[ "$FAILFAST" == "true" ]]; then
        phase_timer_start=$SECONDS
        phase_journey || exit 1
        log_timing "Phase 4 (journey)" $((SECONDS - phase_timer_start))

        phase_timer_start=$SECONDS
        phase_tests || exit 1
        log_timing "Phase 5 (tests)" $((SECONDS - phase_timer_start))

        phase_timer_start=$SECONDS
        phase_screenshots || exit 1
        log_timing "Phase 6 (screenshots)" $((SECONDS - phase_timer_start))
    else
        phase_timer_start=$SECONDS
        phase_journey || true  # Continue on journey test failure
        log_timing "Phase 4 (journey)" $((SECONDS - phase_timer_start))

        phase_timer_start=$SECONDS
        phase_tests || true  # Continue on test failure
        log_timing "Phase 5 (tests)" $((SECONDS - phase_timer_start))

        phase_timer_start=$SECONDS
        phase_screenshots || true  # Continue on screenshot failure
        log_timing "Phase 6 (screenshots)" $((SECONDS - phase_timer_start))
    fi
    
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
