# netcup-api-filter — the GATING test-runner image (one per Python version).
#
# The devcontainer is a cockpit: nothing run there is a ship signal. This image is
# built once per shipped runtime (ciu renders one service per version, see
# ciu.compose.yml.j2) so "green" means green on the interpreter that ships:
#   3.11 = Passenger webhosting (tarball variant py311)
#   3.14 = OCI self-hosting image
# A construct or dependency that only works on one of them fails here at
# import/collect, not as a post-deploy 500.
#
# SINGLE SOURCE OF TRUTH — the closure is derived, never duplicated:
#   requirements-runtime.txt (what ships) + requirements-test.txt (the gate toolchain,
#   which already `-r`s the runtime file).
#
# NO BROWSER ENGINE: JS-rendered UI is driven through the external Playwright
# service (pwmcp) over PLAYWRIGHT_SERVER_WS.
#
# The repo is BIND-MOUNTED at runtime; this image supplies only the closure + toolchain.
# Build (ciu does this; PYTHON_VERSION has no default on purpose — an unset value
# makes the FROM below fail instead of silently choosing an interpreter):
#   docker build -f tooling/test-runner/Dockerfile --build-arg PYTHON_VERSION=3.11 .
ARG PYTHON_VERSION
FROM python:${PYTHON_VERSION}-slim-trixie

ARG PYTHON_VERSION
# No defaults: ciu passes the host-owned uid/gid (CONTAINER_UID / DOCKER_GID); an unset
# value fails the build instead of baking a host-specific number.
ARG RUN_UID
ARG RUN_GID

# git (>= 2.38, run-gate's exec-mode safe.directory contract), curl (health probes),
# procps (hang inspection). Thin on purpose: this is a gate, not a debug cockpit.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl procps \
 && rm -rf /var/lib/apt/lists/*

# One venv under /opt built with --copies (a real interpreter binary), so a runtime
# HOME bind can never shadow it.
COPY requirements-runtime.txt requirements-test.txt /tmp/reqs/
RUN python -m venv --copies /opt/tester-venv \
 && /opt/tester-venv/bin/pip install --no-cache-dir --upgrade pip \
 && /opt/tester-venv/bin/pip install --no-cache-dir -r /tmp/reqs/requirements-test.txt \
 && rm -rf /tmp/reqs \
 && /opt/tester-venv/bin/python -c "import flask, sqlalchemy, bcrypt, pyotp, geoip2, httpx, pytest, hypothesis; print('netcup test-runner closure OK on python ${PYTHON_VERSION}')"

# jsonschema + pyyaml: only for tooling/test-runner/lint_trove.py (nyxloom handoff
# frontmatter). Not app dependencies, so not in the repo's requirements files.
RUN /opt/tester-venv/bin/pip install --no-cache-dir jsonschema pyyaml

# The container runs as the host-owned uid so bind-mounted files stay writable. The
# base image has no passwd entry for it and no writable HOME: provide BOTH a passwd
# entry (pwd.getpwuid() must resolve) AND a HOME with XDG dirs, or suites fail with
# PermissionError/KeyError that look like breakage but are pure environment.
RUN echo "tester:x:${RUN_UID}:${RUN_GID}:tester:/home/tester:/bin/bash" >> /etc/passwd \
 && echo "docker:x:${RUN_GID}:tester" >> /etc/group \
 && mkdir -p /home/tester/.config /home/tester/.cache /home/tester/.local/state \
 && chown -R ${RUN_UID}:${RUN_GID} /home/tester

# run-gate durable state root (assay resume state + judge scratch). Mode 1777 is
# copied into the fresh named volume so the lane user can write it. MUST equal
# run-gate.toml [environments.*].state_root and lie outside every checkout.
RUN mkdir -p /run-gate-state && chmod 1777 /run-gate-state

USER ${RUN_UID}
ENV HOME=/home/tester \
    XDG_CONFIG_HOME=/home/tester/.config \
    XDG_CACHE_HOME=/home/tester/.cache \
    XDG_STATE_HOME=/home/tester/.local/state \
    TESTER_VENV=/opt/tester-venv \
    PATH=/opt/tester-venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /workspaces/netcup-api-filter

# Persistent peer: run-gate `docker exec`s lanes into it.
CMD ["sleep", "infinity"]
