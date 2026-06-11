#!/usr/bin/env bash
# Parameterized test launcher for VS Code tasks.
# Usage: .vscode/run-tests.sh [TEST_PATH]
#   TEST_PATH  - optional path/selector forwarded to run-local-tests.sh
#                (default: run-local-tests.sh's own default, ui_tests/tests)
#   UI_PYTEST_ARGS - optional extra pytest flags (set by the caller before invoking)
#
# All run-*.sh wrappers in this directory delegate here to keep the
# bootstrap logic (env sourcing, existence check) in one place.
set -euo pipefail

WORKSPACE_DIR="/workspaces/netcup-api-filter"
cd "${WORKSPACE_DIR}"

if [[ ! -f ".env.workspace" ]]; then
  echo "ERROR: .env.workspace not found; rebuild devcontainer or regenerate workspace env" >&2
  exit 1
fi

# shellcheck source=/dev/null
source .env.workspace

TEST_PATH="${1:-}"

if [[ -n "${TEST_PATH}" ]]; then
  exec ./run-local-tests.sh --with-mocks "${TEST_PATH}"
else
  exec ./run-local-tests.sh --with-mocks
fi
