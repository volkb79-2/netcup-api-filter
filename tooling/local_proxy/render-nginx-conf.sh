#!/usr/bin/env bash
#
# render-nginx-conf.sh - Generate nginx configuration from template
#
# Usage:
#   ./render-nginx-conf.sh [proxy.env]
#
# Reads configuration from proxy.env (default) and renders nginx.conf.template
# to conf.d/default.conf by substituting ${LOCAL_TLS_DOMAIN}, ${LOCAL_APP_HOST},
# and ${LOCAL_APP_PORT} template variables.
#
# Prerequisites:
#   - proxy.env must exist (use ./auto-detect-fqdn.sh to generate)
#   - nginx.conf.template must exist
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Default to proxy.env in same directory
ENV_FILE="${1:-${SCRIPT_DIR}/proxy.env}"

# Export for _proxy_lib.sh
export PROXY_ENV_FILE="${ENV_FILE}"

# shellcheck source=/dev/null
source "${SCRIPT_DIR}/_proxy_lib.sh"

proxy_render_nginx_conf "${ENV_FILE}"
echo "✓ nginx configuration rendered"
echo "Next: ./stage-proxy-inputs.sh (if using devcontainer/Codespace)"