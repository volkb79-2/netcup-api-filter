#!/usr/bin/env bash
# shell helpers shared by local proxy scripts

PROXY_TOOLING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# No default - fail fast if not set
PROXY_DEFAULT_ENV_FILE="${PROXY_ENV_FILE:?PROXY_ENV_FILE must be set}"

proxy__require_env_file() {
    local env_file="${1:?env_file parameter required}"
    if [[ ! -f "${env_file}" ]]; then
        echo "proxy env file not found: ${env_file}" >&2
        echo "Copy proxy.env.example first and fill in values." >&2
        exit 1
    fi
}

proxy__source_env() {
    local env_file="${1:?env_file parameter required}"
    proxy__require_env_file "${env_file}"
    set -a
    # shellcheck disable=SC1090
    source "${env_file}"
    set +a
}

proxy_render_nginx_conf() {
    local env_file="${1:?env_file parameter required}"
    local template="${PROXY_TOOLING_DIR}/nginx.conf.template"
    local output="${PROXY_TOOLING_DIR}/conf.d/default.conf"

    if [[ ! -f "${template}" ]]; then
        echo "Missing nginx template: ${template}" >&2
        exit 1
    fi

    local preset_tls="${LOCAL_TLS_DOMAIN:-}"
    local preset_host="${LOCAL_APP_HOST:-}"
    local preset_port="${LOCAL_APP_PORT:-}"

    proxy__source_env "${env_file}"

    if [[ -n "${preset_tls}" ]]; then
        LOCAL_TLS_DOMAIN="${preset_tls}"
    fi
    if [[ -n "${preset_host}" ]]; then
        LOCAL_APP_HOST="${preset_host}"
    fi
    if [[ -n "${preset_port}" ]]; then
        LOCAL_APP_PORT="${preset_port}"
    fi

    mkdir -p "$(dirname "${output}")"
    local vars='${LOCAL_TLS_DOMAIN} ${LOCAL_APP_HOST} ${LOCAL_APP_PORT}'
    envsubst "${vars}" < "${template}" > "${output}"

    echo "Rendered ${output} for ${LOCAL_TLS_DOMAIN} -> ${LOCAL_APP_HOST}:${LOCAL_APP_PORT}"
}

proxy__require_tmp_path() {
    local label="$1"
    local path_value="$2"
    if [[ "${ALLOW_PROXY_ASSET_STAGE_ANYWHERE:?ALLOW_PROXY_ASSET_STAGE_ANYWHERE must be set (0 or 1)}\" == "1" ]]; then
        return 0
    fi
    if [[ "${path_value}" != /tmp/* ]]; then
        echo "${label} must point to /tmp/... (or export ALLOW_PROXY_ASSET_STAGE_ANYWHERE=1)." >&2
        exit 1
    fi
}

proxy__copy_dir_via_docker() {
    local src_dir="$1"
    local dest_dir="$2"
    local label="$3"

    if [[ ! -d "${src_dir}" ]]; then
        echo "Missing directory: ${src_dir}" >&2
        exit 1
    fi
    if ! command -v docker >/dev/null 2>&1; then
        echo "docker is required to stage ${label}" >&2
        exit 1
    fi

    tar -C "${src_dir}" -cf - . \
        | docker run --rm -i -v "${dest_dir}:/stage" alpine \
            sh -c 'set -euo pipefail; rm -rf /stage/*; tar -C /stage -xf -'

    echo "Staged ${label} to ${dest_dir}"
}

proxy_stage_inputs() {
    local env_file="${1:?env_file parameter required}"
    local override_config="${LOCAL_PROXY_CONFIG_PATH:-}"
    local override_cert="${LE_CERT_BASE:-}"

    proxy__source_env "${env_file}"

    if [[ -n "${override_config}" ]]; then
        LOCAL_PROXY_CONFIG_PATH="${override_config}"
    fi
    if [[ -n "${override_cert}" ]]; then
        LE_CERT_BASE="${override_cert}"
    fi

    if [[ -z "${LOCAL_PROXY_CONFIG_PATH:-}" || -z "${LE_CERT_BASE:-}" ]]; then
        echo "LOCAL_PROXY_CONFIG_PATH and LE_CERT_BASE must be defined in ${env_file} (or exported)." >&2
        exit 1
    fi

    proxy__require_tmp_path "LOCAL_PROXY_CONFIG_PATH" "${LOCAL_PROXY_CONFIG_PATH}"
    proxy__require_tmp_path "LE_CERT_BASE" "${LE_CERT_BASE}"

    mkdir -p "${LOCAL_PROXY_CONFIG_PATH}" "${LE_CERT_BASE}"

    proxy__copy_dir_via_docker \
        "${PROXY_TOOLING_DIR}/conf.d" "${LOCAL_PROXY_CONFIG_PATH}" "nginx configs"
    proxy__copy_dir_via_docker \
        "${PROXY_TOOLING_DIR}/certs" "${LE_CERT_BASE}" "cert bundle"
}