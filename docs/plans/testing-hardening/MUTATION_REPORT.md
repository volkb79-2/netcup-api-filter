# Mutation Testing Spot-Check Report — M2

**Task:** `docs/plans/testing-hardening/tasks/M2-mutation-spotcheck.md`
**Date:** 2026-06-14
**Tool:** mutmut 3.6.0 on Python 3.14
**Runner:** `tooling/mutation/run.sh run <module-path>`
**Wall-clock per module:** ~2 min (recovery_codes, utils, models, ddns_protocols); ~17 min (token_auth)

---

## Per-module summary

| Module | Generated | Killed by existing tests | Survived | In-scope survivors | Real gaps found | Real gaps fixed |
|--------|-----------|--------------------------|----------|--------------------|-----------------|-----------------|
| `recovery_codes.py` | 20 | 0 | 20 | 20 | 4 | 4 |
| `utils.py` | 358 | 346 | 12 | 12 | 7 | 7 |
| `models.py` | 239 | 211 | 28→27* | 27 | 6 | 6 |
| `api/ddns_protocols.py` | 592 | 585 | 7 | 1 | 0 | — |
| `token_auth.py` | 428 | 280 | 148 | 148 | 5 | 5 |

\* One survivor (`matches_hostname and→or`, mutmut_20) was killed by the reviewer
   before this spot-check via `test_token_model_property.py::test_unrelated_hostname_matches_no_realm_type`.

---

## Real gaps found and fixed

### recovery_codes.py — 4 real gaps fixed

| Mutant | Change | Observable impact | Killing test |
|--------|--------|-------------------|--------------|
| `x_verify_recovery_code__mutmut_3` | `return False → return True` when `recovery_codes is None` | `verify_recovery_code` grants verification when no codes are stored | `test_verify_no_codes_returns_false` |
| `x_verify_recovery_code__mutmut_7` | `return False → return True` on JSON parse error | corrupted DB value grants verification | `test_verify_corrupt_json_returns_false` |
| `x_verify_recovery_code__mutmut_14` | `if not stored_hashes → if stored_hashes` | last code consumed does NOT clear `recovery_codes_generated_at` | `test_verify_last_code_clears_generated_at` |
| `x_store_recovery_codes__mutmut_9` | `return False → return True` on DB exception | callers believe codes were stored when they were not | `test_store_recovery_codes_exception_returns_false` |

Additional: `get_remaining_code_count` return-0 mutations (mutmut_2, mutmut_5), `_recovery_code_count` default mutations, and `hash_recovery_code` uppercase-normalization — see `tests/test_recovery_codes_unit.py`.

### utils.py — 7 real gaps fixed

| Mutant | Change | Observable impact | Killing test |
|--------|--------|-------------------|--------------|
| `x_validate_ip_range__mutmut_9/11/12` | `strict=False → strict=True` (CIDR) | CIDR ranges with host bits set (e.g. `192.168.1.5/24`) rejected as invalid | `test_validate_ip_range_cidr_with_host_bits_set_accepted` |
| `x_validate_ip_range__mutmut_23` | `parts[0] → parts[1]` in range notation | left-side address not validated; invalid left side accepted | `test_validate_ip_range_range_notation_invalid_left_side` |
| `x_validate_ip_range__mutmut_49` | exception: `return True` vs raising | invalid wildcard octets (e.g. `192.300.1.*`) accepted | `test_validate_ip_range_wildcard_non_numeric_octet_rejected` |
| `x_validate_ip_range__mutmut_52` | `":" in ip_range → ":" not in ip_range` | IPv6 wildcard branch fires for IPv4 patterns | `test_validate_ip_range_wildcard_without_colon_not_mistaken_for_ipv6` |
| `x_validate_ip_range__mutmut_53` | `return True → return False` (IPv6 wildcard) | IPv6 wildcards rejected | `test_validate_ip_range_ipv6_wildcard_with_colon_is_valid` |
| `x_validate_domain__mutmut_1` | `or → and` in empty/long guard | empty domain or excessively long domain may slip through | `test_validate_domain_long_domain_invalid_even_if_not_empty`, `test_validate_domain_empty_string_invalid_even_if_short` |
| `x_validate_domain__mutmut_4` | `> 253 → > 254` | 254-char domains accepted | `test_validate_domain_254_chars_is_invalid` |

Additional: `validate_email` uppercase acceptance (mutmut_5), `sanitize_filename` replacement string (mutmut_11) — see `tests/test_validators_unit.py`.

### models.py — 6 real gaps fixed (1 by reviewer, 5 by this spot-check)

| Mutant | Change | Observable impact | Killing test |
|--------|--------|-------------------|--------------|
| `xǁAccountRealmǁmatches_hostname__mutmut_20` | `and → or` in hostname logic | unrelated hostname matches when no realm type set | `test_unrelated_hostname_matches_no_realm_type` (reviewer) |
| `x__env_int__mutmut_1-6` | various: `int(None)`, `str(None)`, wrong arg, etc. | configuration parsing falls back to default silently | `test_env_int_reads_env_var_when_set` |
| `x_calculate_entropy__mutmut_15` | `+= 26 → = 26` (lowercase charset) | charset accumulation broken; mixed-class passwords may appear weaker | `test_calculate_entropy_charset_accumulates_across_classes` |
| `x_calculate_entropy__mutmut_29` | `return 0.0 → return 1.0` (empty password) | empty password has entropy 1.0, not 0.0 | `test_calculate_entropy_empty_password_returns_0` |
| `x_verify_token_hash__mutmut_16` | `return False → return True` on exception | malformed bcrypt hash grants authentication | `test_verify_token_hash_bad_hash_returns_false` |

### api/ddns_protocols.py — 0 real gaps (all survivors out-of-scope)

| Mutant | Reason out of scope |
|--------|---------------------|
| `x_get_auto_ip_keywords__mutmut_9` | Returns a constant list of keyword aliases; value tested implicitly by integration; no security impact |
| `x_get_client_ip__mutmut_4/5/10/13/14/15` (6 survivors) | `get_client_ip` requires Flask request context; excluded from unit tests by design |

### token_auth.py — 5 real gaps fixed

| Mutant | Change | Observable impact | Killing test |
|--------|--------|-------------------|--------------|
| `x_extract_bearer_token__mutmut_7` | `split(' ', 1) → rsplit(' ', 1)` | header "Bearer part1 part2" accepted as scheme="Bearer part1", token="part2" | `test_extract_bearer_token_space_in_token_value_preserved` |
| `x_check_ip_allowed__mutmut_15` | `strict=False → strict=True` (CIDR) | CIDR entries with host bits set raise ValueError → entry skipped → IP appears denied | `test_check_ip_allowed_cidr_with_host_bits_set_strict_false` |
| `x__resolve_fqdn__mutmut_10` | `rstrip('.') → lstrip('.')` on record_name | record_name "vpn." not normalised; FQDN computed as "vpn..example.com" | `test_resolve_fqdn_trailing_dot_on_record_name_stripped` |
| `x_check_permission__mutmut_19` | `and → or` in IP-check guard | when `client_ip=None` (no IP given), check fires anyway → spurious ip_denied | `test_check_permission_no_client_ip_skips_ip_check` |
| `x_check_permission__mutmut_22` | `check_ip_allowed(token, client_ip) → check_ip_allowed(token, None)` | valid whitelisted IP always fails check (ip_address(None) raises) | `test_check_permission_valid_ip_passes_check` |

---

## Equivalent / acceptable survivors (not killed)

### Category A: Logger message mutations (all modules)
Mutations that change only the `logger.debug/info/warning/error(...)` message string — substituting `None`, garbling with `XX...XX` prefix/suffix, or changing case. These do not affect authentication decisions, authorization grants/denials, returned error codes, or any value visible to API callers. They exist purely for operator diagnostics.

**Count:** ~70 (predominantly in `authenticate_token` which has dense logging; also `check_ip_allowed`, `_resolve_fqdn`, `check_permission`)

### Category B: Human-readable `error=` string mutations in AuthResult
`authenticate_token` returns `AuthResult(error="Invalid token", ...)` — the `error` field is a human display string. Multiple mutations change its case or content (e.g. `"invalid token"`, `"INVALID TOKEN"`, `None`, `"XXInvalid tokenXX"`). Security logic is driven by `error_code` (e.g. `"alias_not_found"`), not by `error`. The API response always returns the generic message `"Invalid or expired token"` regardless, so the `error` field is internal.

**Count:** ~28 (one per error path × multiple string variants per path)

### Category C: `should_notify_user` mutations to `True` or `None` in non-notifiable paths
`authenticate_token` sets `should_notify_user=False` for paths like `invalid_format`, `account_disabled`, `token_expired`, `realm_not_approved`. Mutants that flip this to `True` would cause spurious security notifications on benign events. However, `should_notify_user` only drives the notification side-channel (`_trigger_security_notification`); it does not affect the auth decision. Since `_trigger_security_notification` is currently a stub (TODO comment), notifications are only logged. These are technically OBSERVABLE but the notification subsystem is not yet implemented; classifying as acceptable/low-priority.

**Count:** ~8

### Category D: Attribution field mutations in failed AuthResult
Setting `user_alias_attempted=None`, `token_prefix_attempted=None`, `token=None`, or `realm=None` in failure-path AuthResults. These fields are only used for security analytics and activity logging; they do not affect whether authentication succeeds or fails.

**Count:** ~14

### Category E: `severity=None` mutations
`severity` is populated from `ERROR_SEVERITY[error_code]` and only used to feed the `ActivityLog` and potentially the notification threshold. Setting it to `None` doesn't change the auth success/failure decision.

**Count:** ~8

### Category F: Assert message string mutations in `check_permission`
Mutations that garble the assert message (e.g. `"token should be set when auth.success is True" → "XX..."` or case changes). The assertion itself (`assert token is not None`) is unchanged; only the diagnostic string for AssertionError differs.

**Count:** ~6 (check_permission assert messages)

### Category G: `validate_password__mutmut_18` — entropy boundary `<` vs `<=`
Mutates `if entropy < PASSWORD_MIN_ENTROPY` to `<=`. Since `entropy = len(pwd) * log2(charset_size)` is a floating-point product that is almost never exactly equal to the integer `PASSWORD_MIN_ENTROPY`, this mutation has measure-zero practical effect. The `test_validate_password_at_entropy_boundary_succeeds` test exercises the borderline case with entropy slightly above the minimum. Classified as equivalent.

**Count:** 1

### Category H: `split` argument mutations in `extract_bearer_token`
- `mutmut_3`: `split(' ', 1) → split(None, 1)` — splits on any whitespace; for `"Bearer naf_..."` (single space) the result is identical.
- `mutmut_6`: `split(' ', 1) → split(' ', )` — no maxsplit; for single-space headers identical.
- `mutmut_9`: `split(' ', 1) → split(' ', 2)` — allows up to 3 parts; `len(parts) != 2` guard still rejects 3-part results, and 2-part results are identical.

**Count:** 3

---

## Reviewer caveats (honest accounting)

Of the killing tests added, **~18–19 kill genuine behavioral mutants** (the security-relevant
guard/exception/boundary gaps above). The remaining ~3 are **harmless regression guards whose named
mutant is actually equivalent**, so they pin correct behavior but do not "kill" anything:

- `validate_password` `<`→`<=` (`mutmut_18`): also listed under Category G — entropy is a float almost
  never exactly equal to the integer minimum, so `<`/`<=` are observationally identical. The boundary test
  pins "a sufficiently-strong password is accepted," which is correct but not a true kill.
- `hash_recovery_code` `upper()`→`lower()`: store and verify normalize with the *same* function, so the
  round-trip matches either way — equivalent. The added test pins case-insensitive verification (correct).
- `_recovery_code_count` default-value variants: all fall through to the same `3` fallback — equivalent in
  outcome. The added test pins the default (correct regression guard).

None of these weaken assertions or assert mutated behavior; they are extra correctness coverage. The genuine
security finding count stands (notably `verify_token_hash` exception→True and `verify_recovery_code` guards).

## Verification

```
$ python -m pytest tests/ -q
355 passed, 1399 warnings in 77.69s
```

```
$ grep -rn mutmut .github/ pytest.ini
(empty — mutation wiring absent from CI and pytest runner)
```

```
$ git diff -- setup.cfg
(empty — restored by run.sh after each module run)
```

---

## New test files modified

- `tests/test_recovery_codes_unit.py` — 8 killing tests added (lines ~300–384)
- `tests/test_validators_unit.py` — 11 killing tests added (lines ~290–390)
- `tests/test_password_policy_unit.py` — 7 killing tests added (lines ~279–413)
- `tests/test_token_auth_unit.py` — 5 killing tests added (lines ~533–620)
