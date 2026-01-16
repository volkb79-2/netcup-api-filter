#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_DIR="/workspaces/netcup-api-filter"

cd "${WORKSPACE_DIR}"

# Source workspace-derived config (PUBLIC_FQDN, docker network, etc.)
# shellcheck source=/dev/null
source "${WORKSPACE_DIR}/.env.workspace"

# Run in fail-fast mode and include mocks.
# Note: the test selection is passed as a normal argument (not via env assignment).
export UI_PYTEST_ARGS="-x"

./run-local-tests.sh --with-mocks ui_tests/tests/test_domain_roots_lifecycle.py::test_admin_domain_roots_lifecycle_journey
