"""
Netcup API Client
Handles communication with the Netcup CCP API
"""
import requests
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class NetcupAPIError(Exception):
    """Exception raised for Netcup API errors"""
    pass


class NetcupClient:
    """Client for interacting with Netcup CCP API"""
    
    def __init__(self, customer_id: str, api_key: str, api_password: str, 
                 api_url: str = "https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON"):
        self.customer_id = customer_id
        self.api_key = api_key
        self.api_password = api_password
        self.api_url = api_url
        self.session_id: Optional[str] = None
        
    def _make_request(self, action: str, param: Dict[str, Any]) -> Dict[str, Any]:
        """Make a request to the Netcup API"""
        payload = {
            "action": action,
            "param": param
        }
        
        try:
            response = requests.post(self.api_url, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            # Check for API-level errors
            if data.get("status") != "success":
                error_msg = data.get("longmessage", data.get("statuscode", "Unknown error"))
                raise NetcupAPIError(f"API error: {error_msg}")
                
            return data
        except requests.RequestException as e:
            logger.error(f"Request failed: {e}")
            raise NetcupAPIError(f"Request failed: {e}")
    
    def login(self) -> str:
        """Login to the Netcup API and get a session ID"""
        param = {
            "customernumber": self.customer_id,
            "apikey": self.api_key,
            "apipassword": self.api_password
        }
        
        response = self._make_request("login", param)
        self.session_id = response["responsedata"]["apisessionid"]
        logger.info("Successfully logged in to Netcup API")
        return self.session_id
    
    def logout(self):
        """Logout from the Netcup API"""
        if not self.session_id:
            return
            
        param = {
            "customernumber": self.customer_id,
            "apikey": self.api_key,
            "apisessionid": self.session_id
        }
        
        try:
            self._make_request("logout", param)
            logger.info("Successfully logged out from Netcup API")
        finally:
            self.session_id = None
    
    def info_dns_zone(self, domain: str) -> Dict[str, Any]:
        """Get DNS zone information for a domain"""
        if not self.session_id:
            self.login()
            
        param = {
            "customernumber": self.customer_id,
            "apikey": self.api_key,
            "apisessionid": self.session_id,
            "domainname": domain
        }
        
        response = self._make_request("infoDnsZone", param)
        return response["responsedata"]
    
    def info_dns_records(self, domain: str) -> List[Dict[str, Any]]:
        """Get all DNS records for a domain"""
        if not self.session_id:
            self.login()
            
        param = {
            "customernumber": self.customer_id,
            "apikey": self.api_key,
            "apisessionid": self.session_id,
            "domainname": domain
        }
        
        response = self._make_request("infoDnsRecords", param)
        return response["responsedata"]["dnsrecords"]
    
    def update_dns_records(self, domain: str, dns_records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Update DNS records for a domain"""
        if not self.session_id:
            self.login()
            
        param = {
            "customernumber": self.customer_id,
            "apikey": self.api_key,
            "apisessionid": self.session_id,
            "domainname": domain,
            "dnsrecordset": {
                "dnsrecords": dns_records
            }
        }
        
        response = self._make_request("updateDnsRecords", param)
        return response["responsedata"]
    
    def __enter__(self):
        """Context manager entry"""
        self.login()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.logout()
