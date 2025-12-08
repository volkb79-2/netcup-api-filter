# Journey Test Contracts

> **This is the CANONICAL specification for journey tests.**
> Tests in `ui_tests/tests/journeys/` MUST implement these contracts exactly.
> When contract and code disagree, **update the code to match the contract**.

## Design Principles

1. **Sequential State Building**: Each journey builds on previous journey's state
2. **Random Credentials**: All passwords/tokens are randomly generated, never hardcoded
3. **State File is Truth**: `deployment_state_local.json` tracks current credentials
4. **Fail Fast**: Missing preconditions should fail immediately with clear message
5. **Observable Actions**: Each action should be verifiable via UI or API
6. **Screenshot Evidence**: Key states captured for visual verification

---

## Journey Overview

| Journey | Purpose | Creates | Depends On |
|---------|---------|---------|------------|
| J1 | Fresh Deployment | Admin session, changed password | Fresh DB |
| J2 | Account Lifecycle | Pending account, verified account | J1 |
| J3 | Admin Approvals | Approved account, rejected account | J2 |
| J4 | Realm Creation | Realms of each type | J3 |
| J5 | Token Issuance | Tokens with various scopes | J4 |
| J6 | API Access | Audit log entries | J5 |
| J7 | Security Operations | Password change, token rotation | J6 |

---

## Journey 1: Fresh Deployment (j1_fresh_deployment.py)

### Contract Reference
```
ui_tests/tests/journeys/j1_fresh_deployment.py
```

### Preconditions
- [x] Database freshly created by `build_deployment.py --local`
- [x] Admin account exists: `admin` / `admin`
- [x] Admin `must_change_password`: `true`
- [x] Demo client exists: `demo-user` with token
- [x] Email config seeded for Mailpit (SMTP host: `mailpit`, port: `1025`)
- [x] State file `deployment_state_local.json` has `admin`/`admin`

### Test: J1_01_login_page_accessible
**Action**: Navigate to `/admin/login`
**Verify**:
- [ ] Page title contains "Netcup API Filter" or "Login"
- [ ] Username field exists (`#username`)
- [ ] Password field exists (`#password`)
- [ ] Submit button exists (`button[type='submit']`)
**Screenshot**: `J1-01-login-page.webp`

### Test: J1_02_default_credentials_work
**Action**: Submit login form with credentials from state file
**Verify**:
- [ ] Form submits without error
- [ ] Redirects away from login page (to 2FA, password change, or dashboard)
- [ ] No "Invalid credentials" error shown
**State Change**:
- `journey_state.admin_password` = password used
**Screenshot**: `J1-02-login-filled.webp`

### Test: J1_03_forced_password_change
**Precondition**: User is authenticated (from J1_02)
**Action**: If on password change page:
1. Generate random password: `generate_token()[:60] + "@#$%"`
2. Fill current password (from state file)
3. Fill new password + confirmation
4. Submit form
**Verify**:
- [ ] Password change form accepts input
- [ ] Submit redirects to dashboard
- [ ] Dashboard shows "Dashboard" in h1
**State Change**:
- `journey_state.admin_password` = new random password
- State file updated via `update_admin_password()`
- `settings.refresh_credentials()` called
**Screenshot**: `J1-03-post-login-state.webp`, `J1-04-dashboard.webp`

### Test: J1_04_dashboard_state
**Action**: Verify dashboard elements
**Verify**:
- [ ] H1 contains "Dashboard"
- [ ] Stats cards present (Accounts, Realms, Tokens, Activity)
- [ ] Navigation bar present
- [ ] No 500 error
**Screenshot**: `J1-04-dashboard.webp`

### Test: J1_05_admin_pages_accessible
**Action**: Visit each admin page
**Pages**:
- `/admin/accounts` → `J1-05-accounts-list.webp`
- `/admin/realms` → `J1-06-realms-list.webp`
- `/admin/audit` → `J1-07-audit-logs.webp`
- `/admin/config/netcup` → `J1-08-config-netcup.webp`
- `/admin/config/email` → `J1-09-config-email.webp`
- `/admin/system` → `J1-10-system-info.webp`
**Verify**:
- [ ] Each page loads without 500 error
- [ ] Not redirected to login (session valid)

### Test: J1_06_summary
**Action**: Log summary of journey state
**Screenshot**: `J1-11-journey-complete.webp`

### Postconditions
- [x] Admin password changed to random value
- [x] State file updated with new password
- [x] Admin session established
- [x] All admin pages accessible

---

## Journey 2: Account Lifecycle (j2_account_lifecycle.py)

### Contract Reference
```
ui_tests/tests/journeys/j2_account_lifecycle.py
```

### Preconditions
- [x] Journey 1 completed
- [x] Admin logged in with changed password
- [x] Email notifications configured for Mailpit

### Test: J2_01_registration_page
**Action**: Navigate to `/account/register`
**Verify**:
- [ ] Registration form exists OR "disabled" message
- [ ] Username field, email field, password field present
**State Change**:
- `journey_state.self_registration_available` = True/False
**Screenshot**: `J2-12-registration-page.webp`

### Test: J2_02_submit_registration
**Precondition**: Self-registration available
**Action**:
1. Generate unique username: `testuser_{6-char-random}`
2. Generate unique email: `{username}@test.example.com`
3. Generate random password
4. Submit registration form
**Verify**:
- [ ] Form submits without error
- [ ] Success message or redirect
**State Change**:
- `journey_state.test_account_username` = username
- `journey_state.test_account_email` = email
- `journey_state.test_account_password` = random password
**Screenshot**: `J2-13-registration-filled.webp`, `J2-14-registration-submitted.webp`

### Test: J2_03_check_verification_email
**Action**: Check Mailpit for verification email
**Verify**:
- [ ] Email sent to correct address (test account email)
- [ ] Subject contains "verify" or "confirm"
- [ ] Body contains verification code or link
**State Change**:
- `journey_state.verification_code` = extracted code
- `journey_state.verification_link` = extracted link
**Screenshot**: (email content logged)

### Test: J2_04_complete_verification
**Action**: Complete email verification
- If link: Navigate to link
- If code: Submit code on verification page
**Verify**:
- [ ] Verification succeeds
- [ ] Redirected to login or success page
**Screenshot**: `J2-15-verification-complete.webp`

### Test: J2_05_admin_sees_pending_account
**Action**: Login as admin, navigate to `/admin/accounts/pending`
**Verify**:
- [ ] Test account appears in pending list
- [ ] Status shows "pending"
- [ ] Approve/Reject buttons available
**Screenshot**: `J2-16-pending-accounts.webp`

### Postconditions
- [x] Test account created and email verified
- [x] Account status: pending (awaiting admin approval)
- [x] Admin can see account in pending list

---

## Journey 3: Admin Approvals (j3_admin_approvals.py)

### Contract Reference
```
ui_tests/tests/journeys/j3_comprehensive_states.py
```

### Preconditions
- [x] Journey 2 completed
- [x] Pending account exists
- [x] Admin logged in

### Test: J3_01_approve_account
**Action**: Click approve button for pending account
**Verify**:
- [ ] Success flash message
- [ ] Account status changes to "approved"
- [ ] Account removed from pending list
**State Change**:
- `journey_state.test_account_approved` = True
**Screenshot**: `J3-17-account-approved.webp`

### Test: J3_02_approval_email_sent
**Action**: Check Mailpit for approval notification
**Verify**:
- [ ] Email sent to test account email
- [ ] Subject contains "approved" or "welcome"
**Screenshot**: (email content logged)

### Test: J3_03_user_can_login
**Action**: Logout admin, login as test account
**Verify**:
- [ ] Login succeeds
- [ ] Redirected to account dashboard
- [ ] Not stuck on login page
**Screenshot**: `J3-18-user-logged-in.webp`

### Test: J3_04_create_multiple_accounts
**Action**: Create accounts in all states from state_matrix.py
- `account-pending`: awaiting approval
- `account-approved`: active account
- `account-rejected`: denied by admin
- `account-unverified`: pending email verification
**Verify**:
- [ ] Each account created successfully
- [ ] Correct status for each
**Screenshots**: `J3-19-account-{name}.webp` for each

### Test: J3_05_accounts_list_shows_all_states
**Action**: Navigate to `/admin/accounts`
**Verify**:
- [ ] All account states visible
- [ ] Status badges/indicators correct
- [ ] Filter/sort works
**Screenshot**: `J3-20-accounts-all-states.webp`

### Postconditions
- [x] Test account approved and can login
- [x] Multiple accounts in various states exist
- [x] Approval workflow verified end-to-end

---

## Journey 4: Realm Creation (j4_realm_creation.py)

### Contract Reference
```
ui_tests/tests/journeys/j3_comprehensive_states.py (realm section)
```

### Preconditions
- [x] Journey 3 completed
- [x] Approved accounts exist
- [x] Admin logged in

### Test: J4_01_create_host_realm
**Action**: Create realm with type "host" (single hostname)
- Account: `account-approved`
- Domain: `example.com`
- Value: `host1` (→ `host1.example.com`)
- Record types: A, AAAA
- Operations: read, update
**Verify**:
- [ ] Realm created successfully
- [ ] Appears in realms list
**Screenshot**: `J4-21-realm-host-created.webp`

### Test: J4_02_create_subdomain_realm
**Action**: Create realm with type "subdomain" (apex + children)
- Account: `account-approved`
- Domain: `example.com`
- Value: `iot` (→ `iot.example.com` + `*.iot.example.com`)
- Record types: A, AAAA, TXT
- Operations: read, update, create
**Verify**:
- [ ] Realm created successfully
- [ ] Type shows "subdomain"
**Screenshot**: `J4-22-realm-subdomain-created.webp`

### Test: J4_03_create_subdomain_only_realm
**Action**: Create realm with type "subdomain_only" (children only)
- Account: `account-approved`
- Domain: `example.com`
- Value: `dynamic` (→ `*.dynamic.example.com` but NOT `dynamic.example.com`)
**Verify**:
- [ ] Realm created successfully
- [ ] Type shows "subdomain_only"
**Screenshot**: `J4-23-realm-subonly-created.webp`

### Test: J4_04_create_restricted_realm
**Action**: Create TXT-only realm for Let's Encrypt
- Account: `account-approved`
- Domain: `example.com`
- Value: `acme`
- Record types: TXT only
- Operations: read, create, delete
**Verify**:
- [ ] Realm restricts record types correctly
**Screenshot**: `J4-24-realm-txt-only.webp`

### Test: J4_05_realms_list_shows_all_types
**Action**: Navigate to `/admin/realms`
**Verify**:
- [ ] All realm types visible
- [ ] Status indicators correct
- [ ] Can filter by type/status
**Screenshot**: `J4-25-realms-all-types.webp`

### Postconditions
- [x] Realms of each type created
- [x] Realms associated with correct accounts
- [x] Ready for token creation

---

## Journey 5: Token Issuance (j5_token_issuance.py)

### Contract Reference
```
ui_tests/tests/journeys/j3_comprehensive_states.py (token section)
```

### Preconditions
- [x] Journey 4 completed
- [x] Approved realms exist
- [x] Admin logged in

### Test: J5_01_create_readonly_token
**Action**: Create read-only token for subdomain realm
- Realm: `realm-subdomain-approved`
- Operations: read only
**Verify**:
- [ ] Token created successfully
- [ ] Token value displayed once (copy warning)
- [ ] Token masked in subsequent views
**State Change**:
- Store token value in `deployment_state_local.json` under clients
**Screenshot**: `J5-26-token-readonly-created.webp`

### Test: J5_02_create_ddns_token
**Action**: Create DDNS update token
- Realm: `realm-host-approved`
- Record types: A, AAAA
- Operations: read, update
**Verify**:
- [ ] Token created with correct scope
**Screenshot**: `J5-27-token-ddns-created.webp`

### Test: J5_03_create_full_access_token
**Action**: Create full control token
- Realm: `realm-full-control`
- Operations: read, update, create, delete
**Verify**:
- [ ] Token has all permissions
**Screenshot**: `J5-28-token-full-created.webp`

### Test: J5_04_create_ip_restricted_token
**Action**: Create token with IP whitelist
- Realm: any approved realm
- IP ranges: `192.168.1.0/24`, `10.0.0.0/8`
**Verify**:
- [ ] IP restrictions saved correctly
**Screenshot**: `J5-29-token-ip-restricted.webp`

### Test: J5_05_tokens_list_shows_all
**Action**: View tokens in realm detail
**Verify**:
- [ ] All tokens listed
- [ ] Status indicators (active, expiring, expired)
- [ ] Scope summary visible
**Screenshot**: `J5-30-tokens-list.webp`

### Postconditions
- [x] Tokens of each type created
- [x] Token values stored in state file
- [x] Ready for API testing

---

## Journey 6: API Access (j6_api_access.py)

### Contract Reference
```
ui_tests/tests/journeys/j3_comprehensive_states.py (API section)
```

### Preconditions
- [x] Journey 5 completed
- [x] Active tokens exist with known values

### Test: J6_01_readonly_token_can_read
**Action**: `GET /api/dns/example.com/records` with readonly token
**Verify**:
- [ ] Response: 200 OK
- [ ] Records returned (or empty list)
**Audit**: Entry logged with success

### Test: J6_02_readonly_token_cannot_update
**Action**: `PUT /api/dns/example.com/records` with readonly token
**Verify**:
- [ ] Response: 403 Forbidden
- [ ] Error message: "Operation not permitted"
**Audit**: Entry logged with failure

### Test: J6_03_ddns_token_can_update
**Action**: `PUT /api/ddns/example.com/host1?ip=1.2.3.4` with DDNS token
**Verify**:
- [ ] Response: 200 OK (or appropriate success)
**Audit**: Entry logged with success

### Test: J6_04_token_outside_realm_fails
**Action**: Try to access domain outside token's realm
**Verify**:
- [ ] Response: 403 Forbidden
- [ ] Error message: "Domain not in scope"
**Audit**: Entry logged with failure

### Test: J6_05_invalid_token_fails
**Action**: Request with malformed token
**Verify**:
- [ ] Response: 401 Unauthorized
**Audit**: Entry logged

### Test: J6_06_expired_token_fails
**Action**: Request with expired token (if created)
**Verify**:
- [ ] Response: 401 Unauthorized
- [ ] Error: "Token expired"

### Test: J6_07_revoked_token_fails
**Action**: Request with revoked token (if created)
**Verify**:
- [ ] Response: 401 Unauthorized
- [ ] Error: "Token revoked"

### Test: J6_08_audit_log_shows_api_calls
**Action**: Navigate to `/admin/audit`
**Verify**:
- [ ] API call entries visible
- [ ] Success/failure status correct
- [ ] Token identity logged
- [ ] Source IP logged
**Screenshot**: `J6-31-audit-api-calls.webp`

### Postconditions
- [x] API authorization verified for all token types
- [x] Audit log populated with API activity
- [x] Security boundaries enforced

---

## Journey 7: Security Operations (j7_security_ops.py)

### Contract Reference
```
(New journey to be created)
```

### Preconditions
- [x] Journey 6 completed
- [x] Admin logged in
- [x] Mailpit available for notifications

### Test: J7_01_admin_password_change
**Action**: Change admin password mid-session
1. Navigate to `/admin/change-password`
2. Enter current password (from state file)
3. Generate new random password
4. Submit form
**Verify**:
- [ ] Password change succeeds
- [ ] Session remains active (not logged out)
- [ ] State file updated
- [ ] Email notification sent (password changed)
**Screenshot**: `J7-32-password-change.webp`

### Test: J7_02_token_rotation
**Action**: Revoke old token, create new one
1. View token in admin UI
2. Click revoke
3. Create replacement token
**Verify**:
- [ ] Old token marked as revoked
- [ ] New token created with same scope
- [ ] Old token fails API calls
- [ ] New token works
**Screenshot**: `J7-33-token-rotated.webp`

### Test: J7_03_security_notifications
**Action**: Verify security notifications sent
- Password change → email sent
- Token revoked → email sent (if configured)
- Login from new IP → email sent (if configured)
**Verify**:
- [ ] Appropriate emails in Mailpit
**Screenshot**: (email evidence)

### Postconditions
- [x] Password rotation tested
- [x] Token rotation tested
- [x] Security notifications verified

---

## State File Contract

### File Location
```
/workspaces/netcup-api-filter/deployment_state_local.json
```

### Schema
```json
{
  "target": "local",
  "build": {
    "built_at": "ISO-8601",
    "git_commit": "short-sha",
    "git_branch": "main"
  },
  "admin": {
    "username": "admin",
    "password": "<current-random-password>",
    "password_changed_at": "ISO-8601 or null"
  },
  "clients": [
    {
      "client_id": "demo-user",
      "secret_key": "naf_<alias>_<token>",
      "description": "Primary demo account",
      "is_primary": true
    }
  ],
  "last_updated_at": "ISO-8601",
  "updated_by": "j1_fresh_deployment|j7_security_ops|etc"
}
```

### Rules
1. **ALWAYS read before login**: `settings.refresh_credentials()`
2. **ALWAYS write after password change**: `update_admin_password(new_pw)`
3. **NEVER hardcode passwords**: Use `generate_token()` or `secrets`
4. **Include `updated_by`**: Track which journey made changes
5. **Atomic updates**: Use helper functions, not direct file writes

---

## Screenshot Naming Convention

```
{Journey}-{Sequence}-{description}.webp
```

Examples:
- `J1-01-login-page.webp`
- `J3-19-account-account-pending.webp`
- `J6-31-audit-api-calls.webp`

### Screenshot Directory
```
deploy-local/screenshots/
```

---

## Debugging Checklist

### When Login Fails
1. Check state file password matches database:
   ```bash
   cat deployment_state_local.json | jq '.admin.password'
   sqlite3 deploy-local/netcup_filter.db \
     "SELECT password_hash FROM accounts WHERE username='admin';"
   ```

2. Check for "Invalid credentials" flash message in page body

3. Verify `refresh_credentials()` was called before login

### When Test Order Matters
1. Journeys MUST run in order: J1 → J2 → J3 → J4 → J5 → J6 → J7
2. Check `journey_state` for expected preconditions
3. Skip gracefully if precondition missing (with clear message)

### When State Is Inconsistent
1. Rebuild fresh: `python build_deployment.py --local`
2. Check `updated_by` in state file to find last modifier
3. Verify `password_changed_at` timestamp

---

## Implementation Checklist

Each journey test file MUST:

- [ ] Import from `ui_tests.config import settings`
- [ ] Import from `ui_tests.deployment_state import update_admin_password`
- [ ] Call `settings.refresh_credentials()` before any login
- [ ] Use `generate_token()` or `secrets` for passwords
- [ ] Call `update_admin_password()` after password changes
- [ ] Update `journey_state` with test results
- [ ] Capture screenshots with consistent naming
- [ ] Log clear progress messages
- [ ] Fail fast with actionable error messages
