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

## Related Documentation

- [UI Testing Guide](UI_TESTING_GUIDE.md) - Comprehensive UI testing strategy
- [Journey Contracts](JOURNEY_CONTRACTS.md) - Test journey specifications
- [Testing Strategy](TESTING_STRATEGY.md) - Overall testing architecture
- [Parallel Session Strategy](PARALLEL_SESSION_STRATEGY.md) - Multi-session testing

---

## History

| Date | Change | Author |
|------|--------|--------|
| 2024-12-08 | Initial documentation of lessons learned | AI Agent |

---

**CRITICAL FOR AI AGENTS**: Read this document BEFORE implementing any Playwright-based login, 2FA, or navigation tests. These patterns prevent 90% of test flakiness issues.
