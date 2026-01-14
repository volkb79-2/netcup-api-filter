# Testing Against Webhosting (HTTPS Production)

## Current Limitations & Solutions

### 1. Session Cookie Domain Mismatch ✅ (Solved)

This used to happen when Flask set session cookies for an internal hostname while the browser accessed the app via the public TLS proxy.

**Current behavior**:
- **Local HTTPS (TLS proxy)**: cookies are set for the public hostname because `PUBLIC_FQDN` is auto-detected and `FLASK_SESSION_COOKIE_DOMAIN=auto` maps it to `SESSION_COOKIE_DOMAIN=.<PUBLIC_FQDN>`.
- **Webhosting (production HTTPS)**: the app already runs behind the production TLS proxy on its public domain, so cookies are issued for the correct host.

**Takeaway**: you should not need any cookie-domain workaround anymore.

**Recommended anyway: reuse Playwright auth state** (faster tests, fewer logins)

```python
from ui_tests.auth_state import ensure_authenticated

async def test_against_webhosting():
    async with browser_session() as browser:
        page = browser._page
        context = page.context
        
        # Authenticate once, reuse session
        authenticated = await ensure_authenticated(
            context=context,
            page=page,
            login_url=settings.url("/admin/login"),
            target="webhosting",
            auth_state_name="webhosting_admin",
        )
        
        if not authenticated:
            pytest.skip("Could not authenticate")
        
        # Now all subsequent requests use saved session
        await page.goto(settings.url("/admin/dashboard"))
```

---

### 2. 2FA Code Retrieval (Webhosting)

For webhosting tests, you have two viable approaches:

#### A. Route webhosting email delivery to your local Mailpit (recommended for automated tests)

This works because the webhosting app can reach your devcontainer host via `PUBLIC_FQDN`.

1. **Secure Mailpit at startup**
    - Ensure Mailpit starts with Basic Auth enabled (username/password set in its config).
    - Do not rely on weak defaults; treat Mailpit credentials like any other secret.

2. **Expose Mailpit API/UI through the local TLS proxy**
    - The reverse proxy can publish Mailpit at a stable HTTPS URL (example: `https://${PUBLIC_FQDN}/mailpit/`).
    - With that in place, tests can query the Mailpit API via the same public hostname (example: `https://${PUBLIC_FQDN}/mailpit/api/v1`).

3. **Expose Mailpit SMTP port to the public host**
    - Publish the SMTP port so the webhosting deployment can send mail to `PUBLIC_FQDN:<mailpit_smtp_port>`.
    - Then configure the webhosting deployment email settings (in the Settings table) to use:
      - SMTP host: `PUBLIC_FQDN`
      - SMTP port: your published Mailpit SMTP port
      - TLS/SSL: disabled (Mailpit is typically plain SMTP)

With this configuration, the webhosting app sends the 2FA email to your Mailpit, and your locally-running tests retrieve the code via the Mailpit API.

#### B. Use TOTP (authenticator app)

```python
async def test_2fa_with_totp():
    """Test using authenticator app codes instead of email."""
    import pyotp
    
    # Get admin's TOTP secret from database or settings
    totp_secret = get_admin_totp_secret()
    totp = pyotp.TOTP(totp_secret)
    
    # Login
    await page.fill("#username", settings.admin_username)
    await page.fill("#password", settings.admin_password)
    await page.click("button[type='submit']")
    
    # Generate current code
    current_code = totp.now()
    
    # Enter 2FA code
    await page.fill("#code", current_code)
    await page.click("button[type='submit']")
```

#### C. Use recovery codes

```python
async def test_with_recovery_code():
    """Use pre-generated recovery codes for testing."""
    # Store recovery codes in deployment_state_webhosting.json
    recovery_code = settings.admin_recovery_codes[0]  # Use first code
    
    # During 2FA prompt
    await page.click("text=Use recovery code")
    await page.fill("#recovery-code", recovery_code)
    await page.click("button[type='submit']")
```

#### D. Adjust 2FA settings directly in the webhosting database (debug only)

If you need to temporarily disable email 2FA for a specific account, do it directly against the webhosting SQLite DB via sshfs (see database section below), then revert.

---

### 3. Database Access (Webhosting via sshfs) ✅

You *can* query the webhosting SQLite database during local test runs.

**How**:
- Mount the webhosting web root via sshfs (devcontainer path is typically under `/home/vscode/sshfs-<sshfs-name>/`).
- The remote DB file (`netcup_filter.db`) is inside that mounted tree.
- Use `sqlite3` locally against the mounted DB file.

This is often the fastest way to verify test preconditions or inspect state when debugging.

Example (adjust paths to your actual mount):
```bash
sqlite3 /home/vscode/sshfs-hosting218629@hosting218629.ae98d.netcup.net/netcup-api-filter/netcup_filter.db \
    "SELECT username, is_admin, must_change_password FROM accounts ORDER BY id DESC LIMIT 10;"
```

#### A. Use UI/API for verification (preferred for black-box tests)

```python
async def verify_account_locked(page, username):
    """Verify lockout via UI instead of database query."""
    # Try to login
    await page.goto(settings.url("/admin/login"))
    await page.fill("#username", username)
    await page.fill("#password", "any_password")
    await page.click("button[type='submit']")
    
    # Check for lockout message in UI
    body = await page.text_content("body")
    return "locked" in body.lower()
```

#### B. Optional: config-gated test endpoints (can be enabled on webhosting too)

If you need better observability than the UI provides, the right pattern is **config-gated endpoints**:
- Endpoint exists in code, but returns `404` unless explicitly enabled
- Enable/disable is driven by the **Settings table** (seedable via `app-config.toml`)
- Works equally well on local and webhosting deployments

Design sketch:
- Setting key: `test_endpoints_enabled` (default: false)
- Optional: `test_endpoints_token` to require a bearer token/header even when enabled

This is safer than tying observability to `FLASK_ENV`.

```python
# In app.py (only enabled when TESTING=True)
@app.route('/__test__/account/<username>/lockout-status')
def test_account_lockout_status(username):
    """Test-only endpoint to check lockout status."""
    if not app.config.get('TESTING'):
        abort(404)
    
    account = Account.query.filter_by(username=username).first()
    if not account:
        return jsonify({"error": "Not found"}), 404
    
    return jsonify({
        "is_2fa_locked": is_2fa_locked(account),
        "is_recovery_code_locked": is_recovery_code_locked(account),
        "2fa_failure_count": get_2fa_failure_count(account)
    })
```

#### C. Optional: test state API (same gating)

```python
# Add to deployment for test observability
@app.route('/api/test/state')
@require_test_mode
def get_test_state():
    """Return current system state for testing."""
    return jsonify({
        "total_accounts": Account.query.count(),
        "locked_accounts": Account.query.join(...).filter(locked).count(),
        "active_sessions": len(sessions),
    })
```

---

### 4. Network Latency & Timeouts

Webhosting performance is usually only marginally slower than local. Instead of assuming a big multiplier, measure a baseline and set timeouts accordingly.

**Baseline idea**:
- Measure the response time for a cheap endpoint like `/admin/login` or an error page.
- Use that as a reference when choosing Playwright timeouts.

```python
import os

# In conftest.py or test config
WEBHOSTING_TIMEOUT = 15000
LOCAL_TIMEOUT = 10000

def get_timeout():
    """Get appropriate timeout based on deployment target."""
    if os.getenv('DEPLOYMENT_TARGET') == 'webhosting':
        return WEBHOSTING_TIMEOUT
    return LOCAL_TIMEOUT

# In tests
async with browser._page.expect_navigation(
    wait_until="networkidle",
    timeout=get_timeout()
):
    await browser.click("button[type='submit']")
```

---

### 5. File System Access (Screenshots, Logs)

Remember the boundary:
- The **application** runs on webhosting.
- The **tests** run locally (devcontainer/Playwright container).

So writing screenshots/logs from tests is a *local filesystem* concern.

**Recommended local targets**:
- `deploy-webhosting/screenshots/` for artifacts produced while testing the webhosting deployment
- Any other local path under the workspace

If you need to inspect the webhosting server’s logs or files, use sshfs (the mounted web root is readable/writable from the devcontainer).

```python
# Detect environment
if os.getenv('DEPLOYMENT_TARGET') == 'webhosting':
    SCREENSHOT_DIR = Path('/workspaces/netcup-api-filter/deploy-webhosting/screenshots')
else:
    SCREENSHOT_DIR = Path('/workspaces/netcup-api-filter/deploy-local/screenshots')

SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# In tests
await page.screenshot(path=str(SCREENSHOT_DIR / 'test.png'))
```

---

## Complete Webhosting Test Example

```python
"""
Example: Testing against webhosting deployment with production-like constraints.
"""

import pytest
from ui_tests.browser import browser_session
from ui_tests.config import settings
from ui_tests.auth_state import ensure_authenticated


@pytest.fixture
def webhosting_timeout():
    """Appropriate timeout for webhosting tests."""
    return 30000 if settings.deployment_target == 'webhosting' else 10000


class TestWebhostingSecurity:
    """Tests that work against webhosting HTTPS deployment."""
    
    async def test_admin_lockout_via_ui(self, webhosting_timeout):
        """Test 2FA lockout by observing UI behavior."""
        async with browser_session() as browser:
            page = browser._page
            context = page.context
            
            # Use saved auth state to bypass initial login
            auth_loaded = await ensure_authenticated(
                context=context,
                page=page,
                login_url=settings.url("/admin/login"),
                target="webhosting",
                auth_state_name="webhosting_admin",
            )
            
            if not auth_loaded:
                pytest.skip("Could not authenticate to webhosting")
            
            # Now test security features via UI observation
            # Logout to test login lockout
            await page.goto(settings.url("/admin/logout"))
            await page.wait_for_load_state('networkidle')
            
            # Try wrong password 5 times
            for attempt in range(1, 6):
                await page.goto(settings.url("/admin/login"))
                await page.fill("#username", settings.admin_username)
                await page.fill("#password", "wrong_password_12345")
                
                async with page.expect_navigation(
                    wait_until="networkidle",
                    timeout=webhosting_timeout
                ):
                    await page.click("button[type='submit']")
                
                body = await page.text_content("body")
                
                if attempt < 5:
                    # Should see error but can retry
                    assert "Invalid" in body or "incorrect" in body.lower()
                else:
                    # Should see lockout message
                    assert "locked" in body.lower() or "too many" in body.lower()
            
            print("✓ Webhosting lockout behavior verified via UI")
    
    async def test_recovery_code_usage(self):
        """Test recovery code redemption on webhosting."""
        async with browser_session() as browser:
            page = browser._page
            
            # Assume we have recovery codes saved in deployment state
            if not hasattr(settings, 'admin_recovery_codes'):
                pytest.skip("No recovery codes available for testing")
            
            # Login triggers 2FA
            await page.goto(settings.url("/admin/login"))
            await page.fill("#username", settings.admin_username)
            await page.fill("#password", settings.admin_password)
            await page.click("button[type='submit']")
            
            # Wait for 2FA page
            await page.wait_for_url("**/2fa", timeout=30000)
            
            # Use recovery code
            await page.click("text=Use recovery code")
            await page.fill("#recovery-code", settings.admin_recovery_codes[0])
            
            async with page.expect_navigation(wait_until="networkidle", timeout=30000):
                await page.click("button[type='submit']")
            
            # Should reach dashboard
            assert "/dashboard" in page.url or "/admin" in page.url
            print("✓ Recovery code accepted on webhosting")
```

---

## Configuration for Webhosting Tests

Add to `deployment_state_webhosting.json`:

```json
{
  "target": "webhosting",
  "admin": {
    "username": "admin",
    "password": "<actual-password>",
    "recovery_codes": [
      "AAAA-BBBB",
      "CCCC-DDDD",
      "EEEE-FFFF"
    ],
    "totp_secret": "<if-using-totp>"
  },
  "test_endpoints_enabled": false,
    "base_url": "https://<your-public-fqdn>/"
}
```

---

## Running Webhosting Tests

```bash
# Set deployment target
export DEPLOYMENT_TARGET=webhosting
export UI_BASE_URL="https://<your-public-fqdn>"

# Run tests with increased timeouts
docker exec \
  -e DEPLOYMENT_TARGET=webhosting \
    -e UI_BASE_URL="https://<your-public-fqdn>" \
  naf-dev-playwright \
  pytest ui_tests/tests/test_2fa_security.py -v --timeout=60

# Or use the test script with webhosting flag (to be created)
./run-2fa-security-tests.sh --webhosting
```

---

## Comparison: Local vs Webhosting Testing

| Feature | Local (HTTP) | Webhosting (HTTPS) |
|---------|-------------|-------------------|
| **Session cookies** | ✅ Work reliably | ✅ Work reliably |
| **2FA codes** | ✅ Via Mailpit API | ✅ Via Mailpit (when routed) or TOTP/recovery |
| **Database access** | ✅ Direct SQLite | ✅ Via sshfs + sqlite3 |
| **Network speed** | ✅ Instant | ✅ Similar (measure baseline) |
| **Logs** | ✅ Direct file access | ✅ Via sshfs (web root) |
| **Test data reset** | ✅ Easy (rebuild) | ⚠️ Requires deployment |
| **Cost** | ✅ Free | 💰 Uses production resources |

---

## Recommendations

1. **Primary Testing**: Use HTTP against local deployment (fast, reliable, full control)
2. **Smoke Testing**: Use storage state against webhosting (verify HTTPS works)
3. **Manual Testing**: Critical flows manually on webhosting (final verification)

**Best Practice**:
```bash
# CI/CD pipeline
1. Run full test suite locally (HTTP) - 90% coverage, fast
2. Run smoke tests on webhosting (HTTPS) - 10% critical paths
3. Manual QA on webhosting - UX validation
```
