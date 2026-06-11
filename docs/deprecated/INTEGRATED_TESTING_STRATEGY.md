# Integrated Testing Strategy

## Executive Summary

This document defines the **journey-based testing architecture** that replaces the current fragmented approach. The core principle: **tests CREATE their prerequisites, VALIDATE behavior, AND CAPTURE screenshots** as unified workflows.

## State Matrix Coverage

The testing framework systematically covers the **combinatorial space** of application states:

### Account States (4 types)
| State | Description | UI Test | API Test |
|-------|-------------|---------|----------|
| Pending | Awaiting admin approval | Admin sees in pending list | Cannot login |
| Approved | Active account | Can login, create realms | Full access |
| Rejected | Denied by admin | Cannot login | Rejected |
| Unverified | Email not verified | Cannot login | Blocked |

### Realm States (3 types × 2 approval states = 6 combinations)
| Type | Approval | Description | Token Creation |
|------|----------|-------------|----------------|
| host | pending | Single hostname only | Blocked |
| host | approved | Single hostname only | Allowed |
| subdomain | pending | Apex + children | Blocked |
| subdomain | approved | Apex + children | Allowed |
| subdomain_only | pending | Children only, not apex | Blocked |
| subdomain_only | approved | Children only, not apex | Allowed |

### Token States (8+ variations)
| Token Type | Scope | Expected Behavior |
|------------|-------|-------------------|
| Read-only | `["read"]` | Can read, cannot update/create/delete |
| DDNS | `["read", "update"]`, A/AAAA only | Can update IP records |
| Full access | All operations | Complete control |
| TXT-only | TXT records, create/delete | ACME/Let's Encrypt |
| IP-restricted | Limited CIDR | 403 from other IPs |
| Expiring | Short TTL | Works until expired |
| Expired | Past expiry | 401 Unauthorized |
| Revoked | is_active=0 | 401 Unauthorized |

### API Test Matrix (10+ test cases per token)
| Scenario | Expected Status | Validation |
|----------|-----------------|------------|
| Authorized operation | 200 | Success response |
| Unauthorized operation | 403 | Permission denied |
| Wrong realm | 403 | Realm mismatch |
| Invalid token | 401 | Bad credentials |
| Expired token | 401 | Token expired |
| Revoked token | 401 | Token revoked |
| IP not in range | 403 | IP blocked |

## Problem Statement

### Current Architecture (Fragmented)

```
Phase 5 (Tests):
├── test_admin_ui.py          → Independent tests, skip if data missing
├── test_email_notifications.py → 8 tests SKIPPED (no pending accounts)
├── test_registration_e2e.py  → Skip if email not configured
├── test_security.py          → Skip if headers not set
└── ... 30+ independent files

Phase 6 (Screenshots):
└── capture_ui_screenshots.py → Runs AFTER tests, shows only current state
```

**Result:** 60+ `pytest.skip()` calls because tests don't create their data.

### Target Architecture (Journey-Based)

```
Phase 5 (Integrated Journeys):
├── Journey 1: Fresh Deployment
│   ├── Screenshot: Login page (clean state)
│   ├── Action: Login as admin (must change password)
│   ├── Screenshot: Password change page
│   ├── Action: Change password
│   ├── Screenshot: Dashboard (empty state)
│   └── Validation: Dashboard stats = 0
│
├── Journey 2: Account Lifecycle
│   ├── Action: Register new account
│   ├── Screenshot: Registration form
│   ├── Action: Verify email
│   ├── Screenshot: Pending accounts (1 pending)
│   ├── Action: Admin approves account
│   ├── Screenshot: Approval email content
│   ├── Validation: Email sent to correct recipient
│   └── Screenshot: Accounts list (1 approved)
│
├── Journey 3: Realm & Token Lifecycle
│   ├── Action: Account creates realm
│   ├── Screenshot: Realm pending
│   ├── Action: Admin approves realm
│   ├── Screenshot: Realm active
│   ├── Action: Account creates token
│   ├── Screenshot: Token created (show token)
│   ├── Action: Test API with token
│   ├── Screenshot: Audit log (API call recorded)
│   └── Validation: API response correct
│
└── Journey 4: Error States & Edge Cases
    ├── Action: Invalid login attempt
    ├── Screenshot: Login error
    ├── Action: Expired token API call
    ├── Screenshot: 401 response
    ├── Action: Unauthorized realm access
    ├── Screenshot: 403 response
    └── Validation: All error codes correct
```

## Design Decisions

### CRITICAL Decision 1: Sequential Journey Execution

**Decision:** Journeys execute in strict order, each building on prior state.

**Rationale:**
- Journey 2 needs a fresh database (from Journey 1)
- Journey 3 needs an approved account (from Journey 2)
- Journey 4 needs tokens (from Journey 3)

**Implementation:**
```python
# ui_tests/tests/test_journey_master.py
import pytest

class TestSystemJourneys:
    """Master test class executing all journeys in order."""
    
    @pytest.fixture(scope="class", autouse=True)
    def journey_state(self):
        """Shared state across all journey tests."""
        return {
            "admin_password": None,
            "test_account": None,
            "test_realm": None,
            "test_token": None,
        }
    
    # Journey 1: Fresh Deployment
    async def test_J1_01_fresh_login_page(self, browser, capture):
        """Fresh system shows login page."""
        await browser.goto(settings.url("/admin/login"))
        await capture("J1-01-fresh-login")
        assert await browser.locator("h1").text_content() == "Admin Login"
    
    async def test_J1_02_admin_password_change(self, browser, journey_state, capture):
        """First login requires password change."""
        await browser.fill("#username", "admin")
        await browser.fill("#password", "admin")
        await browser.click("button[type='submit']")
        await capture("J1-02-password-change-required")
        
        # Change password
        new_password = generate_secure_password()
        await browser.fill("#current_password", "admin")
        await browser.fill("#new_password", new_password)
        await browser.fill("#confirm_password", new_password)
        await browser.click("button[type='submit']")
        
        journey_state["admin_password"] = new_password
        await capture("J1-03-dashboard-empty")
```

### CRITICAL Decision 2: Integrated Screenshot Capture

**Decision:** Screenshots are captured DURING tests, not after.

**Rationale:**
- Each screenshot documents a specific state transition
- Screenshots serve as test documentation AND visual regression baselines
- Failed screenshots indicate failed state transitions

**Implementation:**
```python
# ui_tests/conftest.py
@pytest.fixture
async def capture(browser, request):
    """Capture screenshot with test context."""
    screenshot_dir = Path(os.environ.get("SCREENSHOT_DIR", "screenshots"))
    
    async def _capture(name: str, validate_ux: bool = True):
        filename = f"{request.node.name}_{name}.png"
        filepath = screenshot_dir / filename
        
        # Capture screenshot
        await browser.screenshot(path=str(filepath))
        
        # Optional UX validation
        if validate_ux:
            issues = await validate_ux_compliance(browser, name)
            if issues:
                pytest.fail(f"UX issues on {name}: {issues}")
        
        return filepath
    
    return _capture
```

### CRITICAL Decision 3: Data Creation Over Data Assumption

**Decision:** Tests CREATE data they need, never skip due to missing data.

**Anti-pattern (current):**
```python
async def test_account_approved_email(self, admin_session, mailpit):
    # Check if there are any pending accounts
    page_text = await browser.text('body')
    if 'no pending' in page_text.lower():
        pytest.skip("No pending accounts to approve")  # ❌ WRONG
```

**Correct pattern:**
```python
async def test_J2_account_approval(self, browser, journey_state, mailpit, capture):
    # Create the pending account we need
    account = await create_pending_account(browser)  # ✅ CREATE IT
    await capture("J2-01-pending-account-created")
    
    # Now approve it
    await admin_approve_account(browser, account.id)
    await capture("J2-02-account-approved")
    
    # Verify email
    msg = mailpit.wait_for_message(predicate=lambda m: "approved" in m.subject)
    assert msg is not None, "Approval email should be sent"
    await capture("J2-03-approval-email")
    
    journey_state["test_account"] = account
```

### CRITICAL Decision 4: API + UI in Same Journey

**Decision:** Journeys mix UI and API actions to test the full stack.

**Rationale:**
- UI creates data, API verifies it works
- API creates data, UI shows it correctly
- Both paths tested in realistic workflow

**Implementation:**
```python
async def test_J3_token_lifecycle(self, browser, journey_state, capture):
    """Token creation (UI) and usage (API) in single journey."""
    # UI: Create token
    await browser.goto(settings.url("/account/tokens/new"))
    await browser.fill("#name", "Test Token")
    await browser.click("button[type='submit']")
    await capture("J3-01-token-created")
    
    # Extract token from UI
    token_value = await browser.locator(".token-value").text_content()
    
    # API: Use token
    async with httpx.AsyncClient() as client:
        response = await client.get(
            settings.url("/api/dns/records"),
            headers={"Authorization": f"Bearer {token_value}"}
        )
    
    assert response.status_code == 200, "Token should work immediately"
    await capture("J3-02-api-success")
    
    journey_state["test_token"] = token_value
```

### CRITICAL Decision 5: Error State Documentation

**Decision:** Each error state gets its own screenshot and validation.

**Rationale:**
- Error states are important documentation
- Error handling needs explicit testing
- Screenshots of errors help debugging

**Implementation:**
```python
class TestJ4ErrorStates:
    """Journey 4: Document all error states."""
    
    async def test_J4_01_invalid_login(self, browser, capture):
        """Invalid credentials show error."""
        await browser.goto(settings.url("/admin/login"))
        await browser.fill("#username", "admin")
        await browser.fill("#password", "wrong-password")
        await browser.click("button[type='submit']")
        
        await capture("J4-01-invalid-login-error")
        
        error = await browser.locator(".alert-danger").text_content()
        assert "invalid" in error.lower() or "incorrect" in error.lower()
    
    async def test_J4_02_expired_token(self, browser, capture, journey_state):
        """Expired token returns 401."""
        # Revoke the token first
        await revoke_token(browser, journey_state["test_token"])
        await capture("J4-02-token-revoked")
        
        # Try to use it
        async with httpx.AsyncClient() as client:
            response = await client.get(
                settings.url("/api/dns/records"),
                headers={"Authorization": f"Bearer {journey_state['test_token']}"}
            )
        
        assert response.status_code == 401
        await capture("J4-03-expired-token-401")
    
    async def test_J4_03_unauthorized_realm(self, browser, capture):
        """Access to unauthorized domain returns 403."""
        # Create token with realm for example.com
        token = await create_token_for_realm(browser, "example.com")
        
        # Try to access different domain
        async with httpx.AsyncClient() as client:
            response = await client.get(
                settings.url("/api/dns/records?domain=other.com"),
                headers={"Authorization": f"Bearer {token}"}
            )
        
        assert response.status_code == 403
        await capture("J4-04-realm-mismatch-403")
```

## File Structure

```
ui_tests/
├── tests/
│   ├── test_journey_master.py      # Main sequential journey tests
│   ├── test_journey_helpers.py     # Shared helper functions
│   │
│   ├── journeys/                   # Journey-specific modules
│   │   ├── __init__.py
│   │   ├── j1_fresh_deployment.py  # Journey 1: Fresh state
│   │   ├── j2_account_lifecycle.py # Journey 2: Account flows
│   │   ├── j3_realm_token.py       # Journey 3: Realm & Token
│   │   └── j4_error_states.py      # Journey 4: Error documentation
│   │
│   ├── # Existing files (keep for targeted testing)
│   ├── test_admin_ui.py            # Quick admin UI validation
│   ├── test_security.py            # Security headers check
│   └── ...
│
├── conftest.py                     # Updated with journey fixtures
├── browser.py                      # Browser automation
├── mailpit.py                      # Email testing client
└── config.py                       # Test configuration
```

## deploy.sh Integration

### Updated Phase 5

```bash
phase_tests() {
    log_phase "5" "Integrated Journey Tests"
    
    # First: Run journey tests (create data + screenshots)
    log_step "Running integrated journeys..."
    if run_in_playwright pytest ui_tests/tests/test_journey_master.py -v --timeout=300; then
        log_success "Journey tests passed"
    else
        log_warning "Journey tests failed"
    fi
    
    # Second: Run quick validation tests (no data dependency)
    log_step "Running validation tests..."
    local validation_tests=(
        "ui_tests/tests/test_security.py"
        "ui_tests/tests/test_accessibility.py"
        "ui_tests/tests/test_performance.py"
    )
    
    for test in "${validation_tests[@]}"; do
        if [[ -f "${REPO_ROOT}/${test}" ]]; then
            run_in_playwright pytest "$test" -v --timeout=120 || true
        fi
    done
}
```

### Phase 6: Now Optional

```bash
phase_screenshots() {
    log_phase "6" "Additional Screenshots (Optional)"
    
    # Journey tests already captured most screenshots
    # This phase only captures any additional states needed
    
    log_step "Screenshots already captured during journey tests"
    
    local count
    count=$(find "$SCREENSHOT_DIR" -name "*.png" -type f 2>/dev/null | wc -l)
    log_success "Total screenshots: $count"
}
```

## Migration Plan

### Phase 1: Create Journey Framework (Week 1)
1. Create `ui_tests/tests/journeys/` directory
2. Create `test_journey_master.py` with Journey 1
3. Add `capture` fixture to conftest.py
4. Update deploy.sh to run journey tests first

### Phase 2: Migrate Account Tests (Week 2)
1. Implement Journey 2 (Account Lifecycle)
2. Remove skips from `test_email_notifications.py`
3. Deprecate independent account tests

### Phase 3: Migrate Realm/Token Tests (Week 3)
1. Implement Journey 3 (Realm & Token)
2. Migrate API proxy tests
3. Remove skips from token tests

### Phase 4: Complete Error Coverage (Week 4)
1. Implement Journey 4 (Error States)
2. Document all HTTP error codes
3. Create comprehensive screenshot catalog

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| `pytest.skip()` calls | 60+ | 0 |
| Screenshots per run | ~20 | ~50 |
| Test coverage of states | ~40% | 90%+ |
| API + UI integration | Separate | Unified |
| Data creation in tests | Never | Always |

## Appendix: Full Journey Catalog

### Journey 1: Fresh Deployment
| Step | Action | Screenshot | Validation |
|------|--------|------------|------------|
| 1.1 | Load login page | J1-01-fresh-login | H1 = "Admin Login" |
| 1.2 | Login with default | J1-02-password-change | Must change shown |
| 1.3 | Change password | J1-03-dashboard-empty | Dashboard loads |
| 1.4 | View empty stats | J1-04-stats-zero | All counts = 0 |

### Journey 2: Account Lifecycle
| Step | Action | Screenshot | Validation |
|------|--------|------------|------------|
| 2.1 | Register new user | J2-01-registration-form | Form shown |
| 2.2 | Submit registration | J2-02-verification-sent | Success message |
| 2.3 | Check Mailpit | J2-03-verification-email | Email received |
| 2.4 | Enter code | J2-04-verified | Verification success |
| 2.5 | Admin: pending list | J2-05-pending-accounts | 1 pending shown |
| 2.6 | Approve account | J2-06-account-approved | Success message |
| 2.7 | Check approval email | J2-07-approval-email | Email sent |
| 2.8 | User logs in | J2-08-user-dashboard | Dashboard loads |

### Journey 3: Realm & Token Lifecycle
| Step | Action | Screenshot | Validation |
|------|--------|------------|------------|
| 3.1 | Request realm | J3-01-realm-request | Form shown |
| 3.2 | Submit request | J3-02-realm-pending | Pending status |
| 3.3 | Admin: pending realms | J3-03-admin-pending | 1 pending shown |
| 3.4 | Approve realm | J3-04-realm-approved | Success message |
| 3.5 | Create token | J3-05-token-form | Form shown |
| 3.6 | Token created | J3-06-token-value | Token displayed |
| 3.7 | API: list records | J3-07-api-success | 200 response |
| 3.8 | Audit log shows call | J3-08-audit-log | Entry present |

### Journey 4: Error States
| Step | Action | Screenshot | Validation |
|------|--------|------------|------------|
| 4.1 | Invalid login | J4-01-invalid-login | Error shown |
| 4.2 | Wrong password 3x | J4-02-rate-limited | Rate limit msg |
| 4.3 | Revoke token | J4-03-token-revoked | Success message |
| 4.4 | Use revoked token | J4-04-api-401 | 401 response |
| 4.5 | Access wrong realm | J4-05-api-403 | 403 response |
| 4.6 | Invalid API request | J4-06-api-400 | 400 response |
| 4.7 | 404 page | J4-07-not-found | 404 page shown |
