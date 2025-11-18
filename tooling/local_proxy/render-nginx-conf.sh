#!/usr/bin/env bash
set -euo pipefail

# Always operate from the proxy tooling folder so relative paths resolve.
cd "$(dirname "$0")"

if [[ ! -f "proxy.env" ]]; then
    echo "proxy.env not found; copy proxy.env.example first" >&2
    exit 1
fi

# Allow callers to override values sourced from proxy.env by exporting
# variables beforehand (useful when automation layers compute HOST/IPs).
PRESET_LOCAL_TLS_DOMAIN="${LOCAL_TLS_DOMAIN:-}"
PRESET_LOCAL_APP_HOST="${LOCAL_APP_HOST:-}"
PRESET_LOCAL_APP_PORT="${LOCAL_APP_PORT:-}"

# shellcheck source=/dev/null
set -a
source "proxy.env"
set +a

if [[ -n "${PRESET_LOCAL_TLS_DOMAIN}" ]]; then
    LOCAL_TLS_DOMAIN="${PRESET_LOCAL_TLS_DOMAIN}"
fi
if [[ -n "${PRESET_LOCAL_APP_HOST}" ]]; then
    LOCAL_APP_HOST="${PRESET_LOCAL_APP_HOST}"
fi
if [[ -n "${PRESET_LOCAL_APP_PORT}" ]]; then
    LOCAL_APP_PORT="${PRESET_LOCAL_APP_PORT}"
fi

VARS='${LOCAL_TLS_DOMAIN} ${LOCAL_APP_HOST} ${LOCAL_APP_PORT}'

envsubst "${VARS}" < nginx.conf.template > conf.d/default.conf

echo "Rendered conf.d/default.conf for ${LOCAL_TLS_DOMAIN} -> ${LOCAL_APP_HOST}:${LOCAL_APP_PORT}"
echo "Run ./stage-proxy-inputs.sh if you need to copy configs/certs into host-visible paths"