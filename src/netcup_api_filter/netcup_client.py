"""
Netcup API Client
Handles communication with the Netcup CCP API
"""
import requests
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response normalization helpers
#
# NetcupClient.info_dns_records() returns a plain list of record dicts, while
# some mocks/legacy clients (and the raw Netcup CCP API) return a Netcup-style
# envelope: {"status": "...", "responsedata": {"dnsrecords": [...]}, ...}. These
# helpers centralize the "which shape is it" handling so every DNS/DDNS handler
# treats both forms identically instead of re-deriving it inline.
# ---------------------------------------------------------------------------

def extract_dns_records(result: Any) -> List[dict]:
    """Return the list of record dicts from an info_dns_records() result.

    Accepts either a plain list or a Netcup-style envelope. Raises TypeError on
    any other shape so an unexpected response fails loudly rather than silently
    returning no records.
    """
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return result.get('responsedata', {}).get('dnsrecords', []) or []
    raise TypeError(f"Unexpected Netcup response type: {type(result)}")


def mutation_failed(result: Any) -> bool:
    """True if a Netcup mutation envelope reports a non-success status.

    A plain/None result (or an envelope without a status) is treated as success,
    matching NetcupClient.update_dns_records() which returns {'status':'success'}.
    """
    return (
        isinstance(result, dict)
        and bool(result.get('status'))
        and result.get('status') != 'success'
    )


def mutation_message(result: Any, default: str) -> str:
    """Return the error message from a mutation envelope, or ``default``."""
    if isinstance(result, dict):
        return result.get('message', default)
    return default


class NetcupAPIError(Exception):
    """Exception raised for Netcup API errors"""
    pass


class NetcupClient:
    """Client for interacting with Netcup CCP API"""
    
    def __init__(self, customer_id: str, api_key: str, api_password: str, 
                 api_url: str = "https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON",
                 timeout: int = 30):
        self.customer_id = customer_id
        self.api_key = api_key
        self.api_password = api_password
        self.api_url = api_url
        self.timeout = timeout
        self.session_id: Optional[str] = None
        
    def _make_request(self, action: str, param: Dict[str, Any]) -> Dict[str, Any]:
        """Make a request to the Netcup API"""
        payload = {
            "action": action,
            "param": param
        }
        
        try:
            response = requests.post(self.api_url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            try:
                data = response.json()
            except ValueError as e:
                raise NetcupAPIError(f"Invalid JSON from API: {e}")
            if not isinstance(data, dict):
                raise NetcupAPIError(f"Unexpected response shape: {type(data).__name__}")
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
        try:
            self.session_id = response["responsedata"]["apisessionid"]
        except KeyError as e:
            raise NetcupAPIError(f"Missing key in login response: {e}")
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
        try:
            return response["responsedata"]
        except KeyError as e:
            raise NetcupAPIError(f"Missing key in infoDnsZone response: {e}")
    
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
        try:
            return response["responsedata"]["dnsrecords"]
        except KeyError as e:
            raise NetcupAPIError(f"Missing key in infoDnsRecords response: {e}")
    
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
        try:
            return response["responsedata"]
        except KeyError as e:
            raise NetcupAPIError(f"Missing key in updateDnsRecords response: {e}")
    
    def __enter__(self):
        """Context manager entry"""
        self.login()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.logout()
