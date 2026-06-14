# P4 — PBT: token round-trip + realm-scope invariants

**Goal:** Property tests for the pure model logic that decides **token scope** — the most security-critical
non-I/O code in the app. Pairs with the M2 mutation spot-check on the same functions.

**Model/effort:** Sonnet / high. **Depends:** P1. **Size:** M. **New file:** `tests/test_token_model_property.py`.

## Targets (read first — `src/netcup_api_filter/models.py`)
- `generate_user_alias()`, `generate_token(user_alias)`, `parse_token(token)` — token format round-trip.
- `AccountRealm.get_fqdn()`, `AccountRealm.matches_hostname(hostname)` — host/subdomain/subdomain_only scope.
- `AccountRealm.matches_domain(domain)` — zone equality (case-insensitive).
- `APIToken.get_effective_record_types()` / `get_effective_operations()` — token-level value or None-fallback
  to the realm's. `APIToken.is_expired()` — `expires_at < now`, None ⇒ never.

All callable on **transient** instances (no DB session): construct `AccountRealm()` / `APIToken()` and set
attributes directly, or via `set_allowed_operations([...])`. `matches_hostname`/`get_fqdn` read only
`self.realm_type`, `self.realm_value`, `self.domain`.

## Properties to pin
1. **Token round-trip** — `@given(alias=st.from_regex(r'[A-Za-z0-9]{16}', fullmatch=True))`:
   `parse_token(generate_token(alias)) == (alias, <64-char random>)`; the random part matches
   `[A-Za-z0-9]{64}`; `parse_token` of a malformed string (missing `naf_` prefix, wrong separators, empty)
   returns `None` and never raises (`@given(st.text())`).
2. **Scope monotonicity (host ⊆ subdomain)** — for a generated zone `z` (valid hostname) and realm_value `v`:
   build three realms (`host`, `subdomain`, `subdomain_only`) with the same `domain`/`realm_value`. For any
   generated child `c.<fqdn>`: if `host.matches_hostname(x)` is True then `subdomain.matches_hostname(x)` is
   True (host scope ⊆ subdomain scope). The apex `fqdn` itself matches `host` and `subdomain` but **not**
   `subdomain_only`. A strict child `c.<fqdn>` matches `subdomain` and `subdomain_only` but **not** `host`.
   This pins the exact boundary mutmut will attack (`endswith('.'+fqdn)` and the `!= apex` guard).
3. **matches_hostname never raises** — `@given(st.text(max_size=120))` over arbitrary hostnames for each
   realm_type; always returns `bool`. Unknown `realm_type` ⇒ `False` (the documented fallthrough).
4. **matches_domain case-insensitivity** — `matches_domain(d) == matches_domain(d.upper()) ==
   matches_domain(d.lower())` for the realm's own domain in mixed case; a different domain ⇒ False.
5. **Effective-scope fallback** — if `allowed_operations` is set (non-empty JSON), `get_effective_operations`
   returns exactly it; if `None`, it returns the realm's. Same for record types. Pin that the None sentinel
   means "inherit" and `[]` (empty set) means "deny all" (does NOT fall back) — a mutation flipping
   `is not None` to truthiness would conflate these, so assert the empty-list case explicitly.
6. **is_expired boundary** — `expires_at = now - 1s` ⇒ True; `now + 1h` ⇒ False; `None` ⇒ False. (Use a
   fixed reference far from now to avoid the `< datetime.utcnow()` race; do not generate timestamps within
   milliseconds of now.)

## Constraints
- Pure unit test, **no DB/app/fixtures**; transient model instances only. Note `datetime.utcnow()` is used
  inside `is_expired` — for property 6 pick `expires_at` well clear of "now" so there is no flaky boundary.
- Default profile from P1.

## Verify
`python -m pytest tests/test_token_model_property.py -q` green; `HYPOTHESIS_PROFILE=dev` deep run green;
whole `tests/` suite green. If property 5's empty-list case fails (real inheritance bug), surface it and
`xfail(strict=True)` with a clear note rather than weakening it.
