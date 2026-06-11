#!/usr/bin/env bash
# Run the full test suite with mocks (fail-fast unless UI_PYTEST_ARGS overridden).
set -euo pipefail
: "${UI_PYTEST_ARGS:=-x}"
export UI_PYTEST_ARGS
exec "$(dirname "$0")/run-tests.sh"
