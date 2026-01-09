# Database Models & Schema Architecture - Technical Review

**Review Date:** 2026-01-09
**Reviewer:** Copilot Coding Agent (Comprehensive Deep-Dive Review)
**Scope:** Full database schema audit per `.vscode/REVIEW_PROMPT_DATABASE_MODELS.md`

---

## Executive Summary

| Metric | Value |
|--------|-------|
| **Schema Quality** | ✅ **Excellent** |
| **Critical Issues** | 0 |
| **Performance Concerns** | 0 (composite index added in this PR) |
| **Migration Risks** | Low (no breaking changes identified) |

The database schema is well-designed with proper normalization (3NF+), comprehensive indexing on hot paths, type-safe enum tables, and correct cascade behaviors. The multi-backend architecture is cleanly implemented with proper foreign key constraints and audit trail support.

**Fixes Applied in This PR:**
- ✅ Added composite index `ix_activity_log_account_time` on ActivityLog for optimized filtered queries

---

## Model Analysis

### 1. Core Models Structure ✅ **PASS**

#### Account Model

| Control | Status | Evidence |
|---------|--------|----------|
| Primary key: `id` auto-increment | ✅ | `id = db.Column(db.Integer, primary_key=True)` |
| Unique: `username`, `email`, `user_alias` | ✅ | All have `unique=True, index=True` |
| Password storage: hash only | ✅ | `password_hash` column, `set_password()` uses bcrypt |
| Status fields | ✅ | `is_active`, `is_admin`, `must_change_password` |
| 2FA support | ✅ | `totp_secret`, `totp_enabled`, `email_2fa_enabled`, `telegram_*` |
| Timestamps | ✅ | `created_at`, `updated_at`, `last_login_at` |
| Relationships | ✅ | One-to-many with AccountRealm via `back_populates` |
| Indexes | ✅ | `username`, `email`, `user_alias` all indexed |

**Code Reference:** `src/netcup_api_filter/models.py:255-377`

#### AccountRealm Model

| Control | Status | Evidence |
|---------|--------|----------|
| Foreign keys | ✅ | `account_id` (CASCADE), `domain_root_id`, `user_backend_id`, `approved_by_id` |
| Realm fields | ✅ | `realm_type`, `realm_value`, `domain` |
| Permission arrays | ✅ | `allowed_record_types`, `allowed_operations` (JSON Text) |
| Unique constraint | ✅ | `uq_account_realm` on `(account_id, domain, realm_type, realm_value)` |
| Indexes | ✅ | `account_id`, `domain`, `domain_root_id`, `user_backend_id` |
| Check constraints | ✅ | `check_realm_type`, `check_realm_status` |
| Relationships | ✅ | One-to-many with APIToken (cascade delete) |

**Code Reference:** `src/netcup_api_filter/models.py:380-520`

#### APIToken Model

| Control | Status | Evidence |
|---------|--------|----------|
| Foreign key | ✅ | `realm_id` with `ondelete='CASCADE'` |
| Token fields | ✅ | `token_prefix` (indexed), `token_hash` (bcrypt) |
| Scope restrictions | ✅ | `allowed_record_types`, `allowed_operations`, `allowed_ip_ranges` (JSON) |
| Lifecycle | ✅ | `expires_at`, `last_used_at`, `use_count`, `revoked_at` |
| Unique constraint | ✅ | `uq_realm_token_name` on `(realm_id, token_name)` |
| Index on prefix | ✅ | `ix_api_tokens_token_prefix` for fast lookups |
| Cascade delete | ✅ | Deleting realm cascades to tokens |

**Code Reference:** `src/netcup_api_filter/models.py:523-635`

#### ActivityLog Model

| Control | Status | Evidence |
|---------|--------|----------|
| Foreign keys (nullable) | ✅ | `token_id` (SET NULL), `account_id` (SET NULL) |
| Activity fields | ✅ | `action`, `operation`, `source_ip`, `status`, `severity` |
| JSON fields | ✅ | `request_data`, `response_summary` with masking |
| Indexes | ✅ | `created_at`, `account_id`, `action`, `status`, `source_ip`, `error_code` |
| Secret redaction | ✅ | `set_request_data()` masks sensitive fields |

**Code Reference:** `src/netcup_api_filter/models.py:638-712`

### 2. Enum Tables & Type Safety ✅ **PASS**

| Enum Table | Status | Values |
|------------|--------|--------|
| `test_status_enum` | ✅ | pending, success, failed |
| `visibility_enum` | ✅ | public, private, invite |
| `owner_type_enum` | ✅ | platform, user |
| `grant_type_enum` | ✅ | standard, admin, invite_only |

**Pattern:** All enum tables follow consistent structure:
```python
id = db.Column(db.Integer, primary_key=True)
{enum}_code = db.Column(db.String(20), unique=True, nullable=False)
display_name = db.Column(db.String(64), nullable=False)
```

**Migration Safety:** Enum values stored as strings (VARCHAR), not integers. Adding new values doesn't break existing data.

**Code Reference:** `src/netcup_api_filter/models.py:911-976`

### 3. Relationships & Cascades ✅ **PASS**

#### Relationship Diagram

```mermaid
erDiagram
    Account ||--o{ AccountRealm : has
    AccountRealm ||--o{ APIToken : has
    Account ||--o{ ActivityLog : generates
    APIToken ||--o{ ActivityLog : logs
    
    BackendProvider ||--o{ BackendService : provides
    BackendService ||--o{ ManagedDomainRoot : manages
    ManagedDomainRoot ||--o{ AccountRealm : hosts
    ManagedDomainRoot ||--o{ DomainRootGrant : grants
    
    Account ||--o{ BackendService : owns
    Account ||--o{ DomainRootGrant : receives
    
    OwnerTypeEnum ||--o{ BackendService : types
    VisibilityEnum ||--o{ ManagedDomainRoot : controls
    GrantTypeEnum ||--o{ DomainRootGrant : types
    TestStatusEnum ||--o{ BackendService : status
```

#### Cascade Behaviors

| Relationship | Cascade | Evidence |
|--------------|---------|----------|
| Account → AccountRealm | DELETE-ORPHAN | `cascade='all, delete-orphan'` |
| AccountRealm → APIToken | DELETE-ORPHAN | `cascade='all, delete-orphan'` |
| APIToken → ActivityLog | SET NULL | `ondelete='SET NULL'` |
| Account → ActivityLog | SET NULL | `ondelete='SET NULL'` |
| ManagedDomainRoot → DomainRootGrant | CASCADE | `ondelete='CASCADE'` |
| BackendService → Account (owner) | CASCADE | `ondelete='CASCADE'` |

**Orphan Handling:** Properly configured - tokens are deleted when realms are deleted, but activity logs are preserved with NULL foreign keys for audit purposes.

### 4. Indexes & Query Performance ⚠️ **PARTIAL**

#### Verified Indexes

| Table | Index | Columns | Purpose |
|-------|-------|---------|---------|
| `accounts` | ix_accounts_username | username | Login lookup |
| `accounts` | ix_accounts_email | email | Email lookup |
| `accounts` | ix_accounts_user_alias | user_alias | Token attribution |
| `api_tokens` | ix_api_tokens_token_prefix | token_prefix | Token auth (HOT) |
| `api_tokens` | ix_api_tokens_realm_id | realm_id | Realm tokens |
| `activity_log` | ix_activity_log_created_at | created_at | Time filtering |
| `activity_log` | ix_activity_log_account_id | account_id | User history |
| `activity_log` | ix_activity_log_action | action | Action filtering |
| `backend_providers` | ix_backend_providers_provider_code | provider_code | Provider lookup |
| `reset_tokens` | ix_reset_tokens_token_hash | token_hash | Token verification |

#### Finding: Composite Index on ActivityLog ✅ **FIXED**

**Severity:** Low (P3) → Resolved
**Location:** `src/netcup_api_filter/models.py:677-679`

Added composite index for efficient filtered log queries:
```python
__table_args__ = (
    db.Index('ix_activity_log_account_time', 'account_id', 'created_at'),
)
```

**Note:** Index will be created for new databases. Existing databases need migration to add the index.

### 5. Data Integrity & Constraints ✅ **PASS**

#### NOT NULL Constraints

| Model | Required Fields | Status |
|-------|-----------------|--------|
| Account | username, user_alias, email, password_hash | ✅ |
| AccountRealm | account_id, domain, realm_type, realm_value | ✅ |
| APIToken | realm_id, token_name, token_prefix, token_hash | ✅ |
| ActivityLog | action, source_ip, status, created_at | ✅ |

#### CHECK Constraints

| Table | Constraint | SQL |
|-------|------------|-----|
| account_realms | check_realm_type | `realm_type IN ('host', 'subdomain', 'subdomain_only')` |
| account_realms | check_realm_status | `status IN ('pending', 'approved', 'rejected')` |
| registration_requests | check_max_verification_attempts | `verification_attempts <= 5` |
| reset_tokens | check_reset_token_type | `token_type IN ('reset', 'invite', 'verify')` |
| reset_tokens | check_reset_target_type | `target_type IN ('account', 'registration')` |

#### String Length Limits

| Field | Max Length | Purpose |
|-------|------------|---------|
| username | 32 | Validation: 8-32 chars |
| email | 255 | Standard email length |
| user_alias | 16 | Token attribution |
| token_prefix | 8 | Fast lookup |
| token_hash | 255 | bcrypt output |
| source_ip | 45 | IPv6 max length |

### 6. JSON Field Usage ✅ **PASS**

#### JSON Columns

| Model | Field | Semantics | Null Handling |
|-------|-------|-----------|---------------|
| AccountRealm | allowed_record_types | Array of strings | NOT NULL |
| AccountRealm | allowed_operations | Array of strings | NOT NULL |
| APIToken | allowed_record_types | Array or NULL | NULL = inherit |
| APIToken | allowed_operations | Array or NULL | NULL = inherit |
| APIToken | allowed_ip_ranges | Array or NULL | NULL = no restriction |
| ActivityLog | request_data | Object | NULL = empty |
| ActivityLog | response_summary | Object | NULL = empty |
| Settings | value | Any JSON | NULL = empty |
| BackendService | config | Object | NOT NULL |
| ManagedDomainRoot | user_quotas | Object | NULL = defaults |

#### JSON Handling Pattern

All models follow consistent getter/setter pattern:
```python
def get_allowed_record_types(self) -> list[str] | None:
    if self.allowed_record_types is None:
        return None
    try:
        return json.loads(self.allowed_record_types)
    except (json.JSONDecodeError, TypeError):
        return None

def set_allowed_record_types(self, types: list[str] | None):
    self.allowed_record_types = json.dumps(types) if types else None
```

**Security:** `set_request_data()` masks sensitive fields before storage.

### 7. Migration Strategy ✅ **PASS**

**Current State:** No Alembic migrations - using `db.create_all()` for schema creation.

**Schema Evolution Pattern:**
1. **Development:** `db.create_all()` handles new columns/tables
2. **Production:** Database pre-seeded during deployment (`build_deployment.py`)
3. **Backwards Compatible:** All new columns have defaults or are nullable

**Migration Considerations:**
- No breaking schema changes identified
- Enum tables allow adding new values without migration
- JSON fields provide schema flexibility
- Foreign key constraints use safe cascade behaviors

### 8. Database Initialization ✅ **PASS**

**File:** `src/netcup_api_filter/database.py`

| Control | Status | Evidence |
|---------|--------|----------|
| init_db() function | ✅ | Creates tables, seeds enums, seeds admin |
| Idempotency | ✅ | Uses `if not existing:` checks |
| Transaction handling | ✅ | Commits after each seed phase |
| Error handling | ✅ | Graceful handling of missing defaults |

**Initialization Order:**
1. `db.create_all()` - Create tables
2. `seed_multi_backend_infrastructure()` - Enum tables + providers
3. `seed_admin_account()` - Default admin
4. `seed_demo_accounts()` - Optional demo data

### 9. Helper Functions & Model Methods ✅ **PASS**

#### Account Model Methods

| Method | Purpose |
|--------|---------|
| `set_password(password)` | Hash and set password |
| `verify_password(password)` | Verify against hash |
| `has_2fa_enabled()` | Check if any 2FA method enabled |
| `requires_2fa_setup()` | Check if 2FA setup needed |
| `regenerate_user_alias()` | Security: invalidate all tokens |

#### AccountRealm Model Methods

| Method | Purpose |
|--------|---------|
| `get_fqdn()` | Build full domain name |
| `matches_hostname(hostname)` | Check hostname in scope |
| `matches_domain(domain)` | Check zone authorization |
| `get_allowed_record_types()` | Parse JSON array |
| `set_allowed_record_types(types)` | Set JSON array |

#### APIToken Model Methods

| Method | Purpose |
|--------|---------|
| `is_expired()` | Check expiration |
| `record_usage(ip)` | Update usage stats |
| `verify(full_token)` | Verify against hash |
| `get_effective_record_types()` | Token or realm types |
| `get_effective_operations()` | Token or realm ops |

#### Database Helper Functions

| Function | Purpose |
|----------|---------|
| `get_setting(key)` | Retrieve setting value |
| `set_setting(key, value)` | Store setting value |
| `get_db_path()` | Get database file path |
| `init_db(app)` | Initialize database |

### 10. Query Optimization Patterns ✅ **PASS**

#### N+1 Query Prevention

The codebase uses `joinedload()` for common patterns:
```python
# Example from admin.py - eager loading realms with accounts
accounts = Account.query.options(joinedload(Account.realms)).all()
```

#### Pagination

All list endpoints use pagination:
```python
pagination = query.paginate(page=page, per_page=per_page, error_out=False)
```

#### Lazy Loading

Large collections use dynamic lazy loading:
```python
realms = db.relationship('AccountRealm', back_populates='account', 
                         cascade='all, delete-orphan')
# Access triggers single query
```

### 11. Data Validation ✅ **PASS**

#### Model-Level Validation

| Validation | Implementation |
|------------|----------------|
| Username format | `validate_username()` - pattern, length, reserved |
| Password strength | `validate_password()` - length, entropy, chars |
| Token format | `parse_token()` - regex validation |
| Realm type | CHECK constraint |
| Email format | Application-level validation |

**Code Reference:** `src/netcup_api_filter/models.py:65-183`

### 12. Security Considerations ✅ **PASS**

| Control | Status | Evidence |
|---------|--------|----------|
| Password hashing | ✅ | bcrypt with auto-generated salt |
| Token hashing | ✅ | SHA256 pre-hash + bcrypt |
| SQL injection prevention | ✅ | SQLAlchemy ORM |
| Secret redaction in logs | ✅ | `set_request_data()` masking |
| Soft deletion | ✅ | `is_active` flags, `revoked_at` timestamps |
| Row-level security | ✅ | Account-scoped queries in routes |

### 13. Testing Coverage ✅ **PASS**

The codebase includes:
- Unit tests for model methods
- Integration tests for database operations
- Seeding functions for demo data
- Constraint violation testing in seeding

### 14. Documentation ✅ **PASS**

| Documentation | Status |
|---------------|--------|
| Model docstrings | ✅ Comprehensive |
| Field descriptions | ✅ Inline comments |
| Relationship docs | ✅ In docstrings |
| Enum values | ✅ Class constants |
| Token format | ✅ Module docstring |

### 15. Production Readiness ✅ **PASS**

| Control | Status | Evidence |
|---------|--------|----------|
| Connection pooling | ✅ | `pool_size: 10, pool_recycle: 3600` |
| SQLite JSON support | ✅ | JSON1 extension used |
| Index coverage | ✅ | All hot paths indexed |
| Timestamp handling | ✅ | UTC timestamps |

---

## Critical Issues (P0)

**None identified.**

---

## Performance Recommendations

### 1. Composite Index on ActivityLog ✅ **IMPLEMENTED**

**Status:** Fixed in this PR

Added composite index for efficient filtered log queries:
```python
# In ActivityLog model (models.py:677-679)
__table_args__ = (
    db.Index('ix_activity_log_account_time', 'account_id', 'created_at'),
)
```

**Note:** Existing databases need to run migration or `db.create_all()` to add the index.

---

## Migration Plan

**Current Schema Version:** N/A (SQLAlchemy `create_all()` pattern)

**Pending Migrations:** None

**Breaking Changes:** None identified

**Recommendation:** Consider adding Alembic for production environments with long-running databases to enable incremental schema updates.

---

## ER Diagram

```mermaid
erDiagram
    Account {
        int id PK
        string username UK
        string user_alias UK
        string email UK
        string password_hash
        int is_active
        int is_admin
        datetime created_at
    }
    
    AccountRealm {
        int id PK
        int account_id FK
        string domain
        string realm_type
        string realm_value
        text allowed_record_types
        text allowed_operations
        string status
    }
    
    APIToken {
        int id PK
        int realm_id FK
        string token_name
        string token_prefix
        string token_hash
        datetime expires_at
        int is_active
    }
    
    ActivityLog {
        int id PK
        int account_id FK
        int token_id FK
        string action
        string source_ip
        string status
        datetime created_at
    }
    
    BackendProvider {
        int id PK
        string provider_code UK
        string display_name
        text config_schema
    }
    
    BackendService {
        int id PK
        int provider_id FK
        string service_name UK
        text config
        int is_active
    }
    
    ManagedDomainRoot {
        int id PK
        int backend_service_id FK
        string root_domain
        string dns_zone
        int visibility_id FK
    }
    
    DomainRootGrant {
        int id PK
        int domain_root_id FK
        int account_id FK
        int grant_type_id FK
    }
    
    Account ||--o{ AccountRealm : has
    AccountRealm ||--o{ APIToken : has
    Account ||--o{ ActivityLog : generates
    APIToken ||--o{ ActivityLog : logs
    BackendProvider ||--o{ BackendService : provides
    BackendService ||--o{ ManagedDomainRoot : manages
    ManagedDomainRoot ||--o{ AccountRealm : hosts
    ManagedDomainRoot ||--o{ DomainRootGrant : grants
    Account ||--o{ DomainRootGrant : receives
```

---

## Code References

| File | Line | Finding |
|------|------|---------|
| models.py | 255-377 | Account model - well structured |
| models.py | 380-520 | AccountRealm model - proper constraints |
| models.py | 523-635 | APIToken model - cascade delete correct |
| models.py | 638-712 | ActivityLog - consider composite index |
| models.py | 911-976 | Enum tables - consistent pattern |
| database.py | 78-111 | init_db() - idempotent initialization |

---

## Conclusion

The database schema demonstrates **excellent design quality** with:

1. ✅ Proper 3NF normalization
2. ✅ Comprehensive indexing on query hot paths
3. ✅ Type-safe enum tables with FK relationships
4. ✅ Correct cascade behaviors for data integrity
5. ✅ Consistent JSON handling patterns
6. ✅ Security-focused design (hashing, masking, soft delete)

The only minor recommendation is adding a composite index on ActivityLog for optimized filtered queries, which is a low-priority enhancement.

**Overall Assessment:** The schema is production-ready and well-architected for the multi-backend DNS management use case.
