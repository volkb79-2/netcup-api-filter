# Testing Strategy: Unified Journey-Based Testing

## Executive Summary

**Current Problems:**
- Tests and screenshot capture are separate workflows
- Detail pages have no data when screenshotted
- API activity (calls, errors, denials) not visible in UI tests
- No systematic auth enforcement testing
- deploy.sh runs fragmented test phases that don't build on each other

**Solution:**
**Tests should populate the system while documenting ALL states via screenshots.**

This applies to:
- ✅ **ALL UI pages** (not just detail pages)
- ✅ **API interactions** visible in audit logs
- ✅ **Authentication enforcement** on ALL non-public routes
- ✅ **Error states**, denied requests, success states
- ✅ **Empty states** → populated states → edge case states

---

## CRITICAL: Credentials Management

**NEVER hardcode passwords** like `TestAdmin123!` in code, tests, or documentation.

All credentials MUST come from:
1. **`deployment_state_{target}.json`** - Source of truth after password change
2. **Environment variable** `UI_ADMIN_PASSWORD` - Explicit override only
3. **Fresh deployment default** - `admin` (from `.env.defaults`)

### Password Generation Flow

```python
# In workflows.py - ensure_admin_dashboard()
from netcup_api_filter.utils import generate_token

# Generate cryptographically secure random password
base_token = generate_token()  # 63-65 char alphanumeric
new_password = base_token[:60] + "@#$%"  # Add special chars

# Persist to state file for subsequent tests
_update_deployment_state(admin_password=new_password)
```

### State File Management

```json
{
  "target": "local",
  "admin": {
    "username": "admin",
    "password": "HyqlHUvwaHpkfCN4UbS4mEUwIM5hVPIOMItJS4SjeRfR5FERSPAV9Jw6RBBa@#$%",
    "password_changed_at": "2025-12-04T22:25:30.581280+00:00"
  },
  "last_updated_at": "2025-12-04T22:25:30.581310+00:00",
  "updated_by": "ui_test"
}
```

---

## Phase 0: Authentication Enforcement Testing

**CRITICAL:** Before any other tests, verify auth enforcement on ALL routes.

### Route Classification

Routes must be classified as:
1. **Public** - No auth required (login, register, forgot-password, health)
2. **Admin** - Requires admin session
3. **Account** - Requires account session  
4. **API** - Requires Bearer token

### Dynamic Route Discovery

```python
# Get all routes from Flask app
def get_all_routes():
    """Dynamically discover all application routes."""
    from flask import current_app
    routes = []
    for rule in current_app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'path': rule.rule,
            'methods': list(rule.methods - {'HEAD', 'OPTIONS'}),
            'blueprint': rule.endpoint.split('.')[0] if '.' in rule.endpoint else 'app'
        })
    return routes

# Classify routes
PUBLIC_ROUTES = {
    '/admin/login', '/account/login', '/account/register',
    '/account/forgot-password', '/account/reset-password/<token>',
    '/health', '/', '/component-demo', '/component-demo-bs5'
}

ADMIN_ROUTES_PREFIX = '/admin/'
ACCOUNT_ROUTES_PREFIX = '/account/'
API_ROUTES_PREFIX = ['/api/', '/dns/', '/filter-proxy/']
```

### Auth Enforcement Test

```python
@pytest.mark.asyncio
class TestAuthEnforcement:
    """Phase 0: Verify ALL non-public routes require authentication."""
    
    async def test_unauthenticated_admin_routes_redirect(self, browser, all_admin_routes):
        """Every admin route must redirect to /admin/login when unauthenticated."""
        for route in all_admin_routes:
            if route in PUBLIC_ROUTES:
                continue
            
            await browser.goto(settings.url(route))
            await screenshot(f"auth-{route.replace('/', '-')}-unauthenticated.png")
            
            # Must redirect to login
            assert '/admin/login' in browser.current_url, \
                f"Route {route} accessible without auth! Should redirect to login."
    
    async def test_api_routes_require_bearer_token(self, api_client, all_api_routes):
        """Every API route must return 401 without valid Bearer token."""
        for route in all_api_routes:
            response = await api_client.get(route, headers={})  # No auth
            assert response.status_code == 401, \
                f"API route {route} accessible without token!"
```

---

## Email Verification via Mailpit

**CRITICAL: Test that emails are actually sent and contain valid links.**

### Mailpit Integration

When running locally, the deployment is configured to send emails to Mailpit:
- **SMTP**: `mailpit:1025` (configured in `seed_mock_email_config()`)
- **API**: `http://mailpit:8025/api/v1` (for retrieving sent emails)
- **Web UI**: `http://localhost:8025` (for debugging)

### Email-Aware Test Flows

```python
from ui_tests.mailpit_client import MailpitClient

class TestJourneyEmailVerification:
    """Test email flows with actual email verification via Mailpit."""
    
    @pytest.fixture
    def mailpit(self):
        """Provide Mailpit client, cleared for each test."""
        client = MailpitClient()
        client.clear()  # Start fresh
        yield client
        client.close()
    
    async def test_password_reset_email_flow(self, browser, admin_session, mailpit):
        """Admin sends password reset → email arrives → user follows link."""
        # === 1. Trigger password reset from admin UI ===
        await browser.goto('/admin/accounts/2')
        await browser.click('[data-bs-target="#resetPasswordModal"]')
        await browser.select('#expiry_hours', '24')
        await browser.click('.modal button[type="submit"]')
        await screenshot('email-01-password-reset-sent.png')
        
        # === 2. Verify email arrived in Mailpit ===
        msg = mailpit.wait_for_message(
            predicate=lambda m: 'reset' in m.subject.lower(),
            timeout=10.0
        )
        assert msg is not None, "Password reset email not received!"
        await screenshot('email-02-mailpit-received.png')  # Optional: screenshot Mailpit UI
        
        # === 3. Extract reset link from email ===
        import re
        full_msg = mailpit.get_message(msg.id)
        link_match = re.search(r'https?://[^\s]+/account/reset-password/[a-zA-Z0-9]+', full_msg.text)
        assert link_match, "No reset link found in email body!"
        reset_link = link_match.group()
        
        # === 4. Follow the reset link ===
        await browser.goto(reset_link)
        await screenshot('email-03-reset-password-page.png')
        
        # === 5. Set new password ===
        await browser.fill('#password', 'NewSecurePass123!')
        await browser.fill('#password_confirm', 'NewSecurePass123!')
        await browser.click('button[type="submit"]')
        await screenshot('email-04-password-changed.png')
        
        # === 6. Verify can login with new password ===
        await browser.goto('/account/login')
        await browser.fill('#username', 'testuser')
        await browser.fill('#password', 'NewSecurePass123!')
        await browser.click('button[type="submit"]')
        assert '/account/dashboard' in browser.current_url
    
    async def test_registration_verification_email(self, browser, mailpit):
        """New user registers → receives verification code → completes registration."""
        # === 1. Submit registration form ===
        await browser.goto('/account/register')
        await browser.fill('#username', 'newuser123')
        await browser.fill('#email', 'newuser@example.com')
        await browser.fill('#password', 'SecurePass123!')
        await browser.fill('#password_confirm', 'SecurePass123!')
        await browser.click('button[type="submit"]')
        await screenshot('email-10-registration-submitted.png')
        
        # === 2. Verify email with verification code arrives ===
        msg = mailpit.wait_for_message(
            predicate=lambda m: 'verification' in m.subject.lower() or 'verify' in m.subject.lower(),
            timeout=10.0
        )
        assert msg is not None, "Verification email not received!"
        
        # === 3. Extract verification code from email ===
        full_msg = mailpit.get_message(msg.id)
        code_match = re.search(r'\b[A-Z0-9]{6}\b', full_msg.text)  # 6-char code
        assert code_match, "No verification code found in email!"
        verification_code = code_match.group()
        
        # === 4. Enter verification code ===
        await browser.fill('#verification_code', verification_code)
        await browser.click('button[type="submit"]')
        await screenshot('email-11-verification-complete.png')
        
        # === 5. Verify pending approval message ===
        assert 'pending' in (await browser.text('body')).lower()
    
    async def test_invite_link_email(self, browser, admin_session, mailpit):
        """Admin sends invite → user receives link → creates account."""
        # === 1. Admin creates invite ===
        await browser.goto('/admin/accounts')
        await browser.click('[href="/admin/accounts/invite"]')
        await browser.fill('#email', 'invited@example.com')
        await browser.click('button[type="submit"]')
        await screenshot('email-20-invite-sent.png')
        
        # === 2. Verify invite email arrives ===
        msg = mailpit.wait_for_message(
            predicate=lambda m: 'invite' in m.subject.lower() or 'invitation' in m.subject.lower(),
            timeout=10.0
        )
        assert msg is not None, "Invite email not received!"
        
        # === 3. Extract invite link ===
        full_msg = mailpit.get_message(msg.id)
        link_match = re.search(r'https?://[^\s]+/account/register\?invite=[a-zA-Z0-9]+', full_msg.text)
        invite_link = link_match.group()
        
        # === 4. Follow invite link and complete registration ===
        await browser.goto(invite_link)
        await screenshot('email-21-invite-registration-form.png')
        # ... complete registration
```

### Email Event Coverage Matrix

| Event | Email Type | Test Journey | Verification |
|-------|-----------|--------------|--------------|
| Admin resets password | Password Reset | test_password_reset_email_flow | Extract link, follow, set new password |
| User registers | Verification Code | test_registration_verification_email | Extract code, enter, verify pending |
| Admin sends invite | Invitation Link | test_invite_link_email | Extract link, complete registration |
| Realm approved | Notification | test_realm_approval_notification | Verify email arrives with realm details |
| Token revoked | Security Alert | test_token_revoked_notification | Verify email warns about revocation |
| Login from new IP | Security Alert | test_new_ip_login_notification | Verify email with IP and location |

### Mailpit Fixture in conftest.py

```python
# ui_tests/conftest.py

@pytest.fixture
def mailpit():
    """Mailpit client for email verification tests.
    
    Clears mailbox before each test to ensure isolation.
    Requires Mailpit container running (tooling/mock-services/start.sh).
    """
    from ui_tests.mailpit_client import MailpitClient
    
    client = MailpitClient(
        base_url=os.environ.get('MAILPIT_API_URL', 'http://mailpit:8025')
    )
    
    try:
        # Clear mailbox for test isolation
        client.clear()
        yield client
    finally:
        client.close()

@pytest.fixture
def email_config_for_mailpit():
    """Ensure Flask app is configured to send to Mailpit."""
    # This is handled by build_deployment.py --local (seed_mock_email=True)
    # But tests can verify/override if needed
    return {
        'smtp_host': 'mailpit',
        'smtp_port': 1025,
        'use_tls': False,
        'from_email': 'naf@example.com',
    }
```

---

## Replacing Current Workflow

### Current deploy.sh (Fragmented):
```
Phase 4: Auth test (single test)
Phase 5: Run 40+ test files (no screenshots)
Phase 6: Capture screenshots (no data)
```

### New Workflow (Unified):
```
Phase 4: Auth Enforcement (test ALL routes require auth)
Phase 5: Journey Tests (create data + verify + screenshot)
         - Each journey populates data progressively
         - Screenshots capture empty → populated → error states
         - API calls generate audit log entries
         - UI shows API activity (success, denied, errors)
Phase 6: Visual Validation (compare against baselines)
```

---

## Journey Structure

### Test File Organization

```
ui_tests/journeys/
├── test_00_auth_enforcement.py    # Phase 0: All routes require auth
├── test_01_admin_bootstrap.py     # Login, change password, empty state screenshots
├── test_02_account_lifecycle.py   # Create 4 accounts in different states
├── test_03_realm_management.py    # Add realms, approve/reject, tokens
├── test_04_token_generation.py    # Create tokens with various permissions
├── test_05_api_usage.py           # API calls, audit log verification
├── test_06_system_config.py       # Netcup API, Email, System info
├── test_07_error_scenarios.py     # 404s, validation, edge cases
└── test_08_email_verification.py  # Email flows via Mailpit
```

Each journey:
1. **Progresses from previous state** (accounts exist after test_02)
2. **Captures screenshots at every significant state**
3. **Validates both UI and API responses**
4. **Documents error states and edge cases**

---

## Journey 2: Account Lifecycle (HOLISTIC EXAMPLE)

**This journey demonstrates the pattern for all journeys:**

### Creating 4 Accounts in Different States

By the end of Journey 02, the system has 4 accounts, each in a different state:

| Account | Creation Method | Final State | Purpose |
|---------|-----------------|-------------|---------|
| `client1_pending` | Self-registration | Pending (not approved) | Test pending state |
| `client2_approved` | Self-registration + admin approval | Active | Test approval flow |
| `client3_invited` | Admin invite | Invite not accepted | Test abandoned invite |
| `client4_complete` | Admin invite + password set | Active | Test complete flow |

### Intermediate Verification Steps

For each account, the journey verifies:

1. **Email sent** - Mailpit receives verification/invite email
2. **Email content** - Contains valid link/code
3. **Link works** - Following link leads to correct page
4. **Wrong link rejected** - Fake/expired links show error
5. **Admin visibility** - Account appears in correct list (pending/active)
6. **Final state** - Account list shows correct status

### Code Pattern

```python
class TestSelfRegistrationFlow:
    async def test_02_register_client1_pending(self, browser, mailpit_client, account_data):
        # 1. Navigate to registration
        await browser.goto(settings.url('/account/register'))
        
        # 2. Fill form with generated data (NOT hardcoded)
        client = account_data["client1_pending"]
        await browser.fill('#username', client["username"])
        await browser.fill('#email', client["email"])
        await browser.fill('#password', client["password"])
        
        # 3. Screenshot before submit
        await ss.capture('client1-registration-filled', 'Registration form filled')
        
        # 4. Submit
        await browser.click('button[type="submit"]')
        
        # 5. Verify email in Mailpit
        msg = mailpit_client.wait_for_message(
            predicate=lambda m: client["email"] in [a.address for a in m.to],
            timeout=10.0
        )
        assert msg is not None, f"No email to {client['email']}"
        
        # 6. Screenshot after submit
        await ss.capture('client1-registration-submitted', 'After registration')
        
        # 7. Verify pending state
        body = await browser.text('body')
        assert 'pending' in body.lower() or 'verify' in body.lower()

class TestAccountErrorHandling:
    async def test_14_duplicate_username_rejected(self, browser, account_data):
        # Try to register with same username as client1
        client = account_data["client1_pending"]
        await browser.fill('#username', client["username"])  # Already exists!
        await browser.click('button[type="submit"]')
        
        # Verify rejection
        body = await browser.text('body')
        assert any(word in body.lower() for word in ['already', 'exists', 'taken'])
```

### Final Admin View Screenshot

After all 4 accounts are created, capture the admin accounts list:

```python
async def test_11_admin_account_list_shows_all_states(self, admin_session):
    await browser.goto('/admin/accounts')
    await ss.capture('admin-accounts-all-states', 'Accounts in various states')
    
    # Should show:
    # - client1: Pending
    # - client2: Active (approved)
    # - client3: Invite sent (not accepted)
    # - client4: Active (invite completed)
```

---

## Journey 0: Auth Enforcement (CRITICAL - Runs First)

```python
class TestJourney00AuthEnforcement:
    """
    PHASE 0: Verify authentication is enforced on ALL routes.
    
    This runs BEFORE any other tests to ensure security.
    """
    
    async def test_admin_routes_require_login(self, browser):
        """All /admin/* routes (except login) redirect to login."""
        admin_routes = [
            '/admin/',
            '/admin/accounts',
            '/admin/accounts/1',
            '/admin/accounts/new',
            '/admin/realms',
            '/admin/realms/1',
            '/admin/audit',
            '/admin/security',
            '/admin/config/netcup',
            '/admin/config/email',
            '/admin/system',
        ]
        
        for route in admin_routes:
            await browser.goto(settings.url(route))
            await screenshot(f"00-auth-{route.replace('/', '_')}-noauth.png")
            
            # MUST redirect to login
            assert '/admin/login' in browser.current_url, \
                f"SECURITY: {route} accessible without login!"
    
    async def test_account_routes_require_login(self, browser):
        """All /account/* routes (except public) redirect to login."""
        protected_routes = [
            '/account/dashboard',
            '/account/realms',
            '/account/tokens',
            '/account/settings',
        ]
        
        for route in protected_routes:
            await browser.goto(settings.url(route))
            assert '/account/login' in browser.current_url
    
    async def test_api_routes_require_token(self, api_client):
        """All API routes return 401 without Bearer token."""
        api_routes = [
            '/api/dns/example.com/records',
            '/api/ddns/example.com/home',
            '/filter-proxy/api/dns/example.com/records',
        ]
        
        for route in api_routes:
            response = await api_client.get(route)
            assert response.status_code == 401
```

---

## Journey 1: Admin Bootstrap

```python
class TestJourney01AdminBootstrap:
    """Bootstrap admin: login, change password, capture empty states."""
    
    async def test_admin_login_flow(self, browser):
        # === PUBLIC: Login page ===
        await browser.goto(settings.url('/admin/login'))
        await screenshot('01-admin-login.png')
        
        # Login with default credentials
        await browser.fill('#username', 'admin')
        await browser.fill('#password', DEFAULT_PASSWORD)
        await browser.click('button[type="submit"]')
        
        # === Change password (fresh DB) ===
        await screenshot('01-admin-change-password-required.png')
        # ... change password flow
        
        # === Empty Dashboard ===
        await browser.goto(settings.url('/admin/'))
        await screenshot('01-admin-dashboard-empty.png')
    
    async def test_empty_lists(self, browser, admin_session):
        """Capture all list pages in empty state."""
        empty_pages = [
            ('/admin/accounts', '01-accounts-list-empty.png'),
            ('/admin/accounts/pending', '01-accounts-pending-empty.png'),
            ('/admin/realms', '01-realms-list-empty.png'),
            ('/admin/realms/pending', '01-realms-pending-empty.png'),
            ('/admin/audit', '01-audit-logs-empty.png'),
        ]
        
        for route, name in empty_pages:
            await browser.goto(settings.url(route))
            await screenshot(name)
```

---

## Journey 2: Account Lifecycle

```python
class TestJourney02AccountLifecycle:
    """Full account lifecycle: create → pending → approve → detail."""
    
    async def test_create_account_via_ui(self, browser, admin_session):
        """Admin creates account through UI."""
        await browser.goto(settings.url('/admin/accounts/new'))
        await screenshot('02-account-create-form-empty.png')
        
        await browser.fill('#username', 'testuser')
        await browser.fill('#email', 'test@example.com')
        await browser.fill('#realm_value', 'home.example.com')
        await screenshot('02-account-create-form-filled.png')
        
        await browser.click('button[type="submit"]')
        await screenshot('02-account-created-success.png')
    
    async def test_account_detail_page(self, browser, admin_session):
        """Navigate to account detail with realms and tokens."""
        await browser.goto(settings.url('/admin/accounts'))
        await screenshot('02-accounts-list-with-data.png')
        
        await browser.click('a[href*="/admin/accounts/"]')
        await screenshot('02-account-detail-with-realm.png')
    
    async def test_password_reset_flow(self, browser, admin_session):
        """Admin sends password reset link."""
        await browser.goto(settings.url('/admin/accounts/2'))
        
        await browser.click('[data-bs-target="#resetPasswordModal"]')
        await asyncio.sleep(0.3)
        await screenshot('02-password-reset-modal.png')
        
        await browser.click('.modal button[type="submit"]')
        await screenshot('02-password-reset-sent.png')
```

---

## Journey 4: API Usage & Audit Trail

**CRITICAL: Tests API calls and verifies UI shows all activity.**

```python
class TestJourney04ApiUsage:
    """Make API calls (success/denied/error) and verify UI shows them."""
    
    async def test_successful_api_call(self, api_client, token):
        """Make successful API call, verify in audit log."""
        response = await api_client.get(
            '/api/dns/example.com/records',
            headers={'Authorization': f'Bearer {token}'}
        )
        assert response.status_code == 200
    
    async def test_denied_api_call_wrong_domain(self, api_client, token):
        """Token for example.com can't access other.com."""
        response = await api_client.get(
            '/api/dns/other.com/records',
            headers={'Authorization': f'Bearer {token}'}
        )
        assert response.status_code == 403
    
    async def test_denied_api_call_wrong_operation(self, api_client, readonly_token):
        """Read-only token can't modify."""
        response = await api_client.post(
            '/api/dns/example.com/records',
            headers={'Authorization': f'Bearer {readonly_token}'},
            json={'type': 'A', 'hostname': 'test', 'destination': '1.2.3.4'}
        )
        assert response.status_code == 403
    
    async def test_audit_log_shows_all_activity(self, browser, admin_session):
        """Audit log shows success, denied, and error entries."""
        await browser.goto(settings.url('/admin/audit'))
        await screenshot('04-audit-logs-with-api-activity.png')
        
        body = await browser.text('body')
        # Should show different status types
        assert 'success' in body.lower() or 'allowed' in body.lower()
        assert 'denied' in body.lower() or 'forbidden' in body.lower()
    
    async def test_audit_log_filtering(self, browser, admin_session):
        """Filter audit logs by status."""
        await browser.goto(settings.url('/admin/audit?status=denied'))
        await screenshot('04-audit-logs-filtered-denied.png')
```

---

## Journey 5: Error Scenarios

```python
class TestJourney05ErrorScenarios:
    """Capture ALL error states for documentation."""
    
    async def test_404_page(self, browser):
        """404 error page styling."""
        await browser.goto(settings.url('/nonexistent-page'))
        await screenshot('05-error-404.png')
    
    async def test_invalid_login(self, browser):
        """Login failure message."""
        await browser.goto(settings.url('/admin/login'))
        await browser.fill('#username', 'admin')
        await browser.fill('#password', 'wrongpassword')
        await browser.click('button[type="submit"]')
        await screenshot('05-login-failed.png')
    
    async def test_expired_token(self, api_client, expired_token):
        """Expired token response."""
        response = await api_client.get(
            '/api/dns/example.com/records',
            headers={'Authorization': f'Bearer {expired_token}'}
        )
        assert response.status_code == 401
    
    async def test_rate_limited(self, api_client, token):
        """Rate limit response and audit log entry."""
        # Make many requests quickly
        for _ in range(100):
            await api_client.get(
                '/api/dns/example.com/records',
                headers={'Authorization': f'Bearer {token}'}
            )
        
        # Next should be rate limited
        response = await api_client.get(
            '/api/dns/example.com/records',
            headers={'Authorization': f'Bearer {token}'}
        )
        assert response.status_code == 429
    
    async def test_ip_not_whitelisted(self, api_client, ip_restricted_token):
        """IP whitelist denied."""
        response = await api_client.get(
            '/api/dns/example.com/records',
            headers={
                'Authorization': f'Bearer {ip_restricted_token}',
                'X-Forwarded-For': '1.2.3.4'  # Not in whitelist
            }
        )
        assert response.status_code == 403
```

---

## Journey 6: Security Event Testing (NEW)

**CRITICAL: Test security error handling, attack detection, and security dashboard.**

### Security Error Code Matrix

The system uses granular error codes for security analytics:

| Error Code | Category | Severity | Attribution | Notification |
|------------|----------|----------|-------------|--------------|
| `invalid_format` | Auth | Low | None | No |
| `missing_token` | Auth | Low | None | No |
| `alias_not_found` | Auth | Medium | None | No (rate limit) |
| `token_prefix_not_found` | Auth | High | Account | User |
| `token_hash_mismatch` | Auth | **Critical** | Token | User + Admin |
| `account_disabled` | Auth | Medium | Account | Admin |
| `token_revoked` | Auth | High | Token | User |
| `token_expired` | Auth | Low | Token | No |
| `realm_not_approved` | Auth | Low | Realm | No |
| `ip_denied` | Authz | **Critical** | Token | User + Admin |
| `domain_denied` | Authz | High | Token | User |
| `operation_denied` | Authz | Medium | Token | No |
| `record_type_denied` | Authz | Low | Token | No |

### Token Format Security

Tokens now use `user_alias` instead of `username`:

```
OLD (insecure): naf_<username>_<random64>  ❌ Exposes login credentials
NEW (secure):   naf_<user_alias>_<random64> ✅ 16-char random identifier
```

### Security Journey Tests

```python
class TestJourney06Security:
    """Test security error handling, attack detection, and dashboard."""
    
    async def test_security_dashboard_empty(self, browser, admin_session):
        """Security dashboard shows empty state before any attacks."""
        await browser.goto(settings.url('/admin/security'))
        await screenshot('06-security-dashboard-empty.png')
        
        # Verify page loads correctly
        assert 'Security Dashboard' in await browser.text('h1')
    
    async def test_invalid_token_formats(self, api_client):
        """Test various invalid token formats generate correct error codes."""
        test_cases = [
            # (token, expected_error_code)
            ('', 'missing_token'),
            ('not-a-valid-token', 'invalid_format'),
            ('naf_', 'invalid_format'),
            ('naf_abcd1234efgh5678_short', 'invalid_format'),  # Too short
            ("naf_admin'; DROP TABLE--_xyz", 'invalid_format'),  # SQL injection
        ]
        
        for token, expected_code in test_cases:
            response = await api_client.get(
                '/api/dns/example.com/records',
                headers={'Authorization': f'Bearer {token}'} if token else {}
            )
            assert response.status_code == 401
    
    async def test_alias_not_found(self, api_client):
        """Valid token format but non-existent user_alias."""
        fake_token = 'naf_abcd1234efgh5678_' + 'x' * 64
        response = await api_client.get(
            '/api/dns/example.com/records',
            headers={'Authorization': f'Bearer {fake_token}'}
        )
        assert response.status_code == 401
    
    async def test_token_prefix_not_found(self, api_client, valid_account_alias):
        """Valid alias but wrong token prefix (probing attack)."""
        # Use real account's alias but fake token
        fake_token = f'naf_{valid_account_alias}_wrongpre' + 'x' * 56
        response = await api_client.get(
            '/api/dns/example.com/records',
            headers={'Authorization': f'Bearer {fake_token}'}
        )
        assert response.status_code == 401
    
    async def test_token_hash_mismatch_critical(self, api_client, valid_token_prefix):
        """Correct prefix but wrong body - BRUTE FORCE ATTACK."""
        # Use real token prefix but wrong hash - critical alert
        fake_token = f'naf_validalias_____{valid_token_prefix}' + 'x' * 56
        response = await api_client.get(
            '/api/dns/example.com/records',
            headers={'Authorization': f'Bearer {fake_token}'}
        )
        assert response.status_code == 401
        # This should trigger user notification
    
    async def test_ip_denied_critical(self, api_client, ip_restricted_token):
        """Request from unauthorized IP - potential credential theft."""
        response = await api_client.get(
            '/api/dns/example.com/records',
            headers={
                'Authorization': f'Bearer {ip_restricted_token}',
                'X-Forwarded-For': '1.2.3.4'  # Not in whitelist
            }
        )
        assert response.status_code == 403
    
    async def test_security_dashboard_with_events(self, browser, admin_session):
        """Security dashboard shows events after attack simulation."""
        await browser.goto(settings.url('/admin/security'))
        await screenshot('06-security-dashboard-with-events.png')
        
        # Should show attack events
        body = await browser.text('body')
        assert any(severity in body.lower() for severity in ['critical', 'high'])
    
    async def test_security_api_stats(self, admin_session, api_client):
        """Security stats API endpoint."""
        response = await api_client.get(
            '/admin/api/security/stats?hours=24',
            headers={'Cookie': admin_session}
        )
        assert response.status_code == 200
        data = response.json()
        assert 'total_events' in data
        assert 'by_severity' in data
        assert 'by_error_code' in data
    
    async def test_security_timeline_api(self, admin_session, api_client):
        """Security timeline API for charts."""
        response = await api_client.get(
            '/admin/api/security/timeline?hours=24',
            headers={'Cookie': admin_session}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if data:
            assert 'hour' in data[0]
```

### Attack Pattern Detection

The system detects attack patterns:

```python
ATTACK_PATTERNS = [
    {
        'name': 'brute_force',
        'description': 'Same token prefix, multiple hash mismatches',
        'error_codes': ['token_hash_mismatch'],
        'threshold': 3,
        'window_minutes': 5,
        'severity': 'critical',
    },
    {
        'name': 'credential_stuffing', 
        'description': 'Many non-existent aliases from same IP',
        'error_codes': ['alias_not_found'],
        'threshold': 10,
        'window_minutes': 10,
        'severity': 'high',
    },
    {
        'name': 'scope_probing',
        'description': 'Sequential domain access attempts',
        'error_codes': ['domain_denied'],
        'threshold': 5,
        'window_minutes': 10,
        'severity': 'high',
    },
    {
        'name': 'ip_anomaly',
        'description': 'Token used from new IP location',
        'error_codes': ['ip_denied'],
        'threshold': 1,
        'window_minutes': 60,
        'severity': 'critical',
    },
]
```

---

## Journey 7: Account Security Operations (NEW)

**CRITICAL: Test credential rotation, email changes, and security notifications.**

### Credential Rotation Deep Branching

Test the complete credential rotation flow including edge cases:

```python
class TestJourney07AccountSecurity:
    """Test account security operations - alias rotation and email changes."""
    
    # -------------------------------------------------------------------------
    # Credential Rotation Tests (regenerate-alias)
    # -------------------------------------------------------------------------
    
    async def test_alias_rotation_modal_display(self, browser, admin_session, test_account):
        """Verify credential rotation modal shows correctly."""
        await browser.goto(settings.url(f'/admin/accounts/{test_account.id}'))
        
        # Click the rotate credentials button
        await browser.click('[data-bs-target="#regenerateAliasModal"]')
        await browser.wait_for_selector('#regenerateAliasModal.show')
        await screenshot('07-alias-rotation-modal.png')
        
        # Verify warning text
        modal_text = await browser.text('#regenerateAliasModal')
        assert 'immediately invalidate ALL API tokens' in modal_text
    
    async def test_alias_rotation_invalidates_tokens(
        self, browser, admin_session, test_account, test_token
    ):
        """Rotation should invalidate all existing tokens."""
        # Verify token works before rotation
        response = await api_client.get(
            '/api/dns/example.com/records',
            headers={'Authorization': f'Bearer {test_token}'}
        )
        assert response.status_code in (200, 403)  # Token valid (may lack perms)
        
        # Rotate credentials
        await browser.goto(settings.url(f'/admin/accounts/{test_account.id}'))
        await browser.click('[data-bs-target="#regenerateAliasModal"]')
        await browser.wait_for_selector('#regenerateAliasModal.show')
        await browser.click('#regenerateAliasModal button[type="submit"]')
        await browser.wait_for_load()
        await screenshot('07-alias-rotation-success.png')
        
        # Verify flash message
        flash = await browser.text('.alert')
        assert 'regenerated' in flash.lower()
        assert 'invalidated' in flash.lower()
        
        # Token should now fail
        response = await api_client.get(
            '/api/dns/example.com/records',
            headers={'Authorization': f'Bearer {test_token}'}
        )
        assert response.status_code == 401
    
    async def test_alias_rotation_logs_activity(self, browser, admin_session, test_account):
        """Rotation should create audit log entry."""
        # Rotate credentials
        await browser.goto(settings.url(f'/admin/accounts/{test_account.id}'))
        await browser.click('[data-bs-target="#regenerateAliasModal"]')
        await browser.click('#regenerateAliasModal button[type="submit"]')
        await browser.wait_for_load()
        
        # Check audit log
        await browser.goto(settings.url(f'/admin/audit?account={test_account.id}'))
        await screenshot('07-alias-rotation-audit-log.png')
        
        log_text = await browser.text('body')
        assert 'alias_regenerated' in log_text
    
    async def test_alias_rotation_notification_sent(self, test_account, mailpit_client):
        """User should receive email notification about credential rotation."""
        # Check Mailpit for notification
        emails = await mailpit_client.search(
            to=test_account.email,
            subject='Credentials Rotated'
        )
        assert len(emails) > 0
        
        email = emails[0]
        assert 'All API credentials have been rotated' in email.body
        assert 'tokens invalidated' in email.body.lower()
    
    # -------------------------------------------------------------------------
    # Email Change Tests
    # -------------------------------------------------------------------------
    
    async def test_email_change_modal_display(self, browser, admin_session, test_account):
        """Verify email change modal shows correctly."""
        await browser.goto(settings.url(f'/admin/accounts/{test_account.id}'))
        
        await browser.click('[data-bs-target="#changeEmailModal"]')
        await browser.wait_for_selector('#changeEmailModal.show')
        await screenshot('07-email-change-modal.png')
        
        # Verify current email shown
        modal_text = await browser.text('#changeEmailModal')
        assert test_account.email in modal_text
    
    async def test_email_change_validation_required(self, browser, admin_session, test_account):
        """Email field should be required."""
        await browser.goto(settings.url(f'/admin/accounts/{test_account.id}'))
        await browser.click('[data-bs-target="#changeEmailModal"]')
        
        # Try to submit without email
        await browser.click('#changeEmailModal button[type="submit"]')
        
        # Form should prevent submission (HTML5 validation)
        current_url = await browser.url()
        assert 'accounts/' in current_url  # Still on same page
    
    async def test_email_change_invalid_format(self, browser, admin_session, test_account):
        """Invalid email format should be rejected."""
        await browser.goto(settings.url(f'/admin/accounts/{test_account.id}'))
        await browser.click('[data-bs-target="#changeEmailModal"]')
        
        await browser.fill('#new_email', 'not-an-email')
        await browser.click('#changeEmailModal button[type="submit"]')
        await browser.wait_for_load()
        await screenshot('07-email-change-invalid-format.png')
        
        # Should show error
        flash = await browser.text('.alert-danger')
        assert 'Invalid email' in flash
    
    async def test_email_change_duplicate_rejected(self, browser, admin_session, test_account, other_account):
        """Cannot change to email already in use."""
        await browser.goto(settings.url(f'/admin/accounts/{test_account.id}'))
        await browser.click('[data-bs-target="#changeEmailModal"]')
        
        await browser.fill('#new_email', other_account.email)
        await browser.click('#changeEmailModal button[type="submit"]')
        await browser.wait_for_load()
        await screenshot('07-email-change-duplicate.png')
        
        # Should show error
        flash = await browser.text('.alert-danger')
        assert 'already in use' in flash.lower()
    
    async def test_email_change_success(self, browser, admin_session, test_account):
        """Successful email change flow."""
        new_email = 'new-email@example.com'
        
        await browser.goto(settings.url(f'/admin/accounts/{test_account.id}'))
        await browser.click('[data-bs-target="#changeEmailModal"]')
        
        await browser.fill('#new_email', new_email)
        await browser.click('#changeEmailModal button[type="submit"]')
        await browser.wait_for_load()
        await screenshot('07-email-change-success.png')
        
        # Verify success
        flash = await browser.text('.alert-success')
        assert new_email in flash
        
        # Verify email displayed in account info
        account_info = await browser.text('.card-body')
        assert new_email in account_info
    
    async def test_email_change_resets_verification(self, browser, admin_session, test_account):
        """Email verification status should be reset."""
        # Account has verified email before change
        assert test_account.email_verified
        
        # Change email
        await browser.goto(settings.url(f'/admin/accounts/{test_account.id}'))
        await browser.click('[data-bs-target="#changeEmailModal"]')
        await browser.fill('#new_email', 'new@example.com')
        await browser.click('#changeEmailModal button[type="submit"]')
        await browser.wait_for_load()
        
        # Reload account from DB
        test_account.refresh()
        assert not test_account.email_verified
    
    async def test_email_change_notifications_sent(self, test_account, mailpit_client, old_email):
        """Both old and new email should receive notifications."""
        new_email = 'new@example.com'
        
        # Check notification to old email
        old_emails = await mailpit_client.search(
            to=old_email,
            subject='Email Address Changed'
        )
        assert len(old_emails) > 0
        old_body = old_emails[0].body
        assert 'security alert' in old_body.lower()
        assert new_email in old_body
        
        # Check notification to new email
        new_emails = await mailpit_client.search(
            to=new_email,
            subject='Email Address Updated'
        )
        assert len(new_emails) > 0
        new_body = new_emails[0].body
        assert 'updated' in new_body.lower()
    
    async def test_email_change_audit_log(self, browser, admin_session, test_account):
        """Email change should be logged."""
        await browser.goto(settings.url(f'/admin/audit?account={test_account.id}'))
        await screenshot('07-email-change-audit-log.png')
        
        log_text = await browser.text('body')
        assert 'email_changed' in log_text
    
    # -------------------------------------------------------------------------
    # Security Integration Tests
    # -------------------------------------------------------------------------
    
    async def test_security_actions_visible_in_account_detail(
        self, browser, admin_session, test_account
    ):
        """Security Actions card should be visible."""
        await browser.goto(settings.url(f'/admin/accounts/{test_account.id}'))
        
        # Find Security Actions card
        card = await browser.locator('.card-header:has-text("Security Actions")')
        assert await card.count() == 1
        await screenshot('07-security-actions-card.png')
    
    async def test_user_alias_displayed_in_footer(self, browser, admin_session, test_account):
        """User alias should be partially displayed in security card footer."""
        await browser.goto(settings.url(f'/admin/accounts/{test_account.id}'))
        
        footer_text = await browser.text('.card-footer')
        assert 'User alias:' in footer_text
        # Should show partial alias like "abcd...wxyz"
        assert '...' in footer_text
```

### Screenshots for Journey 7

```
07-alias-rotation-modal.png
07-alias-rotation-success.png
07-alias-rotation-audit-log.png
07-email-change-modal.png
07-email-change-invalid-format.png
07-email-change-duplicate.png
07-email-change-success.png
07-email-change-audit-log.png
07-security-actions-card.png
```

---

## deploy.sh Integration

### Updated Phases

```bash
# Phase 0: Start Mock Services (NEW - prerequisite)
phase_mock_services() {
    log_phase "0" "Starting Mock Services"
    
    # Start Mailpit, Mock GeoIP, Mock Netcup API
    cd tooling/mock-services && docker compose up -d
    
    # Wait for services to be healthy
    wait_for_service "mailpit" "http://mailpit:8025/api/v1/info" 30
    wait_for_service "mock-geoip" "http://mock-geoip:5556/health" 30
    wait_for_service "mock-netcup-api" "http://mock-netcup-api:5555/health" 30
    
    # Clear Mailpit for fresh test run
    curl -X DELETE http://mailpit:8025/api/v1/messages
}

# Phase 4: Auth Enforcement
phase_auth_enforcement() {
    log_phase "4" "Authentication Enforcement"
    
    # Run auth enforcement tests on ALL routes
    run_in_playwright pytest ui_tests/journeys/test_00_auth_enforcement.py -v
}

# Phase 5: Journey Tests (with email verification)
phase_journey_tests() {
    log_phase "5" "Journey Tests (with screenshots + email verification)"
    
    # Run journeys in order (they build on each other)
    local journeys=(
        "test_01_admin_bootstrap.py"
        "test_02_account_lifecycle.py"
        "test_03_realm_management.py"
        "test_04_api_usage.py"
        "test_05_error_scenarios.py"
        "test_06_security_events.py"       # Security error testing
        "test_07_account_security.py"      # Alias rotation & email change (NEW)
        "test_08_account_portal.py"
        "test_09_config_review.py"
        "test_10_email_verification.py"    # Email flow tests
    )
    
    for journey in "${journeys[@]}"; do
        log_step "Running $journey..."
        run_in_playwright pytest "ui_tests/journeys/$journey" -v --timeout=300
    done
}

# Phase 6: Visual Validation (optional - compare baselines)
phase_visual_validation() {
    log_phase "6" "Visual Regression Check"
    
    if [[ -d "$SCREENSHOT_DIR/baselines" ]]; then
        run_in_playwright python3 ui_tests/compare_screenshots.py
    else
        log_warning "No baselines - skipping visual regression"
    fi
}

# Phase 7: Cleanup (NEW)
phase_cleanup() {
    log_phase "7" "Cleanup"
    
    # Stop mock services
    cd tooling/mock-services && docker compose down
    
    # Export Mailpit emails as evidence (optional)
    # curl http://mailpit:8025/api/v1/messages > screenshots/emails.json
}
```

### Environment Configuration

```bash
# .env.local additions for testing
MAILPIT_API_URL=http://mailpit:8025
MAILPIT_SMTP_HOST=mailpit
MAILPIT_SMTP_PORT=1025

# Flask email config (set by build_deployment.py --local)
# Stored in database as email_config setting
# smtp_server=mailpit, smtp_port=1025
```

---

## Screenshot Naming Convention

```
JJ-STEP-description.png

JJ   = Journey number (00-99)
STEP = Step within journey (alphabetic or descriptive)
description = what's being captured

Examples:
00-auth-admin-dashboard-noauth-redirect.png
00-auth-api-dns-401.png
01-admin-login-page.png
01-admin-change-password-required.png
01-admin-dashboard-empty.png
02-account-create-form.png
02-account-created-success.png
02-account-detail-with-realm.png
04-audit-logs-with-api-calls.png
04-audit-logs-filtered-denied.png
05-error-404-page.png
05-login-failed-message.png
```

---

## Complete Route Inventory

### Public Routes (no auth required)
```
/ (root)
/health
/component-demo
/component-demo-bs5
/admin/login
/account/login
/account/register
/account/forgot-password
/account/reset-password/<token>
/account/register/verify
/account/register/pending
```

### Admin Routes (admin session required)
```
/admin/ (dashboard)
/admin/accounts
/admin/accounts/<id>
/admin/accounts/new
/admin/accounts/pending
/admin/accounts/<id>/approve (POST)
/admin/accounts/<id>/delete (POST)
/admin/accounts/<id>/disable (POST)
/admin/accounts/<id>/reset-password (POST)
/admin/accounts/<id>/regenerate-alias (POST)   # Rotate API credentials
/admin/accounts/<id>/change-email (POST)       # Change email address
/admin/accounts/<id>/realms/new
/admin/realms
/admin/realms/<id>
/admin/realms/pending
/admin/realms/<id>/approve (POST)
/admin/realms/<id>/reject (POST)
/admin/tokens/<id>
/admin/tokens/<id>/revoke (POST)
/admin/audit
/admin/audit/export
/admin/security
/admin/api/security/stats
/admin/api/security/timeline
/admin/api/security/events
/admin/config/netcup
/admin/config/email
/admin/config/email/test (POST)
/admin/system
/admin/system/security (POST)
/admin/change-password
/admin/logout
/admin/api/* (internal APIs)
```

### Account Routes (account session required)
```
/account/dashboard
/account/realms
/account/realms/<id>
/account/realms/<id>/dns
/account/realms/<id>/tokens
/account/realms/<id>/tokens/new
/account/tokens
/account/tokens/<id>/activity
/account/tokens/<id>/regenerate
/account/tokens/<id>/revoke (POST)
/account/settings
/account/settings/totp/setup
/account/settings/recovery-codes
/account/change-password
/account/logout
```

### API Routes (Bearer token required)
```
/api/dns/<domain>/records (GET, POST)
/api/dns/<domain>/records/<id> (PUT, DELETE)
/api/ddns/<domain>/<hostname> (POST, PUT)
/api/myip
/api/geoip/<ip>
/filter-proxy/api/* (proxy endpoints)
```

---

## Key Benefits

1. **Auth Enforcement First**
   - Test ALL routes require proper authentication
   - Run before any data-creating tests
   - Screenshot redirect behavior

2. **Journeys Create Data + Document**
   - No separate "screenshot capture" script
   - Tests create data AND capture screenshots
   - Each journey builds on previous state

3. **All States Documented**
   - Empty states before data creation
   - Success states after operations
   - Error states (denied, invalid, expired)
   - API activity visible in audit logs

4. **API + UI Integration**
   - Make API calls, verify UI shows results
   - Audit logs capture success/denied/error
   - Different token types tested

5. **Progressive State**
   - Journey 01 creates admin session
   - Journey 02 creates accounts (available to Journey 03+)
   - Journey 04 makes API calls (visible in audit views)

---

## UI Structure Reference (2025-12 Update)

### Admin Dashboard Sections

The admin dashboard no longer has a "Quick Actions" card section. Instead, it provides:

1. **Stat Cards (Top Row)**
   - Accounts card with link to `/admin/accounts`
   - Realms card with link to `/admin/realms`  
   - Tokens card with overview
   - API Calls card with 24h stats

2. **Aggregated Metrics Row**
   - **Rate Limited IPs** - Shows IPs that hit rate limits
   - **Most Active Clients** - Top API users by call count
   - **Permission Issues** - Failed auth attempts, IP denials

3. **No "Recent Activity" Section**
   - Dashboard focuses on metrics, not activity feed
   - Activity details are in Audit Logs (`/admin/audit`)

### Login Page Structure

The login page h1 contains the app name "Netcup API Filter" (not "Login").
Tests should check for:
- h1 contains "Netcup API Filter" 
- Form has username/password fields
- Submit button exists

### Account Creation Flow (Invite-Based)

Account creation uses invitation links, NOT inline password setting:

1. Admin fills username + email
2. System sends invitation email
3. `skip_approval` checkbox pre-approves account
4. Optional: Configure realm during creation
5. User accepts invite and sets own password

Tests should NOT expect password fields on account creation form.

### Visual Regression Baselines

After security features update (2025-12), baselines need regeneration:
- Dashboard shows security metrics
- Account pages have alias regeneration
- Email change functionality added
- Run with `UPDATE_BASELINES=1` to regenerate

---

## Migration Checklist

- [ ] Create `ui_tests/journeys/` directory
- [ ] Create `test_00_auth_enforcement.py`
- [ ] Create journey test files (01-09)
- [ ] Create `test_06_security_events.py` with security error testing
- [ ] Create `test_09_email_verification.py` with Mailpit integration
- [ ] Update `deploy.sh` phases 0-7
- [ ] Add Phase 0: Start mock services (Mailpit, Mock GeoIP, Mock Netcup API)
- [ ] Remove standalone `capture_ui_screenshots.py`
- [ ] Update `run-local-tests.sh` to use journeys
- [ ] Create route inventory fixture for dynamic testing
- [ ] Add Mailpit fixture to conftest.py
- [ ] Update email config verification in journey tests
- [ ] Add screenshot comparison (optional phase 6)
- [ ] Document email event coverage matrix
- [x] Add security dashboard route (`/admin/security`)
- [x] Add security stats API endpoints
- [x] Create `security_dashboard.html` template
- [x] Update `state_matrix.py` with security test specs
