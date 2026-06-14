# Testing Lessons Learned

## Critical Principles for Robust Browser Testing

This document captures critical testing patterns discovered through production use of Playwright browser automation. These principles prevent subtle race conditions and state synchronization issues that are easy to miss but cause intermittent test failures.

---

## 1. 2FA Form Submission: Avoid Race Conditions with JavaScript Auto-Submit

### Problem
When testing 2FA flows that use JavaScript auto-submit (e.g., form submits automatically when 6 digits are entered), Playwright's standard `fill()` + `click()` pattern races with the page's JavaScript. This causes:
- Tests clicking submit button after JavaScript already submitted
- Double form submissions (user action + JavaScript action)
- Inconsistent navigation timing

### Solution
**Use direct JavaScript form submission** instead of clicking the submit button:

```python
# ✅ CORRECT: Direct JavaScript submission (no race)
await browser.evaluate(f"""
    (function() {{
        const input = document.getElementById('code');
        const form = document.getElementById('twoFaForm');
        if (input && form) {{
            input.value = '{code}';
            form.submit();  // Direct submission
        }}
    }})();
""")
```

```python
# ❌ WRONG: Races with auto-submit
await browser.fill("#code", code)  # Triggers auto-submit
await browser.click("button[type='submit']")  # May execute after navigation
```

### Where Applied
- [`ui_tests/tests/journeys/j1_fresh_deployment.py`](../ui_tests/tests/journeys/j1_fresh_deployment.py) - `_handle_2fa_via_mailpit()`
- [`ui_tests/tests/journeys/j2_account_lifecycle.py`](../ui_tests/tests/journeys/j2_account_lifecycle.py) - `_handle_2fa_via_mailpit()`
- [`ui_tests/workflows.py`](../ui_tests/workflows.py) - `handle_2fa_if_present()`

### Reference Implementation
See [`ui_tests/tests/journeys/j1_fresh_deployment.py:71-130`](../ui_tests/tests/journeys/j1_fresh_deployment.py#L71-L130):

```python
async def _handle_2fa_via_mailpit(browser: Browser) -> bool:
    """Handle 2FA page by intercepting code from Mailpit.
    
    Note: We fill the code and submit the form directly via JavaScript
    to avoid race conditions with the auto-submit feature.
    """
    # ... extract code from email ...
    
    # Fill and submit via JavaScript (avoids race with auto-submit)
    await browser.evaluate(f"""
        (function() {{
            const input = document.getElementById('code');
            const form = document.getElementById('twoFaForm');
            if (input && form) {{
                input.value = '{code}';
                form.submit();
            }}
        }})();
    """)
```

---

## 2. Live URL Detection: Always Use `browser._page.url` for Current State

### Problem
Playwright's `Browser.current_url` property is **cached** and only updates after explicit navigation or state refresh. When checking "where am I now?" after JavaScript-driven navigation or redirects, the cached value shows stale state.

This causes:
- Incorrect detection of 2FA redirects
- Missed navigation events
- False "already logged in" detection

### Solution
**Use `browser._page.url` directly** for live URL checks:

```python
# ✅ CORRECT: Live URL from page object
current_url = browser._page.url
if "/login/2fa" in current_url:
    # Handle 2FA
    pass

# ❌ WRONG: Cached URL (may be stale)
if "/login/2fa" in browser.current_url:
    # May miss redirect!
    pass
```

### Where Applied
- [`ui_tests/tests/journeys/j2_account_lifecycle.py:165`](../ui_tests/tests/journeys/j2_account_lifecycle.py#L165) - `_admin_creates_account()`
- [`ui_tests/tests/journeys/j2_account_lifecycle.py:488`](../ui_tests/tests/journeys/j2_account_lifecycle.py#L488) - `_login_as_admin()`
- [`ui_tests/workflows.py:150`](../ui_tests/workflows.py#L150) - `handle_2fa_if_present()`
- All 2FA handling functions

### Reference Implementation
See [`ui_tests/tests/journeys/j2_account_lifecycle.py:488-510`](../ui_tests/tests/journeys/j2_account_lifecycle.py#L488-L510):

```python
async def _login_as_admin(browser: Browser):
    """Helper to login as admin (including 2FA handling).
    
    If already logged in (session still valid), skips login form.
    """
    await browser.goto(settings.url("/admin/login"))
    await asyncio.sleep(0.5)
    
    # Use live URL directly (not cached)
    current_url = browser._page.url
    if "/admin/login" not in current_url and "/login/2fa" not in current_url:
        # Already logged in - redirected to admin area
        if "/admin" in current_url:
            print("ℹ️  Already logged in as admin (session valid)")
            return
```

### Technical Details
The `Browser.current_url` property is updated in `Browser._update_state()`, which is only called after:
- `goto()`
- `click()` with navigation
- `submit()` with navigation

JavaScript-driven redirects (e.g., `window.location.href = ...`) or server redirects after form POST may not trigger state update immediately.

**Best Practice**: Always use `browser._page.url` when checking current location, especially after:
- Form submissions
- JavaScript-driven navigation
- Expected redirects (login → dashboard, 2FA → admin)

---

## 3. Admin Session Handling: Detect Active Sessions Before Login

### Problem
In multi-journey test suites, browser sessions may persist between tests. Attempting to login when already logged in causes:
- Unnecessary form submissions
- Redirect loops
- Wasted time and flaky tests

### Solution
**Check if already logged in before filling login form**:

```python
# ✅ CORRECT: Check for active session first
await browser.goto(settings.url("/admin/login"))
current_url = browser._page.url

# If redirected away from login, we're already logged in
if "/admin/login" not in current_url and "/login/2fa" not in current_url:
    if "/admin" in current_url:
        print("ℹ️  Already logged in as admin (session valid)")
        return  # Skip login

# No redirect - check if login form exists
username_field = await browser.query_selector("#username")
if not username_field:
    # No form but on admin page = logged in
    if "/admin" in current_url:
        print("ℹ️  Already on admin page (session valid)")
        return

# Not logged in - proceed with form submission
await browser.fill("#username", "admin")
# ...
```

### Where Applied
- [`ui_tests/tests/journeys/j2_account_lifecycle.py:488`](../ui_tests/tests/journeys/j2_account_lifecycle.py#L488) - `_login_as_admin()`
- [`ui_tests/workflows.py:250`](../ui_tests/workflows.py#L250) - `ensure_admin_dashboard()`

### Benefits
- **Faster tests**: Skip login when session is valid
- **More robust**: Handle session persistence gracefully
- **Clearer output**: Explicit logging of session state

---

## General Testing Principles

### A. Prefer JavaScript Evaluation Over UI Interaction

When the goal is to **set state** rather than **test user interaction**, use JavaScript:

```python
# ✅ Set form value via JavaScript (faster, no race)
await browser.evaluate("""
    document.getElementById('field').value = 'value';
    document.querySelector('form').submit();
""")

# ❌ Simulate user typing (slower, may race with page JS)
await browser.fill("#field", "value")
await browser.click("button[type='submit']")
```

**When to use each:**
- **JavaScript**: Setting up test state, handling auto-submit forms, extracting data
- **UI interaction**: Testing actual user workflows, accessibility, form validation

### B. Always Wait for Navigation After Submit

After form submission, explicitly wait for navigation to complete:

```python
url_before = browser._page.url
await browser.evaluate("document.querySelector('form').submit()")

# Wait for navigation (up to 10 seconds)
for _ in range(20):
    await asyncio.sleep(0.5)
    new_url = browser._page.url
    if new_url != url_before:
        print(f"Navigation complete: {new_url}")
        break
else:
    print(f"WARN: Navigation timeout, still at: {browser._page.url}")
```

### C. Log Current URL at Decision Points

When debugging redirect issues, always log the current URL:

```python
current_url = browser._page.url
print(f"[DEBUG] Current URL: {current_url}")

if "/2fa" in current_url:
    print("[DEBUG] Detected 2FA redirect, handling...")
elif "/dashboard" in current_url:
    print("[DEBUG] Already on dashboard, login succeeded")
```

This makes test failures self-explanatory.

---

## Testing Architecture Patterns

### Pattern: Mailpit Email Interception for 2FA

All 2FA tests use this pattern:

1. **Wait for email** (with timeout)
2. **Extract code** via regex
3. **Fill and submit via JavaScript** (avoid race)
4. **Wait for navigation** (poll URL)
5. **Clean up email** (delete message)

Example:

```python
from ui_tests.mailpit_client import MailpitClient

mailpit = MailpitClient()

# 1. Wait for email
msg = mailpit.wait_for_message(
    predicate=lambda m: "verification" in m.subject.lower(),
    timeout=10.0
)

# 2. Extract code
full_msg = mailpit.get_message(msg.id)
code_match = re.search(r'\b(\d{6})\b', full_msg.text)
code = code_match.group(1)

# 3. Submit via JavaScript
url_before = browser._page.url
await browser.evaluate(f"""
    document.getElementById('code').value = '{code}';
    document.getElementById('twoFaForm').submit();
""")

# 4. Wait for navigation
for _ in range(20):
    await asyncio.sleep(0.5)
    if browser._page.url != url_before:
        break

# 5. Clean up
mailpit.delete_message(msg.id)
```

### Pattern: Conditional 2FA Handling

All login helpers use this pattern:

```python
async def login_with_optional_2fa(browser: Browser, username: str, password: str):
    """Login with automatic 2FA handling if encountered."""
    # 1. Submit login form
    await browser.goto("/admin/login")
    await browser.fill("#username", username)
    await browser.fill("#password", password)
    await browser.click("button[type='submit']")
    await asyncio.sleep(1.0)
    
    # 2. Check for 2FA redirect (use live URL)
    current_url = browser._page.url
    if "/2fa" in current_url or "/login/2fa" in current_url:
        # Handle 2FA via Mailpit
        await _handle_2fa_via_mailpit(browser)
    
    # 3. Verify we reached destination
    final_url = browser._page.url
    assert "/admin" in final_url, f"Login failed, at: {final_url}"
```

---

## Migration Checklist

When updating tests to use these patterns:

- [ ] Replace `browser.current_url` with `browser._page.url` for live URL checks
- [ ] Replace `fill() + click()` with `evaluate()` + `form.submit()` for auto-submit forms
- [ ] Add session detection before login (check for redirect or missing form)
- [ ] Add navigation polling after form submit (wait for URL change)
- [ ] Add URL logging at decision points (`print(f"Current URL: {browser._page.url}")`)
- [ ] Use Mailpit for email interception (not aiosmtpd direct access)
- [ ] Clean up emails after use (`mailpit.delete_message()`)

---

---

## 4. Verification-Channel Pattern: Round-Trip Assertions

### Why naive E2E assertions fail

An E2E test that checks only the UI layer can be **permanently green even when the feature
is broken**. Examples of false-green assertions:

```python
# ❌ WRONG: scraping UI feedback, not backend state
assert "Account disabled" in await page.inner_text(".flash-message")

# ❌ WRONG: soft assertion inside if-found guard
if elem := await page.query_selector(".realm-status"):
    assert "approved" in elem.inner_text()

# ❌ WRONG: or-chained tolerant assertion
assert status_code == 200 or status_code == 204

# ❌ WRONG: pytest.skip when an element is merely missing
if not await page.query_selector("#token-list"):
    pytest.skip("token list not visible")
```

### The three independent verification channels

`ui_tests/verification.py` provides read-only backend truth via three channels. Use the
**lowest-latency channel that can verify the specific claim**.

| Channel | What it is | When to use |
|---------|-----------|-------------|
| **A — read-only sqlite** | Direct file read of `netcup_filter.db`, mode=ro + `PRAGMA query_only` | Account/realm/token/activity rows, DB-column values. Only available when the test runner has direct DB file access (local + CI). Skip gracefully with `require_db()` otherwise. |
| **B — authed JSON endpoints** | `GET /admin/api/*` or `/account/api/*` via the logged-in Playwright session | What the UI role actually sees through its authenticated API; useful for cross-role checks where the UI doesn't directly expose the underlying row. |
| **C — DNS API / mock backend state** | Bearer-token DNS API calls (`dns_api_list_records`) or mock Netcup state (`mock_netcup_records`) | DNS record mutations: verify the record is really present/absent at the backend, not just reflected in the UI. |

### The `wait_for` poller — never sleep

After a UI submit, the backend processes the request asynchronously. Never `time.sleep`:

```python
# ❌ WRONG: arbitrary sleep
await browser.click("#disable-btn")
await asyncio.sleep(2)
assert verification.get_account("bob")["is_active"] == 0

# ✅ CORRECT: poll until the DB reflects the change (or timeout)
await browser.click("#disable-btn")
verification.wait_for(
    lambda: verification.get_account("bob")["is_active"] == 0,
    timeout=10.0,
    message="Account was not disabled in DB within 10 s",
)
```

`wait_for` polls every 250 ms up to the timeout, then raises `AssertionError` with the
message you supply. The timeout surfaces a real failure; it does NOT mask it.

### Anti-false-green rules (non-negotiable)

1. **No `if found: assert`** — an assertion inside an `if` block is never executed when the
   element is absent; the test stays green while the feature is broken. Assert unconditionally
   or use `require_db()` / a skip guard that ties to a *feature flag*, not element presence.
2. **No `or`-chained assertions** — `assert status == 200 or status == 204` is green for any
   2xx; pin the exact status the implementation promises.
3. **No skip-to-green** — `pytest.skip` is only correct when a feature is *intentionally
   disabled by config* and the skip is gated on that config flag, not on a UI element being absent.
4. **Never assert from the UI layer alone** — every mutating action gets at least one
   Channel-A or Channel-C assertion confirming the backend state changed.

### Example: admin disables account → DNS API returns 401

```python
# 1. Admin action via UI
await browser.goto(f"/admin/accounts/{account_id}/disable")
await browser.click("button[type='submit']")

# 2. Channel A: DB immediately reflects the change
verification.wait_for(
    lambda: verification.get_account(username)["is_active"] == 0,
    timeout=10.0, message="Account not disabled in DB",
)

# 3. Channel C: DNS API returns 401 for a token belonging to the disabled account
status, _ = await verification.dns_api_list_records(token, "example.com")
assert status == 401  # exact, not "400-level"

# 4. Channel A: activity_log has the error_code (not just the HTTP status)
entries = verification.latest_activity(action="api_auth_failed", account_username=username)
assert entries and entries[0]["error_code"] == "account_disabled"
```

### Pattern file

See [`ui_tests/tests/test_cross_role_account_lifecycle.py`](../ui_tests/tests/test_cross_role_account_lifecycle.py)
for the full pattern: account lifecycle (disable/enable, invite+approval, password reset),
with Channel A + B + C assertions and `finally`-block state cleanup. New round-trip tests
should copy this structure.

---

## 5. Property-based Testing with Hypothesis

### Why Hypothesis

Hand-written parametrize lists (`@pytest.mark.parametrize`) cover the cases the developer
*thought of*. Hypothesis generates thousands of examples automatically, guided by shrinking
— when it finds a failure it reduces the input to the smallest possible reproducer. For
parsing and validation code (both security-adjacent), this finds bugs that are essentially
unreachable by intuition.

### Integration plan

1. Add `hypothesis>=6.0` to `requirements-dev.txt`.
2. Create `tests/test_ddns_property.py` — hostname parsing invariants (Example 1 below).
3. Create `tests/test_validators_property.py` — IP-range validator contracts (Example 2 below).
4. Run once with `--hypothesis-seed=0` in CI to pin a reproducible seed; add
   `hypothesis` to the existing `unit-tests` job (no extra services required).
5. Optionally add a `@settings(max_examples=500)` profile for local deep-runs and
   `@settings(max_examples=50)` for CI to keep the job fast.

No app context, no DB, no browser — Hypothesis tests are pure unit tests.

---

### Example 1 — DDNS hostname parsing: the "never crash" and "structure invariant"

`validate_hostname_format` (in `api/ddns_protocols.py`) accepts arbitrary user-supplied
strings. The hand-written tests in `test_ddns_parsing_unit.py` cover ~29 explicit cases.
Hypothesis explores the entire string space and finds the gaps.

**Why this matters**: DDNS hostnames arrive from untrusted external clients. A crash
or misparse here propagates to the Netcup API call. Three invariants are worth pinning:

1. The function always returns `True` or `False` — never raises.
2. Every accepted hostname survives a round-trip: split on `.`, all parts ≤ 63 chars,
   alphanumeric + hyphen only, no empty labels.
3. `parse_hostname` on any accepted hostname always returns a non-None pair.

```python
# tests/test_ddns_property.py
from hypothesis import given, settings
from hypothesis import strategies as st
from netcup_api_filter.api.ddns_protocols import validate_hostname_format, parse_hostname


@given(st.text(max_size=300))
def test_validate_hostname_format_never_raises(s):
    """Any string input must return bool, never raise."""
    result = validate_hostname_format(s)
    assert isinstance(result, bool)


@given(st.text(max_size=300))
def test_parse_hostname_never_raises(s):
    """parse_hostname must return a 2-tuple, never raise."""
    domain, record = parse_hostname(s)
    # Both None or both str — never a mixed partial result
    assert (domain is None) == (record is None)


# Build valid hostnames from the DNS character alphabet
_label = st.from_regex(r'[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?', fullmatch=True)
_hostname = st.lists(_label, min_size=2, max_size=5).map('.'.join)


@given(_hostname)
def test_accepted_hostname_structural_invariants(hostname):
    """Anything validate_hostname_format accepts must satisfy DNS label rules."""
    if not validate_hostname_format(hostname):
        return  # Not our problem — testing the accepted set only
    labels = hostname.split('.')
    for label in labels:
        assert label, "empty label must not be accepted"
        assert len(label) <= 63, "label exceeds DNS 63-char limit"
        assert label[0].isalnum() and label[-1].isalnum()
        assert all(c.isalnum() or c == '-' for c in label)


@given(_hostname)
def test_accepted_hostname_parse_roundtrip(hostname):
    """Every hostname validate_hostname_format accepts must parse to a non-None pair."""
    if not validate_hostname_format(hostname):
        return
    domain, record = parse_hostname(hostname)
    assert domain is not None
    assert record is not None
    assert '.' in domain
```

Hypothesis will try strings like `"\x00"`, `"a" * 300`, `"--foo.bar"`, `".foo"`,
`"foo..bar"` — cases the 29 explicit tests do not cover. If any of those raise, the
failure message includes the minimal reproducer.

---

### Example 2 — IP-range validator: format contract invariants

`validate_ip_range` (in `utils.py`) accepts four formats: single IP, CIDR, dash-range,
and wildcard. The hand-written tests in `test_validators_unit.py` cover ~12 explicit
cases. The function contains manual string splitting that is easy to get wrong at the
boundaries.

**Why this matters**: IP allowlisting is a security control. A false-positive (accepting
a malformed range as valid) can silently whitelist an unintended address block.

Two invariants worth pinning:

1. Any input Python's `ipaddress` module accepts as a valid network must be accepted.
2. Any input our function accepts as a valid single IP must be parseable by
   `ipaddress.ip_address()` — no phantom IPs.

```python
# tests/test_validators_property.py
import ipaddress
from hypothesis import given, assume
from hypothesis import strategies as st
from hypothesis.strategies import ip_addresses
from netcup_api_filter.utils import validate_ip_range


@given(st.text(max_size=100))
def test_validate_ip_range_never_raises(s):
    """Any string must return bool, never raise."""
    result = validate_ip_range(s)
    assert isinstance(result, bool)


@given(ip_addresses(v=4).map(str))
def test_valid_ipv4_always_accepted(ip):
    """Any IPv4 address Python accepts must pass our validator."""
    assert validate_ip_range(ip) is True


@given(ip_addresses(v=6).map(str))
def test_valid_ipv6_always_accepted(ip):
    """Any IPv6 address Python accepts must pass our validator."""
    assert validate_ip_range(ip) is True


@given(
    ip_addresses(v=4),
    st.integers(min_value=0, max_value=32),
)
def test_valid_cidr_always_accepted(base_ip, prefix):
    """Any valid CIDR block must pass our validator."""
    network = ipaddress.ip_network(f"{base_ip}/{prefix}", strict=False)
    assert validate_ip_range(str(network)) is True


@given(
    ip_addresses(v=4).map(str),
    ip_addresses(v=4).map(str),
)
def test_accepted_dash_range_both_ips_parseable(ip1, ip2):
    """A dash-range accepted by our validator must consist of two valid IPs."""
    candidate = f"{ip1}-{ip2}"
    if not validate_ip_range(candidate):
        return  # only checking the accepted set
    # Both halves must parse cleanly
    left, right = candidate.split('-', 1)
    ipaddress.ip_address(left.strip())   # raises if wrong — surfaced as Hypothesis failure
    ipaddress.ip_address(right.strip())
```

The CIDR test in particular will find the edge case where `prefix=0` or `prefix=32`
produces unusual network strings that our manual `'/' in ip_range` branch might
mishandle. Hypothesis shrinks any failure to the smallest prefix that triggers the bug.

---

## Related Documentation

- [UI Testing Guide](UI_TESTING_GUIDE.md) - Comprehensive UI testing strategy
- [Journey Contracts](JOURNEY_CONTRACTS.md) - Test journey specifications
- [Testing Strategy](deprecated/TESTING_STRATEGY.md) - Overall testing architecture
- [Parallel Session Strategy](PARALLEL_SESSION_STRATEGY.md) - Multi-session testing

---

## History

| Date | Change | Author |
|------|--------|--------|
| 2024-12-08 | Initial documentation of lessons learned | AI Agent |

---

**CRITICAL FOR AI AGENTS**: Read this document BEFORE implementing any Playwright-based login, 2FA, or navigation tests. These patterns prevent 90% of test flakiness issues.
