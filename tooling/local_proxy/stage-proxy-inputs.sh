#!/usr/bin/env bash
#
# stage-proxy-inputs.sh - Stage nginx configs and certificates to host-visible paths
#
# Usage:
#   ./stage-proxy-inputs.sh [proxy.env]
#
# Copies rendered nginx configurations and certificate bundles to host-visible
# paths (typically under /tmp/) so Docker daemon can mount them. Required when
# running inside devcontainer/Codespace where Docker can't access /workspaces/.
#
# Prerequisites:
#   - proxy.env must exist with LE_CERT_BASE and LOCAL_PROXY_CONFIG_PATH defined
#   - conf.d/default.conf must exist (run ./render-nginx-conf.sh first)
#   - Docker must be available (uses alpine container for staging)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Default to proxy.env in same directory
ENV_FILE="${1:-${SCRIPT_DIR}/proxy.env}"

# Export for _proxy_lib.sh
export PROXY_ENV_FILE="${ENV_FILE}"

# shellcheck source=/dev/null
source "${SCRIPT_DIR}/_proxy_lib.sh"

proxy_stage_inputs "${ENV_FILE}"
echo "✓ Proxy inputs staged to host-visible paths"
echo "Next: docker compose --env-file ${ENV_FILE} up -d"
