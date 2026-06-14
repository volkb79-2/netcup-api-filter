# P2 — PBT: DDNS hostname parse/validate invariants

**Goal:** Property tests for the untrusted-input DDNS parsing/validation functions, finding edge cases the
~29 hand-written cases in `tests/test_ddns_parsing_unit.py` miss.

**Model/effort:** Sonnet / high. **Depends:** P1. **Size:** M. **New file:** `tests/test_ddns_property.py`.

## Targets (read first)
`src/netcup_api_filter/api/ddns_protocols.py`:
- `validate_hostname_format(hostname)` → bool (label rules: ≥1 dot, no `..`, each label non-empty, ≤63,
  starts/ends alnum, chars alnum-or-hyphen).
- `parse_hostname(hostname)` → `(domain, record_name)` or `(None, None)`. Lowercases, splits on `.`, takes
  last two labels as the zone, `'@'` record for a 2-label apex.
- `should_auto_detect_ip(myip)` → bool (True for None/empty/keyword in `DDNS_AUTO_IP_KEYWORDS`).
- `validate_ip_address(ip_str)` → `(is_valid, is_ipv6, normalized)`.

These are reachable from untrusted external DDNS clients (`process_ddns_update`), so a crash or misparse is
security-relevant.

## Properties to pin (extend §5 Example 1 in TESTING_LESSONS_LEARNED, do not just copy it)
1. **Never raises / type contract** — `@given(st.text(max_size=300))`:
   - `validate_hostname_format(s)` is always `bool`.
   - `parse_hostname(s)` always returns a 2-tuple with `(domain is None) == (record is None)` (no mixed
     partial). Also assert it never raises on bytes-like/control chars (`"\x00"`, `"a"*300`, `".foo"`,
     `"foo..bar"`, `"-x.y"`).
   - `should_auto_detect_ip(s)` and `validate_ip_address(s)` never raise and return the documented shapes.
2. **Accepted-set structural invariant** — generate valid hostnames from the DNS alphabet
   (`_label = st.from_regex(r'[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?', fullmatch=True)`,
   `_hostname = st.lists(_label, min_size=2, max_size=5).map('.'.join)`). For any `h` where
   `validate_hostname_format(h)` is True: every label is non-empty, ≤63 chars, first/last alnum, chars ⊆
   alnum∪`-`. (Guard with `if not validate_hostname_format(h): return` — only testing the accepted set.)
3. **validate→parse consistency** — for any `h` accepted by `validate_hostname_format`, `parse_hostname(h)`
   returns non-None `domain` and `record`, and `'.' in domain`. **This is the key cross-function invariant**:
   if validation accepts something the parser then rejects (returns None), `process_ddns_update` would log
   `invalid_hostname` after already passing format validation — pin that the two agree on the accepted set.
4. **Idempotence / case** — `parse_hostname(h) == parse_hostname(h.upper())` for accepted `h` (parser
   lowercases). `should_auto_detect_ip(kw) is True` for every configured keyword regardless of case.
5. **Known edge probes (regression, not generated)** — assert behavior is *defined* (True or False, never a
   raise) for: trailing dot `"example.com."`, leading dot, `"a..b"`, single label `"localhost"`, all-numeric
   `"1.2"`, a 64-char label, and a 300-char hostname. Document the actual current behavior in a comment; if a
   probe reveals a genuine bug (e.g. validation accepts something the parser misparses), **do not paper over
   it** — note it in your summary and add an `xfail(strict=True)` with a clear reason so the bug is tracked.

## Constraints
- Pure unit test: **no app context, no DB, no fixtures** (keeps Hypothesis health checks quiet and the file
  fast). Import functions directly.
- Use `@given`; rely on the default profile from P1 (no per-test `max_examples` unless a test is unusually
  slow, then `@settings(max_examples=50)`).

## Verify
`python -m pytest tests/test_ddns_property.py -q` green; `HYPOTHESIS_PROFILE=dev python -m pytest
tests/test_ddns_property.py -q` green (deeper run). Whole `tests/` suite still green.
