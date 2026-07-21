# naf-P05 — REPORT (PARTIAL: O1 merged, O2 open)

**Status:** O1 MERGED to `main` (merge `b7ae4cd`, impl commit `628457e`). Orchestrator
(Opus) implementation. **The handoff stays OPEN in `handoffs/` for O2.**

## O1 — done (`.env.services` + `tests/test_env_services_sourcing.py`)

`.env.services` derived `POWERDNS_API_URL` from an unconditional `${PUBLIC_FQDN}`, so under
`set -euo pipefail` (every consumer) sourcing aborted with "PUBLIC_FQDN: unbound variable"
whenever post-create hadn't written it — bricking `deploy.sh` / `run-local-tests.sh` on any
devcontainer rebuild. Fix: derive the URL only when `PUBLIC_FQDN` is set, else leave it
empty. Verified `env -i bash -c 'set -euo pipefail; source .env.services'` → rc 0.

**O1 = the critical defuse.** Even with post-create still not writing `PUBLIC_FQDN` (O2), the
guarded `.env.services` no longer aborts consumers; the HTTPS/PowerDNS path simply has an
empty URL until O2 lands.

Test note: the first assertion was buggy (`${VAR:-<unset>}` renders an empty string as
`<unset>`, so it couldn't tell "set-to-empty" from "unbound"). The GATE caught it (1 failed)
— it was never merged. Corrected to `${VAR-<UNBOUND>}` (single dash). The `.env.services`
fix itself was correct throughout (rc 0 from the start). A small reminder that the gate
catches the reviewer's own mistakes too.

## O2 — deferred (still the handoff's remaining scope)

`post-create.sh` writes no `PUBLIC_FQDN` to `.env.workspace` (reverse-DNS detection per
`docs/FQDN_DETECTION.md`). Implementing it is straightforward; VALIDATING it is not — reverse
DNS depends on the actual host/network, so O2 needs a real devcontainer rebuild, which the
gate cannot exercise. Left for a session that can drive a rebuild. Scope narrows to
`post-create.sh` + `docs/FQDN_DETECTION.md`.

## Gate

`./tooling/test-runner/testing-exec.sh unit` → **422 passed on python 3.11 AND 3.9**.
