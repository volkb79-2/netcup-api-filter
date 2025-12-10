#!/usr/bin/env bash
# netcup-api-filter specific test runner using generic Playwright container

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load workspace environment
if [[ -f "${PROJECT_ROOT}/.env.workspace" ]]; then
    # shellcheck source=/dev/null
    source "${PROJECT_ROOT}/.env.workspace"
fi

# Load service names
if [[ -f "${PROJECT_ROOT}/.env.services" ]]; then
    # shellcheck source=/dev/null
    source "${PROJECT_ROOT}/.env.services"
fi

# Fail-fast: require essential variables
: "${SERVICE_PLAYWRIGHT:?SERVICE_PLAYWRIGHT must be set (source .env.services)}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# Ensure container is running
if ! docker ps --filter "name=${SERVICE_PLAYWRIGHT}" | grep -q "${SERVICE_PLAYWRIGHT}"; then
    log_info "Starting Playwright container..."
    cd tooling/playwright
    ./setup.sh
    cd "$PROJECT_ROOT"
fi

log_info "Running tests inside Playwright container..."

# Run pytest with project-specific tests
docker exec "${SERVICE_PLAYWRIGHT}" \
    pytest /workspaces/netcup-api-filter/ui_tests/tests -v --tb=short

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    log_success "All tests passed!"
else
    log_error "Tests failed with exit code $EXIT_CODE"
fi

exit $EXIT_CODE
