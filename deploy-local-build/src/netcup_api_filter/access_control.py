"""
Access Control Logic
Validates requests against configured permissions
Supports both YAML config and database modes
"""
import fnmatch
import ipaddress
import logging
import re
from typing import Dict, List, Optional, Any, Union
from datetime import datetime

logger = logging.getLogger(__name__)

# Security: Limit pattern complexity to prevent ReDoS
MAX_PATTERN_LENGTH = 100
SAFE_PATTERN_REGEX = re.compile(r'^[a-zA-Z0-9\-\.\*_/]+$')  # Allow / for CIDR notation


class AccessControl:
    """Manages access control for API requests"""
    
    def __init__(self, tokens_config: Optional[List[Dict[str, Any]]] = None, use_database: bool = False):
        """
        Initialize access control with token configuration or database
        
        Args:
            tokens_config: List of token configurations with permissions (for YAML mode)
            use_database: Whether to use database for token lookup
        """
        self.use_database = use_database
        self.tokens = {}
        
        # YAML mode - load from config
        if tokens_config and not use_database:
            for token_config in tokens_config:
                token = token_config.get("token")
                if token:
                    self.tokens[token] = {
                        "description": token_config.get("description", ""),
                        "permissions": token_config.get("permissions", []),
                        "allowed_origins": token_config.get("allowed_origins", [])
                    }
    
    def validate_token(self, token: str) -> bool:
        """Check if a token exists and is valid"""
        if self.use_database:
            from .database import get_client_by_token
            client = get_client_by_token(token)
            return client is not None
        else:
            return token in self.tokens
    
    def get_token_info(self, token: str) -> Optional[Dict[str, Any]]:
        """Get information about a token"""
        if self.use_database:
            from .database import get_client_by_token
            client = get_client_by_token(token)
            if client:
                return {
                    "client_id": client.client_id,
                    "description": client.description,
                    "realm_type": client.realm_type,
                    "realm_value": client.realm_value,
                    "allowed_record_types": client.get_allowed_record_types(),
                    "allowed_operations": client.get_allowed_operations(),
                    "allowed_origins": client.get_allowed_ip_ranges(),
                    "email_address": client.email_address,
                    "email_notifications_enabled": bool(client.email_notifications_enabled)
                }
            return None
        else:
            return self.tokens.get(token)
    
    def _is_ip_in_network(self, ip: str, network: str) -> bool:
        """
        Check if an IP address is in a network (supports CIDR notation)
        
        Args:
            ip: IP address to check
            network: Network in CIDR notation (e.g., 192.168.1.0/24) or single IP
        
        Returns:
            True if IP is in network, False otherwise
        """
        try:
            ip_obj = ipaddress.ip_address(ip)
            # Check if network contains '/' for CIDR notation
            if '/' in network:
                network_obj = ipaddress.ip_network(network, strict=False)
                return ip_obj in network_obj
            else:
                # Single IP comparison
                return ip == network
        except ValueError:
            logger.warning(f"Invalid IP address or network: {ip}, {network}")
            return False
    
    def _matches_domain_pattern(self, origin: str, pattern: str) -> bool:
        """
        Check if an origin matches a domain pattern
        
        Args:
            origin: Origin domain or IP to check
            pattern: Pattern (supports wildcards, e.g., *.example.com)
        
        Returns:
            True if origin matches pattern, False otherwise
        """
        # Security: Validate pattern to prevent ReDoS
        if len(pattern) > MAX_PATTERN_LENGTH:
            logger.warning(f"Pattern too long: {len(pattern)} characters")
            return False
        
        if not SAFE_PATTERN_REGEX.match(pattern):
            logger.warning(f"Unsafe pattern detected: {pattern}")
            return False
        
        # Try to parse as IP first
        try:
            ipaddress.ip_address(origin)
            # It's an IP, check against IP patterns
            return self._is_ip_in_network(origin, pattern)
        except ValueError:
            # It's a domain, use fnmatch with validated pattern
            return fnmatch.fnmatch(origin.lower(), pattern.lower())
    
    def check_origin(self, token: str, client_ip: Optional[str] = None, 
                    origin_host: Optional[str] = None) -> bool:
        """
        Check if the request origin is allowed for this token
        
        Args:
            token: The authentication token
            client_ip: Client IP address
            origin_host: Origin hostname from request headers
        
        Returns:
            True if origin is allowed or no restrictions configured, False otherwise
        """
        if not self.validate_token(token):
            return False
        
        token_info = self.get_token_info(token)
        if not token_info:
            return False
        
        allowed_origins = token_info.get("allowed_origins", [])
        
        # If no restrictions configured, allow all origins
        if not allowed_origins:
            return True
        
        # Check client IP if provided
        if client_ip:
            for allowed_origin in allowed_origins:
                if self._matches_domain_pattern(client_ip, allowed_origin):
                    logger.info(f"Origin allowed: {client_ip} matches {allowed_origin}")
                    return True
        
        # Check origin host if provided
        if origin_host:
            for allowed_origin in allowed_origins:
                if self._matches_domain_pattern(origin_host, allowed_origin):
                    logger.info(f"Origin allowed: {origin_host} matches {allowed_origin}")
                    return True
        
        logger.warning(f"Origin denied: {client_ip} / {origin_host} not in allowed origins")
        return False
    
    def _matches_realm(self, domain: str, realm_type: str, realm_value: str) -> bool:
        """
        Check if a domain matches the realm configuration
        
        Args:
            domain: Domain to check
            realm_type: 'host' or 'subdomain'
            realm_value: Domain value (e.g., example.com)
        
        Returns:
            True if domain matches realm, False otherwise
        """
        if realm_type == 'host':
            # Exact domain match
            return domain.lower() == realm_value.lower()
        elif realm_type == 'subdomain':
            # Subdomain pattern match (*.realm_value)
            # Match both the domain itself and subdomains
            domain_lower = domain.lower()
            realm_lower = realm_value.lower()
            return domain_lower == realm_lower or domain_lower.endswith('.' + realm_lower)
        else:
            logger.warning(f"Unknown realm_type: {realm_type}")
            return False
    
    def check_permission(self, token: str, action: str, domain: str, 
                        record_name: Optional[str] = None, 
                        record_type: Optional[str] = None) -> bool:
        """
        Check if a token has permission for a specific action
        
        Args:
            token: The authentication token
            action: The action being performed (read, update, create, delete)
            domain: The domain being accessed
            record_name: The DNS record name (hostname) being accessed
            record_type: The DNS record type (A, AAAA, CNAME, etc.)
        
        Returns:
            True if permission is granted, False otherwise
        """
        if not self.validate_token(token):
            logger.warning(f"Invalid token attempted")
            return False
        
        token_info = self.get_token_info(token)
        if not token_info:
            return False
        
        # Database mode - check realm and permissions
        if self.use_database:
            # Check if domain matches realm
            realm_type = token_info.get("realm_type")
            realm_value = token_info.get("realm_value")
            
            if not self._matches_realm(domain, realm_type, realm_value):
                logger.warning(f"Domain {domain} does not match realm {realm_type}:{realm_value}")
                return False
            
            # Check if operation is allowed
            allowed_operations = token_info.get("allowed_operations", [])
            if action not in allowed_operations:
                logger.warning(f"Operation {action} not in allowed operations: {allowed_operations}")
                return False
            
            # Check record type if specified
            if record_type:
                allowed_record_types = token_info.get("allowed_record_types", [])
                if record_type not in allowed_record_types:
                    logger.warning(f"Record type {record_type} not in allowed types: {allowed_record_types}")
                    return False
            
            logger.info(f"Permission granted for {action} on domain {domain}")
            return True
        
        # YAML mode - check permissions list
        permissions = token_info.get("permissions", [])
        
        for perm in permissions:
            # Check domain match
            perm_domain = perm.get("domain", "")
            
            # Security: Validate pattern
            if len(perm_domain) > MAX_PATTERN_LENGTH or not SAFE_PATTERN_REGEX.match(perm_domain):
                logger.warning(f"Invalid domain pattern in config: {perm_domain}")
                continue
            
            if not fnmatch.fnmatch(domain, perm_domain):
                continue
            
            # Check operation match
            perm_operations = perm.get("operations", [])
            if action not in perm_operations and "*" not in perm_operations:
                continue
            
            # If no record-specific checks needed (e.g., for infoDnsZone)
            if record_name is None:
                logger.info(f"Permission granted for {action} on domain {domain}")
                return True
            
            # Check record name match
            perm_record_name = perm.get("record_name", "*")
            
            # Security: Validate pattern
            if len(perm_record_name) > MAX_PATTERN_LENGTH or not SAFE_PATTERN_REGEX.match(perm_record_name):
                logger.warning(f"Invalid record_name pattern in config: {perm_record_name}")
                continue
            
            if not fnmatch.fnmatch(record_name, perm_record_name):
                continue
            
            # Check record type match
            if record_type:
                perm_record_types = perm.get("record_types", ["*"])
                if record_type not in perm_record_types and "*" not in perm_record_types:
                    continue
            
            logger.info(f"Permission granted for {action} on {domain}/{record_name} ({record_type})")
            return True
        
        logger.warning(f"Permission denied for {action} on {domain}/{record_name} ({record_type})")
        return False
    
    def filter_dns_records(self, token: str, domain: str, 
                          records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter DNS records based on token permissions
        
        Args:
            token: The authentication token
            domain: The domain
            records: List of DNS records
        
        Returns:
            Filtered list of DNS records the token has permission to see
        """
        if not self.validate_token(token):
            return []
        
        token_info = self.get_token_info(token)
        if not token_info:
            return []
        
        # Database mode - filter by allowed record types
        if self.use_database:
            allowed_record_types = token_info.get("allowed_record_types", [])
            filtered_records = []
            
            for record in records:
                record_type = record.get("type", "")
                if record_type in allowed_record_types:
                    filtered_records.append(record)
            
            logger.info(f"Filtered {len(records)} records to {len(filtered_records)} for token")
            return filtered_records
        
        # YAML mode - filter by permissions
        permissions = token_info.get("permissions", [])
        
        filtered_records = []
        for record in records:
            record_name = record.get("hostname", "")
            record_type = record.get("type", "")
            
            # Check if token has permission to read this record
            for perm in permissions:
                # Check domain match
                perm_domain = perm.get("domain", "")
                
                # Security: Validate pattern
                if len(perm_domain) > MAX_PATTERN_LENGTH or not SAFE_PATTERN_REGEX.match(perm_domain):
                    continue
                
                if not fnmatch.fnmatch(domain, perm_domain):
                    continue
                
                # Check if read operation is allowed
                perm_operations = perm.get("operations", [])
                if "read" not in perm_operations and "*" not in perm_operations:
                    continue
                
                # Check record name match
                perm_record_name = perm.get("record_name", "*")
                
                # Security: Validate pattern
                if len(perm_record_name) > MAX_PATTERN_LENGTH or not SAFE_PATTERN_REGEX.match(perm_record_name):
                    continue
                
                if not fnmatch.fnmatch(record_name, perm_record_name):
                    continue
                
                # Check record type match
                perm_record_types = perm.get("record_types", ["*"])
                if record_type not in perm_record_types and "*" not in perm_record_types:
                    continue
                
                # Permission granted for this record
                filtered_records.append(record)
                break
        
        logger.info(f"Filtered {len(records)} records to {len(filtered_records)} for token")
        return filtered_records
    
    def validate_dns_records_update(self, token: str, domain: str, 
                                   records: List[Dict[str, Any]]) -> tuple[bool, Optional[str]]:
        """
        Validate if a token can update the specified DNS records
        
        Args:
            token: The authentication token
            domain: The domain
            records: List of DNS records to update
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self.validate_token(token):
            return False, "Invalid token"
        
        for record in records:
            record_name = record.get("hostname", "")
            record_type = record.get("type", "")
            delete_record = record.get("deleterecord", False)
            record_id = record.get("id")
            
            # Determine the operation
            if delete_record:
                operation = "delete"
            elif record_id:
                operation = "update"
            else:
                operation = "create"
            
            # Check permission for this record
            if not self.check_permission(token, operation, domain, record_name, record_type):
                return False, f"No permission to {operation} record {record_name} ({record_type})"
        
        return True, None
