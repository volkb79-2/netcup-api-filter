# Route Coverage Matrix

Complete inventory of all routes with test and screenshot coverage status.

## Public Routes (No Authentication)

| Route | Method | Purpose | Test Coverage | Screenshot |
|-------|--------|---------|---------------|------------|
| `/` | GET | Landing page | ✅ | ✅ |
| `/health` | GET | Health check endpoint | ✅ | ❌ (API only) |
| `/theme-demo` | GET | Theme demo page | ⚠️ Partial | ⚠️ |
| `/component-demo` | GET | Component demo | ⚠️ Partial | ⚠️ |
| `/component-demo-bs5` | GET | BS5 reference demo | ✅ | ✅ |
| `/theme-demo2` | GET | Alternative theme demo | ❌ | ❌ |
| `/theme-demo2/<path>` | GET | Theme demo assets | ❌ (Static) | ❌ |

## Admin Routes (`/admin/...`)

### Authentication
| Route | Method | Purpose | Test Coverage | Screenshot |
|-------|--------|---------|---------------|------------|
| `/admin/login` | GET, POST | Admin login | ✅ | ✅ |
| `/admin/logout` | GET | Admin logout | ✅ | ❌ (Redirect) |
| `/admin/change-password` | GET, POST | Change admin password | ✅ | ✅ |

### Dashboard & Overview
| Route | Method | Purpose | Test Coverage | Screenshot |
|-------|--------|---------|---------------|------------|
| `/admin/` | GET | Dashboard | ✅ | ✅ |

### Account Management
| Route | Method | Purpose | Test Coverage | Screenshot |
|-------|--------|---------|---------------|------------|
| `/admin/accounts` | GET | List all accounts | ✅ | ✅ |
| `/admin/accounts/pending` | GET | Pending accounts | ⚠️ Partial | ❌ |
| `/admin/accounts/new` | GET, POST | Create account | ✅ | ✅ |
| `/admin/accounts/<id>` | GET | Account detail | ⚠️ Partial | ❌ |
| `/admin/accounts/<id>/approve` | POST | Approve account | ✅ | ❌ (Action) |
| `/admin/accounts/<id>/disable` | POST | Disable account | ⚠️ | ❌ (Action) |
| `/admin/accounts/<id>/delete` | POST | Delete account | ⚠️ | ❌ (Action) |
| `/admin/accounts/<id>/realms/new` | GET, POST | Create realm for account | ⚠️ Partial | ❌ |

### Realm Management
| Route | Method | Purpose | Test Coverage | Screenshot |
|-------|--------|---------|---------------|------------|
| `/admin/realms` | GET | List all realms | ✅ | ✅ |
| `/admin/realms/pending` | GET | Pending realm requests | ✅ | ✅ |
| `/admin/realms/<id>` | GET | Realm detail | ⚠️ Partial | ❌ |
| `/admin/realms/<id>/approve` | POST | Approve realm | ⚠️ | ❌ (Action) |
| `/admin/realms/<id>/reject` | POST | Reject realm | ⚠️ | ❌ (Action) |
| `/admin/realms/<id>/revoke` | POST | Revoke realm | ⚠️ | ❌ (Action) |

### Token Management
| Route | Method | Purpose | Test Coverage | Screenshot |
|-------|--------|---------|---------------|------------|
| `/admin/tokens/<id>` | GET | Token detail | ⚠️ Partial | ❌ |
| `/admin/tokens/<id>/revoke` | POST | Revoke token | ⚠️ | ❌ (Action) |

### Audit Logs
| Route | Method | Purpose | Test Coverage | Screenshot |
|-------|--------|---------|---------------|------------|
| `/admin/audit` | GET | Audit log viewer | ✅ | ✅ |
| `/admin/audit/trim` | POST | Trim old logs | ⚠️ | ❌ (Action) |
| `/admin/audit/export` | GET | Export logs (ODS) | ✅ | ❌ (Download) |

### Configuration
| Route | Method | Purpose | Test Coverage | Screenshot |
|-------|--------|---------|---------------|------------|
| `/admin/config/netcup` | GET, POST | Netcup API config | ✅ | ✅ |
| `/admin/config/email` | GET, POST | Email/SMTP config | ✅ | ✅ |
| `/admin/config/email/test` | POST | Test email sending | ⚠️ | ❌ (Action) |
| `/admin/system` | GET | System info/deps | ✅ | ✅ |

### Admin API Endpoints
| Route | Method | Purpose | Test Coverage | Screenshot |
|-------|--------|---------|---------------|------------|
| `/admin/api/accounts` | GET | JSON accounts list | ⚠️ | ❌ (API) |
| `/admin/api/stats` | GET | Dashboard stats | ⚠️ | ❌ (API) |
| `/admin/api/accounts/bulk` | POST | Bulk account ops | ⚠️ | ❌ (API) |
| `/admin/api/realms/bulk` | POST | Bulk realm ops | ⚠️ | ❌ (API) |

## Account Portal Routes (`/account/...`)

### Authentication
| Route | Method | Purpose | Test Coverage | Screenshot |
|-------|--------|---------|---------------|------------|
| `/account/login` | GET, POST | Account login | ✅ | ✅ |
| `/account/login/2fa` | GET, POST | 2FA verification | ⚠️ | ❌ |
| `/account/logout` | GET | Logout | ⚠️ | ❌ (Redirect) |
| `/account/forgot-password` | GET, POST | Password reset request | ✅ | ✅ |
| `/account/reset-password/<token>` | GET, POST | Reset password with token | ⚠️ | ❌ |

### Registration
| Route | Method | Purpose | Test Coverage | Screenshot |
|-------|--------|---------|---------------|------------|
| `/account/register` | GET, POST | New registration | ✅ | ✅ |
| `/account/register/verify` | GET, POST | Email verification | ⚠️ | ❌ |
| `/account/register/resend` | POST | Resend verification | ⚠️ | ❌ (Action) |
| `/account/register/pending` | GET | Registration pending | ⚠️ | ❌ |

### Dashboard (Authenticated)
| Route | Method | Purpose | Test Coverage | Screenshot |
|-------|--------|---------|---------------|------------|
| `/account/dashboard` | GET | Account dashboard | ⚠️ Partial | ❌ |
| `/account/settings` | GET, POST | Account settings | ⚠️ | ❌ |
| `/account/change-password` | GET, POST | Change password | ⚠️ | ❌ |
| `/account/docs` | GET | API documentation | ⚠️ | ❌ |

### Realm Management (Authenticated)
| Route | Method | Purpose | Test Coverage | Screenshot |
|-------|--------|---------|---------------|------------|
| `/account/realms` | GET | List user's realms | ⚠️ | ❌ |
| `/account/realms/request` | GET, POST | Request new realm | ⚠️ | ❌ |
| `/account/realms/new` | GET, POST | Create realm (redirect) | ⚠️ | ❌ |
| `/account/realms/<id>` | GET | Realm detail | ⚠️ | ❌ |
| `/account/realms/<id>/ddns` | POST | DDNS update | ⚠️ | ❌ (Action) |

### DNS Management (Authenticated)
| Route | Method | Purpose | Test Coverage | Screenshot |
|-------|--------|---------|---------------|------------|
| `/account/realms/<id>/dns` | GET | DNS records list | ⚠️ | ❌ |
| `/account/realms/<id>/dns/create` | GET, POST | Create DNS record | ⚠️ | ❌ |
| `/account/realms/<id>/dns/<rec>/edit` | GET, POST | Edit DNS record | ⚠️ | ❌ |
| `/account/realms/<id>/dns/<rec>/delete` | POST | Delete DNS record | ⚠️ | ❌ (Action) |

### Token Management (Authenticated)
| Route | Method | Purpose | Test Coverage | Screenshot |
|-------|--------|---------|---------------|------------|
| `/account/tokens` | GET | List tokens | ⚠️ | ❌ |
| `/account/tokens/new` | GET, POST | Create token | ⚠️ | ❌ |
| `/account/realms/<id>/tokens/new` | GET, POST | Create token for realm | ⚠️ | ❌ |
| `/account/realms/<id>/tokens` | GET, POST | Realm tokens | ⚠️ | ❌ |
| `/account/tokens/<id>/revoke` | POST | Revoke token | ⚠️ | ❌ (Action) |
| `/account/tokens/<id>/regenerate` | GET, POST | Regenerate token | ⚠️ | ❌ |
| `/account/tokens/<id>/activity` | GET | Token activity log | ⚠️ | ❌ |

### 2FA Settings (Authenticated)
| Route | Method | Purpose | Test Coverage | Screenshot |
|-------|--------|---------|---------------|------------|
| `/account/2fa/verify` | POST | Verify 2FA code | ⚠️ | ❌ (Action) |
| `/account/2fa/resend` | POST | Resend 2FA code | ⚠️ | ❌ (Action) |
| `/account/settings/totp/setup` | GET, POST | Setup TOTP | ⚠️ | ❌ |
| `/account/settings/telegram/link` | GET, POST | Link Telegram | ⚠️ | ❌ |
| `/account/settings/recovery-codes` | GET | View recovery codes | ⚠️ | ❌ |
| `/account/settings/recovery-codes/generate` | POST | Generate new codes | ⚠️ | ❌ (Action) |
| `/account/settings/recovery-codes/display` | GET | Display codes | ⚠️ | ❌ |

### Account API Endpoints
| Route | Method | Purpose | Test Coverage | Screenshot |
|-------|--------|---------|---------------|------------|
| `/account/api/realms` | GET | JSON realms list | ⚠️ | ❌ (API) |
| `/account/api/realms/<id>/tokens` | GET | JSON tokens list | ⚠️ | ❌ (API) |
| `/account/activity/export` | GET | Export activity (ODS) | ⚠️ | ❌ (Download) |

## Coverage Summary

### By Area

| Area | Total Routes | Tested | Screenshots |
|------|-------------|--------|-------------|
| Public | 7 | 4 | 2 |
| Admin Auth | 3 | 3 | 2 |
| Admin Accounts | 8 | 3 | 3 |
| Admin Realms | 6 | 2 | 2 |
| Admin Tokens | 2 | 0 | 0 |
| Admin Audit | 3 | 2 | 1 |
| Admin Config | 4 | 3 | 3 |
| Admin API | 4 | 0 | 0 |
| Account Auth | 5 | 2 | 2 |
| Account Registration | 4 | 2 | 1 |
| Account Dashboard | 4 | 0 | 0 |
| Account Realms | 5 | 0 | 0 |
| Account DNS | 4 | 0 | 0 |
| Account Tokens | 8 | 0 | 0 |
| Account 2FA | 7 | 0 | 0 |
| Account API | 3 | 0 | 0 |
| **TOTAL** | **77** | **21** | **16** |

### Priority Gaps (P0 - Need Coverage)

1. **Account Portal Authenticated Pages** - User journey after login
   - `/account/dashboard`
   - `/account/realms`
   - `/account/realms/<id>`
   - `/account/tokens`
   
2. **Admin Detail Pages** - View specific items
   - `/admin/accounts/<id>`
   - `/admin/realms/<id>`
   - `/admin/tokens/<id>`

3. **DNS Management** - Core functionality
   - `/account/realms/<id>/dns`
   - `/account/realms/<id>/dns/create`
   - `/account/realms/<id>/dns/<rec>/edit`

4. **2FA Setup** - Security feature
   - `/account/settings/totp/setup`
   - `/account/settings/recovery-codes`

### Legend

- ✅ Full coverage (tested + screenshot if applicable)
- ⚠️ Partial coverage (basic test or manual only)
- ❌ No coverage
- (Action) - POST action, no page to screenshot
- (API) - JSON API endpoint, no UI
- (Redirect) - Redirects to another page
- (Download) - File download, no UI to capture

## Test Files by Route

| Route Pattern | Primary Test File |
|---------------|------------------|
| `/admin/*` | `test_admin_*.py`, `test_user_journeys.py` |
| `/account/login\|register\|forgot-password` | `test_account_portal.py` |
| `/account/dashboard\|realms\|tokens` | `test_holistic_coverage.py` (new) |
| All pages | `test_ux_theme_validation.py` (CSS compliance) |
| All forms | `test_ui_interactive.py` (JS validation) |
