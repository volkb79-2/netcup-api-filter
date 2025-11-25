"""
Mock Netcup API Client for Local Testing
Simulates Netcup CCP API responses with realistic demo data
"""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import os

logger = logging.getLogger(__name__)


class NetcupAPIError(Exception):
    """Exception raised for Netcup API errors"""
    pass


class MockNetcupClient:
    """Mock client for simulating Netcup CCP API responses in local testing"""
    
    # Mock DNS records database (in-memory)
    _mock_records: Dict[str, List[Dict[str, Any]]] = {}
    _next_record_id: int = 1000
    
    def __init__(self, customer_id: str, api_key: str, api_password: str, 
                 api_url: str = "https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON"):
        self.customer_id = customer_id
        self.api_key = api_key
        self.api_password = api_password
        self.api_url = api_url
        self.session_id: Optional[str] = None
        
        # Initialize mock data if empty
        if not self._mock_records:
            self._initialize_mock_data()
        
        logger.info(f"🎭 MockNetcupClient initialized with {len(self._mock_records)} domains")
        
    def _initialize_mock_data(self):
        """Initialize realistic mock DNS records for demo domains"""
        # Domain: example.com
        self._mock_records["example.com"] = [
            {
                "id": "1001",
                "hostname": "www",
                "type": "A",
                "priority": "0",
                "destination": "93.184.216.34",
                "deleterecord": False,
                "state": "yes",
                "ttl": "3600"
            },
            {
                "id": "1002",
                "hostname": "mail",
                "type": "A",
                "priority": "0",
                "destination": "93.184.216.35",
                "deleterecord": False,
                "state": "yes",
                "ttl": "3600"
            },
            {
                "id": "1003",
                "hostname": "@",
                "type": "A",
                "priority": "0",
                "destination": "93.184.216.34",
                "deleterecord": False,
                "state": "yes",
                "ttl": "3600"
            },
            {
                "id": "1004",
                "hostname": "ftp",
                "type": "CNAME",
                "priority": "0",
                "destination": "www.example.com",
                "deleterecord": False,
                "state": "yes",
                "ttl": "3600"
            }
        ]
        
        # Domain: api.example.com
        self._mock_records["api.example.com"] = [
            {
                "id": "2001",
                "hostname": "@",
                "type": "A",
                "priority": "0",
                "destination": "203.0.113.10",
                "deleterecord": False,
                "state": "yes",
                "ttl": "300"
            },
            {
                "id": "2002",
                "hostname": "v2",
                "type": "A",
                "priority": "0",
                "destination": "203.0.113.20",
                "deleterecord": False,
                "state": "yes",
                "ttl": "300"
            },
            {
                "id": "2003",
                "hostname": "docs",
                "type": "CNAME",
                "priority": "0",
                "destination": "api.example.com",
                "deleterecord": False,
                "state": "yes",
                "ttl": "3600"
            }
        ]
        
        # Domain: dyn.example.com (for Dynamic DNS)
        self._mock_records["dyn.example.com"] = [
            {
                "id": "3001",
                "hostname": "home",
                "type": "A",
                "priority": "0",
                "destination": "198.51.100.42",
                "deleterecord": False,
                "state": "yes",
                "ttl": "60"
            },
            {
                "id": "3002",
                "hostname": "office",
                "type": "A",
                "priority": "0",
                "destination": "198.51.100.50",
                "deleterecord": False,
                "state": "yes",
                "ttl": "60"
            },
            {
                "id": "3003",
                "hostname": "vpn",
                "type": "A",
                "priority": "0",
                "destination": "198.51.100.100",
                "deleterecord": False,
                "state": "yes",
                "ttl": "300"
            }
        ]
        
        # Domain: services.example.com (multi-record types)
        self._mock_records["services.example.com"] = [
            {
                "id": "4001",
                "hostname": "@",
                "type": "A",
                "priority": "0",
                "destination": "192.0.2.10",
                "deleterecord": False,
                "state": "yes",
                "ttl": "3600"
            },
            {
                "id": "4002",
                "hostname": "@",
                "type": "AAAA",
                "priority": "0",
                "destination": "2001:db8::1",
                "deleterecord": False,
                "state": "yes",
                "ttl": "3600"
            },
            {
                "id": "4003",
                "hostname": "ns1",
                "type": "A",
                "priority": "0",
                "destination": "192.0.2.50",
                "deleterecord": False,
                "state": "yes",
                "ttl": "86400"
            },
            {
                "id": "4004",
                "hostname": "@",
                "type": "MX",
                "priority": "10",
                "destination": "mail.services.example.com",
                "deleterecord": False,
                "state": "yes",
                "ttl": "3600"
            }
        ]
        
        logger.info(f"Initialized mock DNS records for {len(self._mock_records)} domains")
        
    def _make_request(self, action: str, param: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate API request/response"""
        logger.debug(f"Mock API call: {action} with params: {param}")
        
        # Simulate API success response structure
        return {
            "serverrequestid": "mock-request-123",
            "clientrequestid": "",
            "action": action,
            "status": "success",
            "statuscode": 2000,
            "shortmessage": "Login successful",
            "longmessage": "Session has been created successful.",
            "responsedata": {}
        }
    
    def login(self) -> str:
        """Simulate login to Netcup API"""
        self.session_id = f"mock-session-{datetime.now().timestamp()}"
        logger.info(f"Mock login successful: {self.session_id}")
        return self.session_id
    
    def logout(self):
        """Simulate logout from Netcup API"""
        if not self.session_id:
            return
        logger.info(f"Mock logout: {self.session_id}")
        self.session_id = None
    
    def info_dns_zone(self, domain: str) -> Dict[str, Any]:
        """Simulate DNS zone information"""
        if not self.session_id:
            self.login()
        
        logger.info(f"Mock infoDnsZone: {domain}")
        
        # Return realistic zone info
        return {
            "name": domain,
            "ttl": "86400",
            "serial": "2024112501",
            "refresh": "28800",
            "retry": "7200",
            "expire": "1209600",
            "dnssecstatus": False
        }
    
    def info_dns_records(self, domain: str) -> List[Dict[str, Any]]:
        """Simulate getting DNS records"""
        if not self.session_id:
            self.login()
        
        logger.info(f"🎭 Mock infoDnsRecords called for: {domain}")
        
        # Return mock records for known domains
        records = self._mock_records.get(domain, [])
        logger.info(f"🎭 Returning {len(records)} mock records for {domain}")
        if records:
            logger.info(f"🎭 First record: {records[0]['hostname']} -> {records[0]['destination']}")
        return records
    
    def update_dns_records(self, domain: str, dns_records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Simulate updating DNS records"""
        if not self.session_id:
            self.login()
        
        logger.info(f"Mock updateDnsRecords: {domain} with {len(dns_records)} records")
        
        # Initialize domain if doesn't exist
        if domain not in self._mock_records:
            self._mock_records[domain] = []
        
        current_records = self._mock_records[domain]
        
        for record in dns_records:
            record_id = record.get("id")
            
            # Handle delete
            if record.get("deleterecord"):
                self._mock_records[domain] = [r for r in current_records if r["id"] != record_id]
                logger.info(f"Mock deleted record {record_id} from {domain}")
                continue
            
            # Handle create (no ID or new ID)
            if not record_id or record_id == "":
                new_id = str(self._next_record_id)
                self._next_record_id += 1
                record["id"] = new_id
                record["deleterecord"] = False
                self._mock_records[domain].append(record)
                logger.info(f"Mock created record {new_id} in {domain}: {record['hostname']} {record['type']}")
                continue
            
            # Handle update (existing ID)
            found = False
            for i, existing in enumerate(current_records):
                if existing["id"] == record_id:
                    # Preserve ID, update other fields
                    record["deleterecord"] = False
                    self._mock_records[domain][i] = record
                    logger.info(f"Mock updated record {record_id} in {domain}: {record['hostname']} {record['type']}")
                    found = True
                    break
            
            if not found:
                logger.warning(f"Record {record_id} not found in {domain}, treating as create")
                record["deleterecord"] = False
                self._mock_records[domain].append(record)
        
        # Return success response
        return {
            "status": "success",
            "statuscode": 2000
        }
    
    def __enter__(self):
        """Context manager entry"""
        self.login()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.logout()


def get_netcup_client(customer_id: str, api_key: str, api_password: str, api_url: Optional[str] = None) -> Any:
    """
    Factory function to get appropriate Netcup client based on environment.
    
    Returns MockNetcupClient if MOCK_NETCUP_API=true, otherwise real NetcupClient.
    """
    use_mock = os.environ.get('MOCK_NETCUP_API', '').lower() in ('true', '1', 'yes')
    
    if use_mock:
        logger.info("🎭 Using MockNetcupClient for local testing")
        return MockNetcupClient(customer_id, api_key, api_password, api_url or "")
    else:
        from netcup_client import NetcupClient
        logger.info("Using real NetcupClient")
        return NetcupClient(customer_id, api_key, api_password, api_url or "https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON")
