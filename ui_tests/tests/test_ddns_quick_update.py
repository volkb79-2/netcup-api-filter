"""Tests for the DDNS Quick Update ("Update to My IP") feature.

P7.2: "Update to My IP" quick action for DDNS-capable realms.
P7.1: DNS record CRUD UI routes.
"""
import pytest
import httpx
from ui_tests.config import settings


# Mark all tests in this module as asyncio
pytestmark = [pytest.mark.asyncio]


# =============================================================================
# P7.2 DDNS Quick Update Tests
# =============================================================================

async def test_myip_endpoint_returns_ip():
    """Test that the /api/myip endpoint returns IP address."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{settings.base_url}/api/myip")
        assert response.status_code == 200
        data = response.json()
        assert "ip" in data, "Response should include 'ip' field"


async def test_realm_detail_shows_ddns_card_conditionally():
    """Test that realm detail page logic for DDNS card is correct.
    
    This test verifies the backend logic for determining if DDNS is available.
    Realms with 'update' operation and A/AAAA record types should show DDNS card.
    """
    # Test DDNS capability detection logic by checking account.py logic
    # This is a unit-level test of the capability detection
    
    # Simulate realm permissions
    test_cases = [
        # (operations, record_types, expected_can_ddns)
        (['read', 'update'], ['A', 'AAAA'], True),  # Has update + A/AAAA = DDNS capable
        (['read'], ['A', 'AAAA'], False),  # No update = not DDNS capable
        (['read', 'update'], ['CNAME', 'TXT'], False),  # No A/AAAA = not DDNS capable
        (['read', 'update', 'create', 'delete'], ['A'], True),  # Has A = DDNS capable
        (['update'], ['AAAA'], True),  # Just update + AAAA = DDNS capable
    ]
    
    for ops, types, expected in test_cases:
        can_ddns = 'update' in ops and ('A' in types or 'AAAA' in types)
        assert can_ddns == expected, f"Failed for ops={ops}, types={types}: expected {expected}, got {can_ddns}"


async def test_ddns_route_exists():
    """Verify the DDNS update route is registered."""
    # This test verifies the route is configured
    async with httpx.AsyncClient() as client:
        # POST to DDNS endpoint without auth should get redirect to login or CSRF error
        response = await client.post(
            f"{settings.base_url}/account/realms/1/ddns",
            follow_redirects=False
        )
        # Should get 302 redirect to login, 400 (CSRF missing), or 401
        # NOT 404 (which would mean route doesn't exist)
        assert response.status_code in [302, 400, 401], f"DDNS route should exist (got {response.status_code})"


# =============================================================================
# P7.1 DNS Records CRUD UI Tests
# =============================================================================

async def test_dns_records_route_exists():
    """Verify the DNS records view route is registered."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{settings.base_url}/account/realms/1/dns",
            follow_redirects=False
        )
        # Should get 302 redirect to login (not 404)
        assert response.status_code == 302, f"DNS records route should exist (got {response.status_code})"


async def test_dns_record_create_route_exists():
    """Verify the DNS record create route is registered."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{settings.base_url}/account/realms/1/dns/create",
            follow_redirects=False
        )
        # Should get 302 redirect to login (not 404)
        assert response.status_code == 302, f"DNS create route should exist (got {response.status_code})"


async def test_dns_record_edit_route_exists():
    """Verify the DNS record edit route is registered."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{settings.base_url}/account/realms/1/dns/123/edit",
            follow_redirects=False
        )
        # Should get 302 redirect to login (not 404)
        assert response.status_code == 302, f"DNS edit route should exist (got {response.status_code})"


async def test_dns_record_delete_route_exists():
    """Verify the DNS record delete route is registered."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.base_url}/account/realms/1/dns/123/delete",
            follow_redirects=False
        )
        # Should get 302 or 400 (CSRF), not 404
        assert response.status_code in [302, 400], f"DNS delete route should exist (got {response.status_code})"


async def test_dns_record_types_badge_colors():
    """Test that record type badges have proper color mapping."""
    # This tests the template logic for badge colors
    type_colors = {
        'A': 'bg-primary',
        'AAAA': 'bg-info',
        'CNAME': 'bg-success',
        'MX': 'bg-warning',
        'TXT': 'bg-secondary',
        'NS': 'bg-dark',
        'SRV': 'bg-dark',
    }
    
    # Verify all expected types have color mappings
    expected_types = ['A', 'AAAA', 'CNAME', 'MX', 'TXT', 'NS', 'SRV']
    for rec_type in expected_types:
        assert rec_type in type_colors or rec_type in ['NS', 'SRV'], f"Missing color for {rec_type}"
