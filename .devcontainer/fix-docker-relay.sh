#!/usr/bin/env bash
# Repair the docker socket relay's half-close timeout.  Idempotent; safe to run
# on every container start, and a no-op on setups that don't use the relay.
#
# WHY (diagnosed 2026-07-27, dstdns devcontainer):
#   The `docker-outside-of-docker` devcontainer feature bind-mounts the host
#   socket to /var/run/docker-host.sock and — whenever the host socket's GID
#   already exists as a container group (994/docker here, so: always) — fronts
#   it with
#       socat UNIX-LISTEN:/var/run/docker.sock,fork,... UNIX-CONNECT:/var/run/docker-host.sock
#   with NO -t flag.  socat's default half-close timeout is 0.5 SECONDS.
#
#   A non-interactive `docker run` hijacks the HTTP connection and shuts down
#   its write side immediately.  socat sees EOF client->server and tears down
#   server->client half a second later.  The container still runs to completion
#   on the daemon (which neither knows nor cares that the client left), but the
#   CLI receives only the first ~0.5s of output, and may report EXIT 0 for a
#   container that exited non-zero.
#
#   That makes a FAILING containerised test suite indistinguishable from a
#   passing one.  It is a false-green generator sitting underneath every gate
#   run from this cockpit.  Measured: two red gate containers (exit 1) came back
#   as `docker run` exit 0 with 25 bytes of output.
#
#   Asymmetry worth knowing when testing for this: the TRUNCATION is
#   deterministic, the EXIT-CODE corruption is NOT — a sentinel against the same
#   broken relay was truncated yet still returned the right code.  Judge on
#   OUTPUT, never the exit code alone.  `docker version` and `docker logs` stay
#   healthy throughout (plain request/response, never hijacked), so neither is a
#   valid check.
#
# WHAT THIS DOES
#   1. Patches the feature's init script so a plain `docker restart` is correct.
#   2. Restarts the live relay, because the entrypoint already started an
#      unpatched socat before any lifecycle hook could run.
#
# WHAT THIS DELIBERATELY DOES NOT DO
#   It does not fail the container start.  A broken transport is only dangerous
#   when a gate is being read, so the fail-CLOSED assertion belongs in the gate
#   path (`nyxloom doctor`, and the gate harness itself), not in the IDE path.
#   See vbpub nyxloom reference/LESSONS.md L18 defeat 4 for the transport sentinel.
#
# STOPGAP.  The real home for this repair is the mdt base image
# (vbpub/modern-debian-tools-python-debug, scripts/finalize_container_environment.py
# :: repair_docker_socket_relay), so that EVERY mdt-based devcontainer gets it
# rather than just this repo.  That has landed there; this hook stays until the
# mdt image is rebuilt and pinned GHCR tags are bumped, after which it is
# a harmless no-op (it detects the already-repaired relay and exits).
set -uo pipefail

INIT_SCRIPT=/usr/local/share/docker-init.sh
HALF_CLOSE_TIMEOUT=86400   # seconds; must exceed the longest gate run

log() { echo "[fix-docker-relay] $*"; }

# --- 0. Is the relay even in play? -------------------------------------------
if ! command -v socat >/dev/null 2>&1; then
    log "socat not installed — relay not in use, nothing to do."
    exit 0
fi
if [ ! -S /var/run/docker-host.sock ]; then
    log "no /var/run/docker-host.sock — not a docker-outside-of-docker relay setup, nothing to do."
    exit 0
fi

# --- 1. Patch the init script so future starts are correct -------------------
if [ -w "$INIT_SCRIPT" ] || sudo -n true 2>/dev/null; then
    if grep -q "socat -t " "$INIT_SCRIPT" 2>/dev/null; then
        log "init script already carries -t; leaving it alone."
    elif grep -q "sudoIf socat UNIX-LISTEN:/var/run/docker.sock" "$INIT_SCRIPT" 2>/dev/null; then
        sudo cp -n "$INIT_SCRIPT" "${INIT_SCRIPT}.bak-pre-t-fix" 2>/dev/null || true
        sudo sed -i \
            "s|sudoIf socat UNIX-LISTEN:/var/run/docker.sock|sudoIf socat -t ${HALF_CLOSE_TIMEOUT} UNIX-LISTEN:/var/run/docker.sock|" \
            "$INIT_SCRIPT"
        log "patched $INIT_SCRIPT to start socat with -t ${HALF_CLOSE_TIMEOUT}."
    else
        log "WARNING: $INIT_SCRIPT has an unrecognised socat line; not patching. Inspect it by hand."
    fi
fi

# --- 2. Restart the live relay if it is missing -t ---------------------------
# NB: every pgrep/pkill pattern below brackets its first character ("[s]ocat").
# `pkill -f` matches the FULL command line of every process -- including the
# `sudo pkill -f <pattern>` process doing the killing, whose own argv contains
# the pattern verbatim. An unbracketed pattern makes pkill kill its own parent
# and die with it: the relay survives and the caller sees success. The bracket
# still matches the literal "socat" in the target's argv, but the killer's argv
# holds the characters "[s]ocat", which the regex does not match.
# The entrypoint started socat before any lifecycle hook could run, so the
# process currently serving /var/run/docker.sock is the unpatched one.
if pgrep -f "[s]ocat -t ${HALF_CLOSE_TIMEOUT} UNIX-LISTEN:/var/run/docker.sock" >/dev/null 2>&1; then
    log "live relay already has -t ${HALF_CLOSE_TIMEOUT}; nothing to restart."
    exit 0
fi

if ! pgrep -f "[s]ocat UNIX-LISTEN:/var/run/docker.sock" >/dev/null 2>&1; then
    log "no unpatched relay running; nothing to restart."
    exit 0
fi

log "restarting the relay with -t ${HALF_CLOSE_TIMEOUT} (current one truncates at 0.5s)…"
# Kill the socat and its sudo wrapper, drop the stale listener, start a fresh one.
sudo pkill -f "[s]ocat UNIX-LISTEN:/var/run/docker.sock" 2>/dev/null || true
sleep 1
sudo rm -f /var/run/docker.sock
sudo sh -c "nohup setsid socat -t ${HALF_CLOSE_TIMEOUT} \
    UNIX-LISTEN:/var/run/docker.sock,fork,mode=660,user=${USER:-vscode},backlog=128 \
    UNIX-CONNECT:/var/run/docker-host.sock \
    >>/tmp/vscr-docker-from-docker.log 2>&1 &"
sleep 2

if [ -S /var/run/docker.sock ] && \
   pgrep -f "[s]ocat -t ${HALF_CLOSE_TIMEOUT} UNIX-LISTEN:/var/run/docker.sock" >/dev/null 2>&1; then
    log "relay restarted OK."
else
    log "ERROR: relay restart FAILED — /var/run/docker.sock may be unusable."
    log "       Fall back to: export DOCKER_HOST=unix:///var/run/docker-host.sock"
fi
exit 0
