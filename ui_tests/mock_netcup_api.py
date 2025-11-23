"""Mock Netcup API server for E2E testing.

This mock server implements the Netcup CCP API endpoints used by the application:
- login: Authenticate and get session ID
- logout: Invalidate session
- infoDnsZone: Get DNS zone information
- infoDnsRecords: Get DNS records for a domain
- updateDnsRecords: Update DNS records for a domain

The mock server maintains in-memory state for DNS records and supports
the same API contract as the real Netcup API.
"""
from __future__ import annotations

import secrets
import time
from typing import Any, Dict, List
from flask import Flask, request, jsonify

# Mock data storage
SESSIONS: Dict[str, Dict[str, Any]] = {}  # session_id -> {customer_id, api_key, created_at}
DNS_ZONES: Dict[str, Dict[str, Any]] = {}  # domain -> zone info
DNS_RECORDS: Dict[str, List[Dict[str, Any]]] = {}  # domain -> list of records

# Default test credentials
MOCK_CUSTOMER_ID = "123456"
MOCK_API_KEY = "test-api-key"
MOCK_API_PASSWORD = "test-api-password"

# Session timeout (seconds)
SESSION_TIMEOUT = 300


def create_mock_api_app() -> Flask:
    """Create and configure the mock Netcup API Flask app."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    
    def _validate_session(session_id: str, customer_id: str, api_key: str) -> bool:
        """Validate that a session exists and matches credentials."""
        if session_id not in SESSIONS:
            return False
        
        session = SESSIONS[session_id]
        if session['customer_id'] != customer_id or session['api_key'] != api_key:
            return False
        
        # Check timeout
        if time.time() - session['created_at'] > SESSION_TIMEOUT:
            del SESSIONS[session_id]
            return False
        
        return True
    
    @app.route('/run/webservice/servers/endpoint.php', methods=['POST'])
    def api_endpoint():
        """Main API endpoint that handles all Netcup API actions."""
        try:
            data = request.get_json()
            if not data:
                return jsonify({
                    "status": "error",
                    "statuscode": 4013,
                    "shortmessage": "Validation Error",
                    "longmessage": "Invalid JSON payload"
                }), 400
            
            action = data.get('action')
            param = data.get('param', {})
            
            if action == 'login':
                return handle_login(param)
            elif action == 'logout':
                return handle_logout(param)
            elif action == 'infoDnsZone':
                return handle_info_dns_zone(param)
            elif action == 'infoDnsRecords':
                return handle_info_dns_records(param)
            elif action == 'updateDnsRecords':
                return handle_update_dns_records(param)
            else:
                return jsonify({
                    "status": "error",
                    "statuscode": 4013,
                    "shortmessage": "Validation Error",
                    "longmessage": f"Unknown action: {action}"
                }), 400
        
        except Exception as e:
            return jsonify({
                "status": "error",
                "statuscode": 5029,
                "shortmessage": "Internal Error",
                "longmessage": str(e)
            }), 500
    
    def handle_login(param: Dict[str, Any]) -> tuple:
        """Handle login action."""
        customer_id = param.get('customernumber')
        api_key = param.get('apikey')
        api_password = param.get('apipassword')
        
        # Validate credentials
        if customer_id != MOCK_CUSTOMER_ID or api_key != MOCK_API_KEY or api_password != MOCK_API_PASSWORD:
            return jsonify({
                "status": "error",
                "statuscode": 4013,
                "shortmessage": "Validation Error",
                "longmessage": "Invalid credentials"
            }), 401
        
        # Create session
        session_id = secrets.token_hex(16)
        SESSIONS[session_id] = {
            'customer_id': customer_id,
            'api_key': api_key,
            'created_at': time.time()
        }
        
        return jsonify({
            "serverrequestid": secrets.token_hex(8),
            "clientrequestid": "",
            "action": "login",
            "status": "success",
            "statuscode": 2000,
            "shortmessage": "Login successful",
            "longmessage": "Session has been created successful.",
            "responsedata": {
                "apisessionid": session_id
            }
        }), 200
    
    def handle_logout(param: Dict[str, Any]) -> tuple:
        """Handle logout action."""
        session_id = param.get('apisessionid')
        
        if session_id in SESSIONS:
            del SESSIONS[session_id]
        
        return jsonify({
            "serverrequestid": secrets.token_hex(8),
            "clientrequestid": "",
            "action": "logout",
            "status": "success",
            "statuscode": 2000,
            "shortmessage": "Logout successful",
            "longmessage": "Session has been terminated successful.",
            "responsedata": {}
        }), 200
    
    def handle_info_dns_zone(param: Dict[str, Any]) -> tuple:
        """Handle infoDnsZone action."""
        session_id = param.get('apisessionid')
        customer_id = param.get('customernumber')
        api_key = param.get('apikey')
        domain = param.get('domainname')
        
        # Validate session
        if not _validate_session(session_id, customer_id, api_key):
            return jsonify({
                "status": "error",
                "statuscode": 4013,
                "shortmessage": "Validation Error",
                "longmessage": "Invalid session"
            }), 401
        
        # Get or create zone info
        if domain not in DNS_ZONES:
            DNS_ZONES[domain] = {
                "name": domain,
                "ttl": "86400",
                "serial": "2024112201",
                "refresh": "28800",
                "retry": "7200",
                "expire": "1209600",
                "dnssecstatus": False
            }
        
        return jsonify({
            "serverrequestid": secrets.token_hex(8),
            "clientrequestid": "",
            "action": "infoDnsZone",
            "status": "success",
            "statuscode": 2000,
            "shortmessage": "DNS zone information successful",
            "longmessage": "The dns zone information has been queried successful.",
            "responsedata": DNS_ZONES[domain]
        }), 200
    
    def handle_info_dns_records(param: Dict[str, Any]) -> tuple:
        """Handle infoDnsRecords action."""
        session_id = param.get('apisessionid')
        customer_id = param.get('customernumber')
        api_key = param.get('apikey')
        domain = param.get('domainname')
        
        # Validate session
        if not _validate_session(session_id, customer_id, api_key):
            return jsonify({
                "status": "error",
                "statuscode": 4013,
                "shortmessage": "Validation Error",
                "longmessage": "Invalid session"
            }), 401
        
        # Get or create default records
        if domain not in DNS_RECORDS:
            DNS_RECORDS[domain] = [
                {
                    "id": "1",
                    "hostname": "@",
                    "type": "A",
                    "priority": "",
                    "destination": "192.0.2.1",
                    "deleterecord": False,
                    "state": "yes"
                },
                {
                    "id": "2",
                    "hostname": "www",
                    "type": "A",
                    "priority": "",
                    "destination": "192.0.2.1",
                    "deleterecord": False,
                    "state": "yes"
                },
                {
                    "id": "3",
                    "hostname": "@",
                    "type": "AAAA",
                    "priority": "",
                    "destination": "2001:db8::1",
                    "deleterecord": False,
                    "state": "yes"
                },
                {
                    "id": "4",
                    "hostname": "@",
                    "type": "MX",
                    "priority": "10",
                    "destination": "mail.example.com",
                    "deleterecord": False,
                    "state": "yes"
                },
                {
                    "id": "5",
                    "hostname": "mail",
                    "type": "A",
                    "priority": "",
                    "destination": "192.0.2.10",
                    "deleterecord": False,
                    "state": "yes"
                }
            ]
        
        return jsonify({
            "serverrequestid": secrets.token_hex(8),
            "clientrequestid": "",
            "action": "infoDnsRecords",
            "status": "success",
            "statuscode": 2000,
            "shortmessage": "DNS records successful",
            "longmessage": "The dns records have been queried successful.",
            "responsedata": {
                "dnsrecords": DNS_RECORDS[domain]
            }
        }), 200
    
    def handle_update_dns_records(param: Dict[str, Any]) -> tuple:
        """Handle updateDnsRecords action."""
        session_id = param.get('apisessionid')
        customer_id = param.get('customernumber')
        api_key = param.get('apikey')
        domain = param.get('domainname')
        dns_record_set = param.get('dnsrecordset', {})
        new_records = dns_record_set.get('dnsrecords', [])
        
        # Validate session
        if not _validate_session(session_id, customer_id, api_key):
            return jsonify({
                "status": "error",
                "statuscode": 4013,
                "shortmessage": "Validation Error",
                "longmessage": "Invalid session"
            }), 401
        
        # Ensure domain has records initialized
        if domain not in DNS_RECORDS:
            DNS_RECORDS[domain] = []
        
        # Process updates
        current_records = DNS_RECORDS[domain]
        next_id = max([int(r['id']) for r in current_records] + [0]) + 1
        
        # Update existing records and add new ones
        updated_records = []
        for new_record in new_records:
            record_id = new_record.get('id')
            
            if new_record.get('deleterecord') == True:
                # Skip deleted records
                continue
            
            if record_id:
                # Update existing record
                found = False
                for existing in current_records:
                    if existing['id'] == record_id:
                        existing.update({
                            'hostname': new_record.get('hostname', existing['hostname']),
                            'type': new_record.get('type', existing['type']),
                            'priority': new_record.get('priority', existing['priority']),
                            'destination': new_record.get('destination', existing['destination']),
                            'deleterecord': False,
                            'state': 'yes'
                        })
                        updated_records.append(existing)
                        found = True
                        break
                
                if not found:
                    # ID specified but not found - treat as new
                    new_record['id'] = str(next_id)
                    next_id += 1
                    new_record['deleterecord'] = False
                    new_record['state'] = 'yes'
                    updated_records.append(new_record)
            else:
                # New record without ID
                new_record['id'] = str(next_id)
                next_id += 1
                new_record['deleterecord'] = False
                new_record['state'] = 'yes'
                updated_records.append(new_record)
        
        # Replace records
        DNS_RECORDS[domain] = updated_records
        
        # Update zone serial
        if domain in DNS_ZONES:
            current_serial = int(DNS_ZONES[domain]['serial'])
            DNS_ZONES[domain]['serial'] = str(current_serial + 1)
        
        return jsonify({
            "serverrequestid": secrets.token_hex(8),
            "clientrequestid": "",
            "action": "updateDnsRecords",
            "status": "success",
            "statuscode": 2000,
            "shortmessage": "DNS records successful",
            "longmessage": "The dns records have been updated successful.",
            "responsedata": {
                "dnsrecords": updated_records
            }
        }), 200
    
    return app


def reset_mock_state():
    """Reset all mock API state (sessions, zones, records)."""
    SESSIONS.clear()
    DNS_ZONES.clear()
    DNS_RECORDS.clear()


def seed_test_domain(domain: str, records: List[Dict[str, Any]] | None = None):
    """Seed a test domain with optional custom records."""
    DNS_ZONES[domain] = {
        "name": domain,
        "ttl": "86400",
        "serial": "2024112201",
        "refresh": "28800",
        "retry": "7200",
        "expire": "1209600",
        "dnssecstatus": False
    }
    
    if records is None:
        # Default records
        records = [
            {
                "id": "1",
                "hostname": "@",
                "type": "A",
                "priority": "",
                "destination": "192.0.2.1",
                "deleterecord": False,
                "state": "yes"
            },
            {
                "id": "2",
                "hostname": "www",
                "type": "A",
                "priority": "",
                "destination": "192.0.2.1",
                "deleterecord": False,
                "state": "yes"
            }
        ]
    
    DNS_RECORDS[domain] = records


if __name__ == '__main__':
    # For testing the mock server directly
    app = create_mock_api_app()
    seed_test_domain("test.example.com")
    print(f"Mock Netcup API server running on http://localhost:5555")
    print(f"Test credentials: customer_id={MOCK_CUSTOMER_ID}, api_key={MOCK_API_KEY}, api_password={MOCK_API_PASSWORD}")
    app.run(host='0.0.0.0', port=5555, debug=True)
