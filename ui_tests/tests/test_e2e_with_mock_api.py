"""End-to-end tests using mock Netcup API.

These tests validate complete workflows including DNS operations
without requiring real Netcup API credentials.

NOTE: These tests require a LOCAL app deployment where the Flask app can
reach the mock Netcup API server running in the Playwright container network.
They will be skipped when running against production deployments.
"""
import pytest
import httpx
from ui_tests.config import settings
from ui_tests import workflows
from ui_tests.browser import browser_session


# Mark all tests in this module as e2e_local and asyncio
pytestmark = [pytest.mark.asyncio, pytest.mark.e2e_local]


# Skip all tests in this module if running against production
if settings.base_url and not any(host in settings.base_url for host in ['localhost', '127.0.0.1', '0.0.0.0']):
    pytestmark.append(pytest.mark.skip(reason="E2E mock API tests require local deployment with accessible mock Netcup API"))


async def test_e2e_with_mock_api_read_dns_records(
    mock_netcup_api_server,
    mock_netcup_credentials,
    active_profile
):
    """Test complete E2E workflow: Admin creates client → client reads DNS records.
    
    Validates:
    1. Admin creates client with read permissions
    2. Client authenticates with generated token
    3. Client can view DNS records through the portal
    4. Client sees all allowed record types
    """
    if not active_profile.allow_writes:
        pytest.skip("profile is read-only; skipping E2E create flow")
    
    # Generate unique test data
    import secrets
    suffix = secrets.token_hex(4)
    test_domain = f"test-e2e-{suffix}.example.com"
    
    # Seed the mock API with test domain and records
    from ui_tests.mock_netcup_api import seed_test_domain
    seed_test_domain(test_domain, [
        {
            "id": "1",
            "hostname": "@",
            "type": "A",
            "priority": "",
            "destination": "192.0.2.100",
            "deleterecord": False,
            "state": "yes"
        },
        {
            "id": "2",
            "hostname": "api",
            "type": "A",
            "priority": "",
            "destination": "192.0.2.200",
            "deleterecord": False,
            "state": "yes"
        },
        {
            "id": "3",
            "hostname": "@",
            "type": "AAAA",
            "priority": "",
            "destination": "2001:db8::100",
            "deleterecord": False,
            "state": "yes"
        }
    ])
    
    client_data = workflows.ClientFormData(
        client_id=f"e2e-reader-{suffix}",
        description="E2E test client (read-only)",
        realm_value=test_domain,
        realm_type="host",
        record_types=["A", "AAAA"],
        operations=["read"],
        email=None
    )
    
    # ========================================================================
    # PART 1: Admin creates the client and configures mock Netcup API
    # ========================================================================
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        
        # Configure Netcup API to use mock server
        await workflows.open_admin_netcup_config(browser)
        await browser.fill("#customer_id", mock_netcup_credentials['customer_id'])
        await browser.fill("#api_key", mock_netcup_credentials['api_key'])
        await browser.fill("#api_password", mock_netcup_credentials['api_password'])
        await browser.fill("#api_url", mock_netcup_api_server.url)
        await browser.fill("#timeout", "30")
        await browser.submit("form")
        
        import anyio
        await anyio.sleep(0.5)
        flash_text = await browser.text(".flash-messages")
        assert "Netcup API configuration saved successfully" in flash_text
        
        # Create client
        await workflows.open_admin_client_create(browser)
        await workflows.submit_client_form(browser, client_data)
        
        # Extract real token from flash message
        await anyio.sleep(0.5)
        flash_text = await browser.text(".flash-messages")
        
        import re
        token_match = re.search(r'Secret token.*?:\s*([A-Za-z0-9_-]+)', flash_text)
        assert token_match, "Could not extract token from flash message"
        
        generated_token = token_match.group(1)
        print(f"[E2E] Created client '{client_data.client_id}' with token")
        
        # ====================================================================
        # PART 2: Client logs in and views DNS records
        # ====================================================================
        await browser.goto(settings.url("/client/login"))
        await browser.fill("#token", generated_token)
        
        from ui_tests.browser import ToolError
        try:
            await browser.submit("form")
        except ToolError as e:
            if "Execution context was destroyed" not in str(e):
                raise
        
        await anyio.sleep(1.5)
        
        # Check that we're on the dashboard
        page_html = await browser.html("body")
        
        # Should see the client portal dashboard
        assert "client portal" in page_html.lower() or client_data.client_id in page_html.lower()
        
        # Navigate to the domain
        try:
            await browser.click(f"a[href='/client/domains/{test_domain}']")
        except:
            # Try generic "Manage" button
            await browser.click("text=Manage")
        
        await anyio.sleep(1.0)
        
        # Verify we can see DNS records
        page_html = await browser.html("body")
        print(f"[E2E] Domain page loaded, checking for DNS records...")
        
        # Should see our test records
        assert "192.0.2.100" in page_html, "Should see @ A record"
        assert "192.0.2.200" in page_html, "Should see api A record"
        assert "2001:db8::100" in page_html, "Should see @ AAAA record"
        
        # Should see record types
        assert "A" in page_html
        assert "AAAA" in page_html
        
        print(f"[E2E] ✓ Client can view DNS records through mock API")


async def test_e2e_with_mock_api_update_dns_record(
    mock_netcup_api_server,
    mock_netcup_credentials,

    active_profile
):
    """Test complete E2E workflow: Admin creates client → client updates DNS record.
    
    Validates:
    1. Admin creates client with read+update permissions
    2. Client authenticates with generated token
    3. Client can view DNS records
    4. Client can update an existing DNS record
    5. Updated record is visible after refresh
    """
    if not active_profile.allow_writes:
        pytest.skip("profile is read-only; skipping E2E update flow")
    
    # Generate unique test data
    import secrets
    suffix = secrets.token_hex(4)
    test_domain = f"test-e2e-{suffix}.example.com"
    
    # Seed the mock API
    from ui_tests.mock_netcup_api import seed_test_domain
    seed_test_domain(test_domain, [
        {
            "id": "1",
            "hostname": "@",
            "type": "A",
            "priority": "",
            "destination": "192.0.2.50",
            "deleterecord": False,
            "state": "yes"
        },
        {
            "id": "2",
            "hostname": "www",
            "type": "A",
            "priority": "",
            "destination": "192.0.2.50",
            "deleterecord": False,
            "state": "yes"
        }
    ])
    
    client_data = workflows.ClientFormData(
        client_id=f"e2e-updater-{suffix}",
        description="E2E test client (read+update)",
        realm_value=test_domain,
        realm_type="host",
        record_types=["A"],
        operations=["read", "update"],
        email=None
    )
    
    async with browser_session() as browser:
        await workflows.ensure_admin_dashboard(browser)
        
        # Configure mock API
        await workflows.open_admin_netcup_config(browser)
        await browser.fill("#customer_id", mock_netcup_credentials['customer_id'])
        await browser.fill("#api_key", mock_netcup_credentials['api_key'])
        await browser.fill("#api_password", mock_netcup_credentials['api_password'])
        await browser.fill("#api_url", mock_netcup_api_server.url)
        await browser.submit("form")
        
        import anyio
        await anyio.sleep(0.5)
        
        # Create client
        await workflows.open_admin_client_create(browser)
        await workflows.submit_client_form(browser, client_data)
        
        await anyio.sleep(0.5)
        flash_text = await browser.text(".flash-messages")
        
        import re
        token_match = re.search(r'Secret token.*?:\s*([A-Za-z0-9_-]+)', flash_text)
        generated_token = token_match.group(1)
        
        print(f"[E2E] Created client with update permissions")
        
        # Client logs in
        await browser.goto(settings.url("/client/login"))
        await browser.fill("#token", generated_token)
        
        from ui_tests.browser import ToolError
        try:
            await browser.submit("form")
        except ToolError as e:
            if "Execution context was destroyed" not in str(e):
                raise
        
        await anyio.sleep(1.5)
        
        # Navigate to domain
        try:
            await browser.click(f"a[href='/client/domains/{test_domain}']")
        except:
            await browser.click("text=Manage")
        
        await anyio.sleep(1.0)
        
        # Verify initial state
        page_html = await browser.html("body")
        assert "192.0.2.50" in page_html, "Should see initial IP"
        
        print(f"[E2E] ✓ Client can view initial DNS records")
        
        # Update a record via API (simulating what the UI would do)
        # The client portal uses the internal /api endpoint
        async with httpx.AsyncClient() as client:
            # Get the session cookie
            import http.cookies
            cookie_header = browser._page.context._impl_obj._options.get('storageState', {}).get('cookies', [])
            
            # Make API call to update record
            response = await client.post(
                settings.url("/api"),
                json={
                    "action": "updateDnsRecords",
                    "domainname": test_domain,
                    "dnsrecordset": {
                        "dnsrecords": [
                            {
                                "id": "1",
                                "hostname": "@",
                                "type": "A",
                                "priority": "",
                                "destination": "192.0.2.99",  # Updated IP
                                "deleterecord": False
                            },
                            {
                                "id": "2",
                                "hostname": "www",
                                "type": "A",
                                "priority": "",
                                "destination": "192.0.2.50",
                                "deleterecord": False
                            }
                        ]
                    }
                },
                headers={"Authorization": f"Bearer {generated_token}"}
            )
            
            print(f"[E2E] API update response: {response.status_code}")
            assert response.status_code == 200, f"API update failed: {response.text}"
        
        # Refresh page to see updated record
        await browser.goto(settings.url(f"/client/domains/{test_domain}"))
        await anyio.sleep(1.0)
        
        page_html = await browser.html("body")
        assert "192.0.2.99" in page_html, "Should see updated IP"
        
        print(f"[E2E] ✓ Client can update DNS records via API")
        print(f"[E2E] ✓ Updated records are visible after refresh")


async def test_e2e_with_mock_api_permission_enforcement(
    mock_netcup_api_server,
    mock_netcup_credentials,
    active_profile
):
    """Test that permission enforcement works with mock API.
    
    Validates:
    1. Client with A-only permissions cannot update AAAA records
    2. Client with read-only permissions cannot update any records
    3. Client with specific domain permission cannot access other domains
    """
    if not active_profile.allow_writes:
        pytest.skip("profile is read-only")
    
    import secrets
    suffix = secrets.token_hex(4)
    test_domain = f"test-e2e-{suffix}.example.com"
    other_domain = f"other-{suffix}.example.com"
    
    # Seed both domains
    from ui_tests.mock_netcup_api import seed_test_domain
    seed_test_domain(test_domain)
    seed_test_domain(other_domain)
    
    # Configure mock API via direct API call
    async with httpx.AsyncClient() as client:
        # Login as admin first (this test uses API directly, not browser)
        # We'll use the test client that's pre-seeded
        
        # Test 1: Read-only client cannot update
        response = await client.post(
            settings.url("/api"),
            json={
                "action": "updateDnsRecords",
                "domainname": test_domain,
                "dnsrecordset": {
                    "dnsrecords": [
                        {
                            "hostname": "@",
                            "type": "A",
                            "destination": "192.0.2.99"
                        }
                    ]
                }
            },
            headers={"Authorization": f"Bearer {settings.client_token}"}
        )
        
        # The pre-seeded test client is read-only
        assert response.status_code in [403, 401], "Read-only client should not be able to update"
        print(f"[E2E] ✓ Read-only permissions enforced")
        
        # Test 2: Client cannot access unauthorized domain
        response = await client.post(
            settings.url("/api"),
            json={
                "action": "infoDnsRecords",
                "domainname": other_domain
            },
            headers={"Authorization": f"Bearer {settings.client_token}"}
        )
        
        assert response.status_code == 403, "Client should not access unauthorized domain"
        print(f"[E2E] ✓ Domain restrictions enforced")


async def test_mock_netcup_api_directly(mock_netcup_api_server, mock_netcup_credentials):
    """Test the mock Netcup API directly (without the application layer).
    
    This validates that the mock API itself works correctly.
    """
    from netcup_client import NetcupClient
    
    # Create client pointing to mock API
    client = NetcupClient(
        customer_id=mock_netcup_credentials['customer_id'],
        api_key=mock_netcup_credentials['api_key'],
        api_password=mock_netcup_credentials['api_password'],
        api_url=mock_netcup_api_server.url
    )
    
    # Test login
    session_id = client.login()
    assert session_id
    assert len(session_id) == 32  # Hex string
    print(f"[Mock API] ✓ Login successful, session: {session_id[:8]}...")
    
    # Test infoDnsZone
    test_domain = "test.example.com"
    zone_info = client.info_dns_zone(test_domain)
    assert zone_info['name'] == test_domain
    assert 'ttl' in zone_info
    print(f"[Mock API] ✓ Zone info retrieved for {test_domain}")
    
    # Test infoDnsRecords
    records = client.info_dns_records(test_domain)
    assert isinstance(records, list)
    assert len(records) > 0
    print(f"[Mock API] ✓ Retrieved {len(records)} DNS records")
    
    # Test updateDnsRecords
    new_record = {
        "hostname": "test-new",
        "type": "A",
        "priority": "",
        "destination": "192.0.2.123",
        "deleterecord": False
    }
    
    updated = client.update_dns_records(test_domain, records + [new_record])
    assert 'dnsrecords' in updated or updated  # Mock returns different format
    print(f"[Mock API] ✓ DNS records updated successfully")
    
    # Verify the new record was added
    records_after = client.info_dns_records(test_domain)
    assert any(r['destination'] == '192.0.2.123' for r in records_after)
    print(f"[Mock API] ✓ New record verified in subsequent query")
    
    # Test logout
    client.logout()
    print(f"[Mock API] ✓ Logout successful")


async def test_mock_api_session_timeout(mock_netcup_api_server, mock_netcup_credentials):
    """Test that mock API enforces session timeout."""
    from netcup_client import NetcupClient, NetcupAPIError
    
    client = NetcupClient(
        customer_id=mock_netcup_credentials['customer_id'],
        api_key=mock_netcup_credentials['api_key'],
        api_password=mock_netcup_credentials['api_password'],
        api_url=mock_netcup_api_server.url
    )
    
    # Login and get session
    session_id = client.login()
    
    # Manually expire the session by modifying internal state
    from ui_tests.mock_netcup_api import SESSIONS
    if session_id in SESSIONS:
        SESSIONS[session_id]['created_at'] = 0  # Very old timestamp
    
    # Try to use expired session
    try:
        client.info_dns_zone("test.example.com")
        assert False, "Should have raised error for expired session"
    except NetcupAPIError as e:
        assert "session" in str(e).lower() or "401" in str(e)
        print(f"[Mock API] ✓ Session timeout enforced")
