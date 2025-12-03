"""Mock MaxMind GeoIP Web Services server for testing.

Implements the MaxMind GeoIP2 Web Services API for local testing.
This avoids hitting the real MaxMind API during tests.

Documentation:
- https://dev.maxmind.com/geoip/geolocate-an-ip/web-services/
- https://dev.maxmind.com/geoip/docs/web-services/requests/
- https://dev.maxmind.com/geoip/docs/web-services/responses/

Usage:
    # Start mock server
    python ui_tests/mock_geoip_server.py
    
    # Or use in tests via fixture
    @pytest.fixture
    def mock_geoip_server():
        app = create_mock_geoip_app()
        ...
"""
from __future__ import annotations

import base64
from typing import Dict, Any
from flask import Flask, request, jsonify, Response


# Mock GeoIP responses for known test IPs
# Format follows MaxMind GeoIP2 City response structure
MOCK_GEOIP_RESPONSES: Dict[str, Dict[str, Any]] = {
    # Google DNS
    "8.8.8.8": {
        "continent": {
            "code": "NA",
            "geoname_id": 6255149,
            "names": {"en": "North America", "de": "Nordamerika"}
        },
        "country": {
            "geoname_id": 6252001,
            "iso_code": "US",
            "names": {"en": "United States", "de": "USA"}
        },
        "registered_country": {
            "geoname_id": 6252001,
            "iso_code": "US",
            "names": {"en": "United States"}
        },
        "city": {
            "geoname_id": 5375480,
            "names": {"en": "Mountain View"}
        },
        "location": {
            "accuracy_radius": 1000,
            "latitude": 37.386,
            "longitude": -122.0838,
            "time_zone": "America/Los_Angeles"
        },
        "postal": {"code": "94035"},
        "subdivisions": [
            {
                "geoname_id": 5332921,
                "iso_code": "CA",
                "names": {"en": "California"}
            }
        ],
        "traits": {
            "ip_address": "8.8.8.8",
            "network": "8.8.8.0/24"
        }
    },
    # Cloudflare DNS
    "1.1.1.1": {
        "continent": {
            "code": "OC",
            "geoname_id": 6255151,
            "names": {"en": "Oceania"}
        },
        "country": {
            "geoname_id": 2077456,
            "iso_code": "AU",
            "names": {"en": "Australia", "de": "Australien"}
        },
        "registered_country": {
            "geoname_id": 2077456,
            "iso_code": "AU",
            "names": {"en": "Australia"}
        },
        "city": {
            "geoname_id": 2147714,
            "names": {"en": "Sydney"}
        },
        "location": {
            "accuracy_radius": 500,
            "latitude": -33.8688,
            "longitude": 151.2093,
            "time_zone": "Australia/Sydney"
        },
        "subdivisions": [
            {
                "geoname_id": 2155400,
                "iso_code": "NSW",
                "names": {"en": "New South Wales"}
            }
        ],
        "traits": {
            "ip_address": "1.1.1.1",
            "network": "1.1.1.0/24"
        }
    },
    # Germany - Netcup typical location
    "46.38.225.0": {
        "continent": {
            "code": "EU",
            "geoname_id": 6255148,
            "names": {"en": "Europe", "de": "Europa"}
        },
        "country": {
            "geoname_id": 2921044,
            "iso_code": "DE",
            "names": {"en": "Germany", "de": "Deutschland"}
        },
        "city": {
            "geoname_id": 2925533,
            "names": {"en": "Frankfurt", "de": "Frankfurt am Main"}
        },
        "location": {
            "accuracy_radius": 100,
            "latitude": 50.1109,
            "longitude": 8.6821,
            "time_zone": "Europe/Berlin"
        },
        "subdivisions": [
            {
                "geoname_id": 2905330,
                "iso_code": "HE",
                "names": {"en": "Hesse", "de": "Hessen"}
            }
        ],
        "traits": {
            "ip_address": "46.38.225.0",
            "network": "46.38.224.0/21"
        }
    },
    # UK
    "185.199.108.1": {
        "continent": {
            "code": "EU",
            "geoname_id": 6255148,
            "names": {"en": "Europe"}
        },
        "country": {
            "geoname_id": 2635167,
            "iso_code": "GB",
            "names": {"en": "United Kingdom", "de": "Vereinigtes Königreich"}
        },
        "city": {
            "geoname_id": 2643743,
            "names": {"en": "London"}
        },
        "location": {
            "accuracy_radius": 200,
            "latitude": 51.5074,
            "longitude": -0.1278,
            "time_zone": "Europe/London"
        },
        "traits": {
            "ip_address": "185.199.108.1",
            "network": "185.199.108.0/22"
        }
    },
    # Private IP - should return empty/minimal response
    "192.168.1.1": {
        "traits": {
            "ip_address": "192.168.1.1",
            "is_anonymous": False,
            "network": "192.168.0.0/16"
        }
    },
    # Localhost
    "127.0.0.1": {
        "traits": {
            "ip_address": "127.0.0.1",
            "is_anonymous": False,
            "network": "127.0.0.0/8"
        }
    }
}

# Mock credentials (matches format in geoIP.conf)
MOCK_ACCOUNT_ID = "1262143"
MOCK_LICENSE_KEY = "test-license-key"


def create_mock_geoip_app() -> Flask:
    """Create Flask app implementing MaxMind GeoIP Web Services API."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    
    def _verify_auth() -> tuple[bool, str]:
        """Verify Basic Auth header.
        
        Returns:
            (is_valid, error_message)
        """
        auth_header = request.headers.get('Authorization', '')
        
        if not auth_header.startswith('Basic '):
            return False, "Authorization header must use Basic auth"
        
        try:
            # Decode Base64 credentials
            encoded = auth_header[6:]  # Remove 'Basic ' prefix
            decoded = base64.b64decode(encoded).decode('utf-8')
            account_id, license_key = decoded.split(':', 1)
            
            # Validate credentials (accept mock or any for testing)
            # In real tests, you might want to verify specific credentials
            if not account_id or not license_key:
                return False, "Account ID and license key required"
            
            return True, ""
        except Exception as e:
            return False, f"Invalid Authorization header: {e}"
    
    def _get_response_for_ip(ip: str) -> Dict[str, Any]:
        """Get mock response for an IP address."""
        if ip in MOCK_GEOIP_RESPONSES:
            return MOCK_GEOIP_RESPONSES[ip]
        
        # Generate generic response for unknown IPs
        # Determine if it's a private IP
        is_private = (
            ip.startswith('10.') or
            ip.startswith('172.16.') or ip.startswith('172.17.') or
            ip.startswith('172.18.') or ip.startswith('172.19.') or
            ip.startswith('172.2') or ip.startswith('172.30.') or ip.startswith('172.31.') or
            ip.startswith('192.168.') or
            ip.startswith('127.')
        )
        
        if is_private:
            return {
                "traits": {
                    "ip_address": ip,
                    "is_anonymous": False
                }
            }
        
        # Return a generic "unknown location" response
        return {
            "continent": {
                "code": "XX",
                "names": {"en": "Unknown"}
            },
            "country": {
                "iso_code": "XX",
                "names": {"en": "Unknown"}
            },
            "traits": {
                "ip_address": ip
            }
        }
    
    @app.route('/geoip/v2.1/city/<ip>', methods=['GET'])
    def city_lookup(ip: str):
        """GeoIP2 City endpoint.
        
        Returns city-level location data for an IP address.
        https://dev.maxmind.com/geoip/docs/web-services/responses/#city-body
        """
        is_valid, error = _verify_auth()
        if not is_valid:
            return jsonify({
                "code": "AUTHORIZATION_INVALID",
                "error": error
            }), 401
        
        # Validate IP format (basic check)
        parts = ip.split('.')
        if len(parts) != 4:
            return jsonify({
                "code": "IP_ADDRESS_INVALID",
                "error": f"'{ip}' is not a valid IP address"
            }), 400
        
        try:
            for part in parts:
                num = int(part)
                if num < 0 or num > 255:
                    raise ValueError()
        except ValueError:
            return jsonify({
                "code": "IP_ADDRESS_INVALID",
                "error": f"'{ip}' is not a valid IP address"
            }), 400
        
        response = _get_response_for_ip(ip)
        return jsonify(response), 200
    
    @app.route('/geoip/v2.1/country/<ip>', methods=['GET'])
    def country_lookup(ip: str):
        """GeoIP2 Country endpoint.
        
        Returns country-level location data for an IP address.
        https://dev.maxmind.com/geoip/docs/web-services/responses/#country-body
        """
        is_valid, error = _verify_auth()
        if not is_valid:
            return jsonify({
                "code": "AUTHORIZATION_INVALID",
                "error": error
            }), 401
        
        # Get full city response and filter to country-only fields
        response = _get_response_for_ip(ip)
        country_response = {
            k: v for k, v in response.items()
            if k in ['continent', 'country', 'registered_country', 'represented_country', 'traits']
        }
        
        return jsonify(country_response), 200
    
    @app.route('/geoip/v2.1/insights/<ip>', methods=['GET'])
    def insights_lookup(ip: str):
        """GeoIP2 Insights endpoint.
        
        Returns detailed insights data for an IP address.
        https://dev.maxmind.com/geoip/docs/web-services/responses/#insights-body
        """
        is_valid, error = _verify_auth()
        if not is_valid:
            return jsonify({
                "code": "AUTHORIZATION_INVALID",
                "error": error
            }), 401
        
        response = _get_response_for_ip(ip)
        
        # Add additional insights fields
        response.setdefault('traits', {})
        response['traits'].update({
            'autonomous_system_number': 15169,
            'autonomous_system_organization': 'Google LLC',
            'isp': 'Google LLC',
            'organization': 'Google LLC',
            'user_type': 'hosting'
        })
        
        return jsonify(response), 200
    
    @app.route('/health', methods=['GET'])
    def health():
        """Health check endpoint."""
        return jsonify({"status": "ok", "service": "mock-geoip"}), 200
    
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({
            "code": "NOT_FOUND",
            "error": "The requested resource was not found"
        }), 404
    
    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({
            "code": "INTERNAL_ERROR",
            "error": str(e)
        }), 500
    
    return app


def add_test_ip(ip: str, location: Dict[str, Any]):
    """Add a custom IP response for testing.
    
    Args:
        ip: IP address to add
        location: MaxMind-format location response
    """
    MOCK_GEOIP_RESPONSES[ip] = location


def reset_mock_data():
    """Reset mock data to defaults."""
    # Keep only the default entries - modify in place to preserve references
    defaults = {"8.8.8.8", "1.1.1.1", "46.38.225.0", "185.199.108.1", "192.168.1.1", "127.0.0.1"}
    keys_to_remove = [k for k in MOCK_GEOIP_RESPONSES if k not in defaults]
    for key in keys_to_remove:
        del MOCK_GEOIP_RESPONSES[key]


# Create app instance for gunicorn (e.g., gunicorn mock_geoip_server:app)
app = create_mock_geoip_app()


if __name__ == '__main__':
    print("Mock MaxMind GeoIP server running on http://localhost:5556")
    print("Endpoints:")
    print("  GET /geoip/v2.1/city/<ip>     - City lookup")
    print("  GET /geoip/v2.1/country/<ip>  - Country lookup")
    print("  GET /geoip/v2.1/insights/<ip> - Insights lookup")
    print("  GET /health                   - Health check")
    print("\nTest IPs with mock data:")
    for ip in MOCK_GEOIP_RESPONSES:
        print(f"  - {ip}")
    print("\nAuth: Basic auth with any AccountID:LicenseKey")
    app.run(host='0.0.0.0', port=5556, debug=True)
