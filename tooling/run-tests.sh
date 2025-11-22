#!/usr/bin/env bash
# netcup-api-filter specific test runner using generic Playwright container

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# Ensure container is running
if ! docker compose -f tooling/playwright/docker-compose.yml ps | grep -q "playwright"; then
    log_info "Starting Playwright container..."
    cd tooling/playwright
    ./setup.sh
    cd "$PROJECT_ROOT"
fi

log_info "Running tests inside Playwright container..."

# Run pytest with project-specific tests
docker compose -f tooling/playwright/docker-compose.yml exec playwright \
    pytest /workspace/ui_tests/tests -v --tb=short

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    log_success "All tests passed!"
else
    log_error "Tests failed with exit code $EXIT_CODE"
fi

exit $EXIT_CODE
