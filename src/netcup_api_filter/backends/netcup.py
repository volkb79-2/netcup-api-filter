"""
Netcup CCP API Backend Implementation.

Implements DNSBackend interface for Netcup's Customer Control Panel API.
"""

import logging
from typing import Any, Dict, List

from .base import BackendError, DNSBackend

logger = logging.getLogger(__name__)


class NetcupBackend(DNSBackend):
    """Netcup CCP API backend implementation."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize Netcup backend.
        
        Required config keys:
            customer_id: Netcup customer number
            api_key: API key from CCP
            api_password: API password from CCP
        
        Optional config keys:
            api_url: API endpoint URL (default: Netcup production)
            timeout: Request timeout in seconds (default: 30)
        """
        super().__init__(config)
        
        # Import here to avoid circular imports
        from ..netcup_client import NetcupClient
        
        self.client = NetcupClient(
            customer_id=config['customer_id'],
            api_key=config['api_key'],
            api_password=config['api_password'],
            api_url=config.get('api_url', 'https://ccp.netcup.net/run/webservice/servers/endpoint.php?JSON'),
            timeout=config.get('timeout', 30)
        )
    
    def test_connection(self) -> tuple[bool, str]:
        """Test connection by logging in and out."""
        try:
            self.client.login()
            self.client.logout()
            return True, "Connection successful"
        except Exception as e:
            logger.error(f"Netcup connection test failed: {e}")
            return False, str(e)
    
    def list_zones(self) -> List[str]:
        """List zones - Netcup doesn't support zone enumeration.
        
        Netcup API requires knowing the domain name beforehand,
        so we return an empty list. Admin must manually specify zones.
        """
        logger.warning("Netcup API does not support zone enumeration")
        return []
    
    def validate_zone_access(self, zone: str) -> tuple[bool, str]:
        """Validate zone access by attempting to fetch zone info."""
        try:
            self.client.login()
            try:
                self.client.info_dns_zone(zone)
                return True, ""
            finally:
                self.client.logout()
        except Exception as e:
            return False, f"Cannot access zone {zone}: {e}"
    
    def list_records(self, zone: str) -> List[Dict[str, Any]]:
        """List all DNS records for a zone."""
        try:
            self.client.login()
            try:
                records = self.client.info_dns_records(zone)
                return [self.normalize_record(r) for r in records]
            finally:
                self.client.logout()
        except Exception as e:
            logger.error(f"Failed to list records for {zone}: {e}")
            raise BackendError(f"Failed to list records: {e}")
    
    def create_record(self, zone: str, record: Dict[str, Any]) -> Dict[str, Any]:
        """Create a DNS record.
        
        Netcup API works by submitting the full record set,
        so we fetch existing records, add the new one, and update.
        """
        try:
            self.client.login()
            try:
                # Get existing records
                existing = self.client.info_dns_records(zone)
                
                # Add new record
                new_record = {
                    'hostname': record['hostname'],
                    'type': record['type'],
                    'destination': record['destination'],
                }
                if record.get('priority'):
                    new_record['priority'] = record['priority']
                
                existing.append(new_record)
                
                # Update zone
                self.client.update_dns_records(zone, existing)
                
                return self.normalize_record(record)
            finally:
                self.client.logout()
        except Exception as e:
            logger.error(f"Failed to create record in {zone}: {e}")
            raise BackendError(f"Failed to create record: {e}")
    
    def update_record(self, zone: str, record_id: str, record: Dict[str, Any]) -> Dict[str, Any]:
        """Update a DNS record.
        
        Netcup uses record IDs in response but also matches by hostname+type.
        """
        try:
            self.client.login()
            try:
                existing = self.client.info_dns_records(zone)
                
                # Find and update the record
                found = False
                for idx, rec in enumerate(existing):
                    # Match by ID or by hostname+type
                    if (str(rec.get('id')) == str(record_id) or 
                        (rec.get('hostname') == record['hostname'] and 
                         rec.get('type') == record['type'])):
                        existing[idx] = {
                            'id': rec.get('id'),  # Preserve ID
                            'hostname': record['hostname'],
                            'type': record['type'],
                            'destination': record['destination'],
                        }
                        if record.get('priority'):
                            existing[idx]['priority'] = record['priority']
                        found = True
                        break
                
                if not found:
                    raise BackendError(f"Record {record_id} not found")
                
                self.client.update_dns_records(zone, existing)
                return self.normalize_record(record)
            finally:
                self.client.logout()
        except BackendError:
            raise
        except Exception as e:
            logger.error(f"Failed to update record in {zone}: {e}")
            raise BackendError(f"Failed to update record: {e}")
    
    def delete_record(self, zone: str, record_id: str) -> bool:
        """Delete a DNS record by marking it for deletion."""
        try:
            self.client.login()
            try:
                existing = self.client.info_dns_records(zone)
                
                # Filter out the record to delete
                filtered = [r for r in existing if str(r.get('id')) != str(record_id)]
                
                if len(filtered) == len(existing):
                    raise BackendError(f"Record {record_id} not found")
                
                self.client.update_dns_records(zone, filtered)
                return True
            finally:
                self.client.logout()
        except BackendError:
            raise
        except Exception as e:
            logger.error(f"Failed to delete record in {zone}: {e}")
            raise BackendError(f"Failed to delete record: {e}")
    
    def get_zone_info(self, zone: str) -> Dict[str, Any]:
        """Get zone information."""
        try:
            self.client.login()
            try:
                return self.client.info_dns_zone(zone)
            finally:
                self.client.logout()
        except Exception as e:
            logger.error(f"Failed to get zone info for {zone}: {e}")
            raise BackendError(f"Failed to get zone info: {e}")
    
    def normalize_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Netcup record format."""
        return {
            'id': str(record.get('id', '')),
            'hostname': record.get('hostname', '@'),
            'type': record.get('type', ''),
            'destination': record.get('destination', ''),
            'priority': record.get('priority'),
            'ttl': record.get('ttl', 300),
            'state': record.get('state'),  # Netcup-specific
        }
