---
schema_version: 1
id: naf-P07-2fa-lockout-dead-auth
project: naf
title: "TOTP 2FA has no lockout (infinite retries); remove two dead auth functions"
tier: sonnet5-high
input_revision: "c1acb8e"
depends_on: []
session: fresh
source: {kind: review, ref: "docs/deprecated/FOLLOWUP_REVIEW_2026-07-16.md#P1-C"}
advances: [M1]
scope:
  touch:
    - "src/netcup_api_filter/account_auth.py"
    - "src/netcup_api_filter/api/admin.py"
    - "tests/test_totp_lockout.py"
  forbid:
    - "src/netcup_api_filter/api/ddns_protocols.py"
    - "src/netcup_api_filter/api/account.py"
    - "src/netcup_api_filter/password_reset.py"
    - "src/netcup_api_filter/models.py"
oracles:
  - id: O1
    observable: "A backend-truth test drives verify_2fa() with method='totp' and a wrong code TFA_MAX_ATTEMPTS times; after the limit is_2fa_locked(account) is True and the last result's error names the lockout, exactly as for method='email'."
    negative: "Today the TOTP branch returns 'Invalid code' without calling increment_2fa_failures, so is_2fa_locked stays False forever and TOTP codes can be brute-forced indefinitely."
    gate: unit
  - id: O2
    observable: "grep for `request_password_reset` and `generate_secure_password` across src/ returns only removed-then-absent — no definition, no import, no caller; the full unit suite still collects and passes on 3.11 and 3.9."
    negative: "The dead plaintext-code reset path and the random.choices password generator remain as attack surface / import weight."
    gate: unit
gates: [unit]
escalate_if:
  - "removing request_password_reset reveals a live caller (it must not — verify first)"
  - "dropping the definition of generate_secure_password without also removing its api/admin.py:31 import would break collection — both edits are in THIS package; if the import is somehow elsewhere too, escalate"
  - "a named contract cannot be met as specified"
---

# naf-P07 — 2FA TOTP lockout + dead-auth removal

> Base: `main` @ `c1acb8e`. Gate: `./tooling/test-runner/testing-exec.sh unit` (runs 3.11 + 3.9).
> Self-gate in your worktree before finishing. Review is against git state, not this report.

## Item 1 — TOTP branch never counts failures (the real bug)

`account_auth.py:517 verify_2fa()` checks `is_2fa_locked(account)` up front (`:536`) and the
**email/telegram** branch increments on a bad code (`:627 increment_2fa_failures(account)`,
then reports `attempts_left`, `:628-644`). The **TOTP** branch (`:591-609`) returns
`TwoFactorResult(success=False, error="Invalid code")` at `:606` **without incrementing** —
so `is_2fa_locked` never becomes True and TOTP is brute-forceable. The admin path
(`api/admin.py:624`) counts correctly; mirror that.

**Fix:** in the TOTP failure case (`:599-606`, when `totp.verify(...)` is False), before
returning, call `increment_2fa_failures(account)`, compute
`attempts_left = TFA_MAX_ATTEMPTS - get_2fa_failure_count(account)`, and return the same
two-message shape the email branch uses (`attempts remaining` vs `Account locked for
{TFA_LOCKOUT_MINUTES} minutes`). Keep the existing `log_login_attempt(..., reason="Invalid
TOTP code")`. The **success** path already resets counters for all methods (`:648
reset_2fa_failures`), so leave that untouched. Do not alter the recovery-code branch.

## Item 4 — delete the dead second reset path

`account_auth.py:854 request_password_reset(email)` writes a plaintext 6-digit code onto the
Account row via `random` and has **zero callers** (the live flow is the `ResetToken` model
in `password_reset.py`). Verify no caller (`grep -rn request_password_reset src/`) then delete
the function. **Do NOT** drop the `password_reset_code` / `password_reset_expires` columns in
`models.py` — that needs a hand-written migration and `models.py` is forbidden here; leave a
one-line code comment or backlog note that the columns are now write-nowhere. (Backlog item
already tracks the column drop.)

## Item 5 — delete the unused `generate_secure_password` (ATOMIC — both edits here)

`account_auth.py:127 generate_secure_password()` uses `random.choices` (not `secrets`) and has
**zero call sites**; it is imported once at `api/admin.py:31` and never used. Remove **both**
the definition (`account_auth.py`) and the import line (`api/admin.py:31`) in this package —
they must land together or collection breaks. `api/admin.py:31` is the ONLY line you may touch
in `api/admin.py`; the client-IP code in that file belongs to naf-P08 — do not touch it.

## Tests (`tests/test_totp_lockout.py`, new)

Backend-truth, not status-code: build an account with TOTP configured, put a pending-2FA
session (`method='totp'`), call `verify_2fa('000000', ip)` `TFA_MAX_ATTEMPTS` times with a
wrong code, assert `is_2fa_locked(account)` flips True and the final error names the lockout.
Add a parity assertion that a correct TOTP after a partial failure streak resets the counter
(success path). Use the existing conftest `app` fixture and `make_account` helper; do not
roll your own app fixture.

## BLOCKED rule

If a contract cannot be met as specified, or a forbidden file must change, STOP: write
`BLOCKED: <reason>` to the LOG, commit, exit. Do not improvise.
