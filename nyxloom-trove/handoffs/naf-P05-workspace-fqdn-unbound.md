---
schema_version: 1
id: naf-P05-workspace-fqdn-unbound
project: naf
title: "post-create drops PUBLIC_FQDN; .env.services then aborts every set -u consumer"
tier: sonnet5-high
input_revision: "adcba7d"
depends_on: []
session: fresh
source: {kind: review, ref: "docs/deprecated/FOLLOWUP_REVIEW_2026-07-16.md#P0-8"}
scope:
  touch:
    - ".devcontainer/post-create.sh"
    - ".env.services"
    - "docs/FQDN_DETECTION.md"
  forbid:
    - "deploy.sh"
    - "run-local-tests.sh"
    - ".devcontainer/devcontainer.json"
oracles:
  - id: O1
    observable: "`env -i bash -c 'set -euo pipefail; source .env.services'` exits 0 in an environment where no PUBLIC_* variable is set and no .env.workspace exists"
    negative: "it exits non-zero with 'PUBLIC_FQDN: unbound variable' — today's behavior, which aborts deploy.sh at its source line before even --help is parsed"
    gate: trove
  - id: O2
    observable: "After running post-create.sh's workspace-file generation, .env.workspace contains a non-empty PUBLIC_FQDN (detected per docs/FQDN_DETECTION.md), and `bash -n` passes on the generated file"
    negative: "post-create writes a .env.workspace with no PUBLIC_FQDN, so the repo works only while a stale pre-rework file survives on disk and breaks on the next rebuild"
    gate: trove
gates: [trove]
escalate_if:
  - "a named contract cannot be met as specified"
  - "scope requires editing a forbidden file (deploy.sh / run-local-tests.sh / devcontainer.json)"
  - "FQDN detection cannot work offline and no documented fallback exists"
---

# P05 — The devcontainer rebuild bomb

## STATUS 2026-07-21 — O2 SUPERSEDED by naf-I04 (CLOSED)

**O2 is superseded, not implemented.** naf-I04 (host-traefik exposure) retired naf's dev
nginx TLS proxy that O2's reverse-DNS `PUBLIC_FQDN` write existed to feed, and made
`PUBLIC_FQDN` a **ciu config fact** (`topology.external.public_fqdn` in
`ciu.global.defaults.toml.j2`) instead of a post-create reverse-DNS PTR lookup. O1 (below)
already shipped and remains the live fix. `docs/FQDN_DETECTION.md` has been reduced to a
superseded note pointing at `docs/DEV_INFRA_SETUP.md`. This handoff is closed.

## PARTIAL STATUS 2026-07-20 (orchestrator) — O1 LANDED, O2 REMAINS

O1 (the critical bomb-defuse) is **done and merged**: `.env.services` now guards the
`POWERDNS_API_URL` derivation (`if [ -n "${PUBLIC_FQDN:-}" ]`), so sourcing it under
`set -euo pipefail` with no `PUBLIC_*` set exits 0 instead of aborting every consumer.
Verified: `env -i bash -c 'set -euo pipefail; source .env.services'` → rc 0. Regression
test `tests/test_env_services_sourcing.py` runs in the unit gate. This alone un-bricks
`deploy.sh` / `run-local-tests.sh` across a devcontainer rebuild.

**O2 REMAINS (deferred):** `post-create.sh` still writes no `PUBLIC_FQDN` to
`.env.workspace` (reverse-DNS detection per `docs/FQDN_DETECTION.md`). Without it the
HTTPS/PowerDNS-over-public-edge path has an empty URL — but nothing aborts. O2 needs the
detection logic AND validation in a real devcontainer rebuild (reverse DNS depends on the
environment), which cannot be exercised from the gate. Keep this handoff open for O2; the
scope narrows to `post-create.sh` + `docs/FQDN_DETECTION.md`.

---


> Tier: sonnet5-high · Base branch: main (input_revision adcba7d).
> Source: the deep review, finding **P0-8**. Reproduced:
> `env -i bash -c 'set -euo pipefail; source .env.services'` → *"PUBLIC_FQDN: unbound
> variable"*. The repo's whole local workflow currently survives only because a stale,
> pre-rework `.env.workspace` happens to still exist on disk. The next devcontainer
> rebuild breaks `deploy.sh`, `run-local-tests.sh`, and `start-ui-stack.sh` at once.
> The user has confirmed this devcontainer **stays** and will be used soon — so this is
> live, not archaeology.

## Context to read first (read ONLY these)

- `.env.services` ~line 85: `POWERDNS_API_URL="https://${PUBLIC_FQDN}..."` — an
  unconditional expansion. Under `set -u` (which every consumer uses) this aborts at
  *source* time, before any argument parsing.
- `.devcontainer/post-create.sh` ~line 150: the `cat > .env.workspace` heredoc that
  regenerates the workspace file. It writes `REPO_ROOT`, `PHYSICAL_REPO_ROOT`,
  `DOCKER_NETWORK_INTERNAL`, `USER_UID`, `DOCKER_GID`, … but **no** `PUBLIC_FQDN` /
  `PUBLIC_IP` / `PUBLIC_TLS_*`. Grep the file: zero `PUBLIC_FQDN` references.
- `docs/FQDN_DETECTION.md` — the documented reverse-DNS detection contract this used to
  implement. It is the spec; the code drifted from it.
- `deploy.sh` ~line 47 (`source .env.services`) and ~line 722 — READ ONLY. Shows the
  consumer and that the docs still claim post-create auto-detects the FQDN.
- `tooling/test-runner/testing-exec.sh` — READ ONLY, as a worked example of a consumer
  that deliberately does NOT source `.env.services` for exactly this reason, and asserts
  its inputs with `:?`.

## Work

1. Reinstate FQDN detection in `post-create.sh` per `docs/FQDN_DETECTION.md`, writing
   `PUBLIC_FQDN` (and the `PUBLIC_*` companions the file documents) into
   `.env.workspace`. Detection must not hang without network: bound it and fall back to
   a clearly-marked value, or leave it unset and let step 2 handle it — but never silently
   emit an empty string that looks detected.
2. Make `.env.services` robust for mock-only flows: a `POWERDNS_API_URL` derivation that
   needs a TLS FQDN must not abort consumers that never touch PowerDNS. Either guard the
   derivation, or fail with an explicit, actionable message naming the missing variable
   and how to regenerate it — a `:?` message, not an `${X:-default}` cross-environment
   fallback (AGENTS.md §2 / docs/FAIL_FAST_PRINCIPLE.md).
3. Reconcile `docs/FQDN_DETECTION.md` with what the code now does.

## Oracles / gate

O1 and O2 are shell contracts, so they run under the **`trove`** gate — a container
`bash` invocation, not pytest. Add them as a small executable check the gate runs (a
script under `tooling/test-runner/` invoked by the `trove` gate, or a pytest module under
`tests/` that shells out — if you choose the latter, use the `unit` gate id instead and
say so in the report).

```
./tooling/test-runner/testing-exec.sh trove
```

Never validate this in the devcontainer shell alone: a stale `.env.workspace` in the
cockpit will make a broken change look green. That is the exact failure mode this
package exists to kill.

## Scope / forbid

Touch only the three files in `scope.touch`. `deploy.sh` and `run-local-tests.sh` are
victims, not causes — do not paper over the bug by adding defaults there. Editing
`devcontainer.json` is out of scope (the user is keeping it as-is).

## BLOCKED rule

If a named contract cannot be met as specified, or the work requires editing a forbidden
file, STOP — write `BLOCKED: <reason>` to the LOG, commit, and exit. Do NOT improvise a
workaround.
