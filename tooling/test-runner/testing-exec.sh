#!/usr/bin/env bash
# testing-exec.sh — THE gate entrypoint for netcup-api-filter.
#
# Cockpit doctrine: this is the only sanctioned way to produce a "green" signal.
# It runs the suite inside the test-runner container (python 3.11 = the Passenger
# deploy target), never in the devcontainer. See tooling/test-runner/README.md.
#
# Usage:
#   ./tooling/test-runner/testing-exec.sh unit                  # pytest tests/ (hermetic)
#   ./tooling/test-runner/testing-exec.sh unit -k realm         # extra pytest args pass through
#   ./tooling/test-runner/testing-exec.sh trove                 # nyxloom handoff frontmatter lint
#   ./tooling/test-runner/testing-exec.sh e2e ui_tests/tests/security/
#   ./tooling/test-runner/testing-exec.sh shell                 # interactive shell in the gate
#   ./tooling/test-runner/testing-exec.sh build 3.11 -- build_deployment.py --target webhosting ...
#                                                                 # naf-I03: run a command inside the
#                                                                 # per-version image, host-uid-writable
#
# Fail-fast: no cross-environment fallbacks. Required inputs are asserted, not defaulted.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Identity of the gate (version-controlled, not per-environment).
# shellcheck source=runner.env
source "${REPO_ROOT}/tooling/test-runner/runner.env"

# WORKTREE AWARENESS — so a parallel agent working in .worktrees/<pkg> can gate ITS
# checkout in isolation. The daemon binds the MAIN repo root, and worktrees live inside
# it (worktree_root = .worktrees), so the single mount already sees every worktree; we
# just cd to the right subpath inside the container.
#   MAIN_ROOT  — the main working tree (holds the gitignored .env.workspace). The git
#                common-dir is shared by every linked worktree, so its parent is MAIN_ROOT.
#   WT_REL     — REPO_ROOT relative to MAIN_ROOT: "" for main, "/.worktrees/<pkg>" for a wt.
GIT_COMMON_DIR="$(git -C "${REPO_ROOT}" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
if [ -n "${GIT_COMMON_DIR}" ]; then
    MAIN_ROOT="$(dirname "${GIT_COMMON_DIR}")"
else
    MAIN_ROOT="${REPO_ROOT}"   # not a git checkout (shouldn't happen); degrade to self
fi
WT_REL="${REPO_ROOT#"${MAIN_ROOT}"}"   # "" or "/.worktrees/<pkg>"

# Environment-specific paths come from the auto-generated workspace file, which lives in
# the MAIN root only (it is gitignored, so worktrees never carry a copy).
# NOTE: we deliberately do NOT source .env.services here — it expands ${PUBLIC_FQDN}
# unconditionally (POWERDNS_API_URL) and aborts any `set -u` consumer when post-create
# has not written that var. The gate must not inherit that breakage.
# See docs/deprecated/FOLLOWUP_REVIEW_2026-07-16.md §P0-8.
[ -f "${MAIN_ROOT}/.env.workspace" ] || {
    echo "FATAL: .env.workspace missing in ${MAIN_ROOT} — run .devcontainer/post-create.sh (auto-generated)" >&2
    exit 3
}
# shellcheck disable=SC1091
source "${MAIN_ROOT}/.env.workspace"

# DooD: the docker socket is the HOST's, so -v sources must be HOST paths. We mount the
# HOST main root and cd to the worktree subpath (CONTAINER_WORKDIR) inside the container.
PHYSICAL_REPO_ROOT="${PHYSICAL_REPO_ROOT:?PHYSICAL_REPO_ROOT not set (check .env.workspace)}"
DOCKER_NETWORK_INTERNAL="${DOCKER_NETWORK_INTERNAL:?DOCKER_NETWORK_INTERNAL not set (check .env.workspace)}"
CONTAINER_WORKDIR="/workspaces/netcup-api-filter${WT_REL}"
[ -n "${WT_REL}" ] && echo "[gate] worktree: ${REPO_ROOT} -> ${CONTAINER_WORKDIR}" >&2

IMAGE="${TEST_RUNNER_IMAGE:?TEST_RUNNER_IMAGE not set (check tooling/test-runner/runner.env)}"
CONTAINER="${TEST_RUNNER_CONTAINER:?TEST_RUNNER_CONTAINER not set (check tooling/test-runner/runner.env)}"
VENV=/opt/tester-venv/bin/python

usage() { sed -n '2,18p' "${BASH_SOURCE[0]}"; exit 2; }

image_present() { docker image inspect "${IMAGE}" >/dev/null 2>&1; }
container_up()  { [ "$(docker inspect -f '{{.State.Running}}' "${CONTAINER}" 2>/dev/null)" = "true" ]; }

ensure_image() {
    if ! image_present; then
        echo "[gate] image ${IMAGE} missing — building (python ${PYTHON_VERSION:-3.11})" >&2
        docker build \
            --build-arg "PYTHON_VERSION=${PYTHON_VERSION:-3.11}" \
            -f "${REPO_ROOT}/tooling/test-runner/Dockerfile" \
            -t "${IMAGE}" "${REPO_ROOT}" >&2
    fi
}

# Map a Python X.Y version to its test-runner image tag. Shared by the `unit` gate
# loop and the `build` subcommand (naf-I03) so there is exactly one place that knows
# 3.11 is TEST_RUNNER_IMAGE itself and every other version is TEST_RUNNER_IMAGE's repo
# with a ":py<XY>" tag.
image_for_python_version() {
    local ver="$1"
    if [ "${ver}" = "3.11" ]; then
        echo "${TEST_RUNNER_IMAGE}"
    else
        echo "${TEST_RUNNER_IMAGE%:*}:py${ver//./}"
    fi
}

# Ephemeral run: the form nyxloom gates use. No persistent peer required, so a gate
# never depends on prior `ciu up` state.
run_ephemeral() {
    docker run --rm \
        -v "${PHYSICAL_REPO_ROOT}:/workspaces/netcup-api-filter:rw" \
        -w "${CONTAINER_WORKDIR}" \
        "${IMAGE}" "$@"
}

# Networked run: joins naf-dev-network so the suite can reach the mock services and a
# deployed app as a peer. Used by the e2e gate.
run_networked() {
    docker run --rm \
        --network "${DOCKER_NETWORK_INTERNAL}" \
        -v "${PHYSICAL_REPO_ROOT}:/workspaces/netcup-api-filter:rw" \
        -w "${CONTAINER_WORKDIR}" \
        -e "PLAYWRIGHT_SERVER_WS=${PLAYWRIGHT_SERVER_WS:-}" \
        -e "UI_BASE_URL=${UI_BASE_URL:-}" \
        `# Ingress basicauth (naf-I04): the dev app is exposed through the host traefik` \
        `# behind a basicauth guard, so the browser MUST authenticate or every e2e request` \
        `# 401s before reaching the app. Playwright picks these up in _guard_credentials().` \
        -e "NAF_GUARD_USER=${NAF_GUARD_USER:-}" \
        -e "NAF_GUARD_PASSWORD=${NAF_GUARD_PASSWORD:-}" \
        "${IMAGE}" "$@"
}

CMD="${1:-}"; [ -n "${CMD}" ] || usage; shift || true

case "${CMD}" in
    unit)
        # The PRIMARY gate: hermetic, no services, no browser. pytest.ini sets
        # `pythonpath = . src`. -p no:cacheprovider keeps the bind mount clean.
        #
        # Runs BOTH Passenger targets (deploy.sh PYTHON_TARGETS=(3.9 3.11)). 3.11 is
        # primary, but a 3.10+ construct passes there and breaks the 3.9 build, so a
        # single-interpreter gate would ship it. Set GATE_PYTHON=3.11 to run just one.
        rc=0
        for target in ${GATE_PYTHON:-3.11 3.9}; do
            IMAGE="$(image_for_python_version "${target}")"
            PYTHON_VERSION="${target}"
            echo "[gate] === python ${target} (${IMAGE}) ===" >&2
            ensure_image
            run_ephemeral "${VENV}" -m pytest tests/ -p no:cacheprovider "$@" || rc=$?
        done
        exit "${rc}"
        ;;
    trove)
        # Validates every nyxloom handoff's YAML frontmatter against the canonical
        # schema. Mirrors `nyxloom lint` L1 (filename stem == frontmatter id) so the
        # trove is checkable before the daemon can even reach this repo.
        ensure_image
        run_ephemeral "${VENV}" tooling/test-runner/lint_trove.py "$@"
        ;;
    build)
        # naf-I03: run a command (normally `build_deployment.py ...`) INSIDE the
        # test-runner image matching a given Python version, so a webhosting build's
        # DB-seeding step (which IMPORTS the app + vendored cp39/cp311 .so files)
        # actually exercises the target ABI instead of the devcontainer's host
        # python3. deploy.sh phase_build is the caller.
        #
        # Unlike run_ephemeral (used by unit/trove/e2e, which rely on the image's
        # baked-in USER 1003), this ADDS an explicit --user so build artifacts
        # (deploy-webhosting-py*/, deploy-py*.zip, netcup_filter.db) stay writable by
        # whatever uid actually owns the bind-mounted host checkout — the image's
        # baked default is only a coincidence when it happens to match.
        #
        # Usage: testing-exec.sh build <python-version> [--] <cmd...>
        TARGET_PY="${1:?build requires a python version, e.g. 3.11 or 3.9}"; shift
        [ "${1:-}" = "--" ] && shift
        [ $# -gt 0 ] || { echo "usage: testing-exec.sh build <python-version> [--] <cmd...>" >&2; exit 2; }

        IMAGE="$(image_for_python_version "${TARGET_PY}")"
        PYTHON_VERSION="${TARGET_PY}"
        ensure_image

        # Provenance (naf-I03): these images are local-only (never pushed to a
        # registry), so there is no RepoDigest — the content-addressed image ID is
        # the strongest identifier available. build_deployment.py stamps this into
        # build_info.json as "builder_image_digest".
        BUILDER_IMAGE_DIGEST="$(docker image inspect --format='{{.Id}}' "${IMAGE}")"

        docker run --rm \
            -v "${PHYSICAL_REPO_ROOT}:/workspaces/netcup-api-filter:rw" \
            -w "${CONTAINER_WORKDIR}" \
            --user "${USER_UID}:${DOCKER_GID}" \
            -e "NAF_BUILDER_IMAGE_DIGEST=${BUILDER_IMAGE_DIGEST}" \
            "${IMAGE}" "${VENV}" "$@"
        ;;
    e2e)
        # Playwright E2E against a running deploy-local + mocks. The browser is OFFLOADED
        # to the pwmcp container (infra/pwmcp) on naf-dev-network — never an engine in this
        # image. Default to that container's alias; export PLAYWRIGHT_SERVER_WS to override.
        # (INFRA-1 will let ciu own this via [test_runner.pwmcp].ws_url.)
        PLAYWRIGHT_SERVER_WS="${PLAYWRIGHT_SERVER_WS:-ws://pwmcp:3000/}"
        ensure_image
        run_networked "${VENV}" -m pytest -p no:cacheprovider "${@:-ui_tests/tests}"
        ;;
    shell)
        ensure_image
        run_ephemeral bash
        ;;
    *)
        usage
        ;;
esac
