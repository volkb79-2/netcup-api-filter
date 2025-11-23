"""Standalone test to validate mock Netcup API functionality.

Run this with: python -m pytest ui_tests/tests/test_mock_api_standalone.py -v
"""
import pytest


def test_mock_api_basic_operations(mock_netcup_api_server, mock_netcup_credentials):
    """Test basic mock API operations without the application layer."""
    import sys
    from pathlib import Path
    
    # Add root to path to import netcup_client
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    
    from netcup_client import NetcupClient
    
    # Create client pointing to mock API
    client = NetcupClient(
        customer_id=mock_netcup_credentials['customer_id'],
        api_key=mock_netcup_credentials['api_key'],
        api_password=mock_netcup_credentials['api_password'],
        api_url=mock_netcup_api_server.url
    )
    
    print(f"\n[Mock API Test] Connecting to {mock_netcup_api_server.url}")
    
    # Test 1: Login
    session_id = client.login()
    assert session_id
    assert len(session_id) == 32  # Hex string (16 bytes = 32 hex chars)
    print(f"[Mock API Test] ✓ Login successful, session: {session_id[:8]}...")
    
    # Test 2: Get DNS zone info
    test_domain = "test.example.com"
    zone_info = client.info_dns_zone(test_domain)
    assert zone_info['name'] == test_domain
    assert 'ttl' in zone_info
    assert 'serial' in zone_info
    print(f"[Mock API Test] ✓ Zone info retrieved for {test_domain}")
    print(f"[Mock API Test]   - TTL: {zone_info['ttl']}")
    print(f"[Mock API Test]   - Serial: {zone_info['serial']}")
    
    # Test 3: Get DNS records
    records = client.info_dns_records(test_domain)
    assert isinstance(records, list)
    assert len(records) > 0
    print(f"[Mock API Test] ✓ Retrieved {len(records)} DNS records:")
    for record in records[:3]:  # Show first 3
        print(f"[Mock API Test]   - {record['hostname']} {record['type']} {record['destination']}")
    
    # Test 4: Update DNS records (add a new one)
    new_record = {
        "hostname": "test-new",
        "type": "A",
        "priority": "",
        "destination": "192.0.2.123",
        "deleterecord": False
    }
    
    updated_records = records + [new_record]
    result = client.update_dns_records(test_domain, updated_records)
    print(f"[Mock API Test] ✓ DNS records updated successfully")
    
    # Test 5: Verify the new record was added
    records_after = client.info_dns_records(test_domain)
    assert len(records_after) == len(records) + 1
    assert any(r['destination'] == '192.0.2.123' for r in records_after)
    print(f"[Mock API Test] ✓ New record verified in subsequent query")
    print(f"[Mock API Test]   - Record count before: {len(records)}")
    print(f"[Mock API Test]   - Record count after: {len(records_after)}")
    
    # Test 6: Update an existing record
    record_to_update = records_after[0]
    original_destination = record_to_update['destination']
    record_to_update['destination'] = '192.0.2.250'
    
    client.update_dns_records(test_domain, records_after)
    records_final = client.info_dns_records(test_domain)
    
    updated_record = next(r for r in records_final if r['id'] == record_to_update['id'])
    assert updated_record['destination'] == '192.0.2.250'
    print(f"[Mock API Test] ✓ Existing record updated")
    print(f"[Mock API Test]   - Old destination: {original_destination}")
    print(f"[Mock API Test]   - New destination: {updated_record['destination']}")
    
    # Test 7: Delete a record
    record_to_delete = records_final[-1]
    for r in records_final:
        if r['id'] == record_to_delete['id']:
            r['deleterecord'] = True
    
    client.update_dns_records(test_domain, records_final)
    records_after_delete = client.info_dns_records(test_domain)
    
    assert len(records_after_delete) == len(records_final) - 1
    assert not any(r['id'] == record_to_delete['id'] for r in records_after_delete)
    print(f"[Mock API Test] ✓ Record deleted")
    print(f"[Mock API Test]   - Record count after delete: {len(records_after_delete)}")
    
    # Test 8: Logout
    client.logout()
    assert client.session_id is None
    print(f"[Mock API Test] ✓ Logout successful")
    print(f"[Mock API Test] ✓ Session cleared from client")
    
    # Note: The netcup_client will automatically re-login if you call methods after logout,
    # so we just verify the session was cleared rather than trying to make requests


def test_mock_api_multiple_domains(mock_netcup_api_server, mock_netcup_credentials):
    """Test that mock API can handle multiple domains independently."""
    import sys
    from pathlib import Path
    
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    
    from netcup_client import NetcupClient
    
    client = NetcupClient(
        customer_id=mock_netcup_credentials['customer_id'],
        api_key=mock_netcup_credentials['api_key'],
        api_password=mock_netcup_credentials['api_password'],
        api_url=mock_netcup_api_server.url
    )
    
    client.login()
    
    # Create records for domain 1
    domain1 = "domain1.example.com"
    records1 = client.info_dns_records(domain1)
    client.update_dns_records(domain1, records1 + [{
        "hostname": "domain1-specific",
        "type": "A",
        "priority": "",
        "destination": "192.0.2.11",
        "deleterecord": False
    }])
    
    # Create records for domain 2
    domain2 = "domain2.example.com"
    records2 = client.info_dns_records(domain2)
    client.update_dns_records(domain2, records2 + [{
        "hostname": "domain2-specific",
        "type": "A",
        "priority": "",
        "destination": "192.0.2.22",
        "deleterecord": False
    }])
    
    # Verify domains don't interfere
    records1_after = client.info_dns_records(domain1)
    records2_after = client.info_dns_records(domain2)
    
    assert any(r['hostname'] == 'domain1-specific' for r in records1_after)
    assert not any(r['hostname'] == 'domain2-specific' for r in records1_after)
    
    assert any(r['hostname'] == 'domain2-specific' for r in records2_after)
    assert not any(r['hostname'] == 'domain1-specific' for r in records2_after)
    
    print(f"[Mock API Test] ✓ Multiple domains handled independently")
    print(f"[Mock API Test]   - Domain 1 records: {len(records1_after)}")
    print(f"[Mock API Test]   - Domain 2 records: {len(records2_after)}")
    
    client.logout()


def test_mock_api_invalid_credentials(mock_netcup_api_server):
    """Test that mock API rejects invalid credentials."""
    import sys
    from pathlib import Path
    
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    
    from netcup_client import NetcupClient, NetcupAPIError
    
    client = NetcupClient(
        customer_id="wrong",
        api_key="wrong",
        api_password="wrong",
        api_url=mock_netcup_api_server.url
    )
    
    try:
        client.login()
        assert False, "Should have raised error for invalid credentials"
    except NetcupAPIError as e:
        assert "401" in str(e) or "unauthorized" in str(e).lower()
        print(f"[Mock API Test] ✓ Invalid credentials rejected")


def test_mock_api_session_isolation(mock_netcup_api_server, mock_netcup_credentials):
    """Test that different sessions are isolated."""
    import sys
    from pathlib import Path
    
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    
    from netcup_client import NetcupClient
    
    # Create two clients
    client1 = NetcupClient(
        customer_id=mock_netcup_credentials['customer_id'],
        api_key=mock_netcup_credentials['api_key'],
        api_password=mock_netcup_credentials['api_password'],
        api_url=mock_netcup_api_server.url
    )
    
    client2 = NetcupClient(
        customer_id=mock_netcup_credentials['customer_id'],
        api_key=mock_netcup_credentials['api_key'],
        api_password=mock_netcup_credentials['api_password'],
        api_url=mock_netcup_api_server.url
    )
    
    # Login both
    session1 = client1.login()
    session2 = client2.login()
    
    assert session1 != session2
    print(f"[Mock API Test] ✓ Different sessions created")
    print(f"[Mock API Test]   - Session 1: {session1[:8]}...")
    print(f"[Mock API Test]   - Session 2: {session2[:8]}...")
    
    # Both should work independently
    test_domain = "test.example.com"
    zone1 = client1.info_dns_zone(test_domain)
    zone2 = client2.info_dns_zone(test_domain)
    
    assert zone1 == zone2
    print(f"[Mock API Test] ✓ Both sessions work independently")
    
    # Logout one shouldn't affect the other
    client1.logout()
    
    zone2_after = client2.info_dns_zone(test_domain)
    assert zone2_after == zone2
    print(f"[Mock API Test] ✓ Session isolation maintained")
    
    client2.logout()


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
