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

# Fail fast and run only the specific new test modules.
# run-local-tests.sh always supplies a TEST_PATH (defaulting to ui_tests/tests),
# so we pass the first module as TEST_PATH and the remaining modules as extra args.
TEST_PATH="ui_tests/tests/test_admin_security_api_contracts.py"
export UI_PYTEST_ARGS="-x ui_tests/tests/test_admin_system_security_settings.py ui_tests/tests/test_account_2fa_disable.py ui_tests/tests/test_account_byod_backends.py"

echo "[INFO] Running admin security + system security + account 2FA + BYOD tests (with mocks, fail-fast)"
echo "[INFO] UI_PYTEST_ARGS=${UI_PYTEST_ARGS}"

./run-local-tests.sh --with-mocks "${TEST_PATH}"
