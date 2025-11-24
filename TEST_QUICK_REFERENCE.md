# Test Suite Quick Reference

## Current Status: 57/90 Passing (63%)

### Run All Tests
```bash
export UI_ADMIN_PASSWORD="TestAdmin123!"
docker exec -w /workspace \
  -e PYTHONPATH=/workspace \
  -e UI_BASE_URL="${UI_BASE_URL}" \
  -e UI_ADMIN_USERNAME="${UI_ADMIN_USERNAME}" \
  -e UI_ADMIN_PASSWORD="${UI_ADMIN_PASSWORD}" \
  -e UI_CLIENT_ID="${UI_CLIENT_ID}" \
  -e UI_CLIENT_TOKEN="${UI_CLIENT_TOKEN}" \
  -e UI_CLIENT_DOMAIN="${UI_CLIENT_DOMAIN}" \
  playwright python3 -m pytest ui_tests/tests -v
```

### Run Specific Module
```bash
# Perfect modules (100% pass rate)
pytest ui_tests/tests/test_api_proxy.py -v         # API filtering
pytest ui_tests/tests/test_audit_logs.py -v        # Audit logs
pytest ui_tests/tests/test_mock_smtp.py -v         # SMTP mock
pytest ui_tests/tests/test_mock_api_standalone.py -v # Netcup mock

# Excellent modules (90%+ pass rate)
pytest ui_tests/tests/test_admin_ui.py -v          # Admin UI

# Working modules (70%+ pass rate)
pytest ui_tests/tests/test_ui_comprehensive.py -v  # UI validation

# Known failing (need refactoring)
pytest ui_tests/tests/test_e2e_dns.py -v           # E2E DNS workflows
pytest ui_tests/tests/test_e2e_email.py -v         # E2E email workflows
pytest ui_tests/tests/test_client_ui.py -v         # Client portal
```

### Quick Health Check
```bash
# Run only passing modules (~60 tests in ~1 minute)
pytest ui_tests/tests/test_admin_ui.py \
       ui_tests/tests/test_api_proxy.py \
       ui_tests/tests/test_audit_logs.py \
       ui_tests/tests/test_mock_smtp.py \
       ui_tests/tests/test_mock_api_standalone.py \
       -v --tb=no
```

## Module Health Status

| Module | Tests | Status | Ready for CI? |
|--------|-------|--------|---------------|
| test_api_proxy | 8 | ✅ 100% | Yes |
| test_audit_logs | 4 | ✅ 100% | Yes |
| test_mock_api_standalone | 4 | ✅ 100% | Yes |
| test_mock_smtp | 10 | ✅ 100% | Yes |
| test_admin_ui | 10 | ✅ 90% | Yes |
| test_ui_comprehensive | 27 | 🟢 70% | Partial |
| test_end_to_end | 3 | 🟡 33% | No |
| test_e2e_with_mock_api | 5 | 🟡 40% | No |
| test_client_ui | 4 | 🔴 0% | No |
| test_e2e_dns | 7 | 🔴 0% | No |
| test_e2e_email | 8 | 🔴 0% | No |

## Infrastructure Status

✅ **Production Ready**:
- Test collection (all 90 tests discovered)
- Mock Netcup API server (127.0.0.1:5555)
- Mock SMTP server (127.0.0.1:1025)
- Browser automation (Playwright)
- Test fixtures and configuration
- Workflow helpers (admin login, navigation)

🔧 **Needs Work**:
- Client token authentication (5 tests blocked)
- E2E workflow refactoring (22 tests need updates)
- CSS selector updates (4 tests minor fixes)

## Common Issues & Fixes

### Issue: "Invalid token or token is inactive"
**Affected**: test_client_ui.py (4 tests)  
**Fix**: Debug preseeded test client in database
```python
# Check if test client exists
from database import db, Client
client = Client.query.filter_by(client_id='test_qweqweqwe_vi').first()
print(f"Active: {client.is_active if client else 'NOT FOUND'}")
```

### Issue: "Timeout waiting for .alert-success"
**Affected**: test_e2e_dns.py, test_e2e_email.py (15 tests)  
**Fix**: Use workflow helpers instead of manual form filling
```python
# ❌ Don't do this
await browser.fill('input[name="client_id"]', 'test')
# ... 20 more lines ...
await browser.text('.alert-success')

# ✅ Do this
from ui_tests.workflows import submit_client_form, ClientFormData
data = ClientFormData(client_id='test', realm_value='example.com')
success_msg = await submit_client_form(browser, data)
```

### Issue: "Timeout waiting for element"
**Affected**: Various tests  
**Fix**: Check CSS selectors match current UI
```python
# Common selector patterns that work:
'main h1'              # Page heading
'table tbody'          # Table content
'.alert-success'       # Success messages
'button[type="submit"]' # Submit buttons
'#client_id'           # Form fields (by ID)
```

## Test Writing Guidelines

### Use Workflow Helpers
```python
from ui_tests.workflows import (
    ensure_admin_dashboard,      # Login and verify dashboard
    open_admin_client_create,    # Navigate to client form
    submit_client_form,          # Fill and submit client form
    ClientFormData,              # Structured client data
)

# Example usage
async with browser_session() as browser:
    await ensure_admin_dashboard(browser)
    await open_admin_client_create(browser)
    
    data = ClientFormData(
        client_id='test_client',
        realm_value='example.com',
        record_types=['A', 'AAAA'],
        operations=['read']
    )
    success_msg = await submit_client_form(browser, data)
```

### Don't Use Manual Selectors
```python
# ❌ Brittle and hard to maintain
realm_type_select = await browser.query_selector('select[name="realm_type"]')
if realm_type_select:
    await realm_type_select.select_option('host')

# ✅ Use workflow helpers or browser.select()
await browser.select('select[name="realm_type"]', 'host')
```

## Documentation

- **TEST_SUITE_STATUS.md** - Comprehensive status report
- **TEST_FIXES_NEEDED.md** - Detailed fix instructions
- **TEST_REFACTORING_EXAMPLE.md** - Before/after code examples

## Next Steps

1. **Immediate**: Debug client token auth → +5 tests passing
2. **High Priority**: Refactor E2E DNS tests → +7 tests passing
3. **Medium Priority**: Refactor E2E email tests → +8 tests passing
4. **Polish**: Fix UI comprehensive selectors → +4 tests passing

**Target: 85/90 passing (94%)**

---
*Last Updated: November 23, 2025*
