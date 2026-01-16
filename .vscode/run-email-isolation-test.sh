#!/usr/bin/env bash
set -euo pipefail

echo "[INFO] Running email isolation test (with mocks, fail-fast)"

WORKSPACE_DIR="/workspaces/netcup-api-filter"
cd "${WORKSPACE_DIR}"

# shellcheck source=/dev/null
source "${WORKSPACE_DIR}/.env.workspace"

# Use the same production-parity runner, but focus on the failing test.
export UI_PYTEST_ARGS='-x -k test_user_a_email_not_sent_to_user_b'

./run-local-tests.sh --with-mocks
