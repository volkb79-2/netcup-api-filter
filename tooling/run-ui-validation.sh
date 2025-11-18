#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROXY_DIR="${ROOT_DIR}/tooling/local_proxy"
PROXY_LIB="${PROXY_DIR}/_proxy_lib.sh"
PLAYWRIGHT_DIR="${ROOT_DIR}/tooling/playwright-mcp"
UI_TEST_DIR="${ROOT_DIR}/ui_tests"
TMP_DIR="${ROOT_DIR}/tmp"
PROXY_ENV="${PROXY_DIR}/proxy.env"
PLAYWRIGHT_RUN="${PLAYWRIGHT_DIR}/run.sh"

if [[ ! -f "${PROXY_ENV}" ]]; then
    echo "Missing ${PROXY_ENV}. Copy proxy.env.example and update values." >&2
    exit 1
fi

if [[ ! -f "${PROXY_LIB}" ]]; then
    echo "Missing ${PROXY_LIB}." >&2
    exit 1
fi

# shellcheck source=/dev/null
source "${PROXY_LIB}"

if [[ ! -x "${PLAYWRIGHT_RUN}" ]]; then
    echo "Missing executable ${PLAYWRIGHT_RUN}." >&2
    exit 1
fi

mkdir -p "${TMP_DIR}"

# shellcheck disable=SC1091
set -a
source "${PROXY_ENV}"
set +a

LOCAL_APP_PORT="${LOCAL_APP_PORT:-5100}"
LOCAL_PROXY_NETWORK="${LOCAL_PROXY_NETWORK:-naf-local}"
LOCAL_TLS_DOMAIN="${LOCAL_TLS_DOMAIN:-naf.localtest.me}"
LOCAL_TLS_BIND_HTTPS="${LOCAL_TLS_BIND_HTTPS:-443}"
LOCAL_TLS_BIND_HTTP="${LOCAL_TLS_BIND_HTTP:-80}"
if [[ -z "${LOCAL_APP_HOST:-}" || "${LOCAL_APP_HOST}" == "__auto__" ]]; then
    if command -v docker >/dev/null 2>&1; then
        LOCAL_APP_HOST="$(docker inspect -f '{{.Name}}' "$(hostname)" 2>/dev/null | sed 's#^/##')"
    fi
    LOCAL_APP_HOST="${LOCAL_APP_HOST:-$(hostname)}"
fi
export LOCAL_APP_HOST LOCAL_APP_PORT

HOST_GATEWAY_IP="${HOST_GATEWAY_IP:-$(ip route | awk '/default/ {print $3; exit}')}"
HOST_GATEWAY_IP="${HOST_GATEWAY_IP// /}"
HOST_GATEWAY_IP="${HOST_GATEWAY_IP:-172.17.0.1}"

DEFAULT_BASE="https://${HOST_GATEWAY_IP}:${LOCAL_TLS_BIND_HTTPS}"
export UI_BASE_URL="${UI_BASE_URL:-${DEFAULT_BASE}}"
export UI_MCP_URL="${UI_MCP_URL:-http://${HOST_GATEWAY_IP}:8765/mcp}"
export UI_ADMIN_USERNAME="${UI_ADMIN_USERNAME:-admin}"
export UI_ADMIN_PASSWORD="${UI_ADMIN_PASSWORD:-admin}"
export UI_CLIENT_ID="${UI_CLIENT_ID:-test_qweqweqwe_vi}"
export UI_CLIENT_TOKEN="${UI_CLIENT_TOKEN:-qweqweqwe-vi-readonly}"
export UI_CLIENT_DOMAIN="${UI_CLIENT_DOMAIN:-qweqweqwe.vi}"
export UI_SCREENSHOT_PREFIX="${UI_SCREENSHOT_PREFIX:-ui-regression}"

PLAYWRIGHT_START_URL="${UI_BASE_URL%/}/admin/login"
export PLAYWRIGHT_START_URL
export PLAYWRIGHT_HEADLESS="${PLAYWRIGHT_HEADLESS:-true}"
export MCP_PORT="${MCP_PORT:-8765}"
export MCP_HOST="${MCP_HOST:-0.0.0.0}"

PROXY_COMPOSE_ARGS=(-f "${PROXY_DIR}/docker-compose.yml" --env-file "${PROXY_ENV}")
PROXY_STARTED=0
PLAYWRIGHT_STARTED=0
GUNICORN_PID=""

cleanup() {
    local exit_code=$?
    if [[ -n "${GUNICORN_PID}" ]] && kill -0 "${GUNICORN_PID}" 2>/dev/null; then
        kill "${GUNICORN_PID}" 2>/dev/null || true
        wait "${GUNICORN_PID}" 2>/dev/null || true
    fi
    if [[ "${PROXY_STARTED}" == "1" ]]; then
        docker compose "${PROXY_COMPOSE_ARGS[@]}" down >/dev/null 2>&1 || true
    fi
    if [[ "${PLAYWRIGHT_STARTED}" == "1" ]]; then
        (cd "${PLAYWRIGHT_DIR}" && ./run.sh down) >/dev/null 2>&1 || true
    fi
    exit "${exit_code}"
}
trap cleanup EXIT

wait_for_http() {
    local name="$1"
    local url="$2"
    local insecure="${3:-0}"
    local max_attempts="${4:-40}"
    local delay="${5:-2}"
    local allow_errors="${6:-0}"
    local args=("--silent" "--show-error" "--max-time" "5")
    if [[ "${allow_errors}" != "1" ]]; then
        args+=("--fail")
    fi
    if [[ "${insecure}" == "1" ]]; then
        args+=("-k")
    fi
    for attempt in $(seq 1 "${max_attempts}"); do
        if curl "${args[@]}" "${url}" >/dev/null; then
            echo "[ready] ${name}"
            return 0
        fi
        sleep "${delay}"
    done
    echo "Timed out waiting for ${name} (${url})" >&2
    return 1
}

if ! docker network inspect "${LOCAL_PROXY_NETWORK}" >/dev/null 2>&1; then
    docker network create "${LOCAL_PROXY_NETWORK}" >/dev/null
fi

proxy_render_nginx_conf "${PROXY_ENV}"
proxy_stage_inputs "${PROXY_ENV}"

if [[ "${SKIP_UI_TEST_DEPS:-0}" != "1" ]]; then
    pip install -r "${UI_TEST_DIR}/requirements.txt"
fi

cd "${ROOT_DIR}"
LOCAL_DB_PATH="${LOCAL_DB_PATH:-${TMP_DIR}/local-netcup.db}"
export LOCAL_DB_PATH

gunicorn tooling.local_proxy.local_app:app \
    -b "0.0.0.0:${LOCAL_APP_PORT}" \
    --log-file "${TMP_DIR}/local_app.log" \
    >"${TMP_DIR}/local_app.stdout" 2>&1 &
GUNICORN_PID=$!
sleep 2

wait_for_http "Flask backend" "http://127.0.0.1:${LOCAL_APP_PORT}/admin/login"

docker compose "${PROXY_COMPOSE_ARGS[@]}" up -d
PROXY_STARTED=1

wait_for_http "Local TLS proxy" "https://${HOST_GATEWAY_IP}:${LOCAL_TLS_BIND_HTTPS}/admin/login" 1

pushd "${PLAYWRIGHT_DIR}" >/dev/null
./run.sh up -d
PLAYWRIGHT_STARTED=1
popd >/dev/null

wait_for_http "Playwright MCP" "${UI_MCP_URL}" 0 40 2 1

pytest ui_tests/tests -vv
