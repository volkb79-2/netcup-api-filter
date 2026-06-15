#!/usr/bin/env bash
# netcup-api-filter UI test runner — runs pytest in the current process.
#
# Browser connection mode (playwright_client.py reads PLAYWRIGHT_SERVER_WS):
#   unset / empty  -> in-process browser (requires 'playwright install --with-deps chromium')
#   ws://<name>:3000/ -> connect to external Playwright-as-a-Service container
#                        (address the service by container name on the shared Docker network)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load workspace environment
if [[ -f "${PROJECT_ROOT}/.env.workspace" ]]; then
    # shellcheck source=/dev/null
    source "${PROJECT_ROOT}/.env.workspace"
fi

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

log_info "Running UI tests..."

cd "${PROJECT_ROOT}"
pytest ui_tests/tests -v --tb=short

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    log_success "All tests passed!"
else
    log_error "Tests failed with exit code $EXIT_CODE"
fi

exit $EXIT_CODE
