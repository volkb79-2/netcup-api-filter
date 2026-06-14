#!/usr/bin/env bash
# Run the registration verification email test (fail-fast, with mocks).
set -euo pipefail
export UI_PYTEST_ARGS="-x"
exec "$(dirname "$0")/run-tests.sh" \
  "ui_tests/tests/features/test_email_notifications.py::TestRegistrationEmails::test_registration_sends_verification_email"
