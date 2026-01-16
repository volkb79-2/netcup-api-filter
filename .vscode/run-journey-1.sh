#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_DIR="/workspaces/netcup-api-filter"
cd "${WORKSPACE_DIR}"

# shellcheck source=/dev/null
source "${WORKSPACE_DIR}/.env.workspace"

echo "[INFO] Running Journey 1 (fresh deployment) test only (with mocks, fail-fast)"

export UI_PYTEST_ARGS="-x -k test_journey_1_fresh_deployment"

./run-local-tests.sh --with-mocks
