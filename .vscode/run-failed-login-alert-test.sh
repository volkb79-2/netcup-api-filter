#!/usr/bin/env bash
# Run the failed-login security alert email test (fail-fast, with mocks).
set -euo pipefail
export UI_PYTEST_ARGS="-x"
exec "$(dirname "$0")/run-tests.sh" \
  "ui_tests/tests/features/test_email_notifications.py::TestSecurityAlertEmails::test_failed_login_alert"
