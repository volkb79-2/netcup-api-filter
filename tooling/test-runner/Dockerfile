# netcup-api-filter — the GATING test-runner container.
#
# WHY THIS EXISTS — cockpit doctrine:
#   The gating suite NEVER runs in the devcontainer. The devcontainer is a *cockpit*
#   (inspect, drive deploys); its pins are not a ship signal. This is the netcup
#   equivalent of dstdns `tools/test-runner` and vbpub `tester-unified`.
#
# WHY PYTHON 3.11 — fidelity to the DEPLOYED runtime:
#   The app ships to shared webhosting under Passenger. `deploy.sh` builds
#   deploy-py311.zip as the PRIMARY artifact and build_deployment.py vendors wheels
#   with `--python-version 3.11 --only-binary`. The devcontainer runs 3.14, so
#   "green in the devcontainer" can hide a real deploy break: 3.10+ syntax, or a
#   dependency that resolves a cp314 wheel but has no cp311 wheel, fails HERE at
#   import/collect — not as a post-deploy 500. 3.9 is the secondary Passenger
#   target; build it with PYTHON_VERSION=3.9 to reproduce the 3.9 compat guards.
#
# SINGLE SOURCE OF TRUTH — the closure is DERIVED, never duplicated:
#   requirements.webhosting.txt (runtime) + requirements-dev.txt (adds the test
#   toolchain and already `-r`s the runtime file). Change a dependency there and it
#   flows to the gate on the next image rebuild — there is no second list to sync.
#   (Unlike the vbpub family, this repo has no pyproject.toml to derive from.)
#
# NO BROWSER ENGINE, deliberately:
#   JS-rendered UI is driven via the external Playwright-as-a-Service (pwmcp) over
#   PLAYWRIGHT_SERVER_WS. Never install a browser engine here (or in the cockpit).
#
# The app source + tests are BIND-MOUNTED at runtime (see docker-compose.yml) at
# /workspaces/netcup-api-filter; this image supplies only the runtime closure +
# test toolchain. pytest.ini already sets `pythonpath = . src`.
#
# Build (from the repo root):
#   docker build -f tooling/test-runner/Dockerfile -t netcup-api-filter/test-runner:local .
ARG PYTHON_VERSION=3.11
FROM python:${PYTHON_VERSION}-slim-trixie

ARG PYTHON_VERSION=3.11
ARG RUN_UID=1003
ARG RUN_GID=994

# Toolchain the gate itself needs:
#   git    — tests/tooling and nyxloom attempts inspect git state
#   curl   — health probes against a deployed app / mock services
#   procps — process inspection when a gate run hangs
# Kept deliberately thin: this is a gate, not a debug cockpit (that is the devcontainer).
RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl procps \
 && rm -rf /var/lib/apt/lists/*

# One venv under /opt built with --copies (a real interpreter binary), so a runtime
# HOME bind at /home/tester can never shadow it. Deps come from the repo's own
# requirements files — copied alone first so this layer caches independently of source.
COPY requirements.webhosting.txt requirements-dev.txt /tmp/reqs/
RUN python -m venv --copies /opt/tester-venv \
 && /opt/tester-venv/bin/pip install --no-cache-dir --upgrade pip \
 && /opt/tester-venv/bin/pip install --no-cache-dir -r /tmp/reqs/requirements-dev.txt \
 && rm -rf /tmp/reqs \
 && /opt/tester-venv/bin/python -c "import flask, sqlalchemy, bcrypt, pyotp, geoip2, httpx, pytest, hypothesis; print('netcup test-runner closure OK on python ${PYTHON_VERSION}')"

# jsonschema: validates nyxloom handoff frontmatter in the trove gate (nyxloom-trove/).
# Not an app dependency, so it is NOT added to the repo's requirements files.
RUN /opt/tester-venv/bin/pip install --no-cache-dir jsonschema pyyaml

# The container runs as the host-owned uid so bind-mounted files stay writable. The
# base image has no passwd entry for it and no writable HOME. Provide BOTH — a passwd
# entry (pwd.getpwuid() must resolve) AND a writable HOME with XDG dirs — or suites
# fail with PermissionError/KeyError that look like breakage but are pure environment.
# (This is tester-unified's hard-won lesson; do not drop it.)
RUN echo "tester:x:${RUN_UID}:${RUN_GID}:tester:/home/tester:/bin/bash" >> /etc/passwd \
 && echo "docker:x:${RUN_GID}:tester" >> /etc/group \
 && mkdir -p /home/tester/.config /home/tester/.cache /home/tester/.local/state \
 && chown -R ${RUN_UID}:${RUN_GID} /home/tester

USER ${RUN_UID}
ENV HOME=/home/tester \
    XDG_CONFIG_HOME=/home/tester/.config \
    XDG_CACHE_HOME=/home/tester/.cache \
    XDG_STATE_HOME=/home/tester/.local/state \
    TESTER_VENV=/opt/tester-venv \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /workspaces/netcup-api-filter

# Persistent peer: stay up so testing-exec.sh can `docker exec` into it, and so it can
# sit on naf-dev-network alongside the mock services. Ephemeral `docker run --rm` (the
# nyxloom gate form) overrides this CMD.
CMD ["sleep", "infinity"]
