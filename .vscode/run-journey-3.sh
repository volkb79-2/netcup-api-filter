#!/usr/bin/env bash
# Run Journey 3 (comprehensive states) test only (fail-fast, with mocks).
set -euo pipefail
export UI_PYTEST_ARGS="-x -k test_journey_3_comprehensive_states"
exec "$(dirname "$0")/run-tests.sh"
