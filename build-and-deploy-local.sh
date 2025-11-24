#!/bin/bash
set -euo pipefail

# Local deployment script that mirrors webhosting deployment workflow
# This ensures tests run against the EXACT same setup as production

DEPLOY_LOCAL_DIR="/workspaces/netcup-api-filter/deploy-local"
DEPLOY_ZIP="deploy.zip"

echo "=== Building deployment package (same as webhosting) ==="
./build_deployment.py

echo ""
echo "=== Extracting to local deployment directory ==="
# Mirror webhosting: remove old content including dot-files
rm -rf "${DEPLOY_LOCAL_DIR}"
mkdir -p "${DEPLOY_LOCAL_DIR}/tmp"

# Extract deployment package (same as webhosting unzip)
unzip -o -q "${DEPLOY_ZIP}" -d "${DEPLOY_LOCAL_DIR}/"

echo ""
echo "=== Local deployment ready ==="
echo "Deployment directory: ${DEPLOY_LOCAL_DIR}"
echo "Database: ${DEPLOY_LOCAL_DIR}/netcup_filter.db (preseeded with default credentials)"
echo ""
echo "To run Flask:"
echo "  cd ${DEPLOY_LOCAL_DIR}"
echo "  NETCUP_FILTER_DB_PATH=${DEPLOY_LOCAL_DIR}/netcup_filter.db \\"
echo "    gunicorn -b 0.0.0.0:5100 passenger_wsgi:application"
echo ""
echo "To run tests:"
echo "  UI_BASE_URL=http://netcup-api-filter-devcontainer-vb:5100 \\"
echo "    UI_ADMIN_USERNAME=admin \\"
echo "    UI_ADMIN_PASSWORD=admin \\"
echo "    pytest ui_tests/tests -v"
