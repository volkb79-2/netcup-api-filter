# naf release architecture — cmru adoption plan (2026-07-21)

**Plan only — no code in this pass** (operator: "plan only, wait for the SSH/deploy research").
Goal: outsource all reusable build/release/deploy logic to the upstream tools (cmru, ciu) and
keep naf minimal. Retire the ~2500 lines of bespoke `build_deployment.py` + `deploy.sh`.

Sourced from two research sweeps (cmru capabilities; multi-host SSH-deploy across ciu/cmru/
dstdns), both file-cited in the session log.

---

## The three-tool split (decided)

| Tool | Role | naf's use |
|---|---|---|
| **cmru** | RELEASE — version, tag, build+publish artifacts *for external consumption* (GitHub Release, `.sha256`, `latest.json`, ghcr push, the resolver, the `get.py` installer) | produces the tarball variants + the py3.14 oci-image; owns versioning |
| **ciu** | DEPLOY/run — get an artifact onto a host + activate it (inner loop) | push-deploys the tarball to the Passenger webhoster (via a NEW docker-optional `--host` path) |
| **naf** | project-specific detail only | a bake file, one build step, a ~10-line activation script, host + cmru config |

The decisive boundary (`vbpub/docs/ciu-vs-cmru.md:14-16`): *"published for external consumption?
yes → cmru; no → ciu."* Producing the tarball is release (cmru); pushing it to the webhoster is
deploy (ciu). **cmru's S13 ("no FTP/SFTP deploy") stays** — we extend ciu, not challenge cmru.

## Targets → tools

1. **Tarball(s) + installer (py3.9/3.11, webhoster).** cmru `tarball`/`bundle` profile publishes
   them; a NEW cmru feature makes it **multi-variant** (cp39 + cp311 per release). ciu (NEW
   docker-optional `--host`) pushes the chosen variant to the webhoster and activates it.
2. **Container image (py3.14, self-hosting).** cmru `oci-image` (built-in `docker buildx bake
   --push`, already works — mdt is the template) + a naf `docker-bake.hcl`. The *same* bake file
   feeds ciu locally (`bake --load`) and cmru for publishing.
3. **Dev/test on 3 versions.** Stays in ciu (test-runner + app-local). Extend the gate to add
   **3.14** (it now backs a shipped artifact).

## Decisions locked (this session)

- **Multi-variant tarballs**, selected by an **explicit installer argument** — the webhoster has
  no accessible `python`/`python3` to auto-detect, so the sysadmin names the target (3.9|3.11),
  or the installer prompts.
- **3.14 is a gated ship target** now (gate runs 3.9/3.11/3.14).
- **Versioning = cmru `scm`** (git tags → semver + `devN`). naf has none today — pure gain.
- **Push model, not pull** — the webhoster can't run `get.py` (no python3 to bootstrap it),
  can't run dstdns's docker-requiring adapter, can't run `ciu up --host` (docker). Only a
  control-host push (target needs shell + tar/unzip + touch) fits.
- Keep cmru **S13**; extend **ciu `--host`** (its reserved `--thin` slot).

## Two reusable UPSTREAM features to add (per "reusable → upstream")

### CMRU-FEAT — multi-variant tarball publish + variant-selecting installer
cmru is **single-asset-per-tag today** (`release.py:find_artifact:322-334` errors on >1 match;
`get.py.tmpl:404` fetches exactly `<tag><suffix>`). Add: publish N named variants under one tag
(e.g. `<tag>-py39.tar.xz`, `<tag>-py311.tar.xz`), record them in `latest.json`, and let the
installer take a `--variant`/`--python-version` argument (or prompt) to pick. Reusable for any
project shipping per-interpreter/per-arch artifacts. **File in cmru's KNOWN_ISSUES_TODO_BACKLOG.md**
(its canonical tracker — "file cmru bugs/feature-reqs here, not in consumer repos").

### CIU-FEAT — docker-optional `--host` push-activate path
`ciu up --host` today rsyncs the repo + runs `ciu render && ciu up` on the target (needs docker
+ python there); `--thin` is reserved-but-unimplemented (`cli.py:341-343`, exits 1). Generalize
into a **docker-optional** mode:
1. push the artifact to `bundle_dir` — reuse `ssh_sync` (rsync) **+ add an scp/sftp fallback**
   (a webhoster may lack rsync; naf uses `scp` for exactly this).
2. run a **pluggable activation contract** over `ssh_exec` — the SAME `bootstrap/apply/health/
   rollback` verbs cmru's `ProjectAdapter` / dstdns's `scripts/bootstrap.py` use — instead of the
   hardcoded `ciu render && ciu up`. For a shell-only host, ciu runs those verbs remotely; the
   project supplies the (shell) activation script.
Reuses 100% of ciu's `hosts.py` inventory (`.ciu.hosts.toml`, `[deploy.hosts.*]`, `ASK_VAULT`
keys, `known_host` pinning) and `transport_ssh.py`. **File in ciu's KNOWN_ISSUES_TODO_BACKLOG.md.**

*Constraint nuance (from the research):* "no python on the target" is half-true — Passenger runs
a version-pinned python3 and naf's current deploy uses a remote `python3 -c` for optional
SECRET_KEY preservation. The real invariant: you **cannot build/install on-host** (no pip/venv-
build → wheels must be pre-vendored per interpreter), and cannot assume a general-purpose
interpreter. Design the reusable core to need only **shell + tar/unzip + touch**; treat any
remote-python step as optional/best-effort.

## naf-side work (minimal — this is all that stays in naf)

- **`docker-bake.hcl`** with a `py3.14` target (the stale root `Dockerfile` is dead — installs a
  non-existent `requirements.txt`, a YAML config, and runs the dead `filter_proxy`; delete it +
  `docker-compose.yml`, B-OPS). The target builds the real app (gunicorn `passenger_wsgi:application`,
  TOML config) on `python:3.14-slim`.
- **`cmru.toml`**: `[project.naf]` `prefix="naf-v"`, `artifacts=["oci-image","tarball"]` (or
  `bundle`), `[version] strategy="scm"`, `[oci] bake_file/target`, `[installer]`
  (install dirs, `asset_suffix`, `entrypoint=scripts/activate.py`, `required_commands`).
- **One `[steps.build]`**: a slimmed `build_deployment.py` that produces the per-interpreter
  vendored tarballs — reusing the **already-landed containerized build** (`testing-exec.sh build
  <ver> -- …`, INFRA-3) so the ABI is correct per variant.
- **`scripts/activate.py`** (~10 lines, the naf-specific detail ciu's `--host` calls): extract the
  tarball, `touch tmp/restart.txt` (Passenger reload), health-probe `/admin/login`, optional
  SECRET_KEY preserve. Modeled on the `apply/health/rollback` verb contract.
- **`.ciu.hosts.toml`**: the webhoster inventory (`ssh_host`, `ssh_user`, `ssh_key` incl.
  `ASK_VAULT`, `known_host` pin, `bundle_dir=/netcup-api-filter`) — replaces the `.env`
  `WEBHOSTING_SSH_*` vars.
- **Gate**: add a `3.14` test-runner image; gate runs `3.9/3.11/3.14`.
- **Retire**: `build_deployment.py`'s versioning/provenance + `deploy.sh`'s build/scp/ssh push
  (replaced by cmru build + ciu `--host` deploy).

## Phasing (each independently shippable)

- **Phase 1 — container (near-zero upstream change).** naf `docker-bake.hcl` (py3.14) + `cmru.toml`
  `oci-image`; add 3.14 to the gate; delete the dead root `Dockerfile`/`docker-compose.yml`.
  Validates cmru adoption end-to-end with the lowest-risk target (doesn't touch the live webhoster
  path). cmru `oci-image` already works, so this is mostly naf config + a bake file.
- **Phase 2 — cmru multi-variant feature + naf tarball build.** Land CMRU-FEAT upstream; add naf's
  `[steps.build]` tarball step (per-interpreter, via the INFRA-3 container build) + `[installer]`.
  Result: `cmru release` publishes cp39 + cp311 tarballs + a variant-selecting installer.
- **Phase 3 — ciu docker-optional `--host` + naf deploy.** Land CIU-FEAT upstream; add naf's
  `scripts/activate.py` + `.ciu.hosts.toml`. Result: `ciu up --host webhoster` pushes+activates the
  chosen tarball. Retire `deploy.sh`'s push.
- **Phase 4 — cleanup.** Delete the bespoke `build_deployment.py`/`deploy.sh` release plumbing;
  reconcile docs (ties into B-INFRA-DOCS).

## Open sub-decisions (resolve when we execute)

- **`tarball` vs `bundle`** — recommend `bundle` (deterministic tar.xz + `manifest.json` +
  minisign; a strict upgrade; naf strips `.dist-info` today so it has no manifest).
- **Activation contract shape** — adopt the `ProjectAdapter` verbs (`bootstrap/apply/health/
  rollback`) so pull-activated (get.py) and push-activated (ciu `--host`) share ONE contract.
- **Does the py3.14 container also get a curl-installer**, or just ghcr pull? (Probably just pull.)
- **Versioning bump policy** — conventional-commits vs manual.
