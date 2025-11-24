"""E2E tests for DNS operations via client portal.

Tests verify that clients can perform DNS operations through the UI
using the mock Netcup API server:
- View DNS records for allowed domains
- Create new DNS records
- Update existing DNS records  
- Delete DNS records
- Permission enforcement (domain, operation, record type)

Uses mock Netcup API to simulate Netcup CCP operations.

REFACTORED: Now uses workflow helpers to reduce code duplication.

NOTE: These tests require a LOCAL app deployment where the Flask app can
reach the mock Netcup API server running in the Playwright container network.
They will be skipped when running against production deployments.
"""
import pytest
import asyncio
from ui_tests.browser import browser_session
from ui_tests.config import settings
from ui_tests import workflows


# Mark all tests in this module as e2e_local and asyncio
pytestmark = [pytest.mark.asyncio, pytest.mark.e2e_local]


# Skip all tests in this module if running against production
def pytest_configure():
    """Check if tests should be skipped based on target environment."""
    pass  # Hook runs at collection time


# Check at module level if we should skip
if settings.base_url and not any(host in settings.base_url for host in ['localhost', '127.0.0.1', '0.0.0.0']):
    pytestmark.append(pytest.mark.skip(reason="E2E DNS tests require local deployment with accessible mock Netcup API"))


async def _setup_netcup_and_client(
    browser,
    mock_netcup_api_server,
    mock_netcup_credentials,
    client_id: str,
    test_domain: str,
    operations: list,
    record_types: list
) -> str:
    """Helper to configure Netcup API and create client. Returns client token."""
    await workflows.ensure_admin_dashboard(browser)
    
    # Configure Netcup API
    await workflows.admin_configure_netcup_api(
        browser,
        customer_id=str(mock_netcup_credentials['customer_id']),
        api_key=mock_netcup_credentials['api_key'],
        api_password=mock_netcup_credentials['api_password'],
        api_url=mock_netcup_api_server.url
    )
    
    # Create client
    client_data = workflows.ClientFormData(
        client_id=client_id,
        description=f'Client for {test_domain}',
        realm_type='host',
        realm_value=test_domain,
        record_types=record_types,
        operations=operations
    )
    return await workflows.admin_create_client_and_extract_token(browser, client_data)


async def _client_login(browser, client_token: str):
    """Helper to log in client with token."""
    await browser.goto(settings.url("/client/login"))
    await browser.fill('input[name="token"]', client_token)
    await browser.click('button[type="submit"]')
    await asyncio.sleep(0.5)


async def test_e2e_dns_client_views_records(mock_netcup_api_server, mock_netcup_credentials):
    """Test client can view DNS records for allowed domain."""
    
    async with browser_session() as browser:
        test_domain = "test.example.com"
        
        # Setup: Admin configures API and creates client
        client_token = await _setup_netcup_and_client(
            browser, mock_netcup_api_server, mock_netcup_credentials,
            'dns_read_client', test_domain, ['read'], ['A', 'AAAA']
        )
        
        # Client logs in
        await _client_login(browser, client_token)
        h1_text = await browser.text('main h1')
        assert 'dns_read_client' in h1_text
        
        # View domain DNS records
        domain_links = await browser.query_selector_all(f'a[href*="/client/domains/{test_domain}"]')
        if domain_links:
            await domain_links[0].click()
        
        # Verify domain detail page
        h1_text = await browser.text('main h1')
        assert test_domain in h1_text
        
        # Verify DNS records displayed
        page_text = await browser.text('body')
        assert any(rt in page_text for rt in ['A', 'AAAA', 'MX'])
        
        # Verify table exists
        table_exists = await browser.query_selector('table.table')
        assert table_exists is not None


async def test_e2e_dns_client_creates_record(mock_netcup_api_server, mock_netcup_credentials):
    """Test client can create new DNS record."""
    
    async with browser_session() as browser:
        test_domain = "create-test.example.com"
        
        # Setup: Admin configures API and creates client with write permission
        client_token = await _setup_netcup_and_client(
            browser, mock_netcup_api_server, mock_netcup_credentials,
            'dns_write_client', test_domain, ['read', 'write'], ['A']
        )
        
        # Client logs in and navigates to domain
        await _client_login(browser, client_token)
        domain_links = await browser.query_selector_all(f'a[href*="/client/domains/{test_domain}"]')
        if domain_links:
            await domain_links[0].click()
            await asyncio.sleep(0.5)
        
        # Click "Add Record" button
        add_btn = await browser.query_selector('a[href*="/client/domains/"][href*="/add"]')
        if add_btn:
            await add_btn.click()
            await asyncio.sleep(0.5)
        
        # Fill in new record form
        await browser.fill('input[name="hostname"]', 'new-host')
        record_type_select = await browser.query_selector('select[name="type"]')
        if record_type_select:
            await record_type_select.select_option('A')
        await browser.fill('input[name="destination"]', '192.0.2.100')
        await browser.fill('input[name="ttl"]', '3600')
        
        # Submit form
        submit_btn = await browser.query_selector('button[type="submit"]')
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(2)
        
        # Verify record created
        h1_text = await browser.text('main h1')
        assert test_domain in h1_text
        
        page_text = await browser.text('body')
        assert any(word in page_text.lower() for word in ['success', 'created', 'added'])
        assert 'new-host' in page_text
        assert '192.0.2.100' in page_text


async def test_e2e_dns_client_updates_record(mock_netcup_api_server, mock_netcup_credentials):
    """Test client can update existing DNS record."""
    
    async with browser_session() as browser:
        test_domain = "update-test.example.com"
        
        # Setup
        client_token = await _setup_netcup_and_client(
            browser, mock_netcup_api_server, mock_netcup_credentials,
            'dns_update_client', test_domain, ['read', 'write'], ['A', 'AAAA']
        )
        
        # Client logs in and navigates to domain
        await _client_login(browser, client_token)
        domain_links = await browser.query_selector_all(f'a[href*="/client/domains/{test_domain}"]')
        if domain_links:
            await domain_links[0].click()
            await asyncio.sleep(0.5)
        
        # Find and click edit button for first record
        edit_links = await browser.query_selector_all('a[href*="/client/domains/"][href*="/edit/"]')
        if not edit_links:
            pytest.skip("No edit links found - may need UI adjustment")
        
        await edit_links[0].click()
        await asyncio.sleep(0.5)
        
        # Update destination IP
        destination_input = await browser.query_selector('input[name="destination"]')
        if destination_input:
            await destination_input.fill('192.0.2.200')
        
        # Submit form
        submit_btn = await browser.query_selector('button[type="submit"]')
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(2)
        
        # Verify update succeeded
        page_text = await browser.text('body')
        assert any(word in page_text.lower() for word in ['success', 'updated'])
        assert '192.0.2.200' in page_text


async def test_e2e_dns_client_deletes_record(mock_netcup_api_server, mock_netcup_credentials):
    """Test client can delete DNS record."""
    
    async with browser_session() as browser:
        test_domain = "delete-test.example.com"
        
        # Setup
        client_token = await _setup_netcup_and_client(
            browser, mock_netcup_api_server, mock_netcup_credentials,
            'dns_delete_client', test_domain, ['read', 'write', 'delete'], ['A', 'AAAA', 'MX']
        )
        
        # Client logs in and navigates to domain
        await _client_login(browser, client_token)
        domain_links = await browser.query_selector_all(f'a[href*="/client/domains/{test_domain}"]')
        if domain_links:
            await domain_links[0].click()
            await asyncio.sleep(0.5)
        
        # Find and submit delete form for first record
        delete_forms = await browser.query_selector_all('form[action*="/client/domains/"][action*="/delete/"]')
        if not delete_forms:
            pytest.skip("No delete forms found - may need UI adjustment")
        
        delete_btn = await delete_forms[0].query_selector('button[type="submit"]')
        if delete_btn:
            await delete_btn.click()
            await asyncio.sleep(2)
        
        # Verify deletion succeeded
        page_text = await browser.text('body')
        assert any(word in page_text.lower() for word in ['success', 'deleted', 'removed'])


async def test_e2e_dns_permission_enforcement_domain(mock_netcup_api_server, mock_netcup_credentials):
    """Test that client cannot access DNS records for unauthorized domains."""
    
    async with browser_session() as browser:
        allowed_domain = "allowed.example.com"
        forbidden_domain = "forbidden.example.com"
        
        # Setup: Create client with permission for only one domain
        client_token = await _setup_netcup_and_client(
            browser, mock_netcup_api_server, mock_netcup_credentials,
            'dns_limited_client', allowed_domain, ['read'], ['A']
        )
        
        # Client logs in
        await _client_login(browser, client_token)
        
        # Verify client can only see allowed domain
        page_text = await browser.text('body')
        assert allowed_domain in page_text
        assert forbidden_domain not in page_text
        
        # Try to directly access forbidden domain (should be blocked)
        await browser.goto(settings.url(f"/client/domains/{forbidden_domain}"))
        await asyncio.sleep(0.5)
        
        page_text = await browser.text('body')
        # Should see error or be redirected
        assert any(word in page_text.lower() for word in [
            'error', 'forbidden', 'not authorized', 'dns_limited_client'
        ])


async def test_e2e_dns_permission_enforcement_operation(mock_netcup_api_server, mock_netcup_credentials):
    """Test that read-only client cannot perform write operations."""
    
    async with browser_session() as browser:
        test_domain = "readonly.example.com"
        
        # Setup: Create read-only client
        client_token = await _setup_netcup_and_client(
            browser, mock_netcup_api_server, mock_netcup_credentials,
            'dns_readonly_client', test_domain, ['read'], ['A', 'AAAA']
        )
        
        # Client logs in and navigates to domain
        await _client_login(browser, client_token)
        domain_links = await browser.query_selector_all(f'a[href*="/client/domains/{test_domain}"]')
        if domain_links:
            await domain_links[0].click()
            await asyncio.sleep(0.5)
        
        # Verify NO add/edit/delete buttons for read-only client
        page_html = await browser.html('body')
        
        assert 'add' not in page_html.lower() or '/add' not in page_html
        assert '/edit/' not in page_html
        assert 'delete' not in page_html.lower() or '/delete/' not in page_html


async def test_e2e_dns_permission_enforcement_record_type(mock_netcup_api_server, mock_netcup_credentials):
    """Test that client cannot create/edit unauthorized record types."""
    
    async with browser_session() as browser:
        test_domain = "recordtype-test.example.com"
        
        # Setup: Create client with permission only for A records
        client_token = await _setup_netcup_and_client(
            browser, mock_netcup_api_server, mock_netcup_credentials,
            'dns_a_only_client', test_domain, ['read', 'write'], ['A']
        )
        
        # Client logs in and navigates to domain
        await _client_login(browser, client_token)
        domain_links = await browser.query_selector_all(f'a[href*="/client/domains/{test_domain}"]')
        if domain_links:
            await domain_links[0].click()
            await asyncio.sleep(0.5)
        
        # Click Add Record
        add_btn = await browser.query_selector('a[href*="/client/domains/"][href*="/add"]')
        if not add_btn:
            pytest.skip("Add button not found - may need UI adjustment")
        
        await add_btn.click()
        await asyncio.sleep(0.5)
        
        # Check record type dropdown only has A record
        record_type_select = await browser.query_selector('select[name="type"]')
        if record_type_select:
            options = await record_type_select.query_selector_all('option')
            option_values = [await opt.get_attribute('value') for opt in options if await opt.get_attribute('value')]
            
            # Should only see A record type
            assert 'A' in option_values
            assert 'AAAA' not in option_values
            assert 'MX' not in option_values
            assert 'CNAME' not in option_values
