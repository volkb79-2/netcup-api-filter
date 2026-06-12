# T03 — Unit tests: token auth + realm matching (~49 cases)

| Status | Model / effort | Depends on | Size |
|--------|----------------|------------|------|
| open | Sonnet 4.6 / high | T02 | M |

## Objective

Unit-test the security core that today has zero unit coverage: token authentication,
IP allow-listing, record-level permission checks, and realm domain matching. This is the
authorization boundary of the product — precision over volume.

## Context — read first

- `src/netcup_api_filter/token_auth.py` — verified targets: `extract_bearer_token` (114),
  `authenticate_token` (134), `check_ip_allowed` (290), `_resolve_fqdn` (326),
  `check_permission` (343). **Read each function fully before writing cases** — assert on the
  real `AuthResult` fields / error codes, not guessed ones.
- `docs/SECURITY_ERROR_TAXONOMY.md` — the error-code vocabulary assertions should use.
- `tests/test_realm_scope.py` — existing style for DB-free realm tests (bare
  `AccountRealm` instances); extend this style, don't contradict it.
- `tests/conftest.py` factories from T02 (`make_account`, `make_realm`, `make_token`).
- `AGENTS.md` § Core architecture — `host` / `subdomain` / `subdomain_only` semantics.

## Spec

### `tests/test_token_auth_unit.py` (~40 cases, uses T02 fixtures/factories)

`authenticate_token` (~14): invalid format (no `naf_` prefix, too short, empty, None),
alias not found, account disabled (`is_active=0`), prefix not found, hash mismatch (valid
alias+prefix, wrong secret — assert the attribution fields the function sets), token revoked
(`is_active=0` on token), token expired (`expires_at` in the past), realm `pending`, realm
`rejected`, success (assert account/realm/token populated on the result, `last_used_at` /
`use_count` behavior if the function updates them).

`check_ip_allowed` (~8): no restriction set → allowed; exact IPv4 match/mismatch; CIDR
in/out (`203.0.113.0/24`); IPv6 exact + CIDR; invalid client IP string; invalid whitelist
entry (assert the documented behavior — read the code, don't assume skip-vs-deny).

`check_permission` (~12): ip denied; wrong zone (`matches_domain` false); hostname scope —
for each `realm_type` (`host`, `subdomain`, `subdomain_only`) one allow + one deny case
(e.g. `host` realm `vpn` allows `vpn.example.com`, denies `other.example.com` and the apex;
`subdomain_only` denies the apex, allows children); operation denied (realm/token lacks the op);
record-type denied; token-scope override narrower than realm scope (token wins);
token scope unset → realm scope applies; zone-level read with `record_name=None`.

`_resolve_fqdn` (~6): apex via `""` and `"@"`; simple prefix; value already FQDN;
trailing-dot handling; case normalization. Assert the actual implemented contract.

### `tests/test_realm_matching_unit.py` (~9 cases, DB-free like `test_realm_scope.py`)

`AccountRealm.matches_domain`: exact match; case-insensitive match; different zone;
sub-zone must NOT match (`sub.example.com` realm-domain vs `example.com` query and vice
versa); empty/None handling per implementation. `get_fqdn` (~3): host/subdomain/apex forms.

### Rules

- Each case asserts a **specific** outcome (exact error code / boolean / field), never
  "no exception" or membership in a set of acceptable outcomes.
- Use `pytest.mark.parametrize` for the matrix-shaped groups (IP cases, hostname-scope cases).
- If you discover a real bug in `src/` (a case where the code's behavior is clearly wrong
  against AGENTS.md/SECURITY docs), do NOT silently encode the buggy behavior as expected:
  write the test for the *correct* behavior, mark it `xfail(strict=True)` with a comment
  naming the suspected bug, and call it out in your summary.

## Acceptance criteria

- [ ] `python -m pytest tests/test_token_auth_unit.py tests/test_realm_matching_unit.py -v` green (~49 cases, ±20% is fine if justified).
- [ ] `python -m pytest tests/ -v` green overall.
- [ ] Coverage of `token_auth.py` (printed by the default `--cov` term-missing output) shows
      `authenticate_token`, `check_ip_allowed`, `check_permission`, `_resolve_fqdn` bodies
      substantially covered — note the % in your summary.
- [ ] No test asserts an `or` of outcomes; no skips.

## Verify

```bash
cd /workspaces/netcup-api-filter
python -m pytest tests/test_token_auth_unit.py tests/test_realm_matching_unit.py -v
python -m pytest tests/ -q
```

## Guardrails (non-negotiable)

- A test that can't fail is worse than no test: no `pytest.skip` to go green, no assertions
  inside `if found:` blocks, no `or`-chained tolerant assertions.
- Never hardcode credentials; never log token plaintext.
- Run pytest from the repo root. Don't edit `deploy/`, `deploy-local/`, `deploy-webhosting/`.
- Don't modify `src/` to make tests pass (exception: none in this task — report suspected bugs instead).
- Leave changes uncommitted for review unless your operator says otherwise.
- When done: tick T03 in `docs/plans/testing-overhaul/PLAN.md` + add a worklog line.
