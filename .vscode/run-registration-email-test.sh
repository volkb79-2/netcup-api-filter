#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_DIR="/workspaces/netcup-api-filter"
cd "${WORKSPACE_DIR}"

# shellcheck source=/dev/null
source "${WORKSPACE_DIR}/.env.workspace"

export UI_PYTEST_ARGS="-x"

./run-local-tests.sh --with-mocks ui_tests/tests/test_email_notifications.py::TestRegistrationEmails::test_registration_sends_verification_email
