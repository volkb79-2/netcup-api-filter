# Playwright Waiting Patterns - Best Practices

## ❌ BAD: Using `asyncio.sleep()`

```python
# DON'T DO THIS - Flaky and slow
await page.goto("/login")
await asyncio.sleep(1.0)  # Hope page loaded?

await page.click("button")
await asyncio.sleep(2.0)  # Hope navigation finished?

await page.fill("#input", "value")
await asyncio.sleep(0.5)  # Hope element ready?
```

**Problems**:
- ⏱️ **Too slow**: Always waits full duration even if ready earlier
- 🎲 **Flaky**: Might not wait long enough on slow networks
- 🐛 **Hard to debug**: Timeout errors don't explain what was waited for
- 📉 **Masks issues**: Hides race conditions that might occur in production

---

## ✅ GOOD: Playwright's Built-in Waiting

### 1. Wait for Navigation

```python
# Wait for page load after click
async with page.expect_navigation(wait_until="networkidle"):
    await page.click("button[type='submit']")

# Or use goto which waits automatically
await page.goto("/dashboard")  # Waits for load by default

# Wait for specific URL pattern
await page.wait_for_url("**/dashboard")  # Waits until URL matches
await page.wait_for_url(lambda url: "/admin" in url)  # Custom condition
```

**`wait_until` options**:
- `"load"` - DOMContentLoaded event (default for navigation)
- `"domcontentloaded"` - HTML parsed, DOM ready
- `"networkidle"` - No network connections for 500ms (best for dynamic pages)
- `"commit"` - Initial HTML received

---

### 2. Wait for Selectors (Elements)

```python
# Wait for element to appear
await page.wait_for_selector("#submit-button")
await page.wait_for_selector("text=Success!", timeout=10000)

# Wait for element to be visible (not just in DOM)
await page.wait_for_selector("#modal", state="visible")

# Wait for element to disappear
await page.wait_for_selector(".loading-spinner", state="hidden")

# Wait for element to be enabled/disabled
await page.wait_for_selector("button[type='submit']", state="attached")
```

**`state` options**:
- `"attached"` - Element exists in DOM (default)
- `"detached"` - Element removed from DOM
- `"visible"` - Element visible (not display:none, not hidden)
- `"hidden"` - Element not visible

---

### 3. Wait for Load States

```python
# Wait for different load states
await page.wait_for_load_state("load")  # Basic page load
await page.wait_for_load_state("domcontentloaded")  # DOM ready
await page.wait_for_load_state("networkidle")  # All network done

# After navigation
await page.goto("/dashboard")
await page.wait_for_load_state("networkidle")  # Extra safety
```

---

### 4. Auto-Waiting Actions

Most Playwright actions **automatically wait**:

```python
# These all wait for element to be actionable before proceeding
await page.click("#button")  # Waits: exists, visible, stable, enabled
await page.fill("#input", "text")  # Waits: exists, visible, enabled
await page.select_option("#dropdown", "value")  # Waits: exists, visible

# No manual waiting needed!
await page.goto("/login")
await page.fill("#username", "admin")  # Auto-waits for input
await page.fill("#password", "pass123")  # Auto-waits for input
await page.click("button[type='submit']")  # Auto-waits for button
```

**Auto-wait checks**:
- ✅ Element is attached to DOM
- ✅ Element is visible
- ✅ Element is stable (not animating)
- ✅ Element receives events (not obscured)
- ✅ Element is enabled (for inputs/buttons)

---

### 5. Assertions with Auto-Wait

```python
from playwright.async_api import expect

# These poll until condition is true (or timeout)
await expect(page.locator("#status")).to_have_text("Success")
await expect(page.locator(".error")).to_be_visible()
await expect(page.locator("#loading")).to_be_hidden()
await expect(page).to_have_url(/.*dashboard.*/)

# Custom timeout
await expect(page.locator("#slow-element")).to_be_visible(timeout=30000)
```

---

### 6. Wait for Functions/Conditions

```python
# Wait for custom JavaScript condition
await page.wait_for_function("() => document.readyState === 'complete'")
await page.wait_for_function("() => window.myApp.initialized === true")

# Wait for custom condition
await page.wait_for_function(
    "(selector) => document.querySelector(selector).textContent.includes('Done')",
    "div.status"
)
```

---

### 7. Wait for Responses

```python
# Wait for specific API response
async with page.expect_response("**/api/users") as response_info:
    await page.click("#load-users")
response = await response_info.value

# Wait for any response matching condition
async with page.expect_response(lambda r: r.status == 200 and "api" in r.url):
    await page.click("#submit")
```

---

## Real-World Examples

### Example 1: Form Submission with Error Handling

```python
# ❌ BAD
await page.fill("#email", "test@example.com")
await page.click("button[type='submit']")
await asyncio.sleep(2.0)  # Hope something happened?
body = await page.text_content("body")
assert "Success" in body or "Error" in body

# ✅ GOOD
await page.fill("#email", "test@example.com")

async with page.expect_navigation(wait_until="networkidle", timeout=10000):
    await page.click("button[type='submit']")

# Wait for either success or error message
try:
    await page.wait_for_selector("text=Success", timeout=5000)
    print("✓ Form submitted successfully")
except:
    error = await page.wait_for_selector(".alert-error", timeout=1000)
    error_text = await error.text_content()
    print(f"✗ Form submission failed: {error_text}")
```

---

### Example 2: Modal Dialog Interaction

```python
# ❌ BAD
await page.click("#open-modal")
await asyncio.sleep(1.0)  # Hope modal opened?
await page.click("#modal button")

# ✅ GOOD
await page.click("#open-modal")
await page.wait_for_selector("#modal", state="visible")

# Modal is now visible and stable
await page.click("#modal button")

# Wait for modal to close
await page.wait_for_selector("#modal", state="hidden")
```

---

### Example 3: 2FA Code Entry

```python
# ❌ BAD
await page.fill("#username", "admin")
await page.fill("#password", "pass123")
await page.click("button[type='submit']")
await asyncio.sleep(2.0)  # Maybe 2FA page loaded?

if "/2fa" in page.url:  # Race condition - URL might not be updated yet!
    await page.fill("#code", "123456")

# ✅ GOOD
await page.fill("#username", "admin")
await page.fill("#password", "pass123")

async with page.expect_navigation(wait_until="networkidle"):
    await page.click("button[type='submit']")

# URL is definitely updated now
if "/2fa" in page.url:
    # Wait for code input to be ready
    await page.wait_for_selector("#code", state="visible")
    await page.fill("#code", "123456")
    
    async with page.expect_navigation(wait_until="networkidle"):
        await page.click("button[type='submit']")
```

---

### Example 4: Waiting for Dynamic Content

```python
# ❌ BAD
await page.click("#load-data")
await asyncio.sleep(3.0)  # Hope data loaded?
items = await page.query_selector_all(".data-item")

# ✅ GOOD
await page.click("#load-data")

# Wait for loading spinner to disappear
await page.wait_for_selector(".spinner", state="hidden")

# Wait for at least one item to appear
await page.wait_for_selector(".data-item", state="visible")

# Now safe to count items
items = await page.query_selector_all(".data-item")
```

---

### Example 5: File Upload with Progress

```python
# ❌ BAD
await page.set_input_files("#file-upload", "/path/to/file")
await asyncio.sleep(5.0)  # Hope upload finished?

# ✅ GOOD
await page.set_input_files("#file-upload", "/path/to/file")

# Wait for upload to complete
await page.wait_for_selector(".upload-progress[aria-valuenow='100']")

# Or wait for success message
await page.wait_for_selector("text=Upload complete", timeout=30000)
```

---

## Migration Guide

### Before (with asyncio.sleep)

```python
async def test_login():
    await page.goto("/login")
    await asyncio.sleep(0.5)
    
    await page.fill("#username", "admin")
    await page.fill("#password", "pass")
    await page.click("button")
    await asyncio.sleep(2.0)
    
    assert "/dashboard" in page.url
```

### After (with proper waits)

```python
async def test_login():
    await page.goto("/login")
    await page.wait_for_load_state("networkidle")
    
    await page.fill("#username", "admin")
    await page.fill("#password", "pass")
    
    async with page.expect_navigation(wait_until="networkidle"):
        await page.click("button")
    
    await expect(page).to_have_url(/.*dashboard.*/)
```

---

## When to Use Which Wait

| Scenario | Use This |
|----------|----------|
| After navigation (goto, click) | `expect_navigation()` or `wait_for_url()` |
| Element appears/disappears | `wait_for_selector()` with `state` |
| Page finishes loading | `wait_for_load_state("networkidle")` |
| API response returns | `expect_response()` |
| Custom condition | `wait_for_function()` |
| Assert visible text | `expect(locator).to_have_text()` |
| General timeout | Only as last resort, with clear comment why |

---

## Performance Tips

1. **Use shortest necessary wait level**:
   ```python
   # Fast: Just need DOM
   await page.wait_for_load_state("domcontentloaded")
   
   # Slower: Wait for all network
   await page.wait_for_load_state("networkidle")
   ```

2. **Combine waits efficiently**:
   ```python
   # ❌ Slow - two separate waits
   await page.goto("/page")
   await page.wait_for_selector("#element")
   
   # ✅ Fast - goto waits for load, then element
   await page.goto("/page", wait_until="domcontentloaded")
   await page.wait_for_selector("#element")
   ```

3. **Use specific selectors**:
   ```python
   # ❌ Slow - searches whole DOM
   await page.wait_for_selector("div")
   
   # ✅ Fast - specific selector
   await page.wait_for_selector("#specific-id")
   ```

---

## Summary

✅ **DO**:
- Use `expect_navigation()` for clicks that navigate
- Use `wait_for_selector()` for elements appearing/disappearing
- Use `wait_for_load_state()` after goto
- Trust Playwright's auto-waiting for actions
- Use `expect()` assertions for polling conditions

❌ **DON'T**:
- Use `asyncio.sleep()` (almost never needed)
- Assume page loaded without verification
- Check state immediately after action (wait first!)
- Use arbitrary timeouts (be explicit about what you're waiting for)

**Result**: Faster, more reliable, easier to debug tests! 🎉
