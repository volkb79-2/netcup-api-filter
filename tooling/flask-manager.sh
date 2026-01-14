#!/usr/bin/env bash
set -euo pipefail

# Flask process manager for local testing
# Provides start/stop/restart/status for Flask backend

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Source environment (fail-fast if not set)
source "${WORKSPACE_DIR}/.env.workspace"

DEPLOY_DIR="${DEPLOY_DIR:-${WORKSPACE_DIR}/deploy}"
DATABASE_PATH="${DEPLOY_DIR}/netcup_filter.db"
LOG_DIR="${WORKSPACE_DIR}/tmp"
PID_FILE="${LOG_DIR}/flask.pid"

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

usage() {
    cat <<EOF
Usage: $0 {start|stop|restart|status|logs} [OPTIONS]

Commands:
  start     Start Flask backend
  stop      Stop Flask backend
  restart   Restart Flask backend
  status    Check if Flask is running
  logs      Tail Flask logs

Options:
  --port PORT       Flask port (default: 5100)
  --deploy-dir DIR  Deployment directory (default: ${WORKSPACE_DIR}/deploy)

Environment variables (set via .env.workspace or export):
  DEPLOY_DIR       - Deployment directory
  DATABASE_PATH    - Database path

Examples:
  $0 start
  $0 stop
  $0 restart
  $0 status
  $0 logs
EOF
}

get_flask_pid() {
    # Check if PID file exists and process is running
    if [[ -f "${PID_FILE}" ]]; then
        local pid
        pid=$(cat "${PID_FILE}")
        if ps -p "${pid}" > /dev/null 2>&1; then
            echo "${pid}"
            return 0
        else
            # PID file exists but process is dead - clean up
            rm -f "${PID_FILE}"
        fi
    fi
    
    # Fallback: search for Flask process by name
    pgrep -f "flask.*passenger_wsgi" || true
}

start_flask() {
    local port="${PORT:-5100}"
    local deploy_dir="${DEPLOY_DIR}"
    local flask_env="${FLASK_ENV:-local_test}"
    
    log_info "Starting Flask backend..."
    log_info "  Deploy dir: ${deploy_dir}"
    log_info "  Port: ${port}"
    log_info "  Database: ${DATABASE_PATH}"
    log_info "  FLASK_ENV: ${flask_env}"
    
    # Fail-fast: if port is already in use, do not accidentally "start" against a stale server.
    local port_pids
    port_pids=$(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)

    # Check if already running
    local existing_pid
    existing_pid=$(get_flask_pid)
    if [[ -n "${existing_pid}" ]]; then
        log_warn "Flask already running (PID: ${existing_pid})"
        return 0
    fi

    if [[ -n "${port_pids}" ]]; then
        log_error "Port ${port} is already in use (listener PID(s): ${port_pids//$'\n'/, })."
        for pid in ${port_pids}; do
            log_error "  PID ${pid}: $(ps -p "${pid}" -o cmd= 2>/dev/null || echo 'unknown')"
        done
        log_error "Stop the existing listener or choose a different port via --port."
        return 1
    fi
    
    # Ensure directories exist
    mkdir -p "${LOG_DIR}"
    
    # Check deploy directory exists
    if [[ ! -d "${deploy_dir}" ]]; then
        log_error "Deploy directory does not exist: ${deploy_dir}"
        log_error "Run: ./build_deployment.py --target local"
        return 1
    fi
    
    # Check database exists
    if [[ ! -f "${DATABASE_PATH}" ]]; then
        log_error "Database does not exist: ${DATABASE_PATH}"
        log_error "Run: ./build_deployment.py --target local"
        return 1
    fi
    
    # Start Flask
    cd "${deploy_dir}"
    FLASK_ENV="${flask_env}" \
    DATABASE_PATH="${DATABASE_PATH}" \
        nohup python3 -m flask --app passenger_wsgi:application \
        run --host=0.0.0.0 --port="${port}" \
        > "${LOG_DIR}/flask.log" 2>&1 &
    
    local pid=$!
    echo "${pid}" > "${PID_FILE}"
    
    # Wait for Flask to be ready
    log_info "Waiting for Flask to start (PID: ${pid})..."
    for i in {1..30}; do
        if ! ps -p "${pid}" > /dev/null 2>&1; then
            log_error "Flask process exited unexpectedly (PID: ${pid})"
            log_error "Check logs: ${LOG_DIR}/flask.log"
            return 1
        fi

        # Ensure the PID we spawned is actually the listener for the port.
        if lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null | grep -q "^${pid}$"; then
            if curl -s "http://localhost:${port}/admin/login" > /dev/null 2>&1; then
                log_success "Flask started successfully"
                log_info "  URL: http://localhost:${port}"
                log_info "  Logs: ${LOG_DIR}/flask.log"
                log_info "  PID: ${pid}"
                return 0
            fi
        fi

        sleep 1
    done
    
    log_error "Flask failed to start (timeout)"
    log_error "Check logs: ${LOG_DIR}/flask.log"
    return 1
}

stop_flask() {
    log_info "Stopping Flask backend..."

    local port="${PORT:-5100}"
    
    local pid
    pid=$(get_flask_pid)
    
    if [[ -z "${pid}" ]]; then
        # Fallback: if the port is still bound, stop the listener(s).
        local port_pids
        port_pids=$(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)
        if [[ -z "${port_pids}" ]]; then
            log_warn "Flask not running"
            return 0
        fi

        log_warn "PID file not found, but port ${port} is in use; killing listener PID(s): ${port_pids//$'\n'/, }"
        for p in ${port_pids}; do
            log_info "Killing PID ${p}..."
            kill -9 "${p}" 2>/dev/null || true
        done
        rm -f "${PID_FILE}"
        sleep 1
        log_success "Flask stopped"
        return 0
    fi
    
    log_info "Killing Flask (PID: ${pid})..."
    kill -9 "${pid}" 2>/dev/null || true
    rm -f "${PID_FILE}"
    sleep 1
    
    # Verify stopped
    if ps -p "${pid}" > /dev/null 2>&1; then
        log_error "Failed to stop Flask (PID: ${pid})"
        return 1
    fi
    
    log_success "Flask stopped"
}

status_flask() {
    local pid
    pid=$(get_flask_pid)
    
    if [[ -n "${pid}" ]]; then
        log_success "Flask is running (PID: ${pid})"
        log_info "  Port: $(netstat -tuln 2>/dev/null | grep :5100 | awk '{print $4}' | head -1 || echo 'Unknown')"
        log_info "  Logs: ${LOG_DIR}/flask.log"
        return 0
    else
        log_warn "Flask is not running"
        return 1
    fi
}

logs_flask() {
    if [[ ! -f "${LOG_DIR}/flask.log" ]]; then
        log_error "Log file not found: ${LOG_DIR}/flask.log"
        return 1
    fi
    
    tail -f "${LOG_DIR}/flask.log"
}

# Parse arguments
COMMAND="${1:-}"
shift || true

while [[ $# -gt 0 ]]; do
    case $1 in
        --port)
            PORT="$2"
            shift 2
            ;;
        --deploy-dir)
            DEPLOY_DIR="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Execute command
case "${COMMAND}" in
    start)
        start_flask
        ;;
    stop)
        stop_flask
        ;;
    restart)
        stop_flask
        start_flask
        ;;
    status)
        status_flask
        ;;
    logs)
        logs_flask
        ;;
    "")
        log_error "No command specified"
        usage
        exit 1
        ;;
    *)
        log_error "Unknown command: ${COMMAND}"
        usage
        exit 1
        ;;
esac
