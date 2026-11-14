**SUPERSEDED 2026-07-21 — archived; work merged, see STATE.md**

# Infra plan — off the cockpit, onto ciu-governed containers + host traefik (2026-07-20)

## STATUS 2026-07-20 — INFRA-1 + INFRA-2 LANDED; INFRA-3 + INFRA-4 CARVED (paused)

Per **D-006** (decided autonomously; the interview was hook-blocked — all REVIEW-ME):

- **INFRA-1 ciu adoption — DONE.** Repo-root marker `ciu.global.defaults.toml.j2`, stack
  template `tooling/test-runner/ciu.defaults.toml.j2`, compose template
  `ciu.compose.yml.j2`, ciu gitignore rules. The committed rendered-output-named
  `ciu.toml` and the hand-written `docker-compose.yml` are **removed** (superseded).
  Verified end-to-end: `ciu env generate` → `ciu render` → `ciu check` (passes) →
  `ciu up --dry-run` completes all 17 steps and **injects governance**:
  `cgroup_parent=besteffort.slice; mem_limit=2g; mem_reservation=256m; read_iops=200;
  write_iops=400; device=/dev/vda; services_injected=1`. Rendered `workspace` now derives
  from mountinfo instead of the old hardcoded host path.
- **INFRA-2 pwmcp — DONE.** `infra/pwmcp/docker-compose.yml` (hardened: `user 1000:1000`,
  `cap_drop ALL`, `no-new-privileges`, `shm_size 2gb`, healthcheck, alias `pwmcp`),
  `playwright==1.61.*` added to the gate closure, and `testing-exec.sh e2e` now defaults
  `PLAYWRIGHT_SERVER_WS=ws://pwmcp:3000/` instead of hard-failing. **Proven live:**
  `naf-dev-pwmcp` healthy on `naf-dev-network`, and `http://pwmcp:3000/health` returns
  `200 {"status":"ok","max_clients":2}` from a peer container. The e2e gate is no longer
  un-runnable — this unblocks **naf-P06 part 2**.
- **INFRA-3 / INFRA-4 — CARVED, NOT EXECUTED.** See
  `handoffs/naf-I03-containerized-build.md` and `handoffs/naf-I04-host-traefik-exposure.md`.
  Both modify the production deploy path; both PAUSED for operator review. INFRA-4 still
  needs **Decision A (the FQDN)** — it cannot be guessed.

**Findings recorded in backlog B-INFRA** (all hit live during adoption): the gate never
rebuilds on dependency drift (`ensure_image` builds only if missing → silent stale-closure
gating); ciu resolves to the **wrong repo** from this devcontainer (dstdns's sourced env wins
— a bare `ciu render` rendered 17 dstdns stacks, so every naf ciu call needs
`--define-root`); `ciu env generate` derived and **created** its own network
(`netcup-api-filter-7716ce-network`), so `network_name` is now pinned explicitly to
`naf-dev-network`; `infra/pwmcp/` remains hand-written compose (a valid `--shipped` path)
rather than a `.j2` stack.

---


**Goal (operator directive, 2026-07-20):** stop using the devcontainer as a build/test
*cockpit*. Build and test `naf` in **version-specific containers (Python 3.9 + 3.11, the
Passenger deploy targets)** under **ciu** governance (cgroups/mem/IO safeguards). Run UI/e2e
against a **pwmcp** browser container. **Amendment:** drop naf's own reverse-proxy/cert
handling and expose dev services through the **host-side traefik** (`edge-traefik` /
`vbpub/tls-edge`) using ciu-managed labels, copying the dstdns pattern.

This is the doctrine already stated in `tooling/test-runner/` and project memory: *green in
the 3.14 cockpit is not a ship signal.* This plan finishes the job the test-runner started.

Base: `main` @ (B-AUTH batch, this session). Research: ciu / pwmcp / containerized-build /
traefik reference sweeps, all file-cited in the session log.

## Environment facts verified on this host (2026-07-20)

- `ciu` is installed in the devcontainer (`4.7.1.dev153`).
- Running & healthy (4–6 days): `edge-traefik` (traefik v3.7), `edge-dockerproxy`,
  `dstdns-shared-local-pwmcp` (`ghcr.io/volkb79-2/pwmcp:latest`).
- Networks present: `ingress_public` (traefik consumer net), `naf-dev-network`,
  `traefik_internal`.
- `edge-traefik` `websecure` entrypoint carries `certResolver: letsencrypt` — **consumers
  need no TLS/cert labels**, just `traefik.enable` + a `Host()` router + `ingress_public`.
- The shared `dstdns-shared-local-pwmcp` is on `dstdns-98535c-network` / `pwmcp` — **not**
  `naf-dev-network`, so naf can't reach it as-is.
- `.env.workspace` currently has **no** `PUBLIC_*` vars (the stale file was cleaned).

## The four phases

Ordered by risk. INFRA-1/-2 are additive and fully validatable on this host. INFRA-3/-4 modify
the **production deploy path** (`deploy.sh`, `build_deployment.py`) and/or need a live stack.

---

### INFRA-1 — ciu adoption foundation  (naf-I01) · additive · validatable here

**Why:** naf's `tooling/test-runner/ciu.toml` is a *rendered-output* filename committed as
source, with **no generator behind it** and a hardcoded host path
(`ciu.toml:13 = /home/<user>/netcup-api-filter`). `ciu render`/`ciu up` can't run: there
is no repo-root marker, no `.j2` templates, no gitignore rules, no governance table, and the
env layer uses `USER_UID` where ciu expects `CONTAINER_UID`.

**Work:**
1. Add repo-root marker `ciu.global.defaults.toml.j2`: `[deploy]` (project_name=`naf`,
   environment_tag, network_name=`naf-dev-network`), `[deploy.env.defaults]`/`[deploy.env.shared]`
   (bridge `USER_UID`→`CONTAINER_UID`, `DOCKER_GID`, `PHYSICAL_REPO_ROOT`,
   `DOCKER_NETWORK_INTERNAL`), `[governance]` (see below), `[deploy.labels]` reverse-DNS prefix (see B104),
   `[topology.external]` public_fqdn (INFRA-4 consumes it).
2. Convert `tooling/test-runner/ciu.toml` → `ciu.defaults.toml.j2` using `{{ ciu.physical_repo_root }}`
   instead of the hardcoded path; gitignore the rendered `ciu.toml`, `ciu.env`, `**/.ciu/`
   (vendor `vbpub/ciu/.gitignored.ciu`).
3. Author `tooling/test-runner/ciu.compose.yml.j2` (or keep `docker-compose.yml` for the
   `ciu up --dir … --shipped` path — see Decision C).
4. **Governance** `[governance] enabled=true`, `mem_limit="2g"`, `mem_reservation="256m"`,
   blkio `read_iops`/`write_iops` (mirror dstdns 200/400), **`device` set explicitly** (DooD
   autodetect fails in-container). Skip the KSM opt-in shim (dstdns-specific; add only if the
   shim path exists here).
5. `ciu env generate`; validate `ciu render` + `ciu check` succeed and the governance overlay
   (`.ciu/ciu.compose.overlay.yml`) injects cgroup/mem/blkio caps on the gate container.

**Gate:** `ciu render`/`ciu check` clean; overlay present. The existing `testing-exec.sh unit`
gate keeps working unchanged (adoption is additive — the ephemeral `docker run` path stays).

---

### INFRA-2 — pwmcp for the e2e gate  (naf-I02) · additive · validatable here

**Why:** naf's `testing-exec.sh e2e` hard-requires `PLAYWRIGHT_SERVER_WS` but **nothing sets
it**, `playwright` is **absent from the gate image closure**, and there is no pwmcp container on
`naf-dev-network`. So the e2e gate is currently un-runnable. naf's test code already speaks the
raw `chromium.connect(ws://pwmcp:3000/)` path — no `pwmcp_client`/lease adoption needed.

**Work (three real gaps):**
1. Stand pwmcp up on `naf-dev-network` with alias `pwmcp` — either **vendor `infra/pwmcp/`**
   (ciu consumer stack, declarative, matches dstdns) or **attach the existing shared
   `dstdns-shared-local-pwmcp`** to `naf-dev-network` (lighter, but mutates a dstdns-owned container).
   See Decision B. Hardened: `user 1000:1000`, `cap_drop ALL`, `no-new-privileges`,
   `shm_size 2gb`.
2. Set `PLAYWRIGHT_SERVER_WS=ws://pwmcp:3000/` for the e2e gate (from ciu `[test_runner.pwmcp]`
   `ws_url`, already declared).
3. Add `playwright==1.61.*` to `requirements-dev.txt` (match the image tag; no browser install
   — the server owns the engine).

**Gate:** `testing-exec.sh e2e` — a smoke UI test connects to pwmcp and drives a page. **Also
unblocks naf-P06 part 2** (delete the can't-fail ui_tests), which was waiting on a working e2e
gate.

---

### INFRA-3 — containerized build (3.9 + 3.11)  (naf-I03) · MODIFIES DEPLOY PATH · highest value

**Why (the crux):** `deploy.sh phase_build` runs `build_deployment.py` under the **host
interpreter (3.14)** to initialize/seed the DB, while it has vendored **cp311/cp39 `.so`s**
first on `sys.path`. The live `deploy-webhosting/vendor/` holds **35 `cpython-311` `.so`
files** plus an abi3 bcrypt. Under host 3.14 those version-tagged `.so`s are **not even import
candidates**: pure-Python-fallback packages silently use the fallback, C-only ones (greenlet,
maxminddb, Pillow) would `ImportError`, and the abi3 bcrypt loads a cp311 binary under 3.14 —
a silent ABI mismatch. The build validates **nothing** about the target closure. (Flagged in
backlog B-OPS.)

**Work:**
1. Harden `build_deployment.py`: add a **host-vs-target guard** (refuse `initialize_database`
   unless `sys.version_info[:2]` == the requested target), neuter/fix the unsafe sdist
   fallback (`:104-127`) and its wrong-condition warning (`:109`), fix deprecated
   `datetime.utcnow()`.
2. Change `deploy.sh phase_build` to run `build_deployment.py` **inside** the matching
   `test-runner:py39`/`:py311` container (DooD, `--user ${USER_UID}:${DOCKER_GID}`, mount
   `${PHYSICAL_REPO_ROOT}`, `/opt/tester-venv/bin/python`) so `sys.executable` == the target
   interpreter. The version→image map already exists (`testing-exec.sh:110-114`).
3. Keep `--platform manylinux2014_x86_64 --only-binary :all:` for wheel *resolution* (glibc
   fidelity for the webhoster) even in-container. Assert the **all-binary invariant** (the thin
   gate image has no compiler) — escalate if any dep lacks a cp39/cp311 wheel.
4. Stamp the **builder image digest** into `build_info.json` (artifact provenance).

**Gate:** `deploy-py311.zip` + `deploy-py39.zip` build in-container and the DB seeds with the
target-ABI extensions actually loaded. **Risk:** touches the production artifact pipeline;
validate by building both zips and diffing the vendor tree before this ever ships.

---

### INFRA-4 — host traefik exposure; retire naf's reverse-proxy  (naf-I04) · MODIFIES DEPLOY PATH + DEV STACK

**Why:** the amendment. naf's reverse-proxy/cert/FQDN machinery is **dev-only** (production is
Passenger, where the hoster terminates TLS — untouched by this). The host already runs
`edge-traefik` on `ingress_public`. So the dev nginx edge is replaced by traefik labels.

**Removed (all dev):** the whole `tooling/reverse-proxy/` dir; `deploy.sh` `start_tls_proxy`/
`stop_tls_proxy` (`:704-809`), the `USE_HTTPS && local` branch (`:831`), `naf-dev-reverse-proxy`
cleanup (`:1378-1391`), `SERVICE_REVERSE_PROXY` (`:57`); the host `/etc/letsencrypt` mount and
`PUBLIC_TLS_*` handling; `docs/FQDN_DETECTION.md`'s reverse-DNS mechanism.

**Added:** the dev app (and PowerDNS API edge, per Decision D) join `ingress_public` (external)
and carry four labels — `traefik.enable=true`, `routers.<stack>-<svc>.rule=Host(\`<name>.<fqdn>\`)`,
`routers.….entrypoints=websecure`, `services.….loadbalancer.server.port=<port>`. TLS/cert are
inherited from the entrypoint. `PUBLIC_FQDN` becomes a **ciu config fact** (not PTR-detected),
still used for the session-cookie domain; `.env.services` `PUBLIC_FQDN→POWERDNS_API_URL`
re-points to the traefik route or goes internal.

**Supersedes:** **naf-P05 O2** (post-create reverse-DNS `PUBLIC_FQDN` write) is **obsoleted** —
close it, superseded by INFRA-4. The `PUBLIC_TLS_*` cert paths lose all consumers.

**Gate:** dev app reachable at `https://<name>.<fqdn>` via traefik. Validatable here
(edge-traefik + ingress_public are up) once the FQDN/DNS is settled (Decision A).

---

## Decisions this plan needs

- **A · public FQDN / DNS** for the traefik `Host()` rule (INFRA-4). dstdns uses
  `<project>.example.org` behind wildcard DNS. What hostname base for naf? *(operator
  — non-inferable env/DNS config)*
- **B · pwmcp** (INFRA-2): vendor naf's own `infra/pwmcp/` stack on `naf-dev-network`
  (declarative, matches dstdns) vs. attach the running shared `dstdns-shared-local-pwmcp`. *Recommend
  vendor-own* (declarative, no cross-project container mutation).
- **C · ciu depth** (INFRA-1): full `.j2` template convention (matches dstdns) vs. minimal
  `ciu up --shipped` over the hand-written compose. *Recommend full* (the user asked to copy
  the dstdns pattern; `--shipped` leaves the rendered-vs-source confusion in place).
- **D · which dev services get public traefik routes** (INFRA-4): app (HTTPS UI/API) + PowerDNS
  API edge, Mailpit internal-only? *Recommend app + PowerDNS public, Mailpit internal.*
- **E · execution sequencing this session** — see below.

## Recommended sequencing (Decision E)

INFRA-1 + INFRA-2 are additive, low-risk, and validatable on this host — **execute + gate now**.
INFRA-3 + INFRA-4 modify the production deploy path and can't be fully validated by the unit
gate — **carve as detailed handoffs, flag, and pause for operator review** before touching
`deploy.sh`. All autonomous decisions are written here for later review, per operator standing
instruction.
