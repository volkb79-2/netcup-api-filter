"""
PowerDNS Authoritative Server Backend Implementation.

Implements DNSBackend interface for PowerDNS HTTP API.
"""

import logging
from typing import Any, Dict, List

import httpx

from .base import BackendError, DNSBackend

logger = logging.getLogger(__name__)


class PowerDNSBackend(DNSBackend):
    """PowerDNS Authoritative Server backend implementation."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize PowerDNS backend.
        
        Required config keys:
            api_url: PowerDNS API URL (e.g., http://powerdns:8081)
            api_key: X-API-Key value
        
        Optional config keys:
            timeout: Request timeout in seconds (default: 30)
            server_id: Server ID (default: localhost)
        """
        super().__init__(config)
        
        self.api_url = config['api_url'].rstrip('/')
        self.api_key = config['api_key']
        self.timeout = config.get('timeout', 30)
        self.server_id = config.get('server_id', 'localhost')
        
        self._client: httpx.Client | None = None
    
    @property
    def client(self) -> httpx.Client:
        """Lazy-initialize HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.api_url,
                headers={'X-API-Key': self.api_key},
                timeout=self.timeout
            )
        return self._client
    
    def _ensure_trailing_dot(self, name: str) -> str:
        """Ensure zone/record name has trailing dot for PowerDNS."""
        return name if name.endswith('.') else f"{name}."
    
    def _strip_trailing_dot(self, name: str) -> str:
        """Remove trailing dot from zone/record name."""
        return name.rstrip('.')
    
    def test_connection(self) -> tuple[bool, str]:
        """Test connection to PowerDNS API."""
        try:
            response = self.client.get(f'/api/v1/servers/{self.server_id}')
            response.raise_for_status()
            data = response.json()
            version = data.get('version', 'unknown')
            return True, f"Connected to PowerDNS {version}"
        except Exception as e:
            logger.error(f"PowerDNS connection test failed: {e}")
            return False, str(e)
    
    def list_zones(self) -> List[str]:
        """List all zones manageable by this backend."""
        try:
            response = self.client.get(f'/api/v1/servers/{self.server_id}/zones')
            response.raise_for_status()
            zones = response.json()
            return [self._strip_trailing_dot(z.get('name', '')) for z in zones]
        except Exception as e:
            logger.error(f"Failed to list zones: {e}")
            raise BackendError(f"Failed to list zones: {e}")
    
    def validate_zone_access(self, zone: str) -> tuple[bool, str]:
        """Validate zone access by fetching zone info."""
        try:
            zone_name = self._ensure_trailing_dot(zone)
            response = self.client.get(f'/api/v1/servers/{self.server_id}/zones/{zone_name}')
            response.raise_for_status()
            return True, ""
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return False, f"Zone {zone} not found"
            return False, f"Cannot access zone {zone}: {e}"
        except Exception as e:
            return False, f"Cannot access zone {zone}: {e}"
    
    def list_records(self, zone: str) -> List[Dict[str, Any]]:
        """List all DNS records for a zone."""
        try:
            zone_name = self._ensure_trailing_dot(zone)
            response = self.client.get(f'/api/v1/servers/{self.server_id}/zones/{zone_name}')
            response.raise_for_status()
            zone_data = response.json()
            
            records = []
            for rrset in zone_data.get('rrsets', []):
                rr_name = self._strip_trailing_dot(rrset.get('name', ''))
                rr_type = rrset.get('type', '')
                ttl = rrset.get('ttl', 60)
                
                for record in rrset.get('records', []):
                    if record.get('disabled', False):
                        continue
                    records.append(self.normalize_record({
                        'id': f"{rrset['name']}:{rrset['type']}",
                        'hostname': rr_name,
                        'type': rr_type,
                        'content': record.get('content', ''),
                        'ttl': ttl,
                    }))
            
            return records
        except Exception as e:
            logger.error(f"Failed to list records for {zone}: {e}")
            raise BackendError(f"Failed to list records: {e}")
    
    def create_record(self, zone: str, record: Dict[str, Any]) -> Dict[str, Any]:
        """Create a DNS record."""
        try:
            zone_name = self._ensure_trailing_dot(zone)
            hostname = record['hostname']
            
            # Build full name
            if hostname == '@' or hostname == '':
                name = zone_name
            elif hostname.endswith('.'):
                name = hostname
            else:
                name = f"{hostname}.{zone_name}"
            
            rrset = {
                "name": name,
                "type": record['type'],
                "changetype": "REPLACE",
                "ttl": record.get('ttl', 60),
                "records": [
                    {"content": record['destination'], "disabled": False}
                ]
            }
            
            response = self.client.patch(
                f'/api/v1/servers/{self.server_id}/zones/{zone_name}',
                json={"rrsets": [rrset]}
            )
            response.raise_for_status()
            
            return self.normalize_record({
                'id': f"{name}:{record['type']}",
                'hostname': hostname,
                'type': record['type'],
                'content': record['destination'],
                'ttl': record.get('ttl', 60),
            })
        except Exception as e:
            logger.error(f"Failed to create record in {zone}: {e}")
            raise BackendError(f"Failed to create record: {e}")
    
    def update_record(self, zone: str, record_id: str, record: Dict[str, Any]) -> Dict[str, Any]:
        """Update a DNS record.
        
        PowerDNS uses REPLACE changetype, so update is same as create.
        """
        return self.create_record(zone, record)
    
    def delete_record(self, zone: str, record_id: str) -> bool:
        """Delete a DNS record.
        
        record_id format: "name:type" (e.g., "host.example.com.:A")
        """
        try:
            zone_name = self._ensure_trailing_dot(zone)
            
            # Parse record_id
            parts = record_id.rsplit(':', 1)
            if len(parts) != 2:
                raise BackendError(f"Invalid record_id format: {record_id}")
            
            name, rtype = parts
            name = self._ensure_trailing_dot(name) if not name.endswith('.') else name
            
            rrset = {
                "name": name,
                "type": rtype,
                "changetype": "DELETE"
            }
            
            response = self.client.patch(
                f'/api/v1/servers/{self.server_id}/zones/{zone_name}',
                json={"rrsets": [rrset]}
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to delete record in {zone}: {e}")
            raise BackendError(f"Failed to delete record: {e}")
    
    def get_zone_info(self, zone: str) -> Dict[str, Any]:
        """Get zone information."""
        try:
            zone_name = self._ensure_trailing_dot(zone)
            response = self.client.get(f'/api/v1/servers/{self.server_id}/zones/{zone_name}')
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get zone info for {zone}: {e}")
            raise BackendError(f"Failed to get zone info: {e}")
    
    def normalize_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize PowerDNS record format."""
        hostname = record.get('hostname', record.get('name', '@'))
        hostname = self._strip_trailing_dot(hostname)
        
        return {
            'id': record.get('id', ''),
            'hostname': hostname,
            'type': record.get('type', ''),
            'destination': record.get('content', record.get('destination', '')),
            'priority': record.get('priority'),
            'ttl': record.get('ttl', 60),
        }
    
    def __del__(self):
        """Cleanup HTTP client on destruction."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
