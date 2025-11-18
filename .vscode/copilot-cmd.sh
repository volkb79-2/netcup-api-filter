#!/usr/bin/env bash
set -euo pipefail

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

log_plan() {
    echo -e "${BLUE}[PLAN]${NC} $*"
}
log_exec() {
    echo -e "${BLUE}[EXEC]${YELLOW} $*${NC}"
}

log_info "pwd: $(pwd)"
WORKSPACE_DIR="/workspaces/netcup-api-filter"
PLAN_FILE="${PLAN_FILE:-${WORKSPACE_DIR}/.vscode/copilot-plan.sh}"

if [[ -f "${PLAN_FILE}" ]]; then
    # shellcheck source=/dev/null
    source "${PLAN_FILE}"
fi

if [[ -z "${COPILOT_PLAN:-}" || -z "${COPILOT_EXEC:-}" ]]; then
    echo "COPILOT_PLAN or COPILOT_EXEC command not set" >&2
    exit 1
fi

log_plan "${COPILOT_PLAN}"
log_exec "${COPILOT_EXEC}"

cd "${WORKSPACE_DIR}"

eval "${COPILOT_EXEC}"