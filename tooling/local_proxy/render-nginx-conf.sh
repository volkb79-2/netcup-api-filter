#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/_proxy_lib.sh"

proxy_render_nginx_conf "$@"
echo "Run ./stage-proxy-inputs.sh if you need to copy configs/certs into host-visible paths"