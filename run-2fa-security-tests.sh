#!/usr/bin/env bash
#
# Run 2FA security tests against HTTP endpoint
#
# This script runs the 2FA security test suite against the direct Flask HTTP endpoint
# instead of the HTTPS TLS proxy to avoid session cookie handling issues.
#
# Usage:
#   ./run-2fa-security-tests.sh              # Run all 2FA security tests
#   ./run-2fa-security-tests.sh -k lockout   # Run only lockout tests
#   ./run-2fa-security-tests.sh -v           # Verbose output
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

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

# Source environment files
if [[ -f ".env.workspace" ]]; then
    source .env.workspace
else
    log_error ".env.workspace not found"
    exit 1
fi

if [[ -f "tooling/mailpit/.env" ]]; then
    source tooling/mailpit/.env
else
    log_error "tooling/mailpit/.env not found"
    exit 1
fi

# Check if Playwright container is running
if ! docker ps | grep -q naf-dev-playwright; then
    log_error "Playwright container (naf-dev-playwright) is not running"
    log_info "Start it with: cd tooling/playwright && docker compose up -d"
    exit 1
fi

# Check if Mailpit is running
if ! docker ps | grep -q naf-dev-mailpit; then
    log_error "Mailpit container (naf-dev-mailpit) is not running"
    log_info "Start it with: cd tooling/mailpit && docker compose up -d"
    exit 1
fi

# Check if Flask is running
DEVCONTAINER_HOSTNAME="${DEVCONTAINER_HOSTNAME:-netcup-api-filter-devcontainer-vb}"
if ! curl -s "http://${DEVCONTAINER_HOSTNAME}:5100/health" >/dev/null 2>&1; then
    log_warn "Flask may not be running on ${DEVCONTAINER_HOSTNAME}:5100"
    log_info "Start it with: ./run-local-tests.sh --skip-tests (or manually with gunicorn)"
fi

log_info "Running 2FA security tests via HTTP endpoint"
log_info "Target: http://${DEVCONTAINER_HOSTNAME}:5100"
log_info "Mailpit: ${MAILPIT_API_URL:-http://naf-dev-mailpit:8025}"

# Pass through any pytest arguments
PYTEST_ARGS="$@"
if [[ -z "$PYTEST_ARGS" ]]; then
    PYTEST_ARGS="-v"
fi

docker exec \
    -e DEPLOYMENT_TARGET=local \
    -e UI_BASE_URL="http://${DEVCONTAINER_HOSTNAME}:5100" \
    -e MAILPIT_USERNAME="${MAILPIT_USERNAME}" \
    -e MAILPIT_PASSWORD="${MAILPIT_PASSWORD}" \
    -e MAILPIT_API_URL="${MAILPIT_API_URL:-http://naf-dev-mailpit:8025}" \
    naf-dev-playwright \
    pytest /workspaces/netcup-api-filter/ui_tests/tests/test_2fa_security.py $PYTEST_ARGS

EXIT_CODE=$?

if [[ $EXIT_CODE -eq 0 ]]; then
    log_success "All 2FA security tests passed!"
else
    log_error "Some tests failed (exit code: $EXIT_CODE)"
fi

exit $EXIT_CODE
