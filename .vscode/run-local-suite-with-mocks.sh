#!/usr/bin/env bash
# Run local suite with mocks (fail-fast).
set -euo pipefail
export UI_PYTEST_ARGS="-x"
exec "$(dirname "$0")/run-tests.sh"
