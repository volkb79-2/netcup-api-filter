#!/usr/bin/env bash
# Run domain root grant tests only (fail-fast, with mocks).
set -euo pipefail
export UI_PYTEST_ARGS="-x -k domain_root_grant"
exec "$(dirname "$0")/run-tests.sh"
