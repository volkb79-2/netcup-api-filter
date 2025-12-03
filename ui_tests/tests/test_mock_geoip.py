"""Tests for mock GeoIP server.

Run with: pytest ui_tests/tests/test_mock_geoip.py -v
"""
import pytest
import base64
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


pytestmark = pytest.mark.asyncio


@pytest.fixture
def geoip_client():
    """Create test client for mock GeoIP app."""
    from mock_geoip_server import create_mock_geoip_app
    
    app = create_mock_geoip_app()
    with app.test_client() as client:
        yield client


def get_auth_header(account_id: str = "123456", license_key: str = "test-key"):
    """Generate Basic auth header."""
    credentials = f"{account_id}:{license_key}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


class TestGeoIPCityEndpoint:
    """Tests for /geoip/v2.1/city/<ip> endpoint."""
    
    def test_city_lookup_google_dns(self, geoip_client):
        """Test city lookup for Google DNS (8.8.8.8)."""
        response = geoip_client.get(
            "/geoip/v2.1/city/8.8.8.8",
            headers=get_auth_header()
        )
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert data["country"]["iso_code"] == "US"
        assert data["city"]["names"]["en"] == "Mountain View"
        assert data["location"]["latitude"] == pytest.approx(37.386, rel=0.01)
        assert data["location"]["time_zone"] == "America/Los_Angeles"
        assert data["traits"]["ip_address"] == "8.8.8.8"
    
    def test_city_lookup_cloudflare_dns(self, geoip_client):
        """Test city lookup for Cloudflare DNS (1.1.1.1)."""
        response = geoip_client.get(
            "/geoip/v2.1/city/1.1.1.1",
            headers=get_auth_header()
        )
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert data["country"]["iso_code"] == "AU"
        assert data["city"]["names"]["en"] == "Sydney"
    
    def test_city_lookup_germany(self, geoip_client):
        """Test city lookup for German IP."""
        response = geoip_client.get(
            "/geoip/v2.1/city/46.38.225.0",
            headers=get_auth_header()
        )
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert data["country"]["iso_code"] == "DE"
        assert data["city"]["names"]["en"] == "Frankfurt"
        assert data["location"]["time_zone"] == "Europe/Berlin"
    
    def test_city_lookup_private_ip(self, geoip_client):
        """Test city lookup for private IP returns minimal data."""
        response = geoip_client.get(
            "/geoip/v2.1/city/192.168.1.1",
            headers=get_auth_header()
        )
        
        assert response.status_code == 200
        data = response.get_json()
        
        # Private IPs should have traits but no location
        assert data["traits"]["ip_address"] == "192.168.1.1"
        assert "country" not in data or data.get("country") is None
    
    def test_city_lookup_unknown_ip(self, geoip_client):
        """Test city lookup for unknown IP returns generic response."""
        response = geoip_client.get(
            "/geoip/v2.1/city/203.0.113.50",  # TEST-NET-3 (unknown)
            headers=get_auth_header()
        )
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert data["traits"]["ip_address"] == "203.0.113.50"
        # Unknown IPs get "XX" country code
        assert data["country"]["iso_code"] == "XX"
    
    def test_city_lookup_invalid_ip(self, geoip_client):
        """Test city lookup for invalid IP returns 400."""
        response = geoip_client.get(
            "/geoip/v2.1/city/not-an-ip",
            headers=get_auth_header()
        )
        
        assert response.status_code == 400
        data = response.get_json()
        assert data["code"] == "IP_ADDRESS_INVALID"
    
    def test_city_lookup_no_auth(self, geoip_client):
        """Test city lookup without auth returns 401."""
        response = geoip_client.get("/geoip/v2.1/city/8.8.8.8")
        
        assert response.status_code == 401
        data = response.get_json()
        assert data["code"] == "AUTHORIZATION_INVALID"
    
    def test_city_lookup_invalid_auth(self, geoip_client):
        """Test city lookup with invalid auth returns 401."""
        response = geoip_client.get(
            "/geoip/v2.1/city/8.8.8.8",
            headers={"Authorization": "Basic invalid"}
        )
        
        assert response.status_code == 401


class TestGeoIPCountryEndpoint:
    """Tests for /geoip/v2.1/country/<ip> endpoint."""
    
    def test_country_lookup_google_dns(self, geoip_client):
        """Test country lookup returns country-level data only."""
        response = geoip_client.get(
            "/geoip/v2.1/country/8.8.8.8",
            headers=get_auth_header()
        )
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert data["country"]["iso_code"] == "US"
        assert data["continent"]["code"] == "NA"
        assert data["traits"]["ip_address"] == "8.8.8.8"
        
        # Country endpoint shouldn't have city-level data
        assert "city" not in data
        assert "postal" not in data
    
    def test_country_lookup_no_auth(self, geoip_client):
        """Test country lookup without auth returns 401."""
        response = geoip_client.get("/geoip/v2.1/country/8.8.8.8")
        
        assert response.status_code == 401


class TestGeoIPInsightsEndpoint:
    """Tests for /geoip/v2.1/insights/<ip> endpoint."""
    
    def test_insights_lookup_includes_isp(self, geoip_client):
        """Test insights lookup includes ISP data."""
        response = geoip_client.get(
            "/geoip/v2.1/insights/8.8.8.8",
            headers=get_auth_header()
        )
        
        assert response.status_code == 200
        data = response.get_json()
        
        # Insights should include additional traits
        assert "autonomous_system_number" in data["traits"]
        assert "isp" in data["traits"]
        assert "organization" in data["traits"]


class TestHealthEndpoint:
    """Tests for health check endpoint."""
    
    def test_health_check(self, geoip_client):
        """Test health endpoint returns OK."""
        response = geoip_client.get("/health")
        
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "ok"
        assert data["service"] == "mock-geoip"


class TestMockDataManagement:
    """Tests for mock data management functions."""
    
    def test_add_custom_ip(self, geoip_client):
        """Test adding custom IP response."""
        from mock_geoip_server import add_test_ip, reset_mock_data
        
        # Add custom IP
        add_test_ip("10.0.0.1", {
            "country": {"iso_code": "XX", "names": {"en": "Test Country"}},
            "city": {"names": {"en": "Test City"}},
            "traits": {"ip_address": "10.0.0.1"}
        })
        
        response = geoip_client.get(
            "/geoip/v2.1/city/10.0.0.1",
            headers=get_auth_header()
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data["city"]["names"]["en"] == "Test City"
        
        # Reset to defaults
        reset_mock_data()
    
    def test_reset_clears_custom_ips(self, geoip_client):
        """Test reset removes custom IPs."""
        from mock_geoip_server import add_test_ip, reset_mock_data, MOCK_GEOIP_RESPONSES
        
        # Add and reset
        add_test_ip("custom.ip", {"test": True})
        reset_mock_data()
        
        # Custom IP should be gone
        assert "custom.ip" not in MOCK_GEOIP_RESPONSES
        # Default IPs should remain
        assert "8.8.8.8" in MOCK_GEOIP_RESPONSES


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
