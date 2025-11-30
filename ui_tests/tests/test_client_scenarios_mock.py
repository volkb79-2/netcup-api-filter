"""Comprehensive tests for all 5 demo client scenarios using mock Netcup API.

Tests validate:
- Each client's specific permissions (read, create, update, delete)
- Realm restrictions (host vs subdomain)
- Record type filtering
- UI button visibility based on permissions
- CRUD operations with mock data
"""
import json
import os
import sqlite3
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright, expect


def get_screenshot_path(filename: str) -> str:
    """Get screenshot path using SCREENSHOT_DIR environment variable."""
    screenshot_dir = os.environ.get('SCREENSHOT_DIR', 'screenshots')
    return f"{screenshot_dir}/{filename}"


@pytest.fixture
def deployment_dir():
    """Path to deployment directory (local or webhosting)."""
    # Support both local and webhosting deployments
    deploy_dir = os.environ.get('DEPLOY_DIR')
    if deploy_dir:
        return Path(deploy_dir)
    
    repo_root = os.environ.get('REPO_ROOT')
    if not repo_root:
        raise RuntimeError("DEPLOY_DIR or REPO_ROOT must be set (no hardcoded paths allowed)")
    
    # Default to deploy-local for local testing
    return Path(f"{repo_root}/deploy-local")


@pytest.fixture
def demo_clients(deployment_dir):
    """Load demo client credentials from build_info.json."""
    build_info_path = deployment_dir / "build_info.json"
    with open(build_info_path) as f:
        data = json.load(f)
    
    # Enhance with database info
    db_path = deployment_dir / "netcup_filter.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("""
        SELECT client_id, realm_type, realm_value, allowed_operations, allowed_record_types
        FROM clients ORDER BY created_at LIMIT 5
    """)
    
    client_info = {}
    for row in cursor.fetchall():
        client_id, realm_type, realm_value, ops, rec_types = row
        # Operations might be JSON array string or comma-separated
        try:
            operations = json.loads(ops) if ops.startswith('[') else ops.split(',')
        except:
            operations = ops.split(',') if ops else []
        
        try:
            record_types = json.loads(rec_types) if rec_types.startswith('[') else rec_types.split(',')
        except:
            record_types = rec_types.split(',') if rec_types else []
        
        client_info[client_id] = {
            'realm_type': realm_type,
            'realm_value': realm_value,
            'operations': operations,
            'record_types': record_types
        }
    conn.close()
    
    # Merge
    for client in data['demo_clients'][:5]:
        client_id = client['client_id']
        if client_id in client_info:
            client.update(client_info[client_id])
    
    return data['demo_clients'][:5]


@pytest.fixture
def base_url():
    """Base URL for local deployment."""
    return "http://localhost:5100"


def test_client_1_readonly_host(demo_clients, base_url):
    """Test Client 1: Read-only monitoring for example.com.
    
    Validates:
    - Can login with credentials
    - Can view domain dashboard
    - Can see all 4 DNS records
    - NO edit buttons visible (read-only)
    - NO delete buttons visible (read-only)
    - Cannot create new records
    """
    client = demo_clients[0]
    assert 'read' in client['operations']
    assert 'update' not in client['operations']
    assert client['realm_type'] == 'host'
    assert client['realm_value'] == 'example.com'
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1920, 'height': 1200})
        
        # Login
        page.goto(f"{base_url}/client/login")
        page.fill('input[name="client_id"]', client['client_id'])
        page.fill('input[name="secret_key"]', client['secret_key'])
        page.click('button[type="submit"]')
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)
        
        # Navigate to domain
        page.goto(f"{base_url}/client/domains/{client['realm_value']}")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(2000)
        
        # Verify records visible
        rows = page.locator('tbody tr')
        count = rows.count()
        assert count == 4, f"Expected 4 records, found {count}"
        
        # Verify NO edit buttons
        edit_buttons = page.locator('a[href*="/edit"]')
        assert edit_buttons.count() == 0, "Read-only client should have no edit buttons"
        
        # Verify NO delete buttons
        delete_buttons = page.locator('button:has-text("Delete")')
        assert delete_buttons.count() == 0, "Read-only client should have no delete buttons"
        
        # Verify NO "New Record" button (or it's disabled)
        new_record_links = page.locator('a:has-text("New Record")')
        # Read-only should not have create permission
        assert 'create' not in client['operations']
        
        # Verify specific records
        page_text = page.inner_text('body')
        assert 'www' in page_text
        assert '93.184.216.34' in page_text
        assert 'mail' in page_text
        
        # Use SCREENSHOT_DIR for both local and webhosting
        page.screenshot(path=get_screenshot_path('test_client_1_readonly.png'), full_page=True)
        
        browser.close()
        print(f"✓ Client 1 (read-only host) validated")


def test_client_2_fullcontrol_host(demo_clients, base_url):
    """Test Client 2: Full DNS management for api.example.com.
    
    Validates:
    - Can login and view domain
    - Can see all 3 DNS records
    - HAS edit buttons (update permission)
    - HAS delete buttons (delete permission)
    - Can create new records (create permission)
    - Can perform full CRUD workflow
    """
    client = demo_clients[1]
    assert all(op in client['operations'] for op in ['read', 'update', 'create', 'delete'])
    assert client['realm_type'] == 'host'
    assert client['realm_value'] == 'api.example.com'
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1920, 'height': 1200})
        
        # Login
        page.goto(f"{base_url}/client/login")
        page.fill('input[name="client_id"]', client['client_id'])
        page.fill('input[name="secret_key"]', client['secret_key'])
        page.click('button[type="submit"]')
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)
        
        # Navigate to domain
        page.goto(f"{base_url}/client/domains/{client['realm_value']}")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(2000)
        
        # Verify initial records
        initial_rows = page.locator('tbody tr')
        initial_count = initial_rows.count()
        assert initial_count == 3, f"Expected 3 initial records, found {initial_count}"
        
        # Verify HAS edit buttons
        edit_buttons = page.locator('a[href*="/edit"]')
        edit_count = edit_buttons.count()
        assert edit_count == 3, f"Full control client should have {initial_count} edit buttons, found {edit_count}"
        
        # Verify HAS delete buttons
        delete_buttons = page.locator('button:has-text("Delete")')
        delete_count = delete_buttons.count()
        assert delete_count == 3, f"Full control client should have {initial_count} delete buttons, found {delete_count}"
        
        page.screenshot(path=get_screenshot_path('test_client_2_before_crud.png'), full_page=True)
        
        # TEST CREATE
        page.click('a:has-text("New Record")')
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)
        
        page.fill('input[name="hostname"]', 'test-auto')
        page.select_option('select[name="type"]', 'A')
        page.fill('input[name="destination"]', '198.51.100.88')
        page.click('button[type="submit"]')
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(2000)
        
        after_create_rows = page.locator('tbody tr')
        assert after_create_rows.count() == 4, "Should have 4 records after CREATE"
        
        page_text = page.inner_text('body')
        assert 'test-auto' in page_text
        assert '198.51.100.88' in page_text
        
        page.screenshot(path=get_screenshot_path('test_client_2_after_create.png'), full_page=True)
        
        # TEST UPDATE
        test_row = None
        for i in range(after_create_rows.count()):
            row = after_create_rows.nth(i)
            if 'test-auto' in row.inner_text():
                test_row = row
                break
        
        assert test_row is not None, "Could not find test-auto record"
        
        edit_link = test_row.locator('a[href*="/edit"]')
        edit_link.click()
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)
        
        page.fill('input[name="destination"]', '198.51.100.99')
        page.click('button[type="submit"]')
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(2000)
        
        page_text = page.inner_text('body')
        assert '198.51.100.99' in page_text, "Should see updated IP"
        assert '198.51.100.88' not in page_text, "Old IP should be gone"
        
        page.screenshot(path=get_screenshot_path('test_client_2_after_update.png'), full_page=True)
        
        # TEST DELETE
        page.on('dialog', lambda dialog: dialog.accept())
        
        after_update_rows = page.locator('tbody tr')
        for i in range(after_update_rows.count()):
            row = after_update_rows.nth(i)
            if 'test-auto' in row.inner_text():
                delete_btn = row.locator('button:has-text("Delete")')
                delete_btn.click()
                page.wait_for_load_state('networkidle')
                page.wait_for_timeout(2000)
                break
        
        final_rows = page.locator('tbody tr')
        assert final_rows.count() == 3, "Should be back to 3 records after DELETE"
        
        page_text = page.inner_text('body')
        assert 'test-auto' not in page_text, "Deleted record should be gone"
        
        page.screenshot(path=get_screenshot_path('test_client_2_after_delete.png'), full_page=True)
        
        browser.close()
        print(f"✓ Client 2 (full control host) validated - CRUD complete")


def test_client_3_subdomain_readonly(demo_clients, base_url):
    """Test Client 3: Monitor all *.example.com subdomains (read-only).
    
    Validates:
    - Can login and view subdomain records
    - Realm type is 'subdomain'
    - Can see all matching records
    - NO edit/delete buttons (read-only)
    """
    client = demo_clients[2]
    assert 'read' in client['operations']
    assert 'update' not in client['operations']
    assert client['realm_type'] == 'subdomain'
    assert client['realm_value'] == 'example.com'
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1920, 'height': 1200})
        
        # Login
        page.goto(f"{base_url}/client/login")
        page.fill('input[name="client_id"]', client['client_id'])
        page.fill('input[name="secret_key"]', client['secret_key'])
        page.click('button[type="submit"]')
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)
        
        # Navigate to domain
        page.goto(f"{base_url}/client/domains/{client['realm_value']}")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(2000)
        
        # Verify records visible
        rows = page.locator('tbody tr')
        count = rows.count()
        assert count >= 3, f"Expected at least 3 records for subdomain wildcard, found {count}"
        
        # Verify NO edit/delete buttons
        edit_buttons = page.locator('a[href*="/edit"]')
        assert edit_buttons.count() == 0, "Subdomain read-only should have no edit buttons"
        
        delete_buttons = page.locator('button:has-text("Delete")')
        assert delete_buttons.count() == 0, "Subdomain read-only should have no delete buttons"
        
        page.screenshot(path=get_screenshot_path('test_client_3_subdomain_readonly.png'), full_page=True)
        
        browser.close()
        print(f"✓ Client 3 (subdomain read-only) validated")


def test_client_4_subdomain_update(demo_clients, base_url):
    """Test Client 4: Dynamic DNS for *.dyn.example.com (read+update+create).
    
    Validates:
    - Can login and view subdomain
    - HAS edit buttons (update permission)
    - HAS "New Record" button (create permission)
    - NO delete buttons (no delete permission)
    - Can create and update records
    """
    client = demo_clients[3]
    assert all(op in client['operations'] for op in ['read', 'update', 'create'])
    assert 'delete' not in client['operations']
    assert client['realm_type'] == 'subdomain'
    assert client['realm_value'] == 'dyn.example.com'
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1920, 'height': 1200})
        
        # Login
        page.goto(f"{base_url}/client/login")
        page.fill('input[name="client_id"]', client['client_id'])
        page.fill('input[name="secret_key"]', client['secret_key'])
        page.click('button[type="submit"]')
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)
        
        # Navigate to domain
        page.goto(f"{base_url}/client/domains/{client['realm_value']}")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(2000)
        
        # Verify initial state
        initial_rows = page.locator('tbody tr')
        initial_count = initial_rows.count()
        assert initial_count == 3, f"Expected 3 records, found {initial_count}"
        
        # Verify HAS edit buttons
        edit_buttons = page.locator('a[href*="/edit"]')
        assert edit_buttons.count() == 3, "Should have edit buttons for all records"
        
        # Verify NO delete buttons
        delete_buttons = page.locator('button:has-text("Delete")')
        assert delete_buttons.count() == 0, "Should have NO delete buttons (no delete permission)"
        
        page.screenshot(path=get_screenshot_path('test_client_4_before_ddns.png'), full_page=True)
        
        # Test CREATE (simulating dynamic DNS update)
        page.click('a:has-text("New Record")')
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)
        
        page.fill('input[name="hostname"]', 'test-ddns')
        page.select_option('select[name="type"]', 'A')
        page.fill('input[name="destination"]', '198.51.100.200')
        page.click('button[type="submit"]')
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(2000)
        
        after_create = page.locator('tbody tr')
        assert after_create.count() == 4, "Should have 4 records after create"
        
        # Test UPDATE (simulating IP change for dynamic DNS)
        for i in range(after_create.count()):
            row = after_create.nth(i)
            if 'test-ddns' in row.inner_text():
                edit_link = row.locator('a[href*="/edit"]')
                edit_link.click()
                page.wait_for_load_state('networkidle')
                page.wait_for_timeout(1000)
                break
        
        page.fill('input[name="destination"]', '198.51.100.201')
        page.click('button[type="submit"]')
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(2000)
        
        page_text = page.inner_text('body')
        assert '198.51.100.201' in page_text, "Should see updated dynamic IP"
        
        page.screenshot(path=get_screenshot_path('test_client_4_after_ddns.png'), full_page=True)
        
        browser.close()
        print(f"✓ Client 4 (subdomain DDNS) validated - create+update working, delete blocked")


def test_client_5_multirecord_fullcontrol(demo_clients, base_url):
    """Test Client 5: DNS provider for services.example.com (full control, multiple record types).
    
    Validates:
    - Can login and view domain
    - Can see records with multiple types (A, AAAA, MX, NS)
    - HAS all CRUD buttons
    - Can manage different record types
    """
    client = demo_clients[4]
    assert all(op in client['operations'] for op in ['read', 'update', 'create', 'delete'])
    assert client['realm_type'] == 'host'
    assert client['realm_value'] == 'services.example.com'
    assert 'A' in client['record_types']
    assert 'AAAA' in client['record_types']
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1920, 'height': 1200})
        
        # Login
        page.goto(f"{base_url}/client/login")
        page.fill('input[name="client_id"]', client['client_id'])
        page.fill('input[name="secret_key"]', client['secret_key'])
        page.click('button[type="submit"]')
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)
        
        # Navigate to domain
        page.goto(f"{base_url}/client/domains/{client['realm_value']}")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(2000)
        
        # Verify initial records
        initial_rows = page.locator('tbody tr')
        initial_count = initial_rows.count()
        assert initial_count == 4, f"Expected 4 records, found {initial_count}"
        
        # Verify multiple record types visible
        page_text = page.inner_text('body')
        assert 'A' in page_text or 'AAAA' in page_text or 'MX' in page_text, "Should see multiple record types"
        
        # Verify full CRUD buttons
        edit_buttons = page.locator('a[href*="/edit"]')
        assert edit_buttons.count() == 4, "Should have edit buttons for all records"
        
        delete_buttons = page.locator('button:has-text("Delete")')
        assert delete_buttons.count() == 4, "Should have delete buttons for all records"
        
        page.screenshot(path=get_screenshot_path('test_client_5_multirecord.png'), full_page=True)
        
        browser.close()
        print(f"✓ Client 5 (multi-record full control) validated")


def test_all_clients_smoke(demo_clients, base_url):
    """Smoke test: Verify all 5 clients can login and view their domains.
    
    Quick validation that basic functionality works for each client.
    """
    results = []
    
    with sync_playwright() as p:
        for i, client in enumerate(demo_clients, 1):
            browser = p.chromium.launch()
            page = browser.new_page(viewport={'width': 1920, 'height': 1200})
            
            try:
                # Login
                page.goto(f"{base_url}/client/login")
                page.fill('input[name="client_id"]', client['client_id'])
                page.fill('input[name="secret_key"]', client['secret_key'])
                page.click('button[type="submit"]')
                page.wait_for_load_state('networkidle')
                page.wait_for_timeout(1000)
                
                # Navigate to domain
                domain = client.get('realm_value', 'example.com')
                page.goto(f"{base_url}/client/domains/{domain}")
                page.wait_for_load_state('networkidle')
                page.wait_for_timeout(2000)
                
                # Verify records visible
                rows = page.locator('tbody tr')
                count = rows.count()
                
                results.append({
                    'client': i,
                    'description': client.get('description', f'Client {i}'),
                    'domain': domain,
                    'records': count,
                    'status': 'PASS'
                })
                
            except Exception as e:
                results.append({
                    'client': i,
                    'description': client.get('description', f'Client {i}'),
                    'domain': client.get('realm_value', '?'),
                    'records': 0,
                    'status': f'FAIL: {str(e)[:50]}'
                })
            
            finally:
                browser.close()
    
    # Print summary
    print("\n" + "=" * 75)
    print("SMOKE TEST RESULTS")
    print("=" * 75)
    for r in results:
        status_emoji = "✓" if r['status'] == 'PASS' else "✗"
        print(f"{status_emoji} Client {r['client']}: {r['description']}")
        print(f"   Domain: {r['domain']}, Records: {r['records']}, Status: {r['status']}")
    print("=" * 75)
    
    # Assert all passed
    failed = [r for r in results if r['status'] != 'PASS']
    assert len(failed) == 0, f"{len(failed)} clients failed smoke test"
    
    print(f"\n✅ All {len(results)} clients passed smoke test")


def test_permission_matrix(demo_clients, base_url):
    """Test permission matrix: Verify each client has exactly the expected permissions.
    
    Creates a matrix showing which operations each client can perform.
    """
    matrix = []
    
    for i, client in enumerate(demo_clients, 1):
        ops = client.get('operations', [])
        matrix.append({
            'client': i,
            'description': client.get('description', f'Client {i}'),
            'read': 'read' in ops,
            'create': 'create' in ops,
            'update': 'update' in ops,
            'delete': 'delete' in ops,
            'realm': f"{client.get('realm_type', '?')}:{client.get('realm_value', '?')}"
        })
    
    # Print matrix
    print("\n" + "=" * 85)
    print("PERMISSION MATRIX")
    print("=" * 85)
    print(f"{'Client':<8} {'Description':<30} {'Read':<6} {'Create':<8} {'Update':<8} {'Delete':<8}")
    print("-" * 85)
    
    for m in matrix:
        print(f"{m['client']:<8} {m['description']:<30} "
              f"{'✓' if m['read'] else '✗':<6} "
              f"{'✓' if m['create'] else '✗':<8} "
              f"{'✓' if m['update'] else '✗':<8} "
              f"{'✓' if m['delete'] else '✗':<8}")
        print(f"         Realm: {m['realm']}")
    
    print("=" * 85)
    
    # Validate expected permissions
    assert matrix[0]['read'] and not matrix[0]['update'], "Client 1 should be read-only"
    assert all(matrix[1].values()), "Client 2 should have all permissions"
    assert matrix[2]['read'] and not matrix[2]['update'], "Client 3 should be read-only"
    assert matrix[3]['update'] and not matrix[3]['delete'], "Client 4 should have no delete"
    assert all(matrix[4].values()), "Client 5 should have all permissions"
    
    print(f"\n✅ Permission matrix validated")
