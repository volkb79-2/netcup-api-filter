# P3 — PBT: IP-range / domain / email / check_ip_allowed invariants

**Goal:** Property tests for the validators that back a **security control** (IP allowlisting), finding
boundary holes the ~12 hand-written cases in `tests/test_validators_unit.py` miss.

**Model/effort:** Sonnet / high. **Depends:** P1. **Size:** M. **New file:** `tests/test_validators_property.py`.

## Targets (read first)
- `src/netcup_api_filter/utils.py`: `validate_ip_range(s)` (single IP / CIDR / `a-b` range / `*` wildcard,
  via manual string splitting — the easy-to-break boundary code), `validate_domain(s)`, `validate_email(s)`.
- `src/netcup_api_filter/token_auth.py`: `check_ip_allowed(token, client_ip)` — note it takes an `APIToken`;
  it reads `token.get_allowed_ip_ranges()`. For a pure test, construct a transient `APIToken()` and set its
  ranges via `set_allowed_ip_ranges([...])` (no DB needed — it's just JSON on the instance), OR test the
  underlying membership logic by mirroring it; prefer the transient-instance approach so the real code runs.

## Properties to pin (extend §5 Example 2, do not just copy it)
1. **Never raises / type contract** — `@given(st.text(max_size=100))`: `validate_ip_range`,
   `validate_domain`, `validate_email` each always return `bool`, never raise (incl. `"\x00"`, huge strings,
   `"1.2.3.4-"`, `"a-b-c"`, `"/24"`, `"*.*.*.*"`).
2. **Valid IPs always accepted** — `@given(ip_addresses(v=4).map(str))` and `v=6`:
   `validate_ip_range(ip) is True`. (Hypothesis `from hypothesis.strategies import ip_addresses`.)
3. **Valid CIDR always accepted** — `@given(ip_addresses(v=4), st.integers(0, 32))`: build
   `ipaddress.ip_network(f"{ip}/{prefix}", strict=False)`, assert `validate_ip_range(str(net)) is True`.
   Repeat for v6 with prefix 0–128. (Targets the `prefix=0`/`prefix=32` edges of the manual `'/' in s` branch.)
4. **Accepted dash-range ⇒ both halves parse** — `@given(ip_addresses(v=4).map(str), ip_addresses(v=4).map(str))`:
   for `f"{a}-{b}"`, `if validate_ip_range(candidate)` then `ipaddress.ip_address(left)` and `…(right)` must
   not raise. (Pins that the validator never accepts a phantom range.)
5. **check_ip_allowed soundness** — for a token whose allowed ranges are a single concrete CIDR
   (e.g. generated `ipaddress.ip_network` v4): every address `in` that network returns `True`, and an address
   provably outside returns `False`. **Empty/None ranges ⇒ always True** (documented "no restriction"
   behavior). A malformed `client_ip` string ⇒ `False` (never raises). This is the function a mutation test
   (M2) will hammer — the property version proves the boundary directly.
6. **Wildcard octet bounds** — `validate_ip_range` with patterns like `"192.168.1.*"`: assert numeric octets
   >255 are rejected (`"999.1.1.*"` → False) and `"*"` alone → True. Use targeted `@given` over octet ints.

## Constraints
- Pure unit test: **no app context, no DB, no fixtures.** For `check_ip_allowed`, a transient `APIToken()`
  with `set_allowed_ip_ranges(...)` is sufficient (instantiating the model object needs no session).
- Default profile from P1.
- If a property reveals a real bug (e.g. a malformed range accepted as valid — a security false-positive),
  **surface it** in your summary and gate it with `xfail(strict=True)` + reason rather than weakening the
  assertion.

## Verify
`python -m pytest tests/test_validators_property.py -q` green; `HYPOTHESIS_PROFILE=dev` deep run green;
whole `tests/` suite green.
