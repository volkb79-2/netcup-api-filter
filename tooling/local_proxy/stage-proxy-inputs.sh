#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -f "proxy.env" ]]; then
    echo "proxy.env not found; copy proxy.env.example first" >&2
    exit 1
fi

# shellcheck disable=SC1091
set -a
source "proxy.env"
set +a

require_tmp_path() {
    local label="$1"
    local path="$2"
    if [[ "${ALLOW_PROXY_ASSET_STAGE_ANYWHERE:-0}" == "1" ]]; then
        return 0
    fi
    if [[ "$path" != /tmp/* ]]; then
        echo "${label} must point to /tmp/... (or set ALLOW_PROXY_ASSET_STAGE_ANYWHERE=1)." >&2
        exit 1
    fi
}

require_tmp_path "LOCAL_PROXY_CONFIG_PATH" "${LOCAL_PROXY_CONFIG_PATH}"
require_tmp_path "LE_CERT_BASE" "${LE_CERT_BASE}"

mkdir -p "${LOCAL_PROXY_CONFIG_PATH}" "${LE_CERT_BASE}"

copy_dir_via_docker() {
    local src_dir="$1"
    local dest_dir="$2"
    local label="$3"

    tar -C "${src_dir}" -cf - . \
        | docker run --rm -i -v "${dest_dir}:/stage" alpine \
          sh -c 'set -euo pipefail; rm -rf /stage/*; tar -C /stage -xf -'

    echo "Staged ${label} to ${dest_dir}"
}

copy_dir_via_docker "conf.d" "${LOCAL_PROXY_CONFIG_PATH}" "nginx configs"
copy_dir_via_docker "certs" "${LE_CERT_BASE}" "cert bundle"
