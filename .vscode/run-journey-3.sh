#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_DIR="/workspaces/netcup-api-filter"
cd "${WORKSPACE_DIR}"

# shellcheck source=/dev/null
source "${WORKSPACE_DIR}/.env.workspace"

echo "[INFO] Running Journey 3 (comprehensive states) test only (with mocks, fail-fast)"

export UI_PYTEST_ARGS="-x -k test_journey_3_comprehensive_states"

./run-local-tests.sh --with-mocks
