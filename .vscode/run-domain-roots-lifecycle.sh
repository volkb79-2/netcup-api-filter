#!/usr/bin/env bash
# Run the admin domain-roots lifecycle journey test (fail-fast, with mocks).
set -euo pipefail
export UI_PYTEST_ARGS="-x"
exec "$(dirname "$0")/run-tests.sh" \
  "ui_tests/tests/test_domain_roots_lifecycle.py::test_admin_domain_roots_lifecycle_journey"
