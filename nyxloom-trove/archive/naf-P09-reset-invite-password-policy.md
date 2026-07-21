---
schema_version: 1
id: naf-P09-reset-invite-password-policy
project: naf
title: "Reset/invite paths bypass the password policy (hardcoded len<12; reset validates nothing)"
tier: sonnet5-high
input_revision: "c1acb8e"
depends_on: []
session: fresh
source: {kind: review, ref: "docs/deprecated/FOLLOWUP_REVIEW_2026-07-16.md#P1-C"}
advances: [M1]
scope:
  touch:
    - "src/netcup_api_filter/api/account.py"
    - "src/netcup_api_filter/password_reset.py"
    - "tests/test_password_policy_reset_invite.py"
  forbid:
    - "src/netcup_api_filter/account_auth.py"
    - "src/netcup_api_filter/api/admin.py"
    - "src/netcup_api_filter/api/ddns_protocols.py"
    - "src/netcup_api_filter/models.py"
oracles:
  - id: O1
    observable: "A password that passes the old len>=12 check but fails validate_password (e.g. 'aaaaaaaaaaaa' — 12 chars, low entropy) is REJECTED on both the /reset/<token> and /invite/<token> POST paths, with the same policy message validate_password returns."
    negative: "Today both routes gate only on `len(new_password) < 12`, so a weak 12-char password is accepted despite the app's real policy (min 20 chars + 100 bits entropy, models.validate_password)."
    gate: unit
  - id: O2
    observable: "complete_password_reset() itself rejects a policy-violating password (defense in depth) — a direct call with a weak password returns (False, <policy message>) and does not write a password_hash."
    negative: "complete_password_reset validates nothing today, so any caller (or a future one) can set an arbitrarily weak password."
    gate: unit
gates: [unit]
escalate_if:
  - "validate_password's signature or import path differs from models.validate_password(password)->(ok, err)"
  - "a named contract cannot be met as specified"
---

# naf-P09 — reset/invite must honor the real password policy

> **STATE (2026-07-21): ✅ DONE** — merged (`675a338`). See [../STATE.md](../STATE.md).

> Base: `main` @ `c1acb8e`. Gate: `./tooling/test-runner/testing-exec.sh unit` (3.11 + 3.9).
> Self-gate in your worktree. Review is against git state, not this report.

## The bug

The app's password policy is `models.py:166 validate_password(password) -> (ok, err|None)`
(min length + entropy, env-configurable), used by the normal signup/change paths. But the
recovery paths hardcode a weaker check:

- `api/account.py:220` (`/reset/<token>` POST) — `elif len(new_password) < 12:`
- `api/account.py:258` (`/invite/<token>` POST) — `elif len(new_password) < 12:`
- `password_reset.py:269 complete_password_reset()` — validates **nothing** before hashing.

So a 12-char low-entropy password sails through on the two highest-value account-takeover
surfaces (a reset or invite link).

## Fix

1. In both `api/account.py` routes, replace the `len(new_password) < 12` branch with a
   `validate_password(new_password)` call (import from `..models`), flashing the returned
   message on failure. Preserve the existing `new_password != confirm_password` check ahead
   of it and the surrounding control flow.
2. In `password_reset.py:complete_password_reset`, add a `validate_password` gate at the top
   (after token validation, before hashing) returning `(False, err)` on failure — defense in
   depth so the function is safe regardless of caller.

## While here — one leftmost-XFF site in THIS file (owned by P09, not P08)

`api/account.py:210-212` builds `client_ip` from `request.headers.get('X-Forwarded-For', ...)`
then `.split(',')[0]` and feeds it to `verify_reset_token(current_ip=client_ip)` for reset
IP-binding — the same spoofable leftmost pattern naf-P08 fixes elsewhere. Replace those lines
with `client_ip = request.remote_addr` (ProxyFix `x_for=1` is configured in app.py, so
remote_addr is the trusted client). This keeps the XFF fix consistent without P08 and P09
both editing `api/account.py`.

## Coordination

Files here (`api/account.py`, `password_reset.py`) are disjoint from naf-P07 and naf-P08 —
no shared-file merge concerns. `account_auth.py` / `api/admin.py` / `ddns_protocols.py` /
`models.py` are forbidden.

## Tests (`tests/test_password_policy_reset_invite.py`, new)

Backend-truth: (a) POST a weak-but-12-char password to a valid reset token and to a valid
invite token, assert the password is NOT changed (account.password_hash unchanged) and the
policy message surfaces; (b) call complete_password_reset directly with a weak password,
assert `(False, msg)` and no hash write; (c) a strong password still succeeds. Use the
conftest `app` fixture and helpers; mint reset/invite tokens via the real ResetToken flow.

## BLOCKED rule

If a contract cannot be met, or a forbidden file must change, STOP: write `BLOCKED: <reason>`
to the LOG, commit, exit.
