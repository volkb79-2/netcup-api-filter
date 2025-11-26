# E2E Test Refactoring Example

## Problem
E2E tests manually fill forms, leading to maintenance burden and brittleness when UI changes.

## Solution Pattern

### Before (Manual Form Filling) ❌

```python
async def test_e2e_dns_client_views_records(mock_netcup_api_server, mock_netcup_credentials):
    """Test client can view DNS records for allowed domain."""
    
    async with browser_session() as browser:
        # Admin logs in and configures Netcup API
        await workflows.ensure_admin_dashboard(browser)
        await browser.goto(settings.url("/admin/netcup_config/"))
        await asyncio.sleep(1)
        
        # Configure Netcup API manually...
        await browser.fill('input[name="customer_id"]', str(mock_netcup_credentials['customer_id']))
        await browser.fill('input[name="api_key"]', mock_netcup_credentials['api_key'])
        await browser.fill('input[name="api_password"]', mock_netcup_credentials['api_password'])
        await browser.fill('input[name="api_url"]', mock_netcup_api_server.url)
        submit_btn = await browser.query_selector('button[type="submit"]')
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(1)
        
        # Create client manually (20+ lines)...
        test_domain = "test.example.com"
        await browser.goto(settings.url("/admin/client/new/"))
        await asyncio.sleep(1)
        await browser.fill('input[name="client_id"]', 'dns_read_client')
        
        # PROBLEM: Field selectors can break when UI changes
        realm_type_select = await browser.query_selector('select[name="realm_type"]')
        if realm_type_select:
            await realm_type_select.select_option('host')
        
        await browser.fill('input[name="realm_value"]', test_domain)
        ops_select = await browser.query_selector('select[name="allowed_operations"]')
        if ops_select:
            await ops_select.select_option(['read'])
        
        record_types_select = await browser.query_selector('select[name="allowed_record_types"]')
        if record_types_select:
            await record_types_select.select_option(['A', 'AAAA'])
        
        submit_btn = await browser.query_selector('button[type="submit"]')
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(1)
        
        # Extract token from flash message
        flash_text = await browser.text('.alert-success')
        token_match = re.search(r'Secret token.*?:\s*([A-Za-z0-9_-]+)', flash_text)
        assert token_match, f"Could not extract token from: {flash_text}"
        client_token = token_match.group(1)
        
        # ... rest of test ...
```

**Issues with this approach:**
- 40+ lines of form filling code
- Brittle CSS selectors
- Hard to maintain when UI changes
- Duplicated across many tests
- No type safety
- Manual error handling

### After (Workflow Helpers) ✅

```python
from ui_tests.workflows import (
    ensure_admin_dashboard,
    open_admin_client_create,
    submit_client_form,
    ClientFormData,
    configure_netcup_api_for_testing,
    test_client_login_with_token
)

async def test_e2e_dns_client_views_records(mock_netcup_api_server, mock_netcup_credentials):
    """Test client can view DNS records for allowed domain."""
    
    async with browser_session() as browser:
        # Configure Netcup API - single workflow call
        await ensure_admin_dashboard(browser)
        await configure_netcup_api_for_testing(
            browser,
            api_url=mock_netcup_api_server.url,
            credentials=mock_netcup_credentials
        )
        
        # Create client - structured data with type safety
        await open_admin_client_create(browser)
        
        test_domain = "test.example.com"
        client_data = ClientFormData(
            client_id='dns_read_client',
            description='Client for DNS read testing',
            realm_type='host',
            realm_value=test_domain,
            record_types=['A', 'AAAA'],
            operations=['read']
        )
        
        # Submit and get token - single workflow call
        success_msg = await submit_client_form(browser, client_data)
        token_match = re.search(r'Secret token.*?:\s*([A-Za-z0-9_-]+)', success_msg)
        assert token_match, f"Could not extract token from: {success_msg}"
        client_token = token_match.group(1)
        
        # Client login - single workflow call
        await test_client_login_with_token(
            browser, 
            token=client_token,
            expected_client_id='dns_read_client'
        )
        
        # Now test actual DNS operations...
        # ... rest of test ...
```

**Benefits:**
- 15 lines instead of 40+
- Type-safe structured data
- Centralized selectors
- Easy to update when UI changes
- Self-documenting
- Reusable across tests

## New Workflow Helper Needed

Since `configure_netcup_api_for_testing` doesn't exist yet, here's how to add it:

```python
# Add to ui_tests/workflows.py

async def configure_netcup_api_for_testing(
    browser: Browser,
    api_url: str,
    credentials: dict
) -> None:
    """Configure Netcup API settings for testing with mock server.
    
    Args:
        browser: Browser instance
        api_url: URL of mock Netcup API server
        credentials: Dict with customer_id, api_key, api_password
    """
    await browser.goto(settings.url("/admin/netcup_config/"))
    await anyio.sleep(0.5)
    
    await browser.fill('input[name="customer_id"]', str(credentials['customer_id']))
    await browser.fill('input[name="api_key"]', credentials['api_key'])
    await browser.fill('input[name="api_password"]', credentials['api_password'])
    await browser.fill('input[name="api_url"]', api_url)
    
    await browser.submit('form')
    await anyio.sleep(0.5)
    
    # Verify configuration saved
    body_text = await browser.text('body')
    if 'error' in body_text.lower():
        raise AssertionError(f"Failed to configure Netcup API: {body_text[:200]}")
```

## Migration Checklist

For each E2E test file:

- [ ] Import workflow helpers at top
- [ ] Replace manual `ensure_admin_dashboard` calls (already done)
- [ ] Replace manual Netcup API config with `configure_netcup_api_for_testing`
- [ ] Replace manual client creation with `ClientFormData` + `submit_client_form`
- [ ] Replace manual client login with `test_client_login_with_token`
- [ ] Remove duplicate CSS selectors
- [ ] Remove excessive `asyncio.sleep()` calls
- [ ] Test and verify

## Files to Update (Priority Order)

1. ✅ **test_e2e_dns.py** - Most complex, do first as template
2. **test_e2e_email.py** - Similar pattern
3. **test_e2e_with_mock_api.py** - Already partially using workflows
4. **test_ui_comprehensive.py** - Only 4 tests need updates

## Expected Impact

- **Code reduction**: ~500 lines → ~200 lines (-60%)
- **Maintainability**: Centralized selectors, single update point
- **Pass rate**: 63% → 86%+ after updates
- **Development speed**: Faster to write new tests
- **Reliability**: Less brittle, fewer timeout issues

---

*Example created: November 23, 2025*
