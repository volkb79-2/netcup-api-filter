#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="/workspaces/netcup-api-filter"
cd "${REPO_ROOT}"

if [[ ! -f ".env.workspace" ]]; then
  echo "ERROR: .env.workspace not found; rebuild devcontainer or regenerate workspace env" >&2
  exit 1
fi

# shellcheck source=/dev/null
source .env.workspace

# Fail fast and only select the new grant tests.
export UI_PYTEST_ARGS="-x -k domain_root_grant"

echo "[INFO] Running domain root grants tests only (with mocks, fail-fast)"
echo "[INFO] UI_PYTEST_ARGS=${UI_PYTEST_ARGS}"

./run-local-tests.sh --with-mocks
