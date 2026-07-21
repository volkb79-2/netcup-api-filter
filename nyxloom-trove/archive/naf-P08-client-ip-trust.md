---
schema_version: 1
id: naf-P08-client-ip-trust
project: naf
title: "Leftmost X-Forwarded-For is client-controlled; admin + DDNS IP checks are spoofable"
tier: sonnet5-high
input_revision: "c1acb8e"
depends_on: []
session: fresh
source: {kind: review, ref: "docs/deprecated/FOLLOWUP_REVIEW_2026-07-16.md#P1-C"}
advances: [M1]
scope:
  touch:
    - "src/netcup_api_filter/api/admin.py"
    - "src/netcup_api_filter/api/ddns_protocols.py"
    - "tests/test_client_ip_trust.py"
  forbid:
    - "src/netcup_api_filter/account_auth.py"
    - "src/netcup_api_filter/api/account.py"
    - "src/netcup_api_filter/password_reset.py"
    - "src/netcup_api_filter/app.py"
oracles:
  - id: O1
    observable: "With ProxyFix (x_for=1) in place, a request carrying a forged `X-Forwarded-For: 1.2.3.4, <real>` header resolves the client IP used by admin._get_client_ip and ddns_protocols.get_client_ip to the ProxyFix-normalized remote_addr (the real peer), NOT the attacker-supplied leftmost value. A backend-truth test asserts this."
    negative: "Today both helpers return `header.split(',')[0]` — the attacker-controlled leftmost hop — so the admin IP allowlist, admin session IP-binding, and the token IP allowlist can all be defeated by sending a crafted XFF header."
    gate: unit
  - id: O2
    observable: "The two admin audit-log sites (api/admin.py:1207, :1291) record `request.remote_addr` (a single normalized IP), not the raw multi-hop `X-Forwarded-For` string."
    negative: "They store the whole `client, proxy1, proxy2` header (or its default) as source_ip, corrupting the audit trail's IP field."
    gate: unit
gates: [unit]
escalate_if:
  - "ProxyFix is found NOT configured or configured with a different x_for count than 1 — the correct client IP then depends on the real proxy topology; STOP and escalate rather than guessing"
  - "a consumer of these helpers relies on the multi-hop string form"
---

# naf-P08 — trust the ProxyFix-normalized client IP, not the raw header

> **STATE (2026-07-21): ✅ DONE** — merged (`521b788`). See [../STATE.md](../STATE.md).

> Base: `main` @ `c1acb8e`. Gate: `./tooling/test-runner/testing-exec.sh unit` (3.11 + 3.9).
> Self-gate in your worktree. Review is against git state, not this report.

## The bug

`app.py:75` installs `ProxyFix(app.wsgi_app, x_for=1, ...)`, so Werkzeug already sets
`request.remote_addr` to the real client (the rightmost-1 XFF hop, the one hop we trust).
`dns_api.py` correctly uses `request.remote_addr`. But two other helpers re-parse the raw
header and take the **leftmost** (client-controlled) value:

- `api/admin.py:90 _get_client_ip()` — `request.headers.get('X-Forwarded-For', remote_addr)`
  then `.split(',')[0].strip()`. Feeds the admin IP allowlist and admin session IP-binding.
- `api/ddns_protocols.py:61 get_client_ip()` — `forwarded_for.split(',')[0].strip()`. Feeds
  the token IP allowlist and DDNS logging.

Both are **spoofable**: a caller sends `X-Forwarded-For: <allowed-ip>, <real>` and the
leftmost forged value wins.

## Fix

Make both helpers simply return `request.remote_addr` (ProxyFix has already done the
trusted-hop extraction). Keep the `or 'unknown'` fallback in `get_client_ip`. Do NOT re-parse
the header. Verify (read-only) that `app.py:75` has `x_for=1`; if it does not, or if it is a
different count, **escalate** — do not hardcode an assumption.

Also fix the two inline audit sites in `api/admin.py` that log the raw header directly:
`:1207` and `:1291` `source_ip=request.headers.get('X-Forwarded-For', request.remote_addr)`
→ `source_ip=request.remote_addr`. Grep `api/admin.py` and `api/ddns_protocols.py` for any
other `X-Forwarded-For` occurrence and fix consistently within these two files only.

## Coordination (shared file, disjoint lines)

`api/admin.py` is also edited by **naf-P07**, but only its import line 31
(`generate_secure_password`). **Do not touch line 31.** Your hunks are `_get_client_ip` (~90)
and the audit sites (~1207, ~1291) — disjoint, so the merges do not conflict. `app.py` is
read-only for you (forbidden) — you rely on its ProxyFix config, you don't change it. The
XFF site in `api/account.py:210` belongs to naf-P09 — do not touch it.

## Tests (`tests/test_client_ip_trust.py`, new)

Backend-truth against a real request context with ProxyFix applied: issue a request with a
forged `X-Forwarded-For` and a known WSGI `REMOTE_ADDR`, assert both helpers return the
ProxyFix-normalized `remote_addr`, not the forged leftmost. Use the conftest `app` fixture.
Do not assert on HTTP status codes; assert on the resolved IP the helper returns.

## BLOCKED rule

If a contract cannot be met, or a forbidden file must change, STOP: write `BLOCKED: <reason>`
to the LOG, commit, exit.
