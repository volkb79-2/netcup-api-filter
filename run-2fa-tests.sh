#!/bin/bash
set -euo pipefail

# Run tests WITH 2FA enabled (using Mailpit)
# This ensures template components that depend on 2FA render correctly

WORKSPACE_DIR="${REPO_ROOT:?REPO_ROOT must be set}"
DEPLOY_LOCAL_DIR="${WORKSPACE_DIR}/deploy-local"

echo "=== Running 2FA-Enabled Tests ==="
echo ""
echo "Prerequisites:"
echo "  - Mailpit must be running (tooling/mailpit/docker compose up -d)"
echo "  - Fresh deployment with admin/admin credentials"
echo ""

# Check if Mailpit is running
if ! curl -s http://localhost:8025/api/v1/messages > /dev/null 2>&1; then
    echo "❌ Mailpit is not running!"
    echo "   Start it with: cd tooling/mailpit && docker compose up -d"
    exit 1
fi

echo "✓ Mailpit is running"
echo ""

# Build fresh deployment if needed
if [ ! -d "${DEPLOY_LOCAL_DIR}" ]; then
    echo "Building fresh deployment..."
    cd "${WORKSPACE_DIR}"
    ./build_deployment.py --local
    rm -rf "${DEPLOY_LOCAL_DIR}"
    mkdir -p "${DEPLOY_LOCAL_DIR}"
    unzip -o -q deploy.zip -d "${DEPLOY_LOCAL_DIR}/"
    echo "✓ Deployment extracted"
fi

# Kill any existing Flask
pkill -9 gunicorn || true
sleep 1

# Start Flask WITHOUT ADMIN_2FA_SKIP
echo "Starting Flask with 2FA ENABLED (no ADMIN_2FA_SKIP)..."

cd "${DEPLOY_LOCAL_DIR}"

export NETCUP_FILTER_DB_PATH="${DEPLOY_LOCAL_DIR}/netcup_filter.db"
export SECRET_KEY="local-test-secret-key-for-session-persistence-12345678"
export FLASK_ENV="local_test"

# NO ADMIN_2FA_SKIP! This is the key difference.
PYTHONPATH="${DEPLOY_LOCAL_DIR}/vendor" \
  SECRET_KEY="${SECRET_KEY}" \
  NETCUP_FILTER_DB_PATH="${NETCUP_FILTER_DB_PATH}" \
  FLASK_ENV="${FLASK_ENV}" \
  gunicorn -b 0.0.0.0:5100 \
  --workers=1 \
  --timeout=30 \
  --access-logfile=- \
  --error-logfile=- \
  --daemon \
  --pid=/tmp/gunicorn-2fa-test.pid \
  passenger_wsgi:application

sleep 2

# Check if Flask started
if ! curl -s http://localhost:5100/admin/login > /dev/null; then
    echo "❌ Flask failed to start"
    exit 1
fi

echo "✓ Flask started with 2FA enabled"
echo ""

# Run 2FA-specific tests
cd "${WORKSPACE_DIR}"

echo "Running 2FA-enabled test suite..."
pytest ui_tests/tests/test_2fa_enabled_flows.py -v --tb=short

TEST_EXIT_CODE=$?

# Cleanup
echo ""
echo "Cleaning up..."
kill $(cat /tmp/gunicorn-2fa-test.pid) 2>/dev/null || true
rm -f /tmp/gunicorn-2fa-test.pid

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo ""
    echo "✅ All 2FA-enabled tests PASSED"
else
    echo ""
    echo "❌ Some 2FA-enabled tests FAILED (exit code: $TEST_EXIT_CODE)"
fi

exit $TEST_EXIT_CODE
