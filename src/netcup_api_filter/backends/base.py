"""
Abstract base class for DNS backends.

All DNS providers must implement this interface.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class BackendError(Exception):
    """Exception raised for backend operation failures."""
    pass


class DNSBackend(ABC):
    """Abstract base class for DNS backends.
    
    Each DNS provider (Netcup, PowerDNS, Cloudflare, etc.) must implement
    this interface to be usable as a backend service.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize backend with configuration.
        
        Args:
            config: Provider-specific configuration dict
        """
        self.config = config
    
    @abstractmethod
    def test_connection(self) -> tuple[bool, str]:
        """Test backend connectivity.
        
        Returns:
            Tuple of (success, message).
            success: True if connection test passed
            message: Human-readable status message
        """
        pass
    
    @abstractmethod
    def list_zones(self) -> List[str]:
        """List all zones manageable by this backend.
        
        Used for admin UI to select available zones when
        creating managed domain roots.
        
        Returns:
            List of zone names (e.g., ['example.com', 'test.org'])
        """
        pass
    
    @abstractmethod
    def validate_zone_access(self, zone: str) -> tuple[bool, str]:
        """Verify backend can manage this zone.
        
        Args:
            zone: Zone name to validate
        
        Returns:
            Tuple of (can_manage, error_message).
            can_manage: True if backend can modify this zone
            error_message: Reason if cannot manage (empty if can)
        """
        pass
    
    @abstractmethod
    def list_records(self, zone: str) -> List[Dict[str, Any]]:
        """List all DNS records for a zone.
        
        Args:
            zone: Zone name (e.g., 'example.com')
        
        Returns:
            List of normalized record dicts with keys:
            - id: Record identifier (provider-specific)
            - hostname: Record name (relative to zone or absolute)
            - type: Record type (A, AAAA, CNAME, TXT, etc.)
            - destination: Record value/content
            - priority: Priority (for MX, SRV)
            - ttl: Time to live in seconds
        """
        pass
    
    @abstractmethod
    def create_record(self, zone: str, record: Dict[str, Any]) -> Dict[str, Any]:
        """Create a DNS record.
        
        Args:
            zone: Zone name
            record: Dict with hostname, type, destination, priority (optional)
        
        Returns:
            Normalized record dict of created record
        
        Raises:
            BackendError: If creation fails
        """
        pass
    
    @abstractmethod
    def update_record(self, zone: str, record_id: str, record: Dict[str, Any]) -> Dict[str, Any]:
        """Update a DNS record.
        
        Args:
            zone: Zone name
            record_id: Provider-specific record identifier
            record: Dict with hostname, type, destination, priority (optional)
        
        Returns:
            Normalized record dict of updated record
        
        Raises:
            BackendError: If update fails
        """
        pass
    
    @abstractmethod
    def delete_record(self, zone: str, record_id: str) -> bool:
        """Delete a DNS record.
        
        Args:
            zone: Zone name
            record_id: Provider-specific record identifier
        
        Returns:
            True if deletion succeeded
        
        Raises:
            BackendError: If deletion fails
        """
        pass
    
    @abstractmethod
    def get_zone_info(self, zone: str) -> Dict[str, Any]:
        """Get zone metadata and SOA information.
        
        Args:
            zone: Zone name
        
        Returns:
            Dict with zone metadata (provider-specific)
        """
        pass
    
    def normalize_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize record format to common schema.
        
        Subclasses can override to handle provider-specific formats.
        
        Args:
            record: Provider-specific record dict
        
        Returns:
            Normalized record dict with standard keys
        """
        return {
            'id': record.get('id'),
            'hostname': record.get('hostname', '@'),
            'type': record.get('type'),
            'destination': record.get('destination') or record.get('content'),
            'priority': record.get('priority'),
            'ttl': record.get('ttl', 300)
        }
    
    def filter_records_by_hostname(
        self, 
        records: List[Dict[str, Any]], 
        hostname: str,
        record_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Filter records by hostname and optionally type.
        
        Args:
            records: List of normalized records
            hostname: Hostname to match
            record_type: Optional record type to match
        
        Returns:
            Filtered list of records
        """
        result = []
        for rec in records:
            if rec.get('hostname', '').lower() == hostname.lower():
                if record_type is None or rec.get('type', '').upper() == record_type.upper():
                    result.append(rec)
        return result
