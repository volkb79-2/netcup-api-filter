# Test Gap Analysis: Why We Missed the current_user Error

**Date**: 2026-01-06  
**Issue**: Template error in initial setup workflow (500 error after password change)  
**Root Cause**: `2fa_setup_warning.html` used `current_user` instead of `g.admin`

## Executive Summary

A critical template error in the initial setup workflow went undetected by our comprehensive test suite (90+ tests). The error only manifested when:
1. Fresh deployment (must_change_password=true)
2. User completes password change
3. Dashboard redirect triggers template rendering
4. 2FA warning component tries to access undefined `current_user`

**Why tests didn't catch it**: Our tests explicitly navigate to pages rather than following redirects, and disable 2FA in local testing which prevents the problematic template from rendering.

---

## The Bug

**Location**: `templates/components/2fa_setup_warning.html:3`  
**Error**: Used `current_user.requires_2fa_setup()` instead of `g.admin.requires_2fa_setup()`  
**Impact**: 500 Internal Server Error on dashboard after initial password change  
**Severity**: **Critical** - blocks 100% of new deployments from completing setup

**Actual error from production log**:
```
jinja2.exceptions.UndefinedError: 'current_user' is undefined
  File "templates/admin/dashboard.html", line 16
    {% include 'components/2fa_setup_warning.html' %}
  File "templates/components/2fa_setup_warning.html", line 3
    {% if current_user.requires_2fa_setup() %}
```

---

## Why Tests Didn't Catch It

### Gap 1: We Don't Test the Redirect Path

**Production Flow (What Users Experience)**:
```
1. POST /admin/change-password (with new password)
2. Flask processes password change
3. → redirect(url_for('admin.dashboard'))
4. GET /admin/dashboard
5. render_template('admin/dashboard.html', ...)
6. Template includes 'components/2fa_setup_warning.html'
7. {% if current_user.requires_2fa_setup() %}
8. ❌ CRASH: UndefinedError
```

**Test Flow (What We Actually Test)**:
```python
# From ui_tests/tests/journeys/j1_fresh_deployment.py:test_J1_03

# Submit password change form
await browser.click('#submitBtn')
await asyncio.sleep(1.0)

# ❌ We stop here! Never verify redirect completed
# ❌ Never check dashboard actually rendered

# Next test: test_J1_04_dashboard_state
from ui_tests import workflows
await workflows.ensure_admin_dashboard(browser)
# ❌ This does a FRESH login, not following the redirect
```

### Gap 2: ensure_admin_dashboard() Masks Problems

**From `ui_tests/workflows.py:235`**:
```python
async def ensure_admin_dashboard(browser: Browser):
    """Log into admin UI and land on dashboard."""
    
    # 1. Check if already logged in
    if "/admin/" in current_url and "/admin/login" not in current_url:
        await browser.goto("/admin/")  # ❌ Explicit navigation
        return browser
    
    # 2. Go to login page
    await browser.goto("/admin/login")
    
    # 3. Submit credentials
    await browser.click("button[type='submit']")
    
    # 4. If password change detected:
    if "Change Password" in h1:
        # ... submit password form ...
        await browser.click("#submitBtn")
        
        # ❌ Wait for h1 to change, but DON'T trust redirect
        while "Dashboard" not in h1:
            await anyio.sleep(0.5)
            h1 = await browser.text("main h1")
    
    # 5. Final verification
    await browser.wait_for_text("main h1", "Dashboard")
    # ❌ Still on the redirected page, but we got lucky
    #    The redirect already happened, we're just checking
```

**The Problem**: 
- This function is too clever
- It handles password changes but doesn't actually verify the redirect worked
- It relies on the redirect having already completed, then just checks the h1
- If the redirect failed (like with our 500 error), the wait_for_text would timeout

**Why it didn't catch our bug**:
- The function waits for "Dashboard" in h1
- With our 500 error, the h1 never says "Dashboard"
- But the error happens AFTER the form submission
- So the test would have timed out or failed differently
- **BUT**: We always run tests with `ADMIN_2FA_SKIP=true` (see Gap 3)

### Gap 3: ADMIN_2FA_SKIP Hides Template Errors

**From `run-local-tests.sh:94`**:
```bash
ADMIN_2FA_SKIP=true \
  gunicorn -b 0.0.0.0:5100 ...
```

**Impact**:
```python
# In the template
{% if current_user.requires_2fa_setup() %}
    <!-- 2FA warning -->
{% endif %}
```

**When `ADMIN_2FA_SKIP=true`**:
- Admin accounts created with `email_2fa_enabled=0`
- `requires_2fa_setup()` returns `False`  
- Template never enters the `{% if %}` block
- **Error never triggers** because the code path isn't executed

**Production (no ADMIN_2FA_SKIP)**:
- Admin accounts have `email_2fa_enabled=1` by default
- `requires_2fa_setup()` returns `True`
- Template enters the `{% if %}` block
- `current_user` is undefined → **500 error**

### Gap 4: Test Execution Order Matters

**Sequential execution** (like in journey tests):
```python
# Test 1: test_J1_03_forced_password_change
await browser.click('#submitBtn')
# Browser state: Redirected to dashboard (or 500 error page)

# Test 2: test_J1_04_dashboard_state  
await workflows.ensure_admin_dashboard(browser)
# ❌ This function checks "already logged in"
# ❌ Sees we're on /admin/ (or /error/500)
# ❌ Just navigates to /admin/ anyway
```

**Independent execution** (like in UI tests):
```python
# Each test starts with fresh browser
async def test_admin_dashboard_and_footer(active_profile):
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        # ❌ Always does full login, never tests the redirect
```

---

## The Missing Tests

### Critical Missing Test: Password Change Redirect Flow

```python
async def test_password_change_redirects_to_dashboard_successfully():
    """Test the complete password change flow including redirect.
    
    This test ensures the redirect from password change to dashboard
    completes successfully and the dashboard renders without errors.
    """
    # 1. Fresh deployment: login with default credentials
    await browser.goto('/admin/login')
    await browser.fill('#username', 'admin')
    await browser.fill('#password', 'admin')
    await browser.click('button[type="submit"]')
    
    # 2. Should redirect to change password (must_change_password=1)
    await browser.wait_for_url('/admin/change-password')
    h1 = await browser.text('h1')
    assert 'Initial Setup' in h1 or 'Change Password' in h1
    
    # 3. Fill and submit password form
    new_password = generate_secure_password()
    await browser.fill('#new_password', new_password)
    await browser.fill('#confirm_password', new_password)
    
    # Wait for validation to enable submit button
    await browser.wait_for_enabled('#submitBtn')
    
    # 4. Submit form
    await browser.click('#submitBtn')
    
    # 5. ✅ CRITICAL: Wait for redirect to complete
    #    This is the key test we were missing!
    await browser.wait_for_url('/admin/')
    
    # 6. ✅ Verify dashboard rendered successfully (no 500 error)
    h1 = await browser.text('h1')
    assert 'Dashboard' in h1, f"Expected dashboard, got: {h1}"
    
    # 7. ✅ Verify no error messages
    body = await browser.text('body')
    assert '500' not in body
    assert 'Internal Server Error' not in body
    assert 'UndefinedError' not in body
    
    # 8. ✅ Verify dashboard components rendered
    assert await browser.query_selector('.dashboard-stats')
    assert await browser.query_selector('footer')
```

### Test 2: Dashboard Components Render Without Error

```python
async def test_dashboard_all_components_render():
    """Verify all dashboard components render without Jinja errors."""
    await ensure_admin_dashboard(browser)
    
    # Check page source for Jinja errors
    page_source = await browser.page_content()
    assert 'jinja2.exceptions' not in page_source
    assert 'UndefinedError' not in page_source
    assert 'TemplateNotFound' not in page_source
    
    # Verify key components exist
    assert await browser.query_selector('.dashboard-stats')
    assert await browser.query_selector('footer')
    assert await browser.query_selector('nav')
```

### Test 3: All Admin Pages After Password Change

```python
async def test_all_admin_pages_accessible_after_setup():
    """Verify all admin pages accessible after initial setup."""
    # Perform complete setup flow (password change)
    await complete_initial_setup(browser)
    
    # Test every admin route
    admin_routes = [
        '/admin/',
        '/admin/accounts',
        '/admin/realms',
        '/admin/audit',
        '/admin/config/netcup',
        '/admin/config/email',
        '/admin/system'
    ]
    
    for route in admin_routes:
        await browser.goto(route)
        
        # Verify no 500 error
        body = await browser.text('body')
        assert '500' not in body, f'500 error on {route}'
        assert 'Internal Server Error' not in body, f'Error on {route}'
        
        # Verify we're not redirected to login (session works)
        assert '/login' not in browser.url, f'Redirected to login from {route}'
```

### Test 4: Run Tests With 2FA Enabled

```bash
# In run-local-tests.sh, add a separate test phase

echo "Running tests with 2FA enabled..."

# Start Flask WITHOUT ADMIN_2FA_SKIP
PYTHONPATH="${DEPLOY_LOCAL_DIR}/vendor" \
  SECRET_KEY="${SECRET_KEY}" \
  NETCUP_FILTER_DB_PATH="${NETCUP_FILTER_DB_PATH}" \
  FLASK_ENV="${FLASK_ENV}" \
  gunicorn -b 0.0.0.0:5100 --workers=1 \
  --daemon --pid /tmp/gunicorn-2fa.pid

# Run 2FA-specific tests
pytest ui_tests/tests/test_2fa_flows.py -v

# Cleanup
kill $(cat /tmp/gunicorn-2fa.pid)
```

---

## Other Potential Gaps

### 1. Template Context Audit Needed

**Problem**: Admin routes use `g.admin`, account routes might use `current_user`

**Files to audit**:
```bash
# Find all uses of current_user in templates
grep -r "current_user" src/netcup_api_filter/templates/

# Check which templates are used in admin context
grep -r "{% extends \"admin/" src/netcup_api_filter/templates/
```

### 2. No Pre-Deployment Smoke Test

**Missing**: Automated test that mirrors actual deployment workflow

**Needed**: A single test that runs the complete setup:
```python
def test_production_deployment_smoke_test():
    """Complete setup workflow from fresh deployment."""
    # 1. Login with admin/admin
    # 2. Change password (follow redirect, check dashboard)
    # 3. Skip email setup
    # 4. Navigate to System Config
    # 5. Configure Netcup API
    # 6. Configure SMTP
    # 7. Set email for 2FA
    # 8. Logout
    # 9. Login with 2FA
```

### 3. No Template Linting

**Problem**: Jinja2 templates allow undefined variables in conditionals

**Example**:
```jinja
{% if nonexistent_variable %}
    This never renders, so error is hidden
{% endif %}
```

**Solution**: Add template linting to CI:
```python
# In a test or pre-commit hook
def test_templates_have_valid_context():
    """Verify all template variables exist in expected context."""
    from jinja2 import Environment, meta
    
    env = Environment()
    
    for template_path in Path('templates').rglob('*.html'):
        with open(template_path) as f:
            ast = env.parse(f.read())
            variables = meta.find_undeclared_variables(ast)
            
            # Check against expected context for this template type
            if 'admin/' in str(template_path):
                assert 'current_user' not in variables, \
                    f"{template_path} uses current_user (should use g.admin)"
```

---

## Progress Update

**Date**: 2026-01-06 (Evening)  
**Status**: All critical gaps addressed ✅

### Completed Actions

#### Immediate Fixes
- [x] **Fixed template**: `current_user` → `g.admin` in `2fa_setup_warning.html`
- [x] **Deployed fix** to production (webhosting)
- [x] **Verified fix** via sshfs + sqlite3 (password change succeeded, database updated)

#### Test Coverage Added
- [x] **Template audit**: All templates use correct context variable
  - Admin templates: `g.admin` ✅
  - Account templates: `current_user` ✅
  - Shared components: Accept as parameter ✅

- [x] **New test file**: `ui_tests/tests/test_password_change_flow.py`
  - `test_password_change_redirects_to_dashboard_successfully()` - THE critical test
  - `test_dashboard_components_render_without_error()` - Template error detection
  - `test_all_admin_pages_accessible_after_password_change()` - Session persistence
  - `test_password_change_with_email_setup_optional()` - Email optional fix verification

- [x] **New test file**: `ui_tests/tests/test_2fa_enabled_flows.py`
  - `test_2fa_warning_component_renders_on_dashboard()` - Component rendering with 2FA
  - `test_complete_2fa_flow_with_mailpit()` - End-to-end 2FA with Mailpit
  - `test_dashboard_renders_with_2fa_enabled()` - Dashboard under real 2FA conditions

- [x] **New test script**: `run-2fa-tests.sh`
  - Runs Flask WITHOUT `ADMIN_2FA_SKIP`
  - Uses Mailpit for real email 2FA testing
  - Catches template errors that only show with 2FA enabled

### What Changed

**Before**:
- 90+ tests, but none tested password-change → redirect → dashboard
- `ADMIN_2FA_SKIP=true` hid template errors in 2FA components
- `ensure_admin_dashboard()` used explicit navigation, masking redirect failures

**After**:
- +7 new tests specifically for password change flow and 2FA scenarios
- Separate test runner for 2FA-enabled tests (with Mailpit)
- Tests now follow actual redirect paths instead of explicit navigation

## Recommendations

### Immediate (Today) ✅ DONE
- [x] Fixed template: `current_user` → `g.admin`
- [x] Manually tested: fresh deployment → setup → verified dashboard works
- [x] Added test: password change redirect to dashboard

### Short Term (This Week) ✅ DONE
- [x] Audited all templates for `current_user` vs `g.admin`
- [x] Added test suite: "post-password-change" scenarios
- [x] Created test variant WITHOUT `ADMIN_2FA_SKIP` (run-2fa-tests.sh)
- [x] Documented template context expectations (see audit results above)

### Medium Term (Next Sprint) 🔄 IN PROGRESS
- [x] Implement full E2E setup workflow test (test_password_change_flow.py)
- [ ] Add template linting to CI/pre-commit (TODO: see Template Linting section below)
- [ ] Create pre-deployment checklist with manual verification (TODO)
- [ ] Set up staging environment with production parity (TODO)
- [ ] Add visual regression tests for dashboard (TODO)

---

## New Test Files Created

### 1. test_password_change_flow.py

**Purpose**: Test the actual redirect path from password change to dashboard

**Key tests**:
- `test_password_change_redirects_to_dashboard_successfully()` - **THE CRITICAL TEST**
  - Submits password form
  - Waits for redirect to complete (not explicit navigation)
  - Verifies dashboard rendered without 500 errors
  - Checks all dashboard components loaded

- `test_dashboard_components_render_without_error()`
  - Verifies no Jinja2 exceptions in page source
  - Checks all key components exist

- `test_all_admin_pages_accessible_after_password_change()`
  - Visits every admin route after password change
  - Ensures session persists
  - Verifies no 500 errors on any page

- `test_password_change_with_email_setup_optional()`
  - Verifies email field is optional (not required)
  - Tests submission without email succeeds
  - Confirms fix for "can't complete setup before SMTP configured" issue

### 2. test_2fa_enabled_flows.py

**Purpose**: Test with 2FA fully enabled (using Mailpit, no ADMIN_2FA_SKIP)

**Key tests**:
- `test_2fa_warning_component_renders_on_dashboard()`
  - Verifies 2FA warning component renders without errors
  - Checks for `current_user` undefined errors
  - Ensures template uses `g.admin` correctly

- `test_complete_2fa_flow_with_mailpit()`
  - End-to-end: login → 2FA email → code submission → dashboard
  - Uses Mailpit API to intercept and extract codes
  - Verifies full flow works with real email 2FA

- `test_dashboard_renders_with_2fa_enabled()`
  - Specifically tests condition that was broken
  - Admin with `email_2fa_enabled=1`
  - Dashboard includes 2FA components
  - All components render correctly

### 3. run-2fa-tests.sh

**Purpose**: Run tests WITHOUT `ADMIN_2FA_SKIP` to catch production-only issues

**What it does**:
- Starts Flask with 2FA fully enabled (no skip flag)
- Requires Mailpit running
- Runs test_2fa_enabled_flows.py test suite
- Automatically cleans up

**Usage**:
```bash
# Start Mailpit first
cd tooling/mailpit && docker compose up -d

# Run 2FA tests
./run-2fa-tests.sh
```

---

## Template Linting (TODO)

**Goal**: Catch undefined variables in templates before deployment

**Approach**: Add pre-commit hook or CI check that validates template context

**Example implementation**:
```python
def test_admin_templates_use_correct_context():
    """Verify admin templates use g.admin, not current_user."""
    from pathlib import Path
    
    admin_templates = Path('src/netcup_api_filter/templates/admin').rglob('*.html')
    
    for template_path in admin_templates:
        with open(template_path) as f:
            content = f.read()
            
            # Check for current_user usage in admin templates
            if 'current_user' in content:
                # Allow in comments
                lines = [l for l in content.split('\n') 
                        if 'current_user' in l and not l.strip().startswith('{#')]
                
                if lines:
                    pytest.fail(f"{template_path} uses current_user (should use g.admin)")
```

**Status**: ⬜ Not yet implemented (add to pre-commit hooks)

---

## Lessons Learned

### 1. Test the Redirect, Not Just the Destination
**Don't**: Navigate explicitly after form submission  
**Do**: Wait for redirect to complete and verify destination loaded correctly

### 2. Test Configuration Parity Matters
**Problem**: `ADMIN_2FA_SKIP=true` in local tests hides production issues  
**Solution**: Run some tests with all security features enabled

### 3. Template Errors Are Silent in Happy Path
**Problem**: Conditional blocks hide undefined variables  
**Solution**: Add template linting, test both branches of conditionals

### 4. Helper Functions Can Mask Issues
**Problem**: `ensure_admin_dashboard()` is too smart, hides failures  
**Solution**: Also have "dumb" tests that just follow user flow

### 5. Initial Setup Deserves Special Attention
**Insight**: Used by 100% of users exactly once  
**Action**: Dedicated test coverage for setup workflows

### 6. Integration Tests Need End-to-End Flows
**Problem**: Testing individual pages doesn't catch flow issues  
**Solution**: Add journey tests that follow complete user workflows

---

## Test Coverage Metrics

### Before This Issue
- **Total tests**: 90+
- **Admin UI tests**: 27 comprehensive
- **Journey tests**: 15 end-to-end
- **Coverage**: High for individual pages
- **Gap**: No test for password-change → dashboard redirect

### After Fixes (Current) ✅
- **Total tests**: 97+ (added 7 new tests)
- **New test files**: 2
  - `test_password_change_flow.py` (4 tests)
  - `test_2fa_enabled_flows.py` (3 tests)
- **New test runner**: `run-2fa-tests.sh` (2FA-enabled variant)
- **Coverage**: 
  - ✅ Password change redirect flow fully tested
  - ✅ Dashboard component rendering validated
  - ✅ All admin pages post-setup verified
  - ✅ 2FA-enabled scenarios covered (with Mailpit)
  - ✅ Template context usage audited and documented
- **CI**: Template linting not yet enabled (TODO)
- **Environments**: Can now run tests with/without ADMIN_2FA_SKIP

### Test Execution Modes

| Mode | Script | ADMIN_2FA_SKIP | Use Case |
|------|--------|----------------|----------|
| **Local (fast)** | `run-local-tests.sh` | ✅ true | Quick iteration, most tests |
| **2FA (real)** | `run-2fa-tests.sh` | ❌ false | Production parity, Mailpit integration |
| **Webhosting** | `deploy.sh webhosting` | ❌ false | Pre-deployment verification |

---

## Conclusion

This was a classic case of **testing the destination but not the journey**. Our tests verified that:
- Login works ✅
- Password change form works ✅  
- Dashboard loads when navigated to ✅

But we never tested:
- Password change → redirect → dashboard render ❌

The fix is simple (one line), but the learning is valuable: **integration tests must follow the actual user flow, including redirects, not take shortcuts with explicit navigation**.
