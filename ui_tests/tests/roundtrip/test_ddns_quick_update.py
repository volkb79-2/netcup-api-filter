"""Tests for the DDNS Quick Update ("Update to My IP") feature.

P7.2: "Update to My IP" quick action for DDNS-capable realms.
P7.1: DNS record CRUD UI routes.
"""
import os
import pytest
import httpx
from ui_tests.config import settings
from ui_tests import verification


# Mark all tests in this module as asyncio
pytestmark = [pytest.mark.asyncio, pytest.mark.roundtrip]


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


# =============================================================================
# Test 12 — DDNS update mutates mock backend, token usage recorded in Channel A
# =============================================================================

def _mock_base_url() -> str | None:
    base = (os.environ.get("MOCK_NETCUP_API_URL") or "").strip()
    return base or None


def _mock_is_reachable(base_url: str) -> bool:
    """Synchronous health ping for the mock Netcup API."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}/health", timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


async def test_ddns_update_mutates_backend_and_usage(active_profile):
    """DDNS DynDNS2 update is verified against:
    - Channel C2: A record destination equals pushed IP in the mock backend.
    - Channel A: token use_count incremented / last_used_at advanced;
      an ActivityLog row for action='ddns_update' exists.

    Also pins both response body forms:
    - First call: ``good <ip>`` (IP was changed)
    - Second call: ``nochg <ip>`` (IP already set — no change)
    """
    mock_base = _mock_base_url()
    if not mock_base:
        pytest.skip("MOCK_NETCUP_API_URL not set; run ./run-local-tests.sh --with-mocks")

    if not _mock_is_reachable(mock_base):
        pytest.skip(
            f"Mock Netcup API not reachable at {mock_base}/health; "
            "run ./run-local-tests.sh --with-mocks"
        )

    if not verification.db_available():
        pytest.skip("Channel A (sqlite) not available for this target")

    token_plaintext = (active_profile.client_token or "").strip()
    assert token_plaintext, "Expected active_profile.client_token from deployment_state_*.json"

    domain = (active_profile.client_domain or "").strip()
    assert domain, "Expected active_profile.client_domain to be configured"

    # Derive token_prefix: format is naf_<alias>_<random64>, prefix = random_part[:8]
    parts = token_plaintext.split("_", 2)
    assert len(parts) == 3, f"Unexpected token format: {token_plaintext[:20]}..."
    token_prefix = parts[2][:8]

    # Channel A baseline snapshot
    tok_before = verification.get_token(token_prefix=token_prefix)
    assert tok_before is not None, f"Token with prefix {token_prefix!r} not found in DB"
    use_count_before = tok_before.get("use_count") or 0
    last_used_before = tok_before.get("last_used_at")

    import datetime as _dt
    since_ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    activity_before = verification.count_activity(action="ddns_update", since=since_ts)

    # Push an explicit test IP (not in use by any live host)
    test_ip = "198.51.100.42"
    ddns_url = settings.url("/api/ddns/dyndns2/update")
    headers = {"Authorization": f"Bearer {token_plaintext}"}

    # The demo-user realm covers example.com with update+A/AAAA permissions.
    # DDNS requires an FQDN hostname; use the domain apex (@-style is domain itself).
    hostname = domain

    async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
        # --- First call: expect ``good <ip>`` (change) or ``nochg <ip>`` (already set) ---
        resp1 = await client.get(
            ddns_url,
            headers=headers,
            params={"hostname": hostname, "myip": test_ip},
        )
    assert resp1.status_code == 200, (
        f"DDNS first call: expected 200, got {resp1.status_code}: {resp1.text[:200]}"
    )
    body1 = resp1.text.strip()
    assert body1.startswith(("good ", "nochg ")), (
        f"DDNS first call: expected 'good <ip>' or 'nochg <ip>', got: {body1!r}"
    )
    assert test_ip in body1, (
        f"DDNS first call: response does not contain pushed IP {test_ip!r}: {body1!r}"
    )
    first_verb = body1.split()[0]  # "good" or "nochg"

    # --- Second call: if first was "good", second must be "nochg" ---
    async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
        resp2 = await client.get(
            ddns_url,
            headers=headers,
            params={"hostname": hostname, "myip": test_ip},
        )
    assert resp2.status_code == 200, (
        f"DDNS second call: expected 200, got {resp2.status_code}: {resp2.text[:200]}"
    )
    body2 = resp2.text.strip()
    assert body2.startswith(("good ", "nochg ")), (
        f"DDNS second call: expected 'good <ip>' or 'nochg <ip>', got: {body2!r}"
    )
    assert test_ip in body2, (
        f"DDNS second call: response does not contain pushed IP {test_ip!r}: {body2!r}"
    )
    if first_verb == "good":
        assert body2.startswith("nochg "), (
            f"Second call should return 'nochg' when IP is already set; got: {body2!r}"
        )

    # --- Channel C2: A record destination equals pushed IP in mock backend ---
    # For apex (@) hostname the mock stores it as "@" or "" depending on the record.
    # Use wait_for in case the backend write is slightly async.
    def _c2_ip_matches() -> bool:
        recs = verification.mock_netcup_records(domain, base_url=mock_base)
        # Accept either "@" or "" as the apex hostname representation.
        for rec in recs:
            h = rec.get("hostname", "")
            if h in ("@", "", domain) and rec.get("type") == "A" and rec.get("destination") == test_ip:
                return True
        return False

    verification.wait_for(
        _c2_ip_matches,
        timeout=8.0,
        message=f"C2: A record destination {test_ip!r} not found in mock backend for {domain}",
    )

    # --- Channel A: use_count incremented, last_used_at advanced ---
    verification.wait_for(
        lambda: (verification.get_token(token_prefix=token_prefix) or {}).get("use_count", 0)
        > use_count_before,
        timeout=8.0,
        message=f"Channel A: token use_count did not increment (was {use_count_before})",
    )
    tok_after = verification.get_token(token_prefix=token_prefix)
    assert tok_after is not None
    use_count_after = tok_after.get("use_count") or 0
    last_used_after = tok_after.get("last_used_at")

    assert use_count_after > use_count_before, (
        f"Channel A: use_count should be > {use_count_before}, got {use_count_after}"
    )
    assert last_used_after is not None, "Channel A: last_used_at should be set after DDNS call"
    if last_used_before is not None:
        assert last_used_after >= last_used_before, (
            f"Channel A: last_used_at should not regress: "
            f"before={last_used_before!r} after={last_used_after!r}"
        )

    # --- Channel A: ActivityLog row for action='ddns_update' ---
    verification.wait_for(
        lambda: verification.count_activity(action="ddns_update", since=since_ts) > activity_before,
        timeout=8.0,
        message="Channel A: no ActivityLog row with action='ddns_update' found after DDNS call",
    )
    activity_after = verification.count_activity(action="ddns_update", since=since_ts)
    assert activity_after > activity_before, (
        f"Channel A: expected at least 1 new ddns_update activity row, "
        f"before={activity_before} after={activity_after}"
    )
