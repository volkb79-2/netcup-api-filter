# T04 — Unit tests: validators + password policy + recovery codes (~59 cases)

| Status | Model / effort | Depends on | Size |
|--------|----------------|------------|------|
| open | Sonnet 4.6 / high | T02 | M |

## Objective

Unit-test the pure validation/crypto helpers that gate user input and the 2FA fallback path.
All currently untested.

## Context — read first

- `src/netcup_api_filter/utils.py` — verified targets: `parse_bool` (27), `validate_ip_range`
  (205), `validate_domain` (276), `validate_email` (294), `sanitize_filename` (312).
  Read each implementation first; assert its actual contract.
- `src/netcup_api_filter/models.py` — `calculate_entropy` (127), `validate_password` (164,
  returns `tuple[bool, str | None]`).
- `src/netcup_api_filter/recovery_codes.py` — `_recovery_code_count` (27),
  `generate_recovery_codes` (48), `hash_recovery_code` (65), `store_recovery_codes` (80),
  `verify_recovery_code` (108), `get_remaining_code_count` (151),
  `regenerate_recovery_codes` (171). Storage/verification touch the DB → use T02 `app` +
  `make_account` fixtures for those.
- `docs/CHARSET_VALIDATION.md` — documented formats the validators should enforce.

## Spec

### `tests/test_validators_unit.py` (~35, pure, parametrized)

- `validate_ip_range` (~10): valid IPv4, valid IPv4 CIDR, valid IPv6, valid IPv6 CIDR,
  invalid octet, invalid prefix length (`/33`, `/129`), garbage string, empty, whitespace,
  hostname-not-ip.
- `validate_domain` (~8): simple domain, multi-label, IDN/punycode (per implementation),
  leading/trailing dot, underscore label, overlong label (>63), overlong total, empty.
- `validate_email` (~6): plain valid, plus-tag, missing `@`, missing TLD-part, spaces, empty.
- `parse_bool` (~6): `"true"/"True"/"1"/"yes"` → True (whichever the impl accepts), `"false"/"0"` → False,
  None → default, weird string → default, bool passthrough, `default=True` honored.
- `sanitize_filename` (~5): path separators stripped, `..` traversal neutralized, unicode,
  empty, already-clean passthrough.

### `tests/test_password_policy_unit.py` (~14, pure)

- `calculate_entropy` (~6): empty → 0 (or impl contract); single-charset short; mixed-charset;
  monotonicity (longer same-charset password ≥ entropy of shorter); known-value spot check
  computed from the implementation's formula; unicode input doesn't crash.
- `validate_password` (~8): too short → `(False, <reason>)`; long but low-entropy (e.g.
  `"aaaaaaaaaaaaaaaa"`); just below vs just at the entropy boundary (derive the boundary from
  the implementation/config, don't hardcode magic numbers without a comment); strong password
  → `(True, None)`; whitespace-only; unicode; assert the reason string is non-empty on failure.

### `tests/test_recovery_codes_unit.py` (~10, app+factory where DB is involved)

Count/format/alphabet of `generate_recovery_codes` (respecting `_recovery_code_count`
config); `hash_recovery_code` deterministic + differs across codes;
`store_recovery_codes` + `verify_recovery_code` happy path consumes the code (second use of
the same code rejected); wrong code rejected; `get_remaining_code_count` decrements;
`regenerate_recovery_codes` invalidates all old codes; verification is case/format tolerant
exactly as implemented (read the normalization in `verify_recovery_code` first).

## Acceptance criteria

- [ ] All three new files green; `python -m pytest tests/ -q` green overall; no skips.
- [ ] Boundary cases (entropy threshold, CIDR edges) are derived from the code/config with a
      comment pointing at the source line, not bare magic numbers.
- [ ] Suspected real bugs (validator accepts something CHARSET_VALIDATION.md forbids, etc.) are
      encoded as `xfail(strict=True)` + named in your summary — not silently blessed.

## Verify

```bash
cd /workspaces/netcup-api-filter
python -m pytest tests/test_validators_unit.py tests/test_password_policy_unit.py tests/test_recovery_codes_unit.py -v
python -m pytest tests/ -q
```

## Guardrails (non-negotiable)

- No `pytest.skip` to go green, no assertions inside `if found:` blocks, no `or`-chained assertions.
- Never hardcode credentials; never log secrets or recovery codes outside test scope.
- Run pytest from the repo root. Don't edit `deploy/`, `deploy-local/`, `deploy-webhosting/`.
- Don't modify `src/` to make tests pass — report suspected bugs instead.
- Leave changes uncommitted for review unless your operator says otherwise.
- When done: tick T04 in `docs/plans/testing-overhaul/PLAN.md` + add a worklog line.
