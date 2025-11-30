"""Smoke tests for all 5 demo client scenarios using mock Netcup API.

These tests run synchronously (no asyncio) to validate basic functionality.
"""
import json
import os
import sqlite3
from pathlib import Path
from playwright.sync_api import sync_playwright


def load_demo_clients():
    """Load demo client credentials with database info."""
    # Support both local and webhosting deployments
    deploy_dir = os.environ.get('DEPLOY_DIR')
    if deploy_dir:
        deployment_dir = Path(deploy_dir)
    else:
        repo_root = os.environ.get('REPO_ROOT')
        if not repo_root:
            raise RuntimeError("DEPLOY_DIR or REPO_ROOT must be set (no hardcoded paths allowed)")
        deployment_dir = Path(f"{repo_root}/deploy-local")
    build_info_path = deployment_dir / "build_info.json"


def get_screenshot_path(filename: str) -> str:
    """Get screenshot path using SCREENSHOT_DIR environment variable."""
    screenshot_dir = os.environ.get('SCREENSHOT_DIR', 'screenshots')
    return f"{screenshot_dir}/{filename}"
    
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


def test_smoke_all_clients_login():
    """Smoke test: All 5 clients can login and view their domains."""
    clients = load_demo_clients()
    base_url = "http://localhost:5100"
    results = []
    
    with sync_playwright() as p:
        for i, client in enumerate(clients, 1):
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
                
                # Count records
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
                    'status': f'FAIL: {str(e)[:100]}'
                })
            
            finally:
                browser.close()
    
    # Print summary
    print("\n" + "=" * 80)
    print("SMOKE TEST: ALL CLIENTS LOGIN AND VIEW DOMAINS")
    print("=" * 80)
    for r in results:
        status_emoji = "✓" if r['status'] == 'PASS' else "✗"
        print(f"{status_emoji} Client {r['client']}: {r['description']}")
        print(f"   Domain: {r['domain']}, Records: {r['records']}")
        if r['status'] != 'PASS':
            print(f"   Status: {r['status']}")
    print("=" * 80)
    
    # Assert all passed
    failed = [r for r in results if r['status'] != 'PASS']
    assert len(failed) == 0, f"{len(failed)} clients failed smoke test"
    
    print(f"\n✅ All {len(results)} clients passed smoke test!")


def test_client_1_readonly_permissions():
    """Test Client 1: Verify read-only permissions (no edit/delete buttons)."""
    clients = load_demo_clients()
    client = clients[0]
    base_url = "http://localhost:5100"
    
    assert 'read' in client['operations']
    assert 'update' not in client['operations']
    assert 'delete' not in client['operations']
    
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
        assert count >= 3, f"Expected at least 3 records, found {count}"
        
        # Verify NO edit buttons
        edit_buttons = page.locator('a[href*="/edit"]')
        assert edit_buttons.count() == 0, "Read-only client should have no edit buttons"
        
        # Verify NO delete buttons
        delete_buttons = page.locator('button:has-text("Delete")')
        assert delete_buttons.count() == 0, "Read-only client should have no delete buttons"
        
        page.screenshot(path=get_screenshot_path('test_smoke_client_1_readonly.png'), full_page=True)
        browser.close()
        
    print(f"✓ Client 1 (read-only) permissions validated: {count} records, 0 edit, 0 delete")


def test_client_2_fullcontrol_crud():
    """Test Client 2: Full CRUD workflow with full control permissions."""
    clients = load_demo_clients()
    client = clients[1]
    base_url = "http://localhost:5100"
    
    assert all(op in client['operations'] for op in ['read', 'update', 'create', 'delete'])
    
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
        
        # Verify initial records and buttons
        initial_rows = page.locator('tbody tr')
        initial_count = initial_rows.count()
        
        edit_buttons = page.locator('a[href*="/edit"]')
        assert edit_buttons.count() == initial_count, "Should have edit button for each record"
        
        delete_buttons = page.locator('button:has-text("Delete")')
        assert delete_buttons.count() == initial_count, "Should have delete button for each record"
        
        page.screenshot(path=get_screenshot_path('test_smoke_client_2_before_crud.png'), full_page=True)
        
        # CREATE
        page.click('a:has-text("New Record")')
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)
        
        page.fill('input[name="hostname"]', 'smoke-test')
        page.select_option('select[name="type"]', 'A')
        page.fill('input[name="destination"]', '198.51.100.77')
        page.click('button[type="submit"]')
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(2000)
        
        after_create = page.locator('tbody tr')
        assert after_create.count() == initial_count + 1, "Should have one more record after CREATE"
        
        # UPDATE
        for i in range(after_create.count()):
            row = after_create.nth(i)
            if 'smoke-test' in row.inner_text():
                edit_link = row.locator('a[href*="/edit"]')
                edit_link.click()
                page.wait_for_load_state('networkidle')
                page.wait_for_timeout(1000)
                break
        
        page.fill('input[name="destination"]', '198.51.100.78')
        page.click('button[type="submit"]')
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(2000)
        
        page_text = page.inner_text('body')
        assert '198.51.100.78' in page_text, "Should see updated IP"
        
        # DELETE
        page.on('dialog', lambda dialog: dialog.accept())
        after_update = page.locator('tbody tr')
        for i in range(after_update.count()):
            row = after_update.nth(i)
            if 'smoke-test' in row.inner_text():
                delete_btn = row.locator('button:has-text("Delete")')
                delete_btn.click()
                page.wait_for_load_state('networkidle')
                page.wait_for_timeout(2000)
                break
        
        final = page.locator('tbody tr')
        assert final.count() == initial_count, "Should be back to original count after DELETE"
        
        page.screenshot(path=get_screenshot_path('test_smoke_client_2_after_crud.png'), full_page=True)
        browser.close()
        
    print(f"✓ Client 2 (full control) CRUD validated: CREATE → UPDATE → DELETE")


def test_client_4_ddns_no_delete():
    """Test Client 4: DDNS client can create/update but not delete."""
    clients = load_demo_clients()
    client = clients[3]
    base_url = "http://localhost:5100"
    
    assert 'update' in client['operations']
    assert 'create' in client['operations']
    assert 'delete' not in client['operations']
    
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
        
        # Verify HAS edit buttons
        edit_buttons = page.locator('a[href*="/edit"]')
        assert edit_buttons.count() > 0, "DDNS client should have edit buttons"
        
        # Verify NO delete buttons
        delete_buttons = page.locator('button:has-text("Delete")')
        assert delete_buttons.count() == 0, "DDNS client should have no delete buttons"
        
        page.screenshot(path=get_screenshot_path('test_smoke_client_4_ddns.png'), full_page=True)
        browser.close()
        
    print(f"✓ Client 4 (DDNS) permissions validated: edit buttons present, no delete buttons")


def test_permission_matrix():
    """Display and validate permission matrix for all clients."""
    clients = load_demo_clients()
    
    matrix = []
    for i, client in enumerate(clients, 1):
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
    print("\n" + "=" * 90)
    print("PERMISSION MATRIX")
    print("=" * 90)
    print(f"{'#':<4} {'Description':<35} {'Read':<7} {'Create':<8} {'Update':<8} {'Delete':<8}")
    print("-" * 90)
    
    for m in matrix:
        print(f"{m['client']:<4} {m['description']:<35} "
              f"{'✓' if m['read'] else '✗':<7} "
              f"{'✓' if m['create'] else '✗':<8} "
              f"{'✓' if m['update'] else '✗':<8} "
              f"{'✓' if m['delete'] else '✗':<8}")
        print(f"     Realm: {m['realm']}")
    
    print("=" * 90)
    
    # Validate expected permissions
    assert matrix[0]['read'] and not matrix[0]['update'], "Client 1 should be read-only"
    assert all(matrix[1].values()), "Client 2 should have all permissions"
    assert matrix[2]['read'] and not matrix[2]['update'], "Client 3 should be read-only"
    assert matrix[3]['update'] and not matrix[3]['delete'], "Client 4 should have no delete"
    
    print(f"\n✅ Permission matrix validated")


if __name__ == "__main__":
    print("Running smoke tests with mock Netcup API...\n")
    
    test_smoke_all_clients_login()
    test_client_1_readonly_permissions()
    test_client_2_fullcontrol_crud()
    test_client_4_ddns_no_delete()
    test_permission_matrix()
    
    print("\n" + "=" * 80)
    print("✅ ALL SMOKE TESTS PASSED")
    print("=" * 80)
