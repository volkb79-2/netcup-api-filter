#!/usr/bin/env bash
# Run Journey 1 (fresh deployment) test only (fail-fast, with mocks).
set -euo pipefail
export UI_PYTEST_ARGS="-x -k test_journey_1_fresh_deployment"
exec "$(dirname "$0")/run-tests.sh"
