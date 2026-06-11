#!/usr/bin/env bash
# Run email isolation test only (fail-fast, with mocks).
set -euo pipefail
export UI_PYTEST_ARGS="-x -k test_user_a_email_not_sent_to_user_b"
exec "$(dirname "$0")/run-tests.sh"
