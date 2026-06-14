#!/usr/bin/env bash
# Run admin security + system security + account 2FA + BYOD tests (fail-fast, with mocks).
# Extra test modules are passed via UI_PYTEST_ARGS alongside the -x flag.
set -euo pipefail
export UI_PYTEST_ARGS="-x ui_tests/tests/features/test_admin_system_security_settings.py ui_tests/tests/security/test_account_2fa_disable.py ui_tests/tests/features/test_account_byod_backends.py"
exec "$(dirname "$0")/run-tests.sh" \
  "ui_tests/tests/roundtrip/test_admin_security_api_contracts.py"
