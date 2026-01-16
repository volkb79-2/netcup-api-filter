#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_DIR="/workspaces/netcup-api-filter"
cd "${WORKSPACE_DIR}"

# shellcheck source=/dev/null
source "${WORKSPACE_DIR}/.env.workspace"

# Fail-fast to surface the first regression quickly.
export UI_PYTEST_ARGS="-x"

./run-local-tests.sh --with-mocks
