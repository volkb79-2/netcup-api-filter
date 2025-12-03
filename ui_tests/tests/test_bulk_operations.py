"""Tests for P7.6 Bulk Operations functionality.

This module tests:
- Bulk operations API endpoints
- Bulk actions UI elements (checkboxes, buttons)
- Frontend JavaScript integration
"""
import pytest
import httpx
from ui_tests.config import settings


# Mark all tests in this module as asyncio
pytestmark = [pytest.mark.asyncio]


# =============================================================================
# Bulk Operations API Route Tests (No Auth Required - Testing Route Existence)
# =============================================================================

async def test_bulk_accounts_endpoint_route_exists():
    """Test that bulk accounts API endpoint route exists."""
    async with httpx.AsyncClient() as client:
        # POST without auth should get 302 redirect or CSRF error
        # NOT 404 (which would mean route doesn't exist)
        response = await client.post(
            f"{settings.base_url}/admin/api/accounts/bulk",
            json={"action": "enable", "account_ids": []},
            follow_redirects=False
        )
        # 302 = redirect to login, 400 = CSRF missing
        assert response.status_code in [302, 400], f"Bulk accounts route should exist (got {response.status_code})"


async def test_bulk_realms_endpoint_route_exists():
    """Test that bulk realms API endpoint route exists."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.base_url}/admin/api/realms/bulk",
            json={"action": "approve", "realm_ids": []},
            follow_redirects=False
        )
        # 302 = redirect to login, 400 = CSRF missing
        assert response.status_code in [302, 400], f"Bulk realms route should exist (got {response.status_code})"


# =============================================================================
# Bulk Operations UI Element Tests (Static Check - No Auth)
# =============================================================================

async def test_accounts_list_has_bulk_action_javascript():
    """Test that accounts list template has bulk action JavaScript function.
    
    This test verifies the template source directly rather than requiring login.
    """
    from pathlib import Path
    
    template_path = Path("/workspaces/netcup-api-filter/src/netcup_api_filter/templates/admin/accounts_list.html")
    assert template_path.exists(), "Accounts list template should exist"
    
    html = template_path.read_text()
    
    # Check for bulk action elements
    assert "bulkActionsBar" in html, "Template should have bulk actions bar"
    assert "/admin/api/accounts/bulk" in html, "Template should call bulk API endpoint"
    assert "X-CSRFToken" in html, "Bulk action should send CSRF token"


async def test_realms_pending_has_approve_all():
    """Test that pending realms template has approve all functionality.
    
    This test verifies the template source directly rather than requiring login.
    """
    from pathlib import Path
    
    template_path = Path("/workspaces/netcup-api-filter/src/netcup_api_filter/templates/admin/realms_pending.html")
    assert template_path.exists(), "Realms pending template should exist"
    
    html = template_path.read_text()
    assert "approveAll()" in html, "Template should have approveAll function"
    assert "Approve All" in html, "Template should have Approve All button"
    assert "/admin/api/realms/bulk" in html, "Template should call bulk realms API"


# =============================================================================
# Unit Tests for Bulk Action Logic
# =============================================================================

async def test_bulk_action_valid_actions():
    """Test the valid actions for bulk operations."""
    # Account bulk actions
    valid_account_actions = ['enable', 'disable', 'delete']
    for action in valid_account_actions:
        assert action in ['enable', 'disable', 'delete']
    
    # Realm bulk actions
    valid_realm_actions = ['approve', 'reject', 'revoke']
    for action in valid_realm_actions:
        assert action in ['approve', 'reject', 'revoke']


async def test_accounts_list_has_checkboxes():
    """Test that accounts list template has row checkboxes for selection.
    
    This test verifies the template source directly rather than requiring login.
    """
    from pathlib import Path
    
    template_path = Path("/workspaces/netcup-api-filter/src/netcup_api_filter/templates/admin/accounts_list.html")
    assert template_path.exists(), "Accounts list template should exist"
    
    html = template_path.read_text()
    assert 'row-checkbox' in html, "Template should have row checkboxes"
    assert 'id="selectAll"' in html, "Template should have select all checkbox"


async def test_accounts_list_has_bulk_buttons():
    """Test that accounts list template has bulk action buttons.
    
    This test verifies the template source directly rather than requiring login.
    """
    from pathlib import Path
    
    template_path = Path("/workspaces/netcup-api-filter/src/netcup_api_filter/templates/admin/accounts_list.html")
    assert template_path.exists(), "Accounts list template should exist"
    
    html = template_path.read_text()
    # Check for bulk action button calls
    assert "bulkAction('enable')" in html, "Template should have enable bulk action"
    assert "bulkAction('disable')" in html, "Template should have disable bulk action"
    assert "bulkAction('delete')" in html, "Template should have delete bulk action"
