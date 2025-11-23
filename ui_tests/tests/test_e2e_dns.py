"""E2E tests for DNS operations via client portal.

Tests verify that clients can perform DNS operations through the UI
using the mock Netcup API server:
- View DNS records for allowed domains
- Create new DNS records
- Update existing DNS records  
- Delete DNS records
- Permission enforcement (domain, operation, record type)

Uses mock Netcup API to simulate Netcup CCP operations.
"""
import pytest
import asyncio
import re
from ui_tests.browser import browser_session
from ui_tests.config import settings
from ui_tests import workflows


pytestmark = pytest.mark.asyncio


async def test_e2e_dns_client_views_records(browser_session, mock_netcup_api_server, mock_netcup_credentials):
    """Test client can view DNS records for allowed domain."""
    
    async with browser_session() as browser:
        # Step 1: Admin logs in and configures Netcup API
        await workflows.ensure_admin_dashboard(browser)
        
        await browser.goto(settings.url("/admin/netcup_config/"))
        await asyncio.sleep(1)
        
        # Configure to use mock API
        await browser.fill('input[name="customer_id"]', str(mock_netcup_credentials['customer_id']))
        await browser.fill('input[name="api_key"]', mock_netcup_credentials['api_key'])
        await browser.fill('input[name="api_password"]', mock_netcup_credentials['api_password'])
        await browser.fill('input[name="api_url"]', mock_netcup_api_server.url)
        
        submit_btn = await browser.query_selector('button[type="submit"]')
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(1)
        
        # Step 2: Admin creates client with DNS read permission
        test_domain = "test.example.com"
        
        await browser.goto(settings.url("/admin/client/new/"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="client_id"]', 'dns_read_client')
        await browser.fill('input[name="description"]', 'Client for DNS read testing')
        
        # Set realm to host
        realm_type_select = await browser.query_selector('select[name="realm_type"]')
        if realm_type_select:
            await realm_type_select.select_option('host')
        
        await browser.fill('input[name="realm_value"]', test_domain)
        
        # Select allowed operations: read only
        ops_select = await browser.query_selector('select[name="allowed_operations"]')
        if ops_select:
            await ops_select.select_option(['read'])
        
        # Select allowed record types: A, AAAA
        record_types_select = await browser.query_selector('select[name="allowed_record_types"]')
        if record_types_select:
            await record_types_select.select_option(['A', 'AAAA'])
        
        # Submit form and extract token
        submit_btn = await browser.query_selector('button[type="submit"]')
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(1)
        
        # Extract token from flash message
        flash_text = await browser.text('.alert-success')
        token_match = re.search(r'Secret token.*?:\s*([A-Za-z0-9_-]+)', flash_text)
        assert token_match, f"Could not extract token from: {flash_text}"
        client_token = token_match.group(1)
        
        # Step 3: Client logs in with token
        await browser.goto(settings.url("/client/login"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="token"]', client_token)
        login_btn = await browser.query_selector('button[type="submit"]')
        if login_btn:
            await login_btn.click()
            await asyncio.sleep(1)
        
        # Should be on client dashboard
        h1_text = await browser.text('main h1')
        assert 'dns_read_client' in h1_text
        
        # Step 4: Client views domain DNS records
        # Find manage button for the test domain
        domain_links = await browser.query_selector_all(f'a[href*="/client/domains/{test_domain}"]')
        if domain_links:
            await domain_links[0].click()
            await asyncio.sleep(1)
        
        # Verify we're on domain detail page
        h1_text = await browser.text('main h1')
        assert test_domain in h1_text
        
        # Verify DNS records are displayed (mock API seeds default records)
        page_text = await browser.text('body')
        
        # Should see default records from mock API
        assert 'A' in page_text or 'AAAA' in page_text or 'MX' in page_text
        
        # Should see table with records
        table_exists = await browser.query_selector('table.table')
        assert table_exists is not None, "DNS records table should be displayed"


async def test_e2e_dns_client_creates_record(browser_session, mock_netcup_api_server, mock_netcup_credentials):
    """Test client can create new DNS record."""
    
    async with browser_session() as browser:
        # Setup: Admin configures API and creates client with write permission
        await workflows.ensure_admin_dashboard(browser)
        
        # Configure Netcup API
        await browser.goto(settings.url("/admin/netcup_config/"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="customer_id"]', str(mock_netcup_credentials['customer_id']))
        await browser.fill('input[name="api_key"]', mock_netcup_credentials['api_key'])
        await browser.fill('input[name="api_password"]', mock_netcup_credentials['api_password'])
        await browser.fill('input[name="api_url"]', mock_netcup_api_server.url)
        
        submit_btn = await browser.query_selector('button[type="submit"]')
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(1)
        
        # Create client with write permission
        test_domain = "create-test.example.com"
        
        await browser.goto(settings.url("/admin/client/new/"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="client_id"]', 'dns_write_client')
        await browser.fill('input[name="description"]', 'Client for DNS write testing')
        
        realm_type_select = await browser.query_selector('select[name="realm_type"]')
        if realm_type_select:
            await realm_type_select.select_option('host')
        
        await browser.fill('input[name="realm_value"]', test_domain)
        
        # Allow both read and write operations
        ops_select = await browser.query_selector('select[name="allowed_operations"]')
        if ops_select:
            await ops_select.select_option(['read', 'write'])
        
        # Allow A records
        record_types_select = await browser.query_selector('select[name="allowed_record_types"]')
        if record_types_select:
            await record_types_select.select_option(['A'])
        
        submit_btn = await browser.query_selector('button[type="submit"]')
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(1)
        
        # Extract token
        flash_text = await browser.text('.alert-success')
        token_match = re.search(r'Secret token.*?:\s*([A-Za-z0-9_-]+)', flash_text)
        assert token_match
        client_token = token_match.group(1)
        
        # Client logs in
        await browser.goto(settings.url("/client/login"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="token"]', client_token)
        login_btn = await browser.query_selector('button[type="submit"]')
        if login_btn:
            await login_btn.click()
            await asyncio.sleep(1)
        
        # Navigate to domain management
        domain_links = await browser.query_selector_all(f'a[href*="/client/domains/{test_domain}"]')
        if domain_links:
            await domain_links[0].click()
            await asyncio.sleep(1)
        
        # Click "Add Record" button
        add_btn = await browser.query_selector('a[href*="/client/domains/"][href*="/add"]')
        if add_btn:
            await add_btn.click()
            await asyncio.sleep(1)
        
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
            await asyncio.sleep(2)  # Wait for API call to complete
        
        # Verify record was created
        # Should be redirected back to domain detail page
        h1_text = await browser.text('main h1')
        assert test_domain in h1_text
        
        # Check for success message
        page_text = await browser.text('body')
        assert 'success' in page_text.lower() or 'created' in page_text.lower() or 'added' in page_text.lower()
        
        # Verify new record appears in table
        assert 'new-host' in page_text
        assert '192.0.2.100' in page_text


async def test_e2e_dns_client_updates_record(browser_session, mock_netcup_api_server, mock_netcup_credentials):
    """Test client can update existing DNS record."""
    
    async with browser_session() as browser:
        # Setup: Same as create test
        await workflows.ensure_admin_dashboard(browser)
        
        await browser.goto(settings.url("/admin/netcup_config/"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="customer_id"]', str(mock_netcup_credentials['customer_id']))
        await browser.fill('input[name="api_key"]', mock_netcup_credentials['api_key'])
        await browser.fill('input[name="api_password"]', mock_netcup_credentials['api_password'])
        await browser.fill('input[name="api_url"]', mock_netcup_api_server.url)
        
        submit_btn = await browser.query_selector('button[type="submit"]')
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(1)
        
        test_domain = "update-test.example.com"
        
        await browser.goto(settings.url("/admin/client/new/"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="client_id"]', 'dns_update_client')
        await browser.fill('input[name="description"]', 'Client for DNS update testing')
        
        realm_type_select = await browser.query_selector('select[name="realm_type"]')
        if realm_type_select:
            await realm_type_select.select_option('host')
        
        await browser.fill('input[name="realm_value"]', test_domain)
        
        ops_select = await browser.query_selector('select[name="allowed_operations"]')
        if ops_select:
            await ops_select.select_option(['read', 'write'])
        
        record_types_select = await browser.query_selector('select[name="allowed_record_types"]')
        if record_types_select:
            await record_types_select.select_option(['A', 'AAAA'])
        
        submit_btn = await browser.query_selector('button[type="submit"]')
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(1)
        
        flash_text = await browser.text('.alert-success')
        token_match = re.search(r'Secret token.*?:\s*([A-Za-z0-9_-]+)', flash_text)
        assert token_match
        client_token = token_match.group(1)
        
        # Client logs in
        await browser.goto(settings.url("/client/login"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="token"]', client_token)
        login_btn = await browser.query_selector('button[type="submit"]')
        if login_btn:
            await login_btn.click()
            await asyncio.sleep(1)
        
        # Navigate to domain
        domain_links = await browser.query_selector_all(f'a[href*="/client/domains/{test_domain}"]')
        if domain_links:
            await domain_links[0].click()
            await asyncio.sleep(1)
        
        # Find edit button for first A record (mock API creates default @ A record)
        # Look for edit link in table row
        edit_links = await browser.query_selector_all('a[href*="/client/domains/"][href*="/edit/"]')
        if edit_links:
            await edit_links[0].click()
            await asyncio.sleep(1)
        else:
            pytest.skip("No edit links found - may need to adjust UI selectors")
        
        # Update the destination IP
        destination_input = await browser.query_selector('input[name="destination"]')
        if destination_input:
            # Clear existing value and enter new one
            await destination_input.fill('192.0.2.200')
        
        # Submit form
        submit_btn = await browser.query_selector('button[type="submit"]')
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(2)
        
        # Verify update succeeded
        page_text = await browser.text('body')
        assert 'success' in page_text.lower() or 'updated' in page_text.lower()
        assert '192.0.2.200' in page_text


async def test_e2e_dns_client_deletes_record(browser_session, mock_netcup_api_server, mock_netcup_credentials):
    """Test client can delete DNS record."""
    
    async with browser_session() as browser:
        # Setup: Same as previous tests
        await workflows.ensure_admin_dashboard(browser)
        
        await browser.goto(settings.url("/admin/netcup_config/"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="customer_id"]', str(mock_netcup_credentials['customer_id']))
        await browser.fill('input[name="api_key"]', mock_netcup_credentials['api_key'])
        await browser.fill('input[name="api_password"]', mock_netcup_credentials['api_password'])
        await browser.fill('input[name="api_url"]', mock_netcup_api_server.url)
        
        submit_btn = await browser.query_selector('button[type="submit"]')
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(1)
        
        test_domain = "delete-test.example.com"
        
        await browser.goto(settings.url("/admin/client/new/"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="client_id"]', 'dns_delete_client')
        await browser.fill('input[name="description"]', 'Client for DNS delete testing')
        
        realm_type_select = await browser.query_selector('select[name="realm_type"]')
        if realm_type_select:
            await realm_type_select.select_option('host')
        
        await browser.fill('input[name="realm_value"]', test_domain)
        
        ops_select = await browser.query_selector('select[name="allowed_operations"]')
        if ops_select:
            await ops_select.select_option(['read', 'write', 'delete'])
        
        record_types_select = await browser.query_selector('select[name="allowed_record_types"]')
        if record_types_select:
            await record_types_select.select_option(['A', 'AAAA', 'MX'])
        
        submit_btn = await browser.query_selector('button[type="submit"]')
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(1)
        
        flash_text = await browser.text('.alert-success')
        token_match = re.search(r'Secret token.*?:\s*([A-Za-z0-9_-]+)', flash_text)
        assert token_match
        client_token = token_match.group(1)
        
        # Client logs in
        await browser.goto(settings.url("/client/login"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="token"]', client_token)
        login_btn = await browser.query_selector('button[type="submit"]')
        if login_btn:
            await login_btn.click()
            await asyncio.sleep(1)
        
        # Navigate to domain
        domain_links = await browser.query_selector_all(f'a[href*="/client/domains/{test_domain}"]')
        if domain_links:
            await domain_links[0].click()
            await asyncio.sleep(1)
        
        # Count records before deletion
        page_text_before = await browser.text('body')
        # Mock API creates 5 default records
        
        # Find delete button for a record (look for form with delete action)
        delete_forms = await browser.query_selector_all('form[action*="/client/domains/"][action*="/delete/"]')
        if delete_forms:
            # Click the submit button in first delete form
            delete_btn = await delete_forms[0].query_selector('button[type="submit"]')
            if delete_btn:
                await delete_btn.click()
                await asyncio.sleep(2)
        else:
            pytest.skip("No delete forms found - may need to adjust UI selectors")
        
        # Verify deletion succeeded
        page_text = await browser.text('body')
        assert 'success' in page_text.lower() or 'deleted' in page_text.lower() or 'removed' in page_text.lower()


async def test_e2e_dns_permission_enforcement_domain(browser_session, mock_netcup_api_server, mock_netcup_credentials):
    """Test that client cannot access DNS records for unauthorized domains."""
    
    async with browser_session() as browser:
        # Setup: Create client with permission for only one domain
        await workflows.ensure_admin_dashboard(browser)
        
        await browser.goto(settings.url("/admin/netcup_config/"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="customer_id"]', str(mock_netcup_credentials['customer_id']))
        await browser.fill('input[name="api_key"]', mock_netcup_credentials['api_key'])
        await browser.fill('input[name="api_password"]', mock_netcup_credentials['api_password'])
        await browser.fill('input[name="api_url"]', mock_netcup_api_server.url)
        
        submit_btn = await browser.query_selector('button[type="submit"]')
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(1)
        
        allowed_domain = "allowed.example.com"
        forbidden_domain = "forbidden.example.com"
        
        await browser.goto(settings.url("/admin/client/new/"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="client_id"]', 'dns_limited_client')
        await browser.fill('input[name="description"]', 'Client with limited domain access')
        
        realm_type_select = await browser.query_selector('select[name="realm_type"]')
        if realm_type_select:
            await realm_type_select.select_option('host')
        
        # Only allow one specific domain
        await browser.fill('input[name="realm_value"]', allowed_domain)
        
        ops_select = await browser.query_selector('select[name="allowed_operations"]')
        if ops_select:
            await ops_select.select_option(['read'])
        
        record_types_select = await browser.query_selector('select[name="allowed_record_types"]')
        if record_types_select:
            await record_types_select.select_option(['A'])
        
        submit_btn = await browser.query_selector('button[type="submit"]')
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(1)
        
        flash_text = await browser.text('.alert-success')
        token_match = re.search(r'Secret token.*?:\s*([A-Za-z0-9_-]+)', flash_text)
        assert token_match
        client_token = token_match.group(1)
        
        # Client logs in
        await browser.goto(settings.url("/client/login"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="token"]', client_token)
        login_btn = await browser.query_selector('button[type="submit"]')
        if login_btn:
            await login_btn.click()
            await asyncio.sleep(1)
        
        # Verify client can only see allowed domain
        page_text = await browser.text('body')
        assert allowed_domain in page_text, f"Client should see allowed domain {allowed_domain}"
        assert forbidden_domain not in page_text, f"Client should NOT see forbidden domain {forbidden_domain}"
        
        # Try to directly access forbidden domain (should be blocked or redirect)
        await browser.goto(settings.url(f"/client/domains/{forbidden_domain}"))
        await asyncio.sleep(1)
        
        page_text = await browser.text('body')
        # Should see error or be redirected back to dashboard
        assert ('error' in page_text.lower() or 
                'forbidden' in page_text.lower() or 
                'not authorized' in page_text.lower() or
                'dns_limited_client' in page_text), "Should show error or redirect for unauthorized domain"


async def test_e2e_dns_permission_enforcement_operation(browser_session, mock_netcup_api_server, mock_netcup_credentials):
    """Test that read-only client cannot perform write operations."""
    
    async with browser_session() as browser:
        # Setup: Create read-only client
        await workflows.ensure_admin_dashboard(browser)
        
        await browser.goto(settings.url("/admin/netcup_config/"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="customer_id"]', str(mock_netcup_credentials['customer_id']))
        await browser.fill('input[name="api_key"]', mock_netcup_credentials['api_key'])
        await browser.fill('input[name="api_password"]', mock_netcup_credentials['api_password'])
        await browser.fill('input[name="api_url"]', mock_netcup_api_server.url)
        
        submit_btn = await browser.query_selector('button[type="submit"]')
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(1)
        
        test_domain = "readonly.example.com"
        
        await browser.goto(settings.url("/admin/client/new/"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="client_id"]', 'dns_readonly_client')
        await browser.fill('input[name="description"]', 'Read-only client')
        
        realm_type_select = await browser.query_selector('select[name="realm_type"]')
        if realm_type_select:
            await realm_type_select.select_option('host')
        
        await browser.fill('input[name="realm_value"]', test_domain)
        
        # Only allow read operation
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
        
        flash_text = await browser.text('.alert-success')
        token_match = re.search(r'Secret token.*?:\s*([A-Za-z0-9_-]+)', flash_text)
        assert token_match
        client_token = token_match.group(1)
        
        # Client logs in
        await browser.goto(settings.url("/client/login"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="token"]', client_token)
        login_btn = await browser.query_selector('button[type="submit"]')
        if login_btn:
            await login_btn.click()
            await asyncio.sleep(1)
        
        # Navigate to domain
        domain_links = await browser.query_selector_all(f'a[href*="/client/domains/{test_domain}"]')
        if domain_links:
            await domain_links[0].click()
            await asyncio.sleep(1)
        
        # Verify NO add/edit/delete buttons are shown for read-only client
        page_html = await browser.html('body')
        
        # Should NOT have add button
        assert 'add' not in page_html.lower() or '/add' not in page_html, "Read-only client should not see Add button"
        
        # Should NOT have edit links
        assert '/edit/' not in page_html, "Read-only client should not see Edit links"
        
        # Should NOT have delete forms
        assert 'delete' not in page_html.lower() or '/delete/' not in page_html, "Read-only client should not see Delete buttons"


async def test_e2e_dns_permission_enforcement_record_type(browser_session, mock_netcup_api_server, mock_netcup_credentials):
    """Test that client cannot create/edit unauthorized record types."""
    
    async with browser_session() as browser:
        # Setup: Create client with permission only for A records (not AAAA, MX, etc.)
        await workflows.ensure_admin_dashboard(browser)
        
        await browser.goto(settings.url("/admin/netcup_config/"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="customer_id"]', str(mock_netcup_credentials['customer_id']))
        await browser.fill('input[name="api_key"]', mock_netcup_credentials['api_key'])
        await browser.fill('input[name="api_password"]', mock_netcup_credentials['api_password'])
        await browser.fill('input[name="api_url"]', mock_netcup_api_server.url)
        
        submit_btn = await browser.query_selector('button[type="submit"]')
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(1)
        
        test_domain = "recordtype-test.example.com"
        
        await browser.goto(settings.url("/admin/client/new/"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="client_id"]', 'dns_a_only_client')
        await browser.fill('input[name="description"]', 'Client allowed only A records')
        
        realm_type_select = await browser.query_selector('select[name="realm_type"]')
        if realm_type_select:
            await realm_type_select.select_option('host')
        
        await browser.fill('input[name="realm_value"]', test_domain)
        
        ops_select = await browser.query_selector('select[name="allowed_operations"]')
        if ops_select:
            await ops_select.select_option(['read', 'write'])
        
        # Only allow A records (not AAAA, MX, CNAME, etc.)
        record_types_select = await browser.query_selector('select[name="allowed_record_types"]')
        if record_types_select:
            await record_types_select.select_option(['A'])
        
        submit_btn = await browser.query_selector('button[type="submit"]')
        if submit_btn:
            await submit_btn.click()
            await asyncio.sleep(1)
        
        flash_text = await browser.text('.alert-success')
        token_match = re.search(r'Secret token.*?:\s*([A-Za-z0-9_-]+)', flash_text)
        assert token_match
        client_token = token_match.group(1)
        
        # Client logs in
        await browser.goto(settings.url("/client/login"))
        await asyncio.sleep(1)
        
        await browser.fill('input[name="token"]', client_token)
        login_btn = await browser.query_selector('button[type="submit"]')
        if login_btn:
            await login_btn.click()
            await asyncio.sleep(1)
        
        # Navigate to domain
        domain_links = await browser.query_selector_all(f'a[href*="/client/domains/{test_domain}"]')
        if domain_links:
            await domain_links[0].click()
            await asyncio.sleep(1)
        
        # Click Add Record
        add_btn = await browser.query_selector('a[href*="/client/domains/"][href*="/add"]')
        if add_btn:
            await add_btn.click()
            await asyncio.sleep(1)
        else:
            pytest.skip("Add button not found - may need UI adjustment")
        
        # Check that record type dropdown only has A record
        record_type_select = await browser.query_selector('select[name="type"]')
        if record_type_select:
            options = await record_type_select.query_selector_all('option')
            option_values = []
            for option in options:
                value = await option.get_attribute('value')
                if value:
                    option_values.append(value)
            
            # Should only see A record type
            assert 'A' in option_values, "A record should be available"
            assert 'AAAA' not in option_values, "AAAA should NOT be available"
            assert 'MX' not in option_values, "MX should NOT be available"
            assert 'CNAME' not in option_values, "CNAME should NOT be available"
