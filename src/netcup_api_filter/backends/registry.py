"""
Backend Registry and Resolution.

Provides factory functions to instantiate backends by provider code
and resolve backends for realms.
"""

import json
import logging
from typing import Any, Dict, Type

logger = logging.getLogger(__name__)

# Import backend implementations
from .base import BackendError, DNSBackend
from .netcup import NetcupBackend
from .powerdns import PowerDNSBackend


# Registry of available backend implementations
BACKEND_REGISTRY: Dict[str, Type[DNSBackend]] = {
    'netcup': NetcupBackend,
    'powerdns': PowerDNSBackend,
}


def get_backend(provider_code: str, config: Dict[str, Any]) -> DNSBackend:
    """Get backend instance by provider code and configuration.
    
    Args:
        provider_code: Provider identifier (e.g., 'netcup', 'powerdns')
        config: Provider-specific configuration dict
    
    Returns:
        Configured DNSBackend instance
    
    Raises:
        BackendError: If provider is unknown or config is invalid
    """
    backend_class = BACKEND_REGISTRY.get(provider_code)
    if not backend_class:
        raise BackendError(f"Unknown backend provider: {provider_code}")
    
    return backend_class(config)


def get_backend_for_realm(realm: 'AccountRealm') -> DNSBackend:
    """Resolve the correct backend for a realm.
    
    Exactly one of domain_root_id or user_backend_id must be set
    (enforced by database trigger).
    
    Args:
        realm: AccountRealm model instance
    
    Returns:
        Configured DNSBackend instance for this realm
    
    Raises:
        BackendError: If backend resolution fails or ownership mismatch
    """
    # Lazy import to avoid circular dependencies
    from ..models import BackendProvider, BackendService, ManagedDomainRoot
    
    # Case B: User-provided backend (BYOD)
    if realm.user_backend_id:
        service = BackendService.query.get(realm.user_backend_id)
        if not service or not service.is_active:
            raise BackendError("User backend is disabled or deleted")
        
        # Security check: backend must belong to realm's account
        if service.owner_id != realm.account_id:
            raise BackendError("Backend ownership mismatch")
        
        return instantiate_backend(service)
    
    # Case A: Platform-managed via domain root
    if realm.domain_root_id:
        root = ManagedDomainRoot.query.get(realm.domain_root_id)
        if not root or not root.is_active:
            raise BackendError("Domain root is disabled")
        
        service = BackendService.query.get(root.backend_service_id)
        if not service or not service.is_active:
            raise BackendError("Backend service is disabled")
        
        return instantiate_backend(service)
    
    # Should never reach here due to database trigger constraint
    raise BackendError("No backend configured for realm (invalid state)")


def instantiate_backend(service: 'BackendService') -> DNSBackend:
    """Create backend instance from service configuration.
    
    Validates config against provider's JSON Schema before instantiation.
    
    Args:
        service: BackendService model instance
    
    Returns:
        Configured DNSBackend instance
    
    Raises:
        BackendError: If provider is unavailable or config is invalid
    """
    from ..models import BackendProvider
    
    provider = BackendProvider.query.get(service.provider_id)
    if not provider or not provider.is_enabled:
        raise BackendError(f"Provider {service.provider_id} is not available")
    
    backend_class = BACKEND_REGISTRY.get(provider.provider_code)
    if not backend_class:
        raise BackendError(f"No implementation for provider: {provider.provider_code}")
    
    # Parse and validate config
    try:
        config = json.loads(service.config)
    except json.JSONDecodeError as e:
        raise BackendError(f"Invalid config JSON: {e}")
    
    # Optional: Validate against provider's JSON Schema
    if provider.config_schema:
        try:
            import jsonschema
            schema = json.loads(provider.config_schema)
            jsonschema.validate(instance=config, schema=schema)
        except ImportError:
            logger.warning("jsonschema not available, skipping config validation")
        except json.JSONDecodeError:
            logger.warning(f"Invalid config_schema JSON for provider {provider.provider_code}")
        except Exception as e:
            raise BackendError(f"Config validation failed: {e}")
    
    return backend_class(config)


def get_available_providers() -> Dict[str, Type[DNSBackend]]:
    """Get dict of available backend providers.
    
    Returns:
        Dict mapping provider_code to backend class
    """
    return BACKEND_REGISTRY.copy()


def register_backend(provider_code: str, backend_class: Type[DNSBackend]) -> None:
    """Register a new backend implementation.
    
    Used for dynamically adding custom backends.
    
    Args:
        provider_code: Unique provider identifier
        backend_class: Class implementing DNSBackend interface
    """
    if not issubclass(backend_class, DNSBackend):
        raise TypeError(f"{backend_class} must be a subclass of DNSBackend")
    
    BACKEND_REGISTRY[provider_code] = backend_class
    logger.info(f"Registered backend provider: {provider_code}")
